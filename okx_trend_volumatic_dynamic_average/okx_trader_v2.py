#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OKX 交易接口 V2版本
使用限价单 + 订单簿优化，最大化省手续费
"""

import ccxt
import time
from datetime import datetime
from okx_config import OKX_API_CONFIG, TRADING_CONFIG


class OKXTraderV2:
    """OKX交易接口V2 - 优化版（省手续费）"""
    
    def __init__(self, test_mode=True, leverage=1, symbols=None):
        """
        初始化OKX交易接口V2
        
        Args:
            test_mode: 测试模式
            leverage: 杠杆倍数
            symbols: 需要监听的交易对列表
        """
        self.test_mode = test_mode or TRADING_CONFIG['test_mode']
        self.leverage = leverage
        
        # 初始化CCXT交易所
        try:
            self.exchange = ccxt.okx(OKX_API_CONFIG)
            
            if TRADING_CONFIG['mode'] == 'paper':
                self.exchange.set_sandbox_mode(True)
                print("⚠️  【模拟盘模式】已启用 OKX 沙盒环境")
            else:
                print("🔴 【实盘模式】注意！将在真实市场交易！")
            
            self.exchange.load_markets()
            print(f"✅ OKX 交易接口V2初始化成功")
            print(f"📊 默认杠杆倍数: {self.leverage}x")
            print(f"💰 优化: 限价单优先 | 订单簿定价 | 省手续费")
            
        except Exception as e:
            print(f"❌ OKX 交易接口初始化失败: {e}")
            self.exchange = None
        
        # 不使用WebSocket订单簿监听器，直接用ccxt获取
        self.orderbook_watcher = None
        print("📊 使用ccxt直接获取订单簿（无需WebSocket）")
        
        # 记录当前止损止盈单ID
        self.stop_loss_order_id = None
        self.stop_loss_order_type = None  # 记录订单类型：'limit' 或 'conditional_limit'
        self.take_profit_order_id = None
        
        # 🔴 混合方案：监听待优化的止损止盈单
        self.pending_stop_loss = {}  # {symbol: {'side': 'long', 'trigger_price': 3800, 'amount': 1, 'conditional_order_id': 'xxx'}}
        self.pending_take_profit = {}  # 同上
    
    def _get_orderbook(self, symbol):
        """直接使用ccxt获取订单簿"""
        try:
            return self.exchange.fetch_order_book(symbol, limit=5)
        except Exception as e:
            print(f"❌ 获取订单簿失败: {e}")
            return None
    
    def _cancel_conditional_order(self, order_id, symbol):
        """取消条件单（使用专用API）
        
        Args:
            order_id: 条件单ID
            symbol: 交易对
            
        Returns:
            bool: 是否成功
        """
        try:
            # 使用OKX的条件单取消API
            # 参数格式：params 应该是一个列表，包含订单信息
            params_list = [{
                'instId': symbol,
                'algoId': str(order_id)
            }]
            
            response = self.exchange.private_post_trade_cancel_algos(params_list)
            
            if response.get('code') == '0':
                print(f"✅ 条件单已取消: {order_id}")
                return True
            else:
                error_msg = response.get('msg', 'Unknown error')
                print(f"❌ 取消条件单失败: {error_msg}")
                print(f"   响应详情: {response}")
                return False
                
        except Exception as e:
            print(f"❌ 取消条件单异常: {e}")
            return False
    
    def _get_bid_price(self, symbol, level=1):
        """获取买盘价格"""
        orderbook = self._get_orderbook(symbol)
        if orderbook and len(orderbook['bids']) >= level:
            return orderbook['bids'][level - 1][0]
        return None
    
    def _get_ask_price(self, symbol, level=1):
        """获取卖盘价格"""
        orderbook = self._get_orderbook(symbol)
        if orderbook and len(orderbook['asks']) >= level:
            return orderbook['asks'][level - 1][0]
        return None
    
    def get_contract_size(self, symbol):
        """获取合约规格"""
        if self.test_mode:
            return 0.1, 0.01
        
        try:
            if self.exchange is None:
                return 0.1, 0.01
            
            markets = self.exchange.load_markets()
            if symbol in markets:
                market = markets[symbol]
                contract_size = market.get('contractSize', 0.1)
                limits = market.get('limits', {})
                amount_limits = limits.get('amount', {})
                min_size = amount_limits.get('min', 0.01)
                
                return contract_size, min_size
            else:
                print(f"⚠️  未找到 {symbol} 的市场信息，使用默认值")
                return 0.1, 0.01
        except Exception as e:
            print(f"❌ 获取合约规格失败: {e}")
            return 0.1, 0.01
    
    def calculate_contract_amount(self, symbol, usdt_amount, current_price, leverage=None):
        """计算可以购买的合约张数"""
        if leverage is None:
            leverage = self.leverage
        
        contract_size, min_size = self.get_contract_size(symbol)
        
        # 安全保证金：95%缓冲
        safe_margin = usdt_amount * 0.95
        position_value = safe_margin * leverage
        coin_amount = position_value / current_price
        contract_amount = coin_amount / contract_size
        
        # 根据最小下单量调整
        if contract_amount < min_size:
            contract_amount = min_size
        else:
            if min_size >= 1:
                contract_amount = int(contract_amount)
            elif min_size >= 0.1:
                contract_amount = int(contract_amount * 10) / 10
            elif min_size >= 0.01:
                contract_amount = int(contract_amount * 100) / 100
            else:
                contract_amount = round(contract_amount, 4)
        
        print(f"💰 合约数量计算: {contract_amount} 张")
        return contract_amount
    
    def open_long_with_limit_order(self, symbol, amount, stop_loss_price=None, take_profit_price=None):
        """
        开多单（使用限价单 + 订单簿优化 - 持续挂单直到成交）
        
        策略：
        1. 每10秒检查一次，使用最新的买3价挂单
        2. 如果买3价会立即成交，依次尝试买4价、买5价
        3. 持续循环直到成交，最多尝试30次（5分钟）
        
        Args:
            symbol: 交易对符号
            amount: 数量
            stop_loss_price: 止损价格
            take_profit_price: 止盈价格
        
        Returns:
            dict: 订单信息
        """
        result = {
            'entry_order': None,
            'stop_loss_order': None,
            'take_profit_order': None
        }
        
        if self.test_mode:
            print(f"🧪 【测试模式】模拟开多单: {symbol}, 数量: {amount}")
            result['entry_order'] = {'id': 'TEST_ENTRY', 'status': 'simulated'}
            return result
        
        print(f"\n{'='*60}")
        print(f"🔵 开始开多单流程: {symbol} (持续挂单模式)")
        print(f"{'='*60}")
        
        entry_order = None
        start_time = time.time()
        attempt = 0
        max_attempts = 30  # 最多尝试30次（5分钟）
        
        while not entry_order and attempt < max_attempts:
            attempt += 1
            elapsed = time.time() - start_time
            print(f"\n📊 第{attempt}次尝试 (已过{elapsed:.0f}秒)")
            
            # 获取最新的买3价
            bid3 = self._get_bid_price(symbol, level=3)
            if bid3:
                print(f"   买3价: ${bid3:.2f}")
                entry_order = self._place_limit_order(symbol, 'buy', amount, bid3, timeout=10)
                
                # 🔴 如果买3会立即成交，尝试买4/买5
                if not entry_order:
                    print(f"   💡 买3价已穿过，尝试买4价...")
                    bid4 = self._get_bid_price(symbol, level=4)
                    if bid4:
                        print(f"   买4价: ${bid4:.2f}")
                        entry_order = self._place_limit_order(symbol, 'buy', amount, bid4, timeout=10)
                    
                    if not entry_order:
                        print(f"   💡 买4价已穿过，尝试买5价...")
                        bid5 = self._get_bid_price(symbol, level=5)
                        if bid5:
                            print(f"   买5价: ${bid5:.2f}")
                            entry_order = self._place_limit_order(symbol, 'buy', amount, bid5, timeout=10)
            
            # 如果还没成交，等待一小段时间再重试
            if not entry_order and attempt < max_attempts:
                print(f"   ⏳ 未成交，2秒后重试...")
                time.sleep(2)
        
        # 如果达到最大尝试次数仍未成交
        if not entry_order:
            elapsed = time.time() - start_time
            print(f"\n⏰ 达到最大尝试次数({max_attempts}次)，取消本次开仓 (已过{elapsed:.0f}秒)")
            print(f"   💡 市场波动太大或流动性不足")
            
            # 🔴 清理所有可能残留的未成交订单
            try:
                print(f"   🧹 清理残留订单...")
                open_orders = self.exchange.fetch_open_orders(symbol)
                for order in open_orders:
                    if order.get('side') == 'buy' and not order.get('reduceOnly'):
                        try:
                            self.exchange.cancel_order(order['id'], symbol)
                            print(f"   ✅ 已取消订单: {order['id']}")
                        except Exception as e:
                            print(f"   ⚠️  取消订单失败: {e}")
            except Exception as e:
                print(f"   ⚠️  清理订单失败: {e}")
        
        result['entry_order'] = entry_order
        
        if not entry_order:
            print(f"\n❌ 开多单失败: 超时未成交")
            # 🔴 超时失败，不设置止损止盈
            print(f"{'='*60}\n")
            return result
        
        print(f"\n✅ 开多单成功: 订单ID={entry_order['id']}")
        
        # 🔴 不清空监听队列，因为新设置的止损单需要监听
        # 注释掉：if symbol in self.pending_stop_loss:
        #     del self.pending_stop_loss[symbol]
        
        # 🔴 只有开仓成功才设置止损止盈
        if stop_loss_price:
            result['stop_loss_order'] = self._set_stop_loss_limit(
                symbol, 'long', stop_loss_price, amount
            )
        
        if take_profit_price:
            result['take_profit_order'] = self._set_take_profit_limit(
                symbol, 'long', take_profit_price, amount
            )
        
        print(f"{'='*60}\n")
        return result
    
    def open_short_with_limit_order(self, symbol, amount, stop_loss_price=None, take_profit_price=None):
        """
        开空单（使用限价单 + 订单簿优化 - 持续挂单直到成交）
        
        策略：
        1. 每10秒检查一次，使用最新的卖3价挂单
        2. 如果卖3价会立即成交，依次尝试卖4价、卖5价
        3. 持续循环直到成交，最多尝试30次（5分钟）
        
        Args:
            symbol: 交易对符号
            amount: 数量
            stop_loss_price: 止损价格
            take_profit_price: 止盈价格
        
        Returns:
            dict: 订单信息
        """
        result = {
            'entry_order': None,
            'stop_loss_order': None,
            'take_profit_order': None
        }
        
        if self.test_mode:
            print(f"🧪 【测试模式】模拟开空单: {symbol}, 数量: {amount}")
            result['entry_order'] = {'id': 'TEST_ENTRY', 'status': 'simulated'}
            return result
        
        print(f"\n{'='*60}")
        print(f"🔴 开始开空单流程: {symbol} (持续挂单模式)")
        print(f"{'='*60}")
        
        entry_order = None
        start_time = time.time()
        attempt = 0
        max_attempts = 30  # 最多尝试30次（5分钟）
        
        while not entry_order and attempt < max_attempts:
            attempt += 1
            elapsed = time.time() - start_time
            print(f"\n📊 第{attempt}次尝试 (已过{elapsed:.0f}秒)")
            
            # 获取最新的卖3价
            ask3 = self._get_ask_price(symbol, level=3)
            if ask3:
                print(f"   卖3价: ${ask3:.2f}")
                entry_order = self._place_limit_order(symbol, 'sell', amount, ask3, timeout=10)
                
                # 🔴 如果卖3会立即成交，尝试卖4/卖5
                if not entry_order:
                    print(f"   💡 卖3价已穿过，尝试卖4价...")
                    ask4 = self._get_ask_price(symbol, level=4)
                    if ask4:
                        print(f"   卖4价: ${ask4:.2f}")
                        entry_order = self._place_limit_order(symbol, 'sell', amount, ask4, timeout=10)
                    
                    if not entry_order:
                        print(f"   💡 卖4价已穿过，尝试卖5价...")
                        ask5 = self._get_ask_price(symbol, level=5)
                        if ask5:
                            print(f"   卖5价: ${ask5:.2f}")
                            entry_order = self._place_limit_order(symbol, 'sell', amount, ask5, timeout=10)
            
            # 如果还没成交，等待一小段时间再重试
            if not entry_order and attempt < max_attempts:
                print(f"   ⏳ 未成交，2秒后重试...")
                time.sleep(2)
        
        # 如果达到最大尝试次数仍未成交
        if not entry_order:
            elapsed = time.time() - start_time
            print(f"\n⏰ 达到最大尝试次数({max_attempts}次)，取消本次开仓 (已过{elapsed:.0f}秒)")
            print(f"   💡 市场波动太大或流动性不足")
            
            # 🔴 清理所有可能残留的未成交订单
            try:
                print(f"   🧹 清理残留订单...")
                open_orders = self.exchange.fetch_open_orders(symbol)
                for order in open_orders:
                    if order.get('side') == 'sell' and not order.get('reduceOnly'):
                        try:
                            self.exchange.cancel_order(order['id'], symbol)
                            print(f"   ✅ 已取消订单: {order['id']}")
                        except Exception as e:
                            print(f"   ⚠️  取消订单失败: {e}")
            except Exception as e:
                print(f"   ⚠️  清理订单失败: {e}")
        
        result['entry_order'] = entry_order
        
        if not entry_order:
            print(f"\n❌ 开空单失败: 超时未成交")
            # 🔴 超时失败，不设置止损止盈
            print(f"{'='*60}\n")
            return result
        
        print(f"\n✅ 开空单成功: 订单ID={entry_order['id']}")
        
        # 🔴 不清空监听队列，因为新设置的止损单需要监听
        # 注释掉：if symbol in self.pending_stop_loss:
        #     del self.pending_stop_loss[symbol]
        
        # 🔴 只有开仓成功才设置止损止盈
        if stop_loss_price:
            result['stop_loss_order'] = self._set_stop_loss_limit(
                symbol, 'short', stop_loss_price, amount
            )
        
        if take_profit_price:
            result['take_profit_order'] = self._set_take_profit_limit(
                symbol, 'short', take_profit_price, amount
            )
        
        print(f"{'='*60}\n")
        return result
    
    def _place_limit_order(self, symbol, side, amount, price, timeout=30, check_immediate_fill=True):
        """
        下限价单并等待成交
        
        Args:
            symbol: 交易对
            side: 'buy' 或 'sell'
            amount: 数量
            price: 价格
            timeout: 超时时间（秒）
            check_immediate_fill: 是否检查立即成交（开仓时True，止损止盈时False）
        
        Returns:
            dict: 成交的订单信息，或 None
        """
        try:
            # 🔴 开仓时检查是否会立即成交
            if check_immediate_fill:
                ticker = self.exchange.fetch_ticker(symbol)
                
                if side == 'buy':
                    best_ask = ticker.get('ask', ticker['last'])
                    if price >= best_ask:
                        print(f"   ⚠️  限价单会立即成交 (限价${price:.2f} >= 卖一${best_ask:.2f})")
                        print(f"   💡 说明: 市场价格已穿过预期价格")
                        # 🔴 不直接放弃，返回None让上层决定
                        return None
                else:
                    best_bid = ticker.get('bid', ticker['last'])
                    if price <= best_bid:
                        print(f"   ⚠️  限价单会立即成交 (限价${price:.2f} <= 买一${best_bid:.2f})")
                        print(f"   💡 说明: 市场价格已穿过预期价格")
                        return None
            
            # 下限价单
            params = {}
            if side == 'buy':
                params['posSide'] = 'long'
            else:
                params['posSide'] = 'short'
            
            try:
                order = self.exchange.create_limit_order(symbol, side, amount, price, params)
            except Exception as e1:
                if '51000' in str(e1) or 'posSide' in str(e1):
                    print(f"   🔄 检测到单向持仓模式")
                    order = self.exchange.create_limit_order(symbol, side, amount, price)
                else:
                    raise e1
            
            order_id = order['id']
            print(f"   ✅ 限价单已下: ID={order_id}, 价格=${price:.2f}")
            
            # 等待成交
            print(f"   ⏳ 等待成交 (超时{timeout}秒)...")
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                time.sleep(1)  # 每1秒检查一次，提高响应速度
                
                order_info = self.exchange.fetch_order(order_id, symbol)
                status = order_info['status']
                
                if status == 'closed':
                    print(f"   ✅ 订单已成交: 成交价=${order_info.get('average', price):.2f}")
                    return order_info
                elif status == 'canceled':
                    print(f"   ❌ 订单已取消")
                    return None
                
                # 显示等待进度
                elapsed = time.time() - start_time
                remaining = timeout - elapsed
                if int(elapsed) % 3 == 0:  # 每3秒显示一次进度
                    print(f"   ⏳ 等待中... 剩余{remaining:.0f}秒")
            
            # 超时未成交，撤单
            print(f"   ⏱️  超时未成交，撤单...")
            self.exchange.cancel_order(order_id, symbol)
            return None
            
        except Exception as e:
            print(f"   ❌ 下限价单失败: {e}")
            return None
    
    def _set_stop_loss_limit(self, symbol, side, trigger_price, amount):
        """
        设置止损限价单（优先限价，失败后降级为条件单）
        
        Args:
            symbol: 交易对
            side: 'long' 或 'short'
            trigger_price: 触发价格（就是止损价，例如4000）
            amount: 数量
        
        Returns:
            dict: 订单信息或None
        """
        print(f"\n   🛡️  设置止损单: ${trigger_price:.2f}")
        
        # Step 1: 先尝试普通限价单（省手续费）
        # 🔴 直接使用 trigger_price 作为限价单价格
        print(f"   📊 方案1: 尝试限价单 价格=${trigger_price:.2f} (Maker手续费0.02%)")
        
        try:
            # 🔴 使用 Post-Only 限价单：如果会立即成交，OKX会拒绝订单
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            if side == 'long':
                # 多单止损：卖出 @ trigger_price
                order_side = 'sell'
                # 检查：如果当前价已经低于止损价，说明已经触发了
                if current_price <= trigger_price:
                    print(f"   ⚠️  止损价已触发 (当前价${current_price:.2f} <= 止损价${trigger_price:.2f})")
                    raise Exception("价格已触发，使用条件单")
            else:
                # 空单止损：买入 @ trigger_price
                order_side = 'buy'
                # 检查：如果当前价已经高于止损价，说明已经触发了
                if current_price >= trigger_price:
                    print(f"   ⚠️  止损价已触发 (当前价${current_price:.2f} >= 止损价${trigger_price:.2f})")
                    raise Exception("价格已触发，使用条件单")
            
            # 🔴 尝试 Post-Only 限价单（OKX会自动拒绝会立即成交的订单）
            params = {
                'reduceOnly': True,
                'postOnly': True  # 🔴 只做Maker，如果会立即成交则拒绝
            }
            
            try:
                params['posSide'] = side
                order = self.exchange.create_limit_order(symbol, order_side, amount, trigger_price, params)
            except Exception as e1:
                error_msg = str(e1)
                # 检查是否是 posSide 错误
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"   🔄 检测到单向持仓模式")
                    del params['posSide']
                    order = self.exchange.create_limit_order(symbol, order_side, amount, trigger_price, params)
                # 检查是否是 Post-Only 被拒绝（订单会立即成交）
                elif '51008' in error_msg or 'post_only' in error_msg.lower() or 'Post only' in error_msg:
                    print(f"   ⚠️  Post-Only被拒绝（订单会立即成交）")
                    raise Exception("会立即成交，使用条件单")
                else:
                    raise e1
            
            print(f"   ✅ 限价止损单已设置: 价格=${trigger_price:.2f}, ID={order['id']}")
            
            # 🔴 立即检查订单状态，如果被撤销则降级为条件单
            try:
                print(f"   🔍 查询新创建止损单状态: {order['id']}")
                order_status = self.exchange.fetch_order(order['id'], symbol)
                print(f"   📊 新止损单API返回结果: {order_status}")
                
                status = order_status.get('status', 'unknown')
                print(f"   🔍 止损单状态检查: {status}")
                
                if status == 'closed':
                    print(f"   ⚠️  止损单已成交！成交价: ${order_status.get('average', 'unknown')}")
                    self.stop_loss_order_id = order['id']
                    self.stop_loss_order_type = 'limit'
                    order['_order_type'] = 'limit'
                    return order
                elif status == 'canceled':
                    print(f"   ⚠️  Post-Only止损单被系统撤销！原因: {order_status.get('info', {}).get('cancelSourceReason', 'unknown')}")
                    print(f"   🔄 降级为条件单...")
                    raise Exception("Post-Only被撤销，降级为条件单")
                else:
                    print(f"   ✅ 止损单状态正常: {status}")
                    self.stop_loss_order_id = order['id']
                    self.stop_loss_order_type = 'limit'
                    order['_order_type'] = 'limit'
                    return order
                    
            except Exception as e:
                error_msg = str(e)
                print(f"   ❌ 检查止损单状态失败: {error_msg}")
                
                if "Post-Only被撤销" in str(e):
                    # 重新抛出异常，让外层catch处理降级逻辑
                    raise e
                else:
                    # 其他错误，继续使用这个订单
                    print(f"   ⚠️  无法确认订单状态，继续使用: {order['id']}")
                    self.stop_loss_order_id = order['id']
                    self.stop_loss_order_type = 'limit'
                    order['_order_type'] = 'limit'
                    return order
            
        except Exception as e:
            print(f"   ❌ 限价单失败: {e}")
            
            # Step 2: 降级为条件限价单（兜底方案）
            print(f"   📊 方案2: 使用条件限价单 (触发后Maker手续费0.02%)")
            try:
                conditional_order = self._set_stop_loss_conditional(symbol, side, trigger_price, amount)
                
                if conditional_order:
                    self.stop_loss_order_id = conditional_order['id']
                    self.stop_loss_order_type = 'conditional_limit'
                    print(f"   ✅ 条件止损单已设置: ID={conditional_order['id']}, 触发价=${trigger_price:.2f}")
                    conditional_order['_order_type'] = 'conditional_limit'
                    
                    # 🔴 加入监听队列（价格到达 trigger_price ± 1% 时，撤条件单改挂限价单）
                    self.pending_stop_loss[symbol] = {
                        'conditional_order_id': conditional_order['id'],
                        'trigger_price': trigger_price,
                        'amount': amount,
                        'side': side,
                        'order_type': 'conditional_limit'  # 记录订单类型
                    }
                    print(f"   🔔 已加入监听队列: 价格到达 ${trigger_price * 0.99:.2f} - ${trigger_price * 1.01:.2f} 时优化为限价单")
                    
                    return conditional_order
                else:
                    print(f"   ❌ 条件单也失败了")
                    return None
                    
            except Exception as e2:
                print(f"   ❌ 条件单失败: {e2}")
                return None
    
    def _set_stop_loss_conditional(self, symbol, side, trigger_price, amount):
        """设置条件止损单（兜底方案）
        
        Args:
            symbol: 交易对
            side: 'long' 或 'short'
            trigger_price: 触发价格
            amount: 数量
        
        Returns:
            dict: 订单信息或None
        """
        if self.test_mode:
            print(f"   🧪 【测试模式】模拟条件止损单")
            return {'id': 'TEST_CONDITIONAL_SL', 'status': 'simulated'}
        
        try:
            # 🔴 使用条件限价单（触发后以限价单成交，省手续费）
            # 委托价直接用 trigger_price（触发后挂该价格的限价单）
            if side == 'long':
                # 多单止损：触发后卖出 @ trigger_price
                order_side = 'sell'
            else:
                # 空单止损：触发后买入 @ trigger_price
                order_side = 'buy'
            
            params = {
                'slTriggerPx': str(trigger_price),  # 止损触发价
                'slOrdPx': str(trigger_price),      # 🔴 止损委托价（就用trigger_price）
                'reduceOnly': True
            }
            
            # 🔴 动态处理posSide参数
            try:
                params['posSide'] = side
                order = self.exchange.create_order(
                    symbol, 'limit', order_side, amount, trigger_price, params
                )
                print(f"   ✅ 条件止损限价单已设置: 触发价=${trigger_price:.2f}, 委托价=${trigger_price:.2f}, ID={order['id']}")
                return order
                
            except Exception as e1:
                error_msg = str(e1)
                # 如果是posSide错误，重试不带posSide
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"   🔄 检测到单向持仓模式，重试不带posSide...")
                    del params['posSide']
                    order = self.exchange.create_order(
                        symbol, 'limit', order_side, amount, trigger_price, params
                    )
                    print(f"   ✅ 条件止损限价单已设置: 触发价=${trigger_price:.2f}, 委托价=${trigger_price:.2f}, ID={order['id']}")
                    return order
                else:
                    raise e1
            
        except Exception as e:
            print(f"   ❌ 条件止损单失败: {e}")
            return None
    
    def _set_take_profit_limit(self, symbol, side, trigger_price, amount):
        """设置止盈单（优先限价，失败后降级为条件单）"""
        print(f"\n   💰 设置止盈单: ${trigger_price:.2f}")
        
        # Step 1: 先尝试普通限价单（省手续费）
        # 🔴 直接使用 trigger_price 作为限价单价格
        print(f"   📊 方案1: 尝试限价单 价格=${trigger_price:.2f} (Maker手续费0.02%)")
        
        try:
            # 🔴 获取订单簿，检查限价单是否会立即成交
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            if side == 'long':
                # 多单止盈：卖出 @ trigger_price
                order_side = 'sell'
                # 检查：如果当前价已经高于止盈价，说明已经触发了
                if current_price >= trigger_price:
                    print(f"   ⚠️  止盈价已触发 (当前价${current_price:.2f} >= 止盈价${trigger_price:.2f})")
                    raise Exception("价格已触发，使用条件单")
            else:
                # 空单止盈：买入 @ trigger_price
                order_side = 'buy'
                # 检查：如果当前价已经低于止盈价，说明已经触发了
                if current_price <= trigger_price:
                    print(f"   ⚠️  止盈价已触发 (当前价${current_price:.2f} <= 止盈价${trigger_price:.2f})")
                    raise Exception("价格已触发，使用条件单")
            
            # 🔴 尝试 Post-Only 限价单（OKX会自动拒绝会立即成交的订单）
            params = {
                'reduceOnly': True,
                'postOnly': True  # 🔴 只做Maker，如果会立即成交则拒绝
            }
            
            try:
                params['posSide'] = side
                order = self.exchange.create_limit_order(symbol, order_side, amount, trigger_price, params)
            except Exception as e1:
                error_msg = str(e1)
                # 检查是否是 posSide 错误
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"   🔄 检测到单向持仓模式")
                    del params['posSide']
                    order = self.exchange.create_limit_order(symbol, order_side, amount, trigger_price, params)
                # 检查是否是 Post-Only 被拒绝（订单会立即成交）
                elif '51008' in error_msg or 'post_only' in error_msg.lower() or 'Post only' in error_msg:
                    print(f"   ⚠️  Post-Only被拒绝（订单会立即成交）")
                    raise Exception("会立即成交，使用条件单")
                else:
                    raise e1
            
            print(f"   ✅ 限价止盈单已设置: 价格=${trigger_price:.2f}, ID={order['id']}")
            self.take_profit_order_id = order['id']
            order['_order_type'] = 'limit'
            return order
            
        except Exception as e:
            print(f"   ❌ 限价单失败: {e}")
            
            # Step 2: 降级为条件限价单（兜底方案）
            print(f"   📊 方案2: 使用条件限价单 (触发后Maker手续费0.02%)")
            try:
                # 🔴 条件单的委托价也用 trigger_price（触发后以该价格限价成交）
                if side == 'long':
                    order_side = 'sell'
                else:
                    order_side = 'buy'
                
                params = {
                    'tpTriggerPx': str(trigger_price),  # 止盈触发价
                    'tpOrdPx': str(trigger_price),      # 🔴 止盈委托价（就用trigger_price）
                    'reduceOnly': True
                }
                
                # 动态处理posSide参数
                try:
                    params['posSide'] = side
                    order = self.exchange.create_order(
                        symbol, 'limit', order_side, amount, trigger_price, params
                    )
                except Exception as e1:
                    if '51000' in str(e1) or 'posSide' in str(e1):
                        print(f"   🔄 检测到单向持仓模式")
                        del params['posSide']
                        order = self.exchange.create_order(
                            symbol, 'limit', order_side, amount, trigger_price, params
                        )
                    else:
                        raise e1
                
                print(f"   ✅ 条件止盈单已设置: 触发价=${trigger_price:.2f}, 委托价=${trigger_price:.2f}, ID={order['id']}")
                self.take_profit_order_id = order['id']
                order['_order_type'] = 'conditional_limit'
                return order
                
            except Exception as e2:
                print(f"   ❌ 条件单失败: {e2}")
                return None
    
    # 保留原有方法以兼容现有代码
    def get_latest_klines(self, symbol, timeframe='1m', limit=100):
        """获取最新K线数据"""
        try:
            klines = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return klines
        except Exception as e:
            print(f"❌ 获取K线数据失败 ({symbol}): {e}")
            return []
    
    def get_balance(self):
        """获取账户余额"""
        try:
            balance = self.exchange.fetch_balance()
            return {
                'total': balance['total'].get('USDT', 0),
                'free': balance['free'].get('USDT', 0),
                'used': balance['used'].get('USDT', 0),
            }
        except Exception as e:
            print(f"❌ 获取账户余额失败: {e}")
            return None
    
    def get_account_info(self):
        """获取账户信息"""
        try:
            balance = self.get_balance()
            return {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'balance': balance,
                'mode': TRADING_CONFIG['mode'],
                'test_mode': self.test_mode
            }
        except Exception as e:
            print(f"❌ 获取账户信息失败: {e}")
            return None
    
    def open_long_with_stop_orders(self, symbol, amount, stop_loss_price, take_profit_price):
        """兼容性方法：调用open_long_with_limit_order"""
        return self.open_long_with_limit_order(symbol, amount, stop_loss_price, take_profit_price)
    
    def open_short_with_stop_orders(self, symbol, amount, stop_loss_price, take_profit_price):
        """兼容性方法：调用open_short_with_limit_order"""
        return self.open_short_with_limit_order(symbol, amount, stop_loss_price, take_profit_price)
    
    def update_stop_loss(self, symbol, position_side, new_stop_loss, amount):
        """兼容性方法：更新止损单（混合方案）
        
        V2版本逻辑：
        1. 取消所有当前的止损单（限价单/条件单）
        2. 尝试挂新的限价单
        3. 如果失败，挂条件单兜底，并加入监听队列
        4. 每分钟检查队列，价格接近时优化为限价单
        """
        print(f"\n🔄 V2更新止损单: {symbol} {position_side} ${new_stop_loss:.2f}")
        
        # Step 1: 取消所有当前的止损单
        print(f"   🗑️  取消旧止损单...")
        self._cancel_stop_loss_orders(symbol)
        
        # Step 2: 尝试挂新的限价单
        side = position_side  # 'long' or 'short'
        result = self._set_stop_loss_limit(symbol, side, new_stop_loss, amount)
        
        # 如果成功挂上限价单，从监听队列移除
        if result and symbol in self.pending_stop_loss:
            # 检查是否是真正的限价单（不是条件单）
            if result.get('id') != self.pending_stop_loss[symbol].get('conditional_order_id'):
                print(f"   ✅ 限价单挂单成功，从监听队列移除")
                del self.pending_stop_loss[symbol]
        
        return result
    
    def cancel_all_stop_orders(self, symbol):
        """兼容性方法：取消所有止损止盈单
        
        🔴 V2修复：只取消reduceOnly=True的订单（止损止盈单）
        避免误删其他limit订单（如开仓限价单）
        """
        if self.test_mode:
            print(f"🧪 【测试模式】模拟取消所有止损单: {symbol}")
            return True
        
        try:
            # V2版本：查询并取消所有活跃的止损止盈单
            open_orders = self.exchange.fetch_open_orders(symbol)
            canceled_count = 0
            
            for order in open_orders:
                # 🔴 修复：只取消reduceOnly=True的订单（止损止盈单）
                order_type = order.get('type', '')
                reduce_only = order.get('reduceOnly', False)
                
                # 判断是否是止损止盈单
                is_stop_or_tp = (
                    reduce_only or  # ← 关键：reduceOnly标志
                    order_type in ['stop', 'stop_limit', 'stop_market']
                )
                
                if is_stop_or_tp:
                    try:
                        self.exchange.cancel_order(order['id'], symbol)
                        canceled_count += 1
                        print(f"✅ 已取消止损止盈单: ID={order['id']}, type={order_type}")
                    except Exception as e:
                        print(f"⚠️  取消订单{order['id']}失败: {e}")
            
            if canceled_count > 0:
                print(f"✅ 共取消 {canceled_count} 个止损止盈单")
            else:
                print(f"📊 无需取消的止损止盈单")
            
            return True
            
        except Exception as e:
            print(f"⚠️  取消止损单失败: {e}")
            return False
    
    def set_leverage(self, symbol, leverage, margin_mode='cross'):
        """设置杠杆倍数"""
        if self.test_mode:
            print(f"🧪 【测试模式】模拟设置杠杆: {symbol}, {leverage}x")
            return True
        
        try:
            params = {
                'instId': symbol,
                'lever': str(leverage),
                'mgnMode': margin_mode,
            }
            
            response = self.exchange.private_post_account_set_leverage(params)
            
            if response.get('code') == '0':
                print(f"✅ 杠杆设置成功: {symbol}, {leverage}x")
                self.leverage = leverage
                return True
            else:
                print(f"❌ 杠杆设置失败: {response.get('msg')}")
                return False
                
        except Exception as e:
            print(f"❌ 设置杠杆失败: {e}")
            return False
    
    def _cancel_stop_loss_orders(self, symbol):
        """取消指定交易对的所有止损单（只取消止损，不取消止盈）
        
        🔴 关键：通过订单ID或价格判断是否是止损单
        - 如果有记录的止损单ID（self.stop_loss_order_id），直接取消
        - 或者从pending_stop_loss队列中获取条件单ID
        """
        if self.test_mode:
            print(f"   🧪 【测试模式】模拟取消止损单")
            # 清空监听队列中的记录
            if symbol in self.pending_stop_loss:
                del self.pending_stop_loss[symbol]
            self.stop_loss_order_id = None
            self.stop_loss_order_type = None
            return True
        
        try:
            canceled_count = 0
            
            # 🔴 方案1：如果有记录止损单ID，直接取消
            if self.stop_loss_order_id:
                try:
                    if self.stop_loss_order_type == 'conditional_limit':
                        # 条件单：使用专用取消方法
                        self._cancel_conditional_order(self.stop_loss_order_id, symbol)
                    else:
                        # 限价单：使用普通取消方法
                        self.exchange.cancel_order(self.stop_loss_order_id, symbol)
                    print(f"   ✅ 已取消止损单: {self.stop_loss_order_id}")
                    self.stop_loss_order_id = None
                    self.stop_loss_order_type = None
                    canceled_count += 1
                except Exception as e:
                    print(f"   ⚠️  取消止损单{self.stop_loss_order_id}失败: {e}")
            
            # 🔴 方案2：如果有pending队列中的订单，也取消
            if symbol in self.pending_stop_loss:
                pending = self.pending_stop_loss[symbol]
                order_id = pending.get('conditional_order_id')
                order_type = pending.get('order_type', 'conditional_limit')
                
                if order_id:
                    try:
                        if order_type == 'conditional_limit':
                            # 条件单：使用专用取消方法
                            self._cancel_conditional_order(order_id, symbol)
                        else:
                            # 限价单：使用普通取消方法
                            self.exchange.cancel_order(order_id, symbol)
                        print(f"   ✅ 已取消止损单: {order_id}")
                        canceled_count += 1
                    except Exception as e:
                        print(f"   ⚠️  取消止损单失败: {e}")
                
                # 清空队列
                del self.pending_stop_loss[symbol]
            
            if canceled_count > 0:
                print(f"   📊 共取消 {canceled_count} 个止损单")
            else:
                print(f"   📊 无止损单需要取消")
            
            return True
            
        except Exception as e:
            print(f"   ❌ 取消止损单失败: {e}")
            return False
    
    def check_and_optimize_stop_orders(self):
        """检查监听队列，优化条件单为限价单（每20秒调用）
        
        遍历pending_stop_loss队列：
        - 检查当前价格与止损价的差距
        - 如果 ≤ 1%，取消条件单，挂限价单
        """
        # 🔴 即使队列为空也打印（让用户知道在运行）
        current_time = datetime.now().strftime('%H:%M:%S')
        
        if not self.pending_stop_loss:
            print(f"[{current_time}] 🔍 监听检查：待优化队列为空")
            return
        
        print(f"\n[{current_time}] 🔍 检查待优化的止损单（队列：{len(self.pending_stop_loss)}个）")
        
        # 🔴 打印队列详情
        for sym, pending_info in self.pending_stop_loss.items():
            print(f"   📋 队列详情: {sym} - 条件单ID: {pending_info.get('conditional_order_id')}, 触发价: ${pending_info.get('trigger_price')}, 方向: {pending_info.get('side')}")
        
        for symbol, pending in list(self.pending_stop_loss.items()):
            try:
                # 获取当前价格
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                trigger_price = pending['trigger_price']
                
                # 计算价差百分比
                price_diff_pct = abs(current_price - trigger_price) / current_price * 100
                
                print(f"   📊 {symbol}: 当前价${current_price:.2f}, 止损价${trigger_price:.2f}, 价差{price_diff_pct:.2f}%")
                
                # 🔴 先检查订单是否还存在
                order_id = pending.get('conditional_order_id')
                order_type = pending.get('order_type', 'conditional_limit')  # 默认条件单
                
                if order_id:
                    try:
                        print(f"   🔍 查询订单状态: {order_id} (类型: {order_type})")
                        
                        order_exists = False
                        
                        if order_type == 'conditional_limit':
                            # 条件单：根据API文档，ordType是必须参数
                            # 1. 先获取所有条件单
                            params = {
                                'ordType': 'conditional',  # 必须参数：查询止盈止损单
                            }
                            
                            try:
                                # 获取所有当前活跃的条件单
                                response = self.exchange.private_get_trade_orders_algo_pending(params)
                                print(f"   📊 获取到 {len(response.get('data', []))} 个条件单")
                                
                                if response.get('code') == '0' and response.get('data'):
                                    # 在结果中查找匹配的订单ID
                                    found_order = None
                                    for algo_data in response['data']:
                                        algo_id = algo_data.get('algoId', '')
                                        if str(algo_id) == str(order_id):
                                            found_order = algo_data
                                            break
                                    
                                    if found_order:
                                        state = found_order.get('state', 'live')
                                        print(f"   ✅ 找到条件单，状态: {state}")
                                        order_exists = True
                                    else:
                                        # 在当前委托列表中找不到匹配的订单
                                        print(f"   ⚠️  条件单不在当前委托列表中")
                                        # 打印所有条件单ID用于调试
                                        all_ids = [d.get('algoId') for d in response['data']]
                                        print(f"   📋 当前条件单ID列表: {all_ids}")
                                else:
                                    # 没有条件单
                                    print(f"   ⚠️  当前没有活跃的条件单")
                                    print(f"   📊 API响应: {response}")
                                    
                            except AttributeError:
                                print(f"   ⚠️  exchange对象不支持条件单API")
                            except Exception as e:
                                print(f"   ⚠️  获取条件单列表失败: {e}")
                                
                        elif order_type == 'limit':
                            # 限价单：使用普通订单API
                            try:
                                order_status = self.exchange.fetch_order(order_id, symbol)
                                print(f"   📊 订单API返回结果: {order_status}")
                                
                                if order_status.get('status') in ['open', 'closed']:
                                    print(f"   ✅ 限价单状态正常: {order_status.get('status')}")
                                    order_exists = True
                                elif order_status.get('status') in ['canceled']:
                                    print(f"   ⚠️  限价单已取消")
                                else:
                                    print(f"   📊 限价单状态: {order_status.get('status')}")
                                    
                            except Exception as e:
                                error_msg = str(e)
                                print(f"   ❌ 限价单查询失败: {error_msg}")
                                
                        # 如果订单不存在，从队列移除
                        if not order_exists:
                            print(f"   ⚠️  订单不存在，从队列移除")
                            del self.pending_stop_loss[symbol]
                            continue
                            
                    except Exception as e:
                        error_msg = str(e)
                        print(f"   ❌ 订单API错误详情: {error_msg}")
                        print(f"   🔍 错误类型: {type(e).__name__}")
                        
                        if "51603" in error_msg or "Order does not exist" in error_msg or "51600" in error_msg:
                            print(f"   ⚠️  订单不存在，从队列移除")
                            del self.pending_stop_loss[symbol]
                            continue
                        else:
                            print(f"   ⚠️  检查订单状态失败: {e}")
                            continue
                
                # 如果价差 ≤ 1%，尝试优化
                if price_diff_pct <= 0.5:
                    print(f"   💡 价格接近止损位（≤1%），尝试优化为限价单...")
                    
                    # 🔴 先检查：如果限价单会失败（价格已触发），就不要优化
                    # 获取当前市场价格
                    side = pending['side']
                    should_skip = False
                    
                    if side == 'long':
                        # 多单止损：如果当前价 <= 止损价，已经触发了
                        if current_price <= trigger_price:
                            print(f"   ⚠️  价格已触发止损 (当前价${current_price:.2f} <= 止损价${trigger_price:.2f})")
                            print(f"   💡 保持条件单，不优化")
                            should_skip = True
                    else:
                        # 空单止损：如果当前价 >= 止损价，已经触发了
                        if current_price >= trigger_price:
                            print(f"   ⚠️  价格已触发止损 (当前价${current_price:.2f} >= 止损价${trigger_price:.2f})")
                            print(f"   💡 保持条件单，不优化")
                            should_skip = True
                    
                    if should_skip:
                        continue
                    
                    # 取消订单（根据类型选择方法）
                    cancel_success = False
                    try:
                        if pending['conditional_order_id']:
                            if order_type == 'conditional_limit':
                                # 条件单：使用专用取消方法
                                self._cancel_conditional_order(pending['conditional_order_id'], symbol)
                            else:
                                # 限价单：使用普通取消方法
                                self.exchange.cancel_order(pending['conditional_order_id'], symbol)
                            print(f"   ✅ 已取消订单: {pending['conditional_order_id']}")
                            cancel_success = True
                    except Exception as e:
                        print(f"   ⚠️  取消订单失败: {e}")
                        # 如果取消失败（可能已经被触发了），就不要继续挂单
                        print(f"   💡 订单可能已触发，跳过优化")
                        del self.pending_stop_loss[symbol]
                        continue
                    
                    # 🔴 只有取消成功才尝试挂限价单
                    if cancel_success:
                        # 尝试挂限价单
                        limit_order = self._set_stop_loss_limit(
                            symbol,
                            pending['side'],
                            trigger_price,
                            pending['amount']
                        )
                        
                        if limit_order and limit_order.get('_order_type') == 'limit':
                            # 成功挂上限价单：从队列移除
                            print(f"   ✅ 优化成功！已替换为限价单")
                            del self.pending_stop_loss[symbol]
                        elif limit_order and limit_order.get('_order_type') == 'conditional_limit':
                            # 降级为条件单：更新ID和类型，继续监听
                            print(f"   💡 降级为条件单，继续监听")
                            self.pending_stop_loss[symbol]['conditional_order_id'] = limit_order['id']
                            self.pending_stop_loss[symbol]['order_type'] = 'conditional_limit'
                        else:
                            # 失败：移除队列（可能已经被触发了）
                            print(f"   ⚠️  挂单失败，从队列移除")
                            del self.pending_stop_loss[symbol]
                
            except Exception as e:
                print(f"   ❌ 检查{symbol}失败: {e}")
                continue
        
        if self.pending_stop_loss:
            print(f"   📋 待优化队列: {len(self.pending_stop_loss)}个")
        else:
            print(f"   ✅ 待优化队列为空")
        
        # 🔴 检查当前止损单状态
        if self.stop_loss_order_id:
            try:
                print(f"   🔍 查询止损单状态: {self.stop_loss_order_id} (类型: {self.stop_loss_order_type})")
                
                if self.stop_loss_order_type == 'conditional_limit':
                    # 条件单：使用条件单API
                    params = {'ordType': 'conditional'}
                    response = self.exchange.private_get_trade_orders_algo_pending(params)
                    
                    if response.get('code') == '0' and response.get('data'):
                        # 查找匹配的订单
                        found = False
                        for algo_data in response['data']:
                            if str(algo_data.get('algoId', '')) == str(self.stop_loss_order_id):
                                state = algo_data.get('state', 'live')
                                print(f"   ✅ 条件单状态: {state}")
                                found = True
                                break
                        
                        if not found:
                            print(f"   ⚠️  条件单不在当前委托列表中")
                            self.stop_loss_order_id = None
                            self.stop_loss_order_type = None
                    else:
                        print(f"   ⚠️  查询条件单失败: {response.get('msg')}")
                else:
                    # 限价单：使用普通订单API
                    order_status = self.exchange.fetch_order(self.stop_loss_order_id, symbol)
                    print(f"   📊 OKX API返回结果: {order_status}")
                    
                    status = order_status.get('status', 'unknown')
                    print(f"   🔍 当前止损单状态: {status}")
                    if status == 'closed':
                        print(f"   ⚠️  止损单已成交！成交价: ${order_status.get('average', 'unknown')}")
                        self.stop_loss_order_id = None  # 清空ID
                        self.stop_loss_order_type = None
                    elif status == 'canceled':
                        print(f"   ⚠️  止损单已取消！")
                        self.stop_loss_order_id = None  # 清空ID
                        self.stop_loss_order_type = None
                    else:
                        print(f"   ✅ 止损单状态正常: {status}")
                        
            except Exception as e:
                error_msg = str(e)
                print(f"   ❌ OKX API错误详情: {error_msg}")
                print(f"   🔍 错误类型: {type(e).__name__}")
                
                if "51603" in error_msg or "Order does not exist" in error_msg:
                    print(f"   ⚠️  止损单不存在（可能已触发或取消）: {self.stop_loss_order_id}")
                    self.stop_loss_order_id = None  # 清空ID
                    self.stop_loss_order_type = None
                else:
                    print(f"   ⚠️  检查止损单状态失败: {e}")

if __name__ == '__main__':
    print("🧪 测试 OKX交易接口V2\n")
    
    # 创建交易接口
    trader = OKXTraderV2(
        test_mode=False,
        leverage=3
    )
    
    symbol = 'ETH-USDT-SWAP'
    
    # 测试获取订单簿
    print(f"📊 测试获取 {symbol} 订单簿...\n")
    
    orderbook = trader._get_orderbook(symbol)
    if orderbook:
        print("✅ 订单簿获取成功！")
        print(f"买1价: ${orderbook['bids'][0][0]:.2f}")
        print(f"买3价: ${orderbook['bids'][2][0]:.2f}")
        print(f"卖1价: ${orderbook['asks'][0][0]:.2f}")
        print(f"卖3价: ${orderbook['asks'][2][0]:.2f}")
    else:
        print("❌ 订单簿获取失败")
    
    print("\n✅ 测试完成！")

