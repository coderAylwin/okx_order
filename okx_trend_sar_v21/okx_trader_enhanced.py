#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OKX 交易接口增强版
支持止损止盈挂单，适合实盘交易
"""

import ccxt
import time
from datetime import datetime
from okx_config import OKX_API_CONFIG, TRADING_CONFIG


class OKXTraderEnhanced:
    """OKX交易接口增强版 - 支持条件单"""
    
    def __init__(self, test_mode=True, leverage=1):
        """初始化OKX交易接口"""
        self.test_mode = test_mode or TRADING_CONFIG['test_mode']
        self.leverage = leverage
        
        # 记录当前止损止盈单ID（用于更新时撤销）
        self.stop_loss_order_id = None
        self.take_profit_order_id = None
        
        try:
            self.exchange = ccxt.okx(OKX_API_CONFIG)
            
            if TRADING_CONFIG['mode'] == 'paper':
                self.exchange.set_sandbox_mode(True)
                print("⚠️  【模拟盘模式】已启用 OKX 沙盒环境")
            else:
                print("🔴 【实盘模式】注意！将在真实市场交易！")
            
            self.exchange.load_markets()
            print(f"✅ OKX 交易接口增强版初始化成功")
            print(f"📊 默认杠杆倍数: {self.leverage}x")
            print(f"🛡️  支持: 止损挂单 | 止盈挂单 | 动态更新")
            
        except Exception as e:
            print(f"❌ OKX 交易接口初始化失败: {e}")
            self.exchange = None
    
    def get_contract_size(self, symbol):
        """获取合约规格（每张合约代表多少币）
        
        Args:
            symbol: 交易对符号 (如 'ETH-USDT-SWAP')
        
        Returns:
            tuple: (contract_size, min_size) - 每张合约币数，最小下单量
        """
        if self.test_mode:
            # 测试模式返回默认值
            return 0.1, 0.01  # ETH-USDT-SWAP: 0.1 ETH/张，最小0.01张
        
        try:
            if self.exchange is None:
                return 0.1, 0.01
            
            # 获取市场信息
            markets = self.exchange.load_markets()
            if symbol in markets:
                market = markets[symbol]
                # OKX的合约大小存储在 contractSize 字段
                contract_size = market.get('contractSize', 0.1)
                
                # 获取最小下单量
                limits = market.get('limits', {})
                amount_limits = limits.get('amount', {})
                min_size = amount_limits.get('min', 0.01)  # 默认0.01张
                
                print(f"📊 {symbol} 合约规格:")
                print(f"   每张合约: {contract_size} 币")
                print(f"   最小下单: {min_size} 张")
                
                return contract_size, min_size
            else:
                print(f"⚠️  未找到 {symbol} 的市场信息，使用默认值")
                return 0.1, 0.01
        except Exception as e:
            print(f"❌ 获取合约规格失败: {e}")
            return 0.1, 0.01
    
    def calculate_contract_amount(self, symbol, usdt_amount, current_price, leverage=None):
        """计算可以购买的合约张数
        
        Args:
            symbol: 交易对符号
            usdt_amount: USDT保证金金额
            current_price: 当前价格
            leverage: 杠杆倍数（用于放大购买力）
        
        Returns:
            float: 可以购买的合约张数（支持小数）
        """
        if leverage is None:
            leverage = self.leverage
        
        # 获取合约规格和最小下单量
        contract_size, min_size = self.get_contract_size(symbol)
        
        # 🔴 增加安全缓冲：只使用95%的保证金，留出5%缓冲
        safe_margin = usdt_amount * 0.95
        print(f"🔒 安全保证金计算: ${usdt_amount:.2f} × 95% = ${safe_margin:.2f}")
        
        # 计算仓位价值 = 安全保证金 × 杠杆
        position_value = safe_margin * leverage
        
        # 计算可购买的币数量 = 仓位价值 ÷ 价格
        coin_amount = position_value / current_price
        
        # 计算合约张数 = 币数量 ÷ 每张合约的币数量
        contract_amount = coin_amount / contract_size
        
        # 检查是否满足最小下单量
        if contract_amount < min_size:
            print(f"⚠️  计算张数 {contract_amount:.4f} 小于最小下单量 {min_size}，调整为 {min_size}")
            contract_amount = min_size
        else:
            # 根据最小下单量的精度进行取整
            # 例如：最小0.1张，则保留1位小数；最小0.01张，则保留2位小数
            if min_size >= 1:
                # 最小1张，向下取整到整数
                contract_amount = int(contract_amount)
            elif min_size >= 0.1:
                # 最小0.1张，向下取整到0.1
                contract_amount = int(contract_amount * 10) / 10
            elif min_size >= 0.01:
                # 最小0.01张，向下取整到0.01
                contract_amount = int(contract_amount * 100) / 100
            else:
                # 更精细的最小值，保留4位小数
                contract_amount = round(contract_amount, 4)
        
        # 计算实际仓位价值和所需保证金
        actual_position_value = contract_amount * contract_size * current_price
        required_margin = actual_position_value / leverage
        
        print(f"💰 合约数量计算:")
        print(f"   原始保证金: ${usdt_amount:.2f}")
        print(f"   安全保证金: ${safe_margin:.2f} (95%缓冲)")
        print(f"   杠杆: {leverage}x")
        print(f"   仓位价值: ${position_value:.2f} (安全保证金 × 杠杆)")
        print(f"   当前价格: ${current_price:.2f}")
        print(f"   合约规格: {contract_size} 币/张")
        print(f"   最小下单: {min_size} 张")
        print(f"   理论张数: {coin_amount / contract_size:.4f}")
        print(f"   实际下单: {contract_amount} 张")
        print(f"   实际仓位价值: ${actual_position_value:.2f}")
        print(f"   实际所需保证金: ${required_margin:.2f}")
        print(f"   安全缓冲: ${usdt_amount - required_margin:.2f} USDT")
        
        return contract_amount
    
    def open_long_with_stop_orders(self, symbol, amount, stop_loss_price=None, take_profit_price=None):
        """开多单并设置止损止盈
        
        Args:
            symbol: 交易对符号
            amount: 数量
            stop_loss_price: 止损价格（可选）
            take_profit_price: 止盈价格（可选）
        
        Returns:
            dict: {
                'entry_order': 开仓订单,
                'stop_loss_order': 止损订单,
                'take_profit_order': 止盈订单
            }
        """
        result = {
            'entry_order': None,
            'stop_loss_order': None,
            'take_profit_order': None
        }
        
        if self.test_mode:
            print(f"🧪 【测试模式】模拟开多单: {symbol}, 数量: {amount}")
            print(f"   止损价: {stop_loss_price}, 止盈价: {take_profit_price}")
            result['entry_order'] = {'id': 'TEST_ENTRY', 'status': 'simulated'}
            result['stop_loss_order'] = {'id': 'TEST_SL', 'status': 'simulated'}
            result['take_profit_order'] = {'id': 'TEST_TP', 'status': 'simulated'}
            return result
        
        try:
            # 1. 开仓 - 根据持仓模式决定是否添加posSide参数
            # 双向持仓模式：需要posSide参数
            # 单向持仓模式（买卖模式）：不需要posSide参数
            try:
                # 先尝试双向持仓模式（带posSide参数）
                params = {
                    'posSide': 'long'  # 明确指定为多仓
                }
                entry_order = self.exchange.create_market_buy_order(symbol, amount, params)
            except Exception as e1:
                error_msg = str(e1)
                # 如果是posSide参数错误，说明是单向持仓模式
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"🔄 检测到单向持仓模式，重试不带posSide参数...")
                    # 单向持仓模式：不传posSide参数
                    params = {}
                    entry_order = self.exchange.create_market_buy_order(symbol, amount, params)
                else:
                    # 其他错误，继续抛出
                    raise e1
            
            result['entry_order'] = entry_order
            print(f"✅ 开多单成功: {symbol}, 数量: {amount}, 订单ID: {entry_order['id']}")
            
        except Exception as e:
            print(f"❌ 开多单失败 ({symbol}): {e}")
            return result
        
        # 🔴 2. 设置止损单（独立处理，不影响开仓结果）
        if stop_loss_price:
            try:
                sl_order = self.set_stop_loss(symbol, 'long', stop_loss_price, amount)
                result['stop_loss_order'] = sl_order
                self.stop_loss_order_id = sl_order['id'] if sl_order else None
            except Exception as e:
                print(f"⚠️  止损单设置失败，但开仓已成功: {e}")
                result['stop_loss_order'] = None
        
        # 🔴 3. 设置止盈单（独立处理，不影响开仓结果）
        if take_profit_price:
            try:
                tp_order = self.set_take_profit(symbol, 'long', take_profit_price, amount)
                result['take_profit_order'] = tp_order
                self.take_profit_order_id = tp_order['id'] if tp_order else None
            except Exception as e:
                print(f"⚠️  止盈单设置失败，但开仓已成功: {e}")
                result['take_profit_order'] = None
        
        return result
    
    def open_short_with_stop_orders(self, symbol, amount, stop_loss_price=None, take_profit_price=None):
        """开空单并设置止损止盈
        
        Args:
            symbol: 交易对符号
            amount: 数量
            stop_loss_price: 止损价格（可选）
            take_profit_price: 止盈价格（可选）
        
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
            print(f"   止损价: {stop_loss_price}, 止盈价: {take_profit_price}")
            result['entry_order'] = {'id': 'TEST_ENTRY', 'status': 'simulated'}
            result['stop_loss_order'] = {'id': 'TEST_SL', 'status': 'simulated'}
            result['take_profit_order'] = {'id': 'TEST_TP', 'status': 'simulated'}
            return result
        
        try:
            # 1. 开仓 - 根据持仓模式决定是否添加posSide参数
            # 双向持仓模式：需要posSide参数
            # 单向持仓模式（买卖模式）：不需要posSide参数
            try:
                # 先尝试双向持仓模式（带posSide参数）
                params = {
                    'posSide': 'short'  # 明确指定为空仓
                }
                entry_order = self.exchange.create_market_sell_order(symbol, amount, params)
            except Exception as e1:
                error_msg = str(e1)
                # 如果是posSide参数错误，说明是单向持仓模式
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"🔄 检测到单向持仓模式，重试不带posSide参数...")
                    # 单向持仓模式：不传posSide参数
                    params = {}
                    entry_order = self.exchange.create_market_sell_order(symbol, amount, params)
                else:
                    # 其他错误，继续抛出
                    raise e1
            
            result['entry_order'] = entry_order
            print(f"✅ 开空单成功: {symbol}, 数量: {amount}, 订单ID: {entry_order['id']}")
            
        except Exception as e:
            print(f"❌ 开空单失败 ({symbol}): {e}")
            return result
        
        # 🔴 2. 设置止损单（独立处理，不影响开仓结果）
        if stop_loss_price:
            try:
                sl_order = self.set_stop_loss(symbol, 'short', stop_loss_price, amount)
                result['stop_loss_order'] = sl_order
                self.stop_loss_order_id = sl_order['id'] if sl_order else None
            except Exception as e:
                print(f"⚠️  止损单设置失败，但开仓已成功: {e}")
                result['stop_loss_order'] = None
        
        # 🔴 3. 设置止盈单（独立处理，不影响开仓结果）
        if take_profit_price:
            try:
                tp_order = self.set_take_profit(symbol, 'short', take_profit_price, amount)
                result['take_profit_order'] = tp_order
                self.take_profit_order_id = tp_order['id'] if tp_order else None
            except Exception as e:
                print(f"⚠️  止盈单设置失败，但开仓已成功: {e}")
                result['take_profit_order'] = None
        
        return result
    
    def set_stop_loss(self, symbol, side, trigger_price, amount):
        """设置止损单（Post-Only限价单）
        
        Args:
            symbol: 交易对符号
            side: 持仓方向 ('long' or 'short')
            trigger_price: 触发价格
            amount: 数量
        
        Returns:
            dict: 订单信息
        """
        if self.test_mode:
            print(f"🧪 【测试模式】模拟设置止损: {symbol}, 触发价: {trigger_price}")
            return {'id': 'TEST_SL', 'status': 'simulated'}
        
        try:
            # 🔴 添加调试信息
            print(f"🔍 设置止损单调试信息:")
            print(f"   交易对: {symbol}")
            print(f"   持仓方向: {side}")
            print(f"   触发价格: ${trigger_price:.2f}")
            print(f"   数量: {amount}")
            
            # 🔴 使用OKX条件单（真正的止损单）
            # 先尝试双向持仓模式（带posSide参数）
            params = {
                'tdMode': 'cross',  # 保证金模式：cross（全仓）或 isolated（逐仓）
                'ordType': 'conditional',  # ✅ 条件单（真正的止损单）
                'slTriggerPx': str(trigger_price),  # 止损触发价
                'slOrdPx': str(trigger_price),  # 止损委托价（触发后以此价格执行）
                'reduceOnly': True,  # 只减仓
                'posSide': 'long' if side == 'long' else 'short',  # 明确指定仓位方向
            }
            
            print(f"🔍 止损单参数: {params}")
            
            try:
                if side == 'long':
                    # 多单止损 = 向下触发，卖出平仓
                    print(f"🔍 多单止损: 卖出 {amount} 张，触发价 ${trigger_price:.2f}")
                    order = self.exchange.create_order(
                        symbol, 'limit', 'sell', amount, trigger_price, params
                    )
                else:
                    # 空单止损 = 向上触发，买入平仓
                    print(f"🔍 空单止损: 买入 {amount} 张，触发价 ${trigger_price:.2f}")
                    order = self.exchange.create_order(
                        symbol, 'limit', 'buy', amount, trigger_price, params
                    )
            except Exception as e1:
                error_msg = str(e1)
                # 如果是posSide参数错误，说明是单向持仓模式
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"🔄 检测到单向持仓模式，重试不带posSide参数...")
                    # 单向持仓模式：不传posSide参数
                    params = {
                        'tdMode': 'cross',
                        'ordType': 'conditional',
                        'slTriggerPx': str(trigger_price),
                        'slOrdPx': str(trigger_price),
                        'reduceOnly': True,
                    }
                    
                    if side == 'long':
                        order = self.exchange.create_order(
                            symbol, 'limit', 'sell', amount, trigger_price, params
                        )
                    else:
                        order = self.exchange.create_order(
                            symbol, 'limit', 'buy', amount, trigger_price, params
                        )
                else:
                    # 其他错误，继续抛出
                    raise e1
            
            print(f"✅ 止损单设置成功（条件单）: {symbol}, 触发价: ${trigger_price:.2f}, 订单ID: {order['id']}")
            return order
            
        except Exception as e:
            print(f"❌ 设置止损单失败 ({symbol}): {e}")
            print(f"   详细错误信息: {str(e)}")
            return None
    
    def set_take_profit(self, symbol, side, trigger_price, amount):
        """设置止盈单（Post-Only限价单）
        
        Args:
            symbol: 交易对符号
            side: 持仓方向
            trigger_price: 触发价格
            amount: 数量
        
        Returns:
            dict: 订单信息
        """
        if self.test_mode:
            print(f"🧪 【测试模式】模拟设置止盈: {symbol}, 触发价: {trigger_price}")
            return {'id': 'TEST_TP', 'status': 'simulated'}
        
        try:
            # 🔴 使用OKX条件单（真正的止盈单）
            # 先尝试双向持仓模式（带posSide参数）
            params = {
                'tdMode': 'cross',
                'ordType': 'conditional',  # ✅ 条件单（真正的止盈单）
                'tpTriggerPx': str(trigger_price),  # 止盈触发价
                'tpOrdPx': str(trigger_price),  # 止盈委托价（触发后以此价格执行）
                'reduceOnly': True,
                'posSide': 'long' if side == 'long' else 'short',  # 明确指定仓位方向
            }
            
            try:
                if side == 'long':
                    # 多单止盈 = 向上触发，卖出平仓
                    order = self.exchange.create_order(
                        symbol, 'limit', 'sell', amount, trigger_price, params
                    )
                else:
                    # 空单止盈 = 向下触发，买入平仓
                    order = self.exchange.create_order(
                        symbol, 'limit', 'buy', amount, trigger_price, params
                    )
            except Exception as e1:
                error_msg = str(e1)
                # 如果是posSide参数错误，说明是单向持仓模式
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"🔄 检测到单向持仓模式，重试不带posSide参数...")
                    # 单向持仓模式：不传posSide参数
                    params = {
                        'tdMode': 'cross',
                        'ordType': 'conditional',
                        'tpTriggerPx': str(trigger_price),
                        'tpOrdPx': str(trigger_price),
                        'reduceOnly': True,
                    }
                    
                    if side == 'long':
                        order = self.exchange.create_order(
                            symbol, 'limit', 'sell', amount, trigger_price, params
                        )
                    else:
                        order = self.exchange.create_order(
                            symbol, 'limit', 'buy', amount, trigger_price, params
                        )
                else:
                    # 其他错误，继续抛出
                    raise e1
            
            print(f"✅ 止盈单设置成功（条件单）: {symbol}, 触发价: ${trigger_price:.2f}, 订单ID: {order['id']}")
            return order
            
        except Exception as e:
            print(f"❌ 设置止盈单失败 ({symbol}): {e}")
            print(f"   详细错误信息: {str(e)}")
            return None
    
    def update_stop_loss(self, symbol, side, new_trigger_price, amount):
        """更新止损单（先限价尝试→失败回退条件单，成功后再撤旧单；含保护性市价平仓）
        
        Args:
            symbol: 交易对符号
            side: 持仓方向
            new_trigger_price: 新止损价格
            amount: 数量
        
        Returns:
            dict: 新订单信息
        """
        if self.test_mode:
            print(f"🧪 【测试模式】模拟更新止损: {symbol}, 新触发价: {new_trigger_price}")
            return {'id': 'TEST_SL_NEW', 'status': 'simulated'}
        
        try:
            old_order_id = getattr(self, 'stop_loss_order_id', None)
            old_price = getattr(self, 'stop_loss_price', None)

            # 1) 先尝试挂“限价止损单”（reduceOnly，按方向选择买/卖）
            print(f"🔄 尝试限价更新止损: 价格=${new_trigger_price:.2f}，数量={amount} 张")
            new_order = None
            limit_params = {
                'tdMode': 'cross',
                'reduceOnly': True,
            }
            try:
                # 优先尝试带 posSide（双向持仓）
                limit_params_with_pos = dict(limit_params)
                limit_params_with_pos['posSide'] = 'long' if side == 'long' else 'short'
                if side == 'long':
                    # 多仓止损：卖出限价单
                    new_order = self.exchange.create_limit_sell_order(symbol, amount, new_trigger_price, limit_params_with_pos)
                else:
                    # 空仓止损：买入限价单
                    new_order = self.exchange.create_limit_buy_order(symbol, amount, new_trigger_price, limit_params_with_pos)
            except Exception as e_limit_pos:
                msg = str(e_limit_pos)
                if '51000' in msg or 'posSide' in msg:
                    print(f"🔄 检测到单向持仓模式，改为不带posSide限价下单重试...")
                    try:
                        if side == 'long':
                            new_order = self.exchange.create_limit_sell_order(symbol, amount, new_trigger_price, limit_params)
                        else:
                            new_order = self.exchange.create_limit_buy_order(symbol, amount, new_trigger_price, limit_params)
                    except Exception as e_limit_plain:
                        print(f"⚠️ 限价止损下单失败，将回退为条件单: {e_limit_plain}")
                else:
                    print(f"⚠️ 限价止损下单失败，将回退为条件单: {e_limit_pos}")

            # 2) 若限价失败，回退到“条件单”，触发价与委托价价差=0.1%
            if not new_order:
                gap_ratio = 0.001  # 0.1%
                if side == 'long':
                    trigger_px = float(new_trigger_price) * (1 + gap_ratio)
                else:
                    trigger_px = float(new_trigger_price) * (1 - gap_ratio)
                trigger_px = float(f"{trigger_px:.6f}")

                print(f"🔁 回退为条件单: 触发价=${trigger_px:.4f}, 委托价=${new_trigger_price:.2f}, 差值=0.1%")
                # 复用 set_stop_loss，并传入委托价=新止损价（该方法内部默认用触发=委托；这里重写params）
                params = {
                    'tdMode': 'cross',
                    'ordType': 'conditional',
                    'slTriggerPx': str(trigger_px),
                    'slOrdPx': str(new_trigger_price),
                    'reduceOnly': True,
                }
                try:
                    params_pos = dict(params)
                    params_pos['posSide'] = 'long' if side == 'long' else 'short'
                    if side == 'long':
                        new_order = self.exchange.create_order(symbol, 'limit', 'sell', amount, new_trigger_price, params_pos)
                    else:
                        new_order = self.exchange.create_order(symbol, 'limit', 'buy', amount, new_trigger_price, params_pos)
                except Exception as e_cond_pos:
                    msg = str(e_cond_pos)
                    if '51000' in msg or 'posSide' in msg:
                        print(f"🔄 条件单检测到单向持仓模式，改为不带posSide重试...")
                        if side == 'long':
                            new_order = self.exchange.create_order(symbol, 'limit', 'sell', amount, new_trigger_price, params)
                        else:
                            new_order = self.exchange.create_order(symbol, 'limit', 'buy', amount, new_trigger_price, params)
                    else:
                        raise

            if not new_order:
                print(f"❌ 新止损单创建失败（限价与条件单均失败）")
                return None

            print(f"✅ 新止损单创建成功: 订单ID={new_order.get('id')}, 价格=${new_trigger_price:.2f}")

            # 3) 保护性检查：若当前价已触发止损阈值，且仍有对应持仓，则立即市价平仓
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                last_price = float(ticker.get('last') or ticker.get('close') or 0)
                print(f"🔍 保护性检查：当前价=${last_price:.2f}, 止损价=${new_trigger_price:.2f}")
                should_close = False
                if side == 'long' and last_price <= float(new_trigger_price):
                    should_close = True
                if side == 'short' and last_price >= float(new_trigger_price):
                    should_close = True
                if should_close:
                    pos = self.get_position(symbol)
                    has_pos = pos is not None and pos.get('side') in ['long', 'short'] and float(pos.get('contracts', 0)) > 0
                    if has_pos:
                        print(f"🚨 保护性触发：立即市价平{pos.get('side')}，数量={amount} 张")
                        market_params = {'tdMode': 'cross', 'reduceOnly': True}
                        try:
                            market_params_pos = dict(market_params)
                            market_params_pos['posSide'] = pos.get('side')
                            if pos.get('side') == 'long':
                                self.exchange.create_market_sell_order(symbol, amount, market_params_pos)
                            else:
                                self.exchange.create_market_buy_order(symbol, amount, market_params_pos)
                        except Exception as e_market_pos:
                            msg = str(e_market_pos)
                            if '51000' in msg or 'posSide' in msg:
                                print(f"🔄 市价平仓检测到单向模式，改为不带posSide重试...")
                                if pos.get('side') == 'long':
                                    self.exchange.create_market_sell_order(symbol, amount, market_params)
                                else:
                                    self.exchange.create_market_buy_order(symbol, amount, market_params)
                        print(f"✅ 保护性市价平仓已提交")
            except Exception as e_protect:
                print(f"⚠️ 保护性检查/平仓异常: {e}")

            # 4) 新单已成功 → 更新内存记录（仅此时更新）
            try:
                self.stop_loss_order_id = new_order.get('id')
                self.stop_loss_price = float(new_trigger_price)
                print(f"🆔 已更新止损记录: id={self.stop_loss_order_id}, price=${self.stop_loss_price:.2f}")
            except Exception:
                pass

            # 5) 撤销旧止损单（若存在），失败则重试最多3次；3次仍失败发送钉钉提醒
            if old_order_id and old_order_id != self.stop_loss_order_id:
                print(f"🔄 开始撤销旧止损单: {old_order_id}")
                retry = 0
                canceled = False
                while retry < 3 and not canceled:
                    retry += 1
                    try:
                        if self.cancel_order(symbol, old_order_id):
                            canceled = True
                            print(f"✅ 旧止损单撤销成功 (尝试第{retry}次)")
                        else:
                            print(f"⚠️ 撤销旧止损单失败 (第{retry}次)")
                            time.sleep(0.6)
                    except Exception as e_cancel:
                        print(f"⚠️ 撤销旧止损单异常(第{retry}次): {e_cancel}")
                        time.sleep(0.6)

                if not canceled:
                    print(f"❌ 旧止损单三次撤销失败，准备发送钉钉提醒")
                    try:
                        # 若在外部已注入 ding notifier，则使用；否则忽略
                        notifier = getattr(self, 'ding_notifier', None)
                        if notifier:
                            title = "【止损撤单失败】告警"
                            content = (
                                f"### 🚨 止损撤单失败告警\n\n"
                                f"- 交易对: {symbol}\n"
                                f"- 旧止损单ID: `{old_order_id}`\n"
                                f"- 新止损单ID: `{self.stop_loss_order_id}`\n"
                                f"- 新止损价: ${float(new_trigger_price):.2f}\n"
                                f"- 尝试次数: 3 次，仍失败\n"
                                f"- 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            )
                            notifier.send_message(title, content)
                    except Exception as e_notify:
                        print(f"⚠️ 发送钉钉提醒失败: {e_notify}")

            return new_order
            
        except Exception as e:
            print(f"❌ 更新止损单失败 ({symbol}): {e}")
            return None
    
    def cancel_order(self, symbol, order_id):
        """撤销订单（支持普通订单和条件单）
        
        Args:
            symbol: 交易对符号
            order_id: 订单ID
        
        Returns:
            bool: 是否成功
        """
        if self.test_mode:
            print(f"🧪 【测试模式】模拟撤销订单: {order_id}")
            return True
        
        try:
            # 对于合约的条件单（止损止盈单），使用专门的撤销API
            print(f"🔄 撤销合约条件单: {order_id}")
            
            # 尝试使用CCXT的cancel_order方法，传递algoId参数
            # OKX的条件单撤销需要特殊处理
            try:
                # 方法1：使用cancel_order，传递stop=True标记
                result = self.exchange.cancel_order(
                    order_id, 
                    symbol,
                    params={'stop': True}  # 标记为条件单
                )
                print(f"✅ 合约条件单已撤销: {order_id}")
                print(f"   响应: {result}")
                return True
            except Exception as e1:
                print(f"⚠️  cancel_order失败: {e1}")
                print(f"   尝试使用低级API...")
                
                # 方法2：使用低级API直接调用
                # CCXT在底层会将params序列化为JSON
                params = {
                    'instId': symbol,
                    'algoId': order_id
                }
                
                response = self.exchange.privatePostTradeCancelAlgos([params])
                
                if response.get('code') == '0':
                    print(f"✅ 合约条件单已撤销: {order_id}")
                    return True
                else:
                    print(f"❌ 撤销合约条件单失败: {response.get('msg', 'Unknown error')}")
                    print(f"   响应详情: {response}")
                    return False
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ 撤销合约条件单异常: {e}")
            
            # 检查是否是"订单不存在"或"已成交"的错误
            if "51400" in error_msg or "has been filled" in error_msg or "does not exist" in error_msg:
                print(f"ℹ️  合约条件单已不存在或已成交: {order_id} (这是正常情况)")
                return True  # 视为成功，因为目标已达成
            else:
                return False
    
    def get_order_status(self, symbol, order_id):
        """获取订单状态
        
        Args:
            symbol: 交易对符号
            order_id: 订单ID
        
        Returns:
            dict: 订单状态信息
        """
        if self.test_mode:
            return {'status': 'test_mode', 'id': order_id}
        
        try:
            # 对于合约条件单，直接查询条件单状态
            params = {
                'instId': symbol,
                'algoId': order_id,
                'ordType': 'conditional'  # 添加ordType参数，指定为条件单
            }
            response = self.exchange.private_get_trade_orders_algo_pending(params)
            # 打印 response
            print(f"   查询条件单状态响应: {response}")
            if response.get('code') == '0' and response.get('data'):
                # 遍历返回的订单列表，查找指定的订单ID
                for algo_data in response['data']:
                    if algo_data.get('algoId') == order_id:
                        return {
                            'id': order_id,
                            'status': algo_data.get('state'),
                            'type': 'conditional',
                            'trigger_price': algo_data.get('slTriggerPx'),
                            'created_time': algo_data.get('cTime'),
                            'order_type': algo_data.get('ordType'),
                            'side': algo_data.get('side'),
                        }
                
                # 如果遍历完所有订单都没找到指定的订单ID
                return {'status': 'not_found', 'id': order_id, 'message': 'Order not found in pending list'}
            else:
                return {'status': 'not_found', 'id': order_id, 'response': response}
        except Exception as e:
            return {'status': 'error', 'id': order_id, 'error': str(e)}
    
    def cancel_all_stop_orders(self, symbol):
        """取消所有止损止盈单
        
        Args:
            symbol: 交易对符号
        
        Returns:
            bool: 是否成功
        """
        success = True
        
        if self.stop_loss_order_id:
            if not self.cancel_order(symbol, self.stop_loss_order_id):
                success = False
            self.stop_loss_order_id = None
        
        if self.take_profit_order_id:
            if not self.cancel_order(symbol, self.take_profit_order_id):
                success = False
            self.take_profit_order_id = None
        
        return success
    
    def cancel_stop_orders_by_position_side(self, symbol, position_side, db_service=None):
        """根据持仓方向取消对应的止损止盈单
        
        Args:
            symbol: 交易对符号
            position_side: 持仓方向 ('long' 或 'short')
            db_service: 数据库服务实例（可选）
        
        Returns:
            bool: 是否成功
        """
        if not db_service:
            print(f"⚠️  未提供数据库服务，无法查询特定方向的订单")
            return False
        
        try:
            print(f"🔍 查询 {position_side} 方向的止损止盈单...")
            
            # 从数据库查询该方向的活跃订单
            session = db_service.get_session()
            try:
                from trading_database_models import OKXStopOrder
                
                active_orders = session.query(OKXStopOrder).filter_by(
                    symbol=symbol,
                    position_side=position_side,
                    status='active'
                ).all()
                
                if not active_orders:
                    print(f"✅ 没有找到 {position_side} 方向的活跃订单")
                    return True
                
                print(f"📋 找到 {len(active_orders)} 个 {position_side} 方向的活跃订单")
                
                success = True
                for order in active_orders:
                    order_id = order.order_id
                    order_type = order.order_type
                    
                    print(f"🔄 撤销 {order_type} 订单: {order_id}")
                    
                    try:
                        cancel_result = self.cancel_order(symbol, order_id)
                        if cancel_result:
                            print(f"✅ 已撤销 {order_type} 订单: {order_id}")
                            
                            # 更新数据库状态
                            order.status = 'canceled'
                            order.canceled_at = datetime.now()
                            session.commit()
                        else:
                            print(f"⚠️  撤销 {order_type} 订单失败: {order_id}")
                            success = False
                    except Exception as e:
                        print(f"❌ 撤销 {order_type} 订单异常: {e}")
                        success = False
                
                return success
                
            finally:
                db_service.close_session(session)
                
        except Exception as e:
            print(f"❌ 查询/撤销 {position_side} 方向订单失败: {e}")
            return False
    
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
    
    def get_position(self, symbol):
        """获取当前持仓"""
        try:
            positions = self.exchange.fetch_positions([symbol])
            for pos in positions:
                if pos['symbol'] == symbol and abs(float(pos['contracts'])) > 0:
                    return {
                        'side': pos['side'],
                        'contracts': float(pos['contracts']),
                        'entry_price': float(pos['entryPrice']),
                        'unrealized_pnl': float(pos['unrealizedPnl']),
                        'leverage': float(pos['leverage']),
                    }
            return None
        except Exception as e:
            print(f"❌ 获取持仓失败 ({symbol}): {e}")
            return None
    
    def set_leverage(self, symbol, leverage, margin_mode='cross'):
        """设置杠杆倍数"""
        if self.test_mode:
            print(f"🧪 【测试模式】模拟设置杠杆: {symbol}, {leverage}x, {margin_mode}")
            return True
        
        try:
            params = {
                'instId': symbol,
                'lever': str(leverage),
                'mgnMode': margin_mode,
            }
            
            response = self.exchange.private_post_account_set_leverage(params)
            
            if response.get('code') == '0':
                print(f"✅ 杠杆设置成功: {symbol}, {leverage}x, {margin_mode}模式")
                self.leverage = leverage
                return True
            else:
                print(f"❌ 杠杆设置失败: {response.get('msg', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"❌ 设置杠杆失败 ({symbol}): {e}")
            return False
    
    def get_account_info(self):
        """获取账户信息"""
        try:
            balance = self.get_balance()
            
            account_info = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'balance': balance,
                'mode': TRADING_CONFIG['mode'],
                'test_mode': self.test_mode
            }
            
            return account_info
        except Exception as e:
            print(f"❌ 获取账户信息失败: {e}")
            return None

