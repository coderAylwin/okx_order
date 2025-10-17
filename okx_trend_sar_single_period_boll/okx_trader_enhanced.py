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
        
        # 计算仓位价值 = 保证金 × 杠杆
        position_value = usdt_amount * leverage
        
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
        print(f"   保证金: ${usdt_amount:.2f}")
        print(f"   杠杆: {leverage}x")
        print(f"   仓位价值: ${position_value:.2f} (保证金 × 杠杆)")
        print(f"   当前价格: ${current_price:.2f}")
        print(f"   合约规格: {contract_size} 币/张")
        print(f"   最小下单: {min_size} 张")
        print(f"   理论张数: {coin_amount / contract_size:.4f}")
        print(f"   实际下单: {contract_amount} 张")
        print(f"   实际仓位价值: ${actual_position_value:.2f}")
        print(f"   实际所需保证金: ${required_margin:.2f}")
        
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
            # 1. 开仓
            entry_order = self.exchange.create_market_buy_order(symbol, amount)
            result['entry_order'] = entry_order
            print(f"✅ 开多单成功: {symbol}, 数量: {amount}, 订单ID: {entry_order['id']}")
            
            # 2. 设置止损单
            if stop_loss_price:
                sl_order = self.set_stop_loss(symbol, 'long', stop_loss_price, amount)
                result['stop_loss_order'] = sl_order
                self.stop_loss_order_id = sl_order['id'] if sl_order else None
            
            # 3. 设置止盈单
            if take_profit_price:
                tp_order = self.set_take_profit(symbol, 'long', take_profit_price, amount)
                result['take_profit_order'] = tp_order
                self.take_profit_order_id = tp_order['id'] if tp_order else None
            
            return result
            
        except Exception as e:
            print(f"❌ 开多单失败 ({symbol}): {e}")
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
            # 1. 开仓
            entry_order = self.exchange.create_market_sell_order(symbol, amount)
            result['entry_order'] = entry_order
            print(f"✅ 开空单成功: {symbol}, 数量: {amount}, 订单ID: {entry_order['id']}")
            
            # 2. 设置止损单
            if stop_loss_price:
                sl_order = self.set_stop_loss(symbol, 'short', stop_loss_price, amount)
                result['stop_loss_order'] = sl_order
                self.stop_loss_order_id = sl_order['id'] if sl_order else None
            
            # 3. 设置止盈单
            if take_profit_price:
                tp_order = self.set_take_profit(symbol, 'short', take_profit_price, amount)
                result['take_profit_order'] = tp_order
                self.take_profit_order_id = tp_order['id'] if tp_order else None
            
            return result
            
        except Exception as e:
            print(f"❌ 开空单失败 ({symbol}): {e}")
            return result
    
    def set_stop_loss(self, symbol, side, trigger_price, amount):
        """设置止损单（条件单）
        
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
            # OKX 条件单参数
            # 参考: https://www.okx.com/docs-v5/en/#order-book-trading-algo-trading-post-place-algo-order
            
            params = {
                'tdMode': 'cross',  # 保证金模式：cross（全仓）或 isolated（逐仓）
                'ordType': 'conditional',  # 条件单类型
                'slTriggerPx': str(trigger_price),  # 止损触发价
                'slOrdPx': str(trigger_price),  # 止损委托价（限价单，使用触发价）
                'reduceOnly': True,  # 只减仓
            }
            
            if side == 'long':
                # 多单止损 = 向下触发，卖出平仓（限价单）
                order = self.exchange.create_order(
                    symbol, 'limit', 'sell', amount, trigger_price, params
                )
            else:
                # 空单止损 = 向上触发，买入平仓（限价单）
                order = self.exchange.create_order(
                    symbol, 'limit', 'buy', amount, trigger_price, params
                )
            
            print(f"✅ 止损单设置成功（限价）: {symbol}, 触发价: {trigger_price}, 订单ID: {order['id']}")
            return order
            
        except Exception as e:
            print(f"❌ 设置止损单失败 ({symbol}): {e}")
            return None
    
    def set_take_profit(self, symbol, side, trigger_price, amount):
        """设置止盈单（条件单）
        
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
            params = {
                'tdMode': 'cross',
                'ordType': 'conditional',
                'tpTriggerPx': str(trigger_price),  # 止盈触发价
                'tpOrdPx': str(trigger_price),  # 止盈委托价（限价单，使用触发价）
                'reduceOnly': True,
            }
            
            if side == 'long':
                # 多单止盈 = 向上触发，卖出平仓（限价单）
                order = self.exchange.create_order(
                    symbol, 'limit', 'sell', amount, trigger_price, params
                )
            else:
                # 空单止盈 = 向下触发，买入平仓（限价单）
                order = self.exchange.create_order(
                    symbol, 'limit', 'buy', amount, trigger_price, params
                )
            
            print(f"✅ 止盈单设置成功（限价）: {symbol}, 触发价: {trigger_price}, 订单ID: {order['id']}")
            return order
            
        except Exception as e:
            print(f"❌ 设置止盈单失败 ({symbol}): {e}")
            return None
    
    def update_stop_loss(self, symbol, side, new_trigger_price, amount):
        """更新止损单（撤销旧单，挂新单）
        
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
            # 1. 撤销旧止损单（如果存在）
            if self.stop_loss_order_id:
                print(f"🔄 检查旧止损单状态: {self.stop_loss_order_id}")
                order_status = self.get_order_status(symbol, self.stop_loss_order_id)
                print(f"   订单状态: {order_status.get('status', 'unknown')}")
                
                print(f"🔄 尝试撤销旧止损单: {self.stop_loss_order_id}")
                cancel_result = self.cancel_order(symbol, self.stop_loss_order_id)
                # 无论撤销成功与否，都继续执行挂新单
            
            # 2. 挂新止损单
            new_order = self.set_stop_loss(symbol, side, new_trigger_price, amount)
            if new_order:
                self.stop_loss_order_id = new_order['id']
                print(f"✅ 止损单已更新: ${new_trigger_price:.2f} (新订单ID: {new_order['id']})")
            
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
            }
            response = self.exchange.private_get_trade_orders_algo_pending(params)
            
            if response.get('code') == '0' and response.get('data'):
                algo_data = response['data'][0]
                return {
                    'id': order_id,
                    'status': algo_data.get('state'),
                    'type': 'conditional',
                    'trigger_price': algo_data.get('slTriggerPx'),
                    'created_time': algo_data.get('cTime'),
                    'order_type': algo_data.get('ordType'),
                    'side': algo_data.get('side'),
                }
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

