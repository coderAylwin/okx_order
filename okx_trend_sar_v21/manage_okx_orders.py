import argparse
import json
from datetime import datetime
from typing import Any, Dict, Optional

from okx_config import OKX_API_CONFIG, TRADING_CONFIG
from okx_trader_v2 import OKXTraderV2


class OKXManagerCLI:
    """简单的 OKX 命令行工具，方便手动调用常用接口。

    功能覆盖：
    1. 设置杠杆/保证金模式;
    2. 查询持仓列表（可按交易对过滤）;
    3. 查询当前委托列表（可按交易对过滤）;
    4. 根据订单 ID 查询订单详情;
    5. 下单：普通限价 / 高级限价(PostOnly) / 条件止盈止损。

    使用方式示例：

    ```bash
    # 1. 设置杠杆 + 保证金模式
    python3 manage_okx_orders.py set-leverage --symbol ETH-USDT-SWAP --leverage 3 --mode isolated

    # 2. 查看账户余额（USDT）
    python3 manage_okx_orders.py balance

    # 3. 查看 ETH 永续的当前持仓
    python3 manage_okx_orders.py positions --symbol ETH-USDT-SWAP [--raw]

    # 4. 查看当前委托
    python3 manage_okx_orders.py open-orders --symbol ETH-USDT-SWAP [--raw] [--state live,partially_filled] [--ord-types limit,post_only]

    # 5. 查询订单详情
    python3 manage_okx_orders.py order-detail --symbol ETH-USDT-SWAP --order-id 3034857607517659136 [--raw]

    # 6. 下限价单（做多 0.2 张，价格 2500 USDT）
    python3 manage_okx_orders.py place-order --symbol ETH-USDT-SWAP \
        --side buy --amount 0.2 --price 2500 --order-type limit

    # 7. 下高级限价单（PostOnly，maker 手续费）
    python3 manage_okx_orders.py place-order --symbol ETH-USDT-SWAP \
        --side sell --amount 0.2 --price 2600 --order-type advanced-limit \
        --post-only --reduce-only

    # 8. 下条件止损单（多单止损：触发 2450，挂 2445）
    python3 manage_okx_orders.py place-order --symbol ETH-USDT-SWAP \
        --side sell --amount 0.2 --order-type conditional \
        --trigger-price 2450 --price 2445 --reduce-only
    ```
    """

    def __init__(self, test_mode: bool = False):
        leverage = TRADING_CONFIG.get('leverage', 1)
        self.trader = OKXTraderV2(test_mode=test_mode, leverage=leverage)
        if not hasattr(self.trader, 'exchange') or self.trader.exchange is None:
            raise RuntimeError("OKX 接口初始化失败，请检查 okx_config.py 的 API 配置")

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def _print_json(data: Any):
        try:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        except TypeError:
            print(data)

    @staticmethod
    def _resolve_symbol(symbol: Optional[str]) -> str:
        if symbol:
            return symbol
        # 默认使用配置文件中的主交易对（ETH 如果存在，否则第一个）
        symbols = TRADING_CONFIG.get('symbols', {})
        for key in ('ETH', 'BTC', 'SOL'):
            if key in symbols:
                return symbols[key]
        if symbols:
            return next(iter(symbols.values()))
        raise ValueError("未在 TRADING_CONFIG['symbols'] 中找到任何交易对配置")

    # ------------------------------------------------------------------
    # 功能实现
    # ------------------------------------------------------------------
    def set_leverage(self, symbol: str, leverage: float, margin_mode: str):
        print(f"⚙️  设置杠杆: {symbol}, leverage={leverage}, margin_mode={margin_mode}")
        print("🛰️  OKX接口: POST /api/v5/account/set-leverage")
        print("📚  文档: https://www.okx.com/docs-v5/zh/#trading-account-rest-api-post-set-leverage")
        success = self.trader.set_leverage(symbol, leverage, margin_mode)
        print("✅ 成功" if success else "❌ 失败")

    def show_balance(self):
        """获取账户余额（默认展示 USDT）"""
        print("💰 查询账户余额")
        print("🛰️  OKX接口: GET /api/v5/account/balance")
        print("📚  文档: https://www.okx.com/docs-v5/zh/#rest-api-account-get-balance")
        info = self.trader.get_account_info()
        if not info or not info.get('balance'):
            print("❌ 获取账户余额失败")
            return
        balance = info['balance']
        print(f"⏰ 时间: {info.get('timestamp')}")
        print(f"💼 模式: {info.get('mode')} | 测试: {info.get('test_mode')}")
        print("------ 账户余额（USDT） ------")
        print(f"总余额(total): {balance.get('total', 0):,.2f}")
        print(f"可用余额(free): {balance.get('free', 0):,.2f}")
        print(f"占用保证金(used): {balance.get('used', 0):,.2f}")

    def list_positions(self, symbol: Optional[str], raw: bool = False):
        symbol = self._resolve_symbol(symbol)
        print(f"📊 查询持仓: {symbol}")
        print("🛰️  OKX接口: GET /api/v5/account/positions")
        print("📚  文档: https://www.okx.com/docs-v5/zh/#trading-account-rest-api-get-positions")
        if raw:
            request = {'instId': symbol}
            try:
                response = self.trader.exchange.private_get_account_positions(request)
                print("📦 原始响应:")
                self._print_json(response)
            except Exception as e:
                print(f"❌ 获取原始数据失败: {e}")
        else:
            positions = self.trader.exchange.fetch_positions([symbol])
            filtered = [pos for pos in positions if pos.get('symbol') == symbol or pos.get('info', {}).get('instId') == symbol]
            if not filtered:
                print("（无持仓）")
            else:
                self._print_json(filtered)

    def list_open_orders(
        self,
        symbol: Optional[str],
        raw: bool = False,
        all_symbols: bool = False,
        state: str = None,
        ord_types: Optional[str] = None,
        algo_types: Optional[str] = None
    ):
        target_symbol = None if all_symbols else self._resolve_symbol(symbol)
        display_symbol = 'ALL' if all_symbols else target_symbol
        print(f"📋 查询当前委托: {display_symbol}")
        print("🛰️  OKX接口: GET /api/v5/trade/orders-pending")
        print("📚  文档: https://www.okx.com/docs-v5/zh/#order-book-trading-trade-get-order-list")
        print("   （条件单将改用 GET /api/v5/trade/orders-algo-pending）")

        # 解析状态过滤
        if state:
            state_filters = [item.strip() for item in state.split(',') if item.strip()]
        else:
            state_filters = [None]  # None 表示不限制状态，让接口返回默认（live + partially_filled）

        # 普通委托参数
        def build_base_params(state_value: Optional[str]) -> Dict[str, Any]:
            params: Dict[str, Any] = {}
            if state_value:
                params['state'] = state_value
            if ord_types:
                params['ordType'] = ord_types
            if not all_symbols and target_symbol:
                params['instId'] = target_symbol

            # 根据交易对推断产品类型，用于原始接口查询
            if not all_symbols and target_symbol:
                if target_symbol.endswith('-SWAP'):
                    params.setdefault('instType', 'SWAP')
                elif target_symbol.endswith('-SPOT') or target_symbol.count('/') == 1:
                    params.setdefault('instType', 'SPOT')
                elif target_symbol.endswith('-FUTURES'):
                    params.setdefault('instType', 'FUTURES')
            return params

        # 条件/算法委托类型列表
        if algo_types:
            algo_list = [item.strip() for item in algo_types.split(',') if item.strip()]
        else:
            algo_list = ['conditional', 'trigger', 'oco', 'move_order_stop', 'iceberg', 'twap']

        if raw:
            normal_responses = []
            combined_orders = []
            for state_filter in state_filters:
                params = build_base_params(state_filter)
                try:
                    response = self.trader.exchange.private_get_trade_orders_pending(params)
                    if response and response.get('data'):
                        normal_responses.append({'state': state_filter or 'default', 'response': response})
                        for item in response.get('data', []):
                            record = dict(item)
                            record['_source'] = 'normal'
                            record['_state'] = state_filter or 'default'
                            combined_orders.append(record)
                except Exception as e:
                    print(f"❌ 获取普通委托原始数据失败(state={state_filter or 'default'}): {e}")
            if normal_responses:
                print("📦 原始响应(普通委托):")
                self._print_json(normal_responses)
            else:
                print("📦 原始响应(普通委托): （无数据）")

            algo_responses = []
            for algo_type in algo_list:
                for state_filter in state_filters:
                    algo_params = {
                        'ordType': algo_type,
                    }
                    if state_filter:
                        algo_params['state'] = state_filter
                    if not all_symbols and target_symbol:
                        algo_params['instId'] = target_symbol
                    try:
                        algo_resp = self.trader.exchange.private_get_trade_orders_algo_pending(algo_params)
                        if algo_resp and algo_resp.get('data'):
                            algo_responses.append({
                                'ordType': algo_type,
                                'state': state_filter or 'default',
                                'response': algo_resp
                            })
                            for item in algo_resp.get('data', []):
                                record = dict(item)
                                record['_source'] = 'algo'
                                record['_ordType'] = algo_type
                                record['_state'] = state_filter or 'default'
                                combined_orders.append(record)
                    except Exception as e:
                        err_msg = str(e)
                        if '51000' not in err_msg:
                            print(f"⚠️ 条件/算法委托原始数据获取失败(ordType={algo_type}, state={state_filter or 'default'}): {e}")
            if algo_responses:
                print("📦 原始响应(条件/算法委托):")
                self._print_json(algo_responses)
            else:
                print("📦 原始响应(条件/算法委托): （无数据）")

            print("📋 合并后的当前委托列表:")
            if combined_orders:
                self._print_json(combined_orders)
            else:
                print("（暂无任何未成交委托）")
        else:
            # ccxt 不接受 instType 参数，删除避免错误
            combined_orders = []
            for state_filter in state_filters:
                params_for_ccxt = build_base_params(state_filter)
            # ccxt 不接受 instType 参数，删除避免错误
            params_for_ccxt.pop('instType', None)

            if all_symbols:
                orders = self.trader.exchange.fetch_open_orders(params=params_for_ccxt)
            else:
                orders = self.trader.exchange.fetch_open_orders(target_symbol, params=params_for_ccxt)
            if orders:
                combined_orders.extend(orders)
            print("📋 普通委托（ccxt解析）:")
            if not combined_orders:
                print("（无普通委托）")
            else:
                self._print_json(combined_orders)

            print("📋 条件/算法委托（原始数据）:")
            algo_outputs = []
            for algo_type in algo_list:
                for state_filter in state_filters:
                    algo_params = {
                        'ordType': algo_type,
                    }
                    if state_filter:
                        algo_params['state'] = state_filter
                    if not all_symbols and target_symbol:
                        algo_params['instId'] = target_symbol
                    try:
                        algo_resp = self.trader.exchange.private_get_trade_orders_algo_pending(algo_params)
                        data = algo_resp.get('data', []) if isinstance(algo_resp, dict) else algo_resp
                        if data:
                            algo_outputs.append({
                                'ordType': algo_type,
                                'state': state_filter or 'default',
                                'response': algo_resp
                            })
                    except Exception as e:
                        err_msg = str(e)
                        if '51000' not in err_msg:
                            print(f"⚠️ 条件/算法委托获取失败(ordType={algo_type}, state={state_filter or 'default'}): {e}")
            if algo_outputs:
                self._print_json(algo_outputs)
            else:
                print("（无条件/算法委托）")

            print("📋 合并后的当前委托列表:")
            merged = []
            for order in combined_orders:
                record = dict(order)
                record['_source'] = 'normal'
                merged.append(record)
            for algo_entry in algo_outputs:
                response = algo_entry.get('response', {})
                ord_type = algo_entry.get('ordType')
                state_label = algo_entry.get('state')
                for item in response.get('data', []):
                    record = dict(item)
                    record['_source'] = 'algo'
                    record['_ordType'] = ord_type
                    record['_state'] = state_label
                    merged.append(record)
            if merged:
                self._print_json(merged)
            else:
                print("（暂无任何未成交委托）")

    def order_detail(self, symbol: Optional[str], order_id: str, raw: bool = False):
        symbol = self._resolve_symbol(symbol)
        print(f"🔍 查询订单详情: {order_id} @ {symbol}")
        print("🛰️  OKX接口: GET /api/v5/trade/order")
        print("📚  文档: https://www.okx.com/docs-v5/zh/#order-book-trading-trade-get-order-details")
        print("   （条件委托对应 GET /api/v5/trade/order-algo）")
        
        if raw:
            # 尝试普通订单接口
            try:
                params = {
                    'instId': symbol,
                    'ordId': order_id,
                }
                response = self.trader.exchange.private_get_trade_order(params)
                print("📦 原始响应（普通订单）:")
                self._print_json(response)
                return
            except Exception as e:
                # 如果普通订单接口失败，尝试算法订单接口
                try:
                    params = {
                        'instId': symbol,
                        'algoId': order_id,
                    }
                    response = self.trader.exchange.private_get_trade_order_algo(params)
                    print("📦 原始响应（算法订单）:")
                    self._print_json(response)
                    return
                except Exception as e2:
                    print(f"❌ 获取原始数据失败（普通订单）: {e}")
                    print(f"❌ 获取原始数据失败（算法订单）: {e2}")
                    print("💡 提示: 请确认订单ID是否正确，或订单是否已过期")
        else:
            order = self.trader.exchange.fetch_order(order_id, symbol)
            self._print_json(order)

    # ------------------------------------------------------------------
    # 下单功能
    # ------------------------------------------------------------------
    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str,
        price: Optional[float],
        trigger_price: Optional[float],
        reduce_only: bool,
        post_only: bool
    ):
        symbol = self._resolve_symbol(symbol)
        side = side.lower()
        if side not in {'buy', 'sell'}:
            raise ValueError("side 只能为 'buy' 或 'sell'")

        td_mode = getattr(self.trader, 'margin_mode', TRADING_CONFIG.get('margin_mode', 'cross'))
        params: Dict[str, Any] = {'tdMode': td_mode}
        if reduce_only:
            params['reduceOnly'] = True
        if post_only:
            params['postOnly'] = True

        print(f"📝 下单参数: symbol={symbol}, side={side}, amount={amount}, order_type={order_type}")
        if price is not None:
            print(f"          price={price}")
        if trigger_price is not None:
            print(f"          trigger_price={trigger_price}")
        print(f"          tdMode={td_mode}, reduceOnly={reduce_only}, postOnly={post_only}")

        order_type = order_type.lower()

        if order_type == 'limit':
            if price is None:
                raise ValueError("限价单需要 --price")
            if post_only and 'postOnly' not in params:
                params['postOnly'] = True
            print("🛰️  OKX接口: POST /api/v5/trade/batch-orders（单笔也可使用 /api/v5/trade/order）")
            print("📚  文档: https://www.okx.com/docs-v5/zh/#order-book-trading-trade-post-place-order")
            order = self.trader.exchange.create_limit_order(symbol, side, amount, price, params)

        elif order_type == 'advanced-limit':
            if price is None:
                raise ValueError("高级限价单需要 --price")
            params['postOnly'] = True
            print("🛰️  OKX接口: POST /api/v5/trade/batch-orders（携带 postOnly）")
            print("📚  文档: https://www.okx.com/docs-v5/zh/#order-book-trading-trade-post-place-order")
            order = self.trader.exchange.create_limit_order(symbol, side, amount, price, params)

        elif order_type == 'conditional':
            if trigger_price is None:
                raise ValueError("条件单需要 --trigger-price")
            if price is None:
                raise ValueError("条件单需要 --price")
            params['instId'] = symbol
            params['ordType'] = 'conditional'
            params['side'] = side
            params['sz'] = str(amount)
            params['posSide'] = 'long' if side == 'sell' else 'short'
            # 止损 / 止盈字段根据开仓方向动态决定
            if side == 'sell':
                # 多单止损：触发卖出
                params['slTriggerPx'] = str(trigger_price)
                params['slOrdPx'] = str(price)
            else:
                # 空单止损：触发买入
                params['slTriggerPx'] = str(trigger_price)
                params['slOrdPx'] = str(price)
            print("🛰️  OKX接口: POST /api/v5/trade/order-algo")
            print("📚  文档: https://www.okx.com/docs-v5/zh/#order-book-trading-algo-trading-post-place-algo-order")
            order = self.trader.exchange.create_order(symbol, 'limit', side, amount, price, params)
        else:
            raise ValueError("order_type 仅支持 limit / advanced-limit / conditional")

        print("✅ 下单结果：")
        self._print_json(order)

    # ------------------------------------------------------------------
    # CLI 入口
    # ------------------------------------------------------------------
    @classmethod
    def main(cls):
        parser = argparse.ArgumentParser(description="OKX 实用命令行工具")
        parser.add_argument('--test-mode', action='store_true', help='启用测试模式（不会真实下单）')
        subparsers = parser.add_subparsers(dest='command', required=True)

        # 1. 设置杠杆
        sp_leverage = subparsers.add_parser('set-leverage', help='设置杠杆和保证金模式')
        sp_leverage.add_argument('--symbol', required=False, help='交易对，例如 ETH-USDT-SWAP')
        sp_leverage.add_argument('--leverage', type=float, required=True, help='杠杆倍数，例如 3')
        sp_leverage.add_argument('--mode', choices=['cross', 'isolated'], required=True, help='保证金模式 cross/isolated')

        # 2. 账户余额
        subparsers.add_parser('balance', help='查询账户余额（USDT）')

        # 2. 持仓列表
        sp_positions = subparsers.add_parser('positions', help='查询当前持仓')
        sp_positions.add_argument('--symbol', required=False, help='交易对，例如 ETH-USDT-SWAP，如不指定则使用默认')
        sp_positions.add_argument('--raw', action='store_true', help='显示OKX原始返回数据')

        # 3. 委托列表
        sp_open_orders = subparsers.add_parser('open-orders', help='查询当前委托订单')
        sp_open_orders.add_argument('--symbol', required=False, help='交易对，例如 ETH-USDT-SWAP，如不指定则使用默认')
        sp_open_orders.add_argument('--raw', action='store_true', help='显示OKX原始返回数据')
        sp_open_orders.add_argument('--all', action='store_true', help='忽略交易对，返回全部未成交委托')
        sp_open_orders.add_argument('--state', required=False, help='订单状态筛选，例如 live,partially_filled')
        sp_open_orders.add_argument('--ord-types', required=False, help='普通委托类型筛选，逗号分隔，例如 limit,post_only')
        sp_open_orders.add_argument('--algo-types', required=False, help='算法委托类型筛选，逗号分隔，例如 conditional,trigger')

        # 4. 订单详情
        sp_order_detail = subparsers.add_parser('order-detail', help='根据订单 ID 查看详情')
        sp_order_detail.add_argument('--symbol', required=False, help='交易对，例如 ETH-USDT-SWAP，如不指定则使用默认')
        sp_order_detail.add_argument('--order-id', required=True, help='订单ID (ordId)')
        sp_order_detail.add_argument('--raw', action='store_true', help='显示OKX原始返回数据')

        # 5. 下单
        sp_place_order = subparsers.add_parser('place-order', help='下单接口：限价 / 高级限价 / 条件单')
        sp_place_order.add_argument('--symbol', required=False, help='交易对，例如 ETH-USDT-SWAP，如不指定则使用默认')
        sp_place_order.add_argument('--side', required=True, choices=['buy', 'sell'], help='买入/卖出')
        sp_place_order.add_argument('--amount', type=float, required=True, help='下单数量，永续合约单位为张')
        sp_place_order.add_argument('--order-type', required=True, choices=['limit', 'advanced-limit', 'conditional'], help='订单类型')
        sp_place_order.add_argument('--price', type=float, help='限价/条件单的挂单价')
        sp_place_order.add_argument('--trigger-price', type=float, help='条件单触发价 (slTriggerPx)')
        sp_place_order.add_argument('--reduce-only', action='store_true', help='reduceOnly，仅减仓模式')
        sp_place_order.add_argument('--post-only', action='store_true', help='postOnly，仅做Maker（高级限价常用）')

        args = parser.parse_args()
        cli = cls(test_mode=args.test_mode)

        if args.command == 'set-leverage':
            symbol = cls._resolve_symbol(args.symbol)
            cli.set_leverage(symbol, args.leverage, args.mode)
        elif args.command == 'balance':
            cli.show_balance()
        elif args.command == 'positions':
            cli.list_positions(args.symbol, raw=args.raw)
        elif args.command == 'open-orders':
            cli.list_open_orders(
                args.symbol,
                raw=args.raw,
                all_symbols=args.all,
                state=args.state,
                ord_types=args.ord_types,
                algo_types=args.algo_types
            )
        elif args.command == 'order-detail':
            cli.order_detail(args.symbol, args.order_id, raw=args.raw)
        elif args.command == 'place-order':
            cli.place_order(
                symbol=args.symbol,
                side=args.side,
                amount=args.amount,
                order_type=args.order_type,
                price=args.price,
                trigger_price=args.trigger_price,
                reduce_only=args.reduce_only,
                post_only=args.post_only
            )
        else:
            parser.print_help()


if __name__ == '__main__':
    OKXManagerCLI.main()
