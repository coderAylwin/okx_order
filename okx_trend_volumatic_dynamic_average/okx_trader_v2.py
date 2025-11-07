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
            # 🔴 兼容旧配置键名（api_key → apiKey）
            api_config = dict(OKX_API_CONFIG)
            if 'api_key' in api_config and 'apiKey' not in api_config:
                api_config['apiKey'] = api_config.pop('api_key')
            self.exchange = ccxt.okx(api_config)
            
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
            raise
        
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
        # 🔴 监听待优化的开仓条件单
        self.pending_entry_orders = {}  # {symbol: {'direction': 'long'/'short', 'limit_price': 158.64, 'amount': 1, 'conditional_order_id': 'xxx', 'stop_loss_price': xxx, 'take_profit_price': xxx}}
    
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
            
            # 🔴 尝试多种symbol格式匹配
            symbol_variants = [
                symbol,  # 原始格式，如 SOL-USDT-SWAP
                symbol.replace('-', '/'),  # SOL/USDT:SWAP
                symbol.replace('-USDT-SWAP', '/USDT:SWAP'),  # SOL/USDT:SWAP
            ]
            
            market = None
            for sym_variant in symbol_variants:
                if sym_variant in markets:
                    market = markets[sym_variant]
                    print(f"   ✅ 找到市场信息: {sym_variant}")
                    break
            
            if market:
                contract_size = market.get('contractSize', 0.1)
                limits = market.get('limits', {})
                amount_limits = limits.get('amount', {})
                min_size = amount_limits.get('min', 0.01)
                
                print(f"   📊 合约规格: {contract_size} SOL/张, 最小下单量: {min_size} 张")
                return contract_size, min_size
            else:
                print(f"⚠️  未找到 {symbol} 的市场信息（已尝试: {symbol_variants}），使用默认值 0.1 SOL/张")
                print(f"   💡 如果持续出现保证金不足错误，请检查合约规格是否正确")
                return 0.1, 0.01
        except Exception as e:
            print(f"❌ 获取合约规格失败: {e}")
            return 0.1, 0.01
    
    def calculate_contract_amount(self, symbol, usdt_amount, current_price, leverage=None):
        """计算可以购买的合约张数
        
        注意：计算出的合约数量，实际所需保证金不能超过输入的 usdt_amount
        """
        if leverage is None:
            leverage = self.leverage
        
        contract_size, min_size = self.get_contract_size(symbol)
        
        # 🔴 安全保证金：95%缓冲（但最终验证时要用原始 usdt_amount）
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
        
        # 🔴 验证：计算实际所需保证金，确保不超过输入的 usdt_amount
        actual_coin_amount = contract_amount * contract_size  # 实际币数量
        actual_position_value = actual_coin_amount * current_price  # 实际持仓价值
        actual_required_margin = actual_position_value / leverage  # 实际所需保证金
        
        # 🔴 如果实际所需保证金超过输入金额，向下调整合约数量
        if actual_required_margin > usdt_amount:
            print(f"   ⚠️  警告：计算出的合约数量需要保证金${actual_required_margin:.2f}，超过输入金额${usdt_amount:.2f}")
            print(f"   🔄 向下调整合约数量...")
            
            # 反向计算：从可用保证金反推最大合约数量
            max_position_value = usdt_amount * leverage  # 最大持仓价值
            max_coin_amount = max_position_value / current_price  # 最大币数量
            max_contract_amount = max_coin_amount / contract_size  # 最大合约张数
            
            # 根据最小下单量向下取整
            if max_contract_amount < min_size:
                contract_amount = min_size
            else:
                if min_size >= 1:
                    contract_amount = int(max_contract_amount)
                elif min_size >= 0.1:
                    contract_amount = int(max_contract_amount * 10) / 10
                elif min_size >= 0.01:
                    contract_amount = int(max_contract_amount * 100) / 100
                else:
                    contract_amount = round(max_contract_amount, 4)
            
            # 重新计算实际所需保证金
            actual_coin_amount = contract_amount * contract_size
            actual_position_value = actual_coin_amount * current_price
            actual_required_margin = actual_position_value / leverage
            
            print(f"   ✅ 调整后合约数量: {contract_amount} 张")
            print(f"   ✅ 调整后所需保证金: ${actual_required_margin:.2f} (≤ 输入金额${usdt_amount:.2f})")
        
        # 🔴 详细的计算过程日志
        print(f"\n   📊 【合约数量计算详情】")
        print(f"      输入保证金: ${usdt_amount:.2f}")
        print(f"      安全保证金(95%): ${safe_margin:.2f} (${usdt_amount:.2f} × 95%)")
        print(f"      理论持仓价值: ${position_value:.2f} (安全保证金${safe_margin:.2f} × {leverage}倍杠杆)")
        print(f"      理论币数量: {coin_amount:.4f} SOL (理论持仓价值${position_value:.2f} ÷ 价格${current_price:.2f})")
        print(f"      合约规格: {contract_size} SOL/张")
        print(f"      最终合约张数: {contract_amount} 张")
        print(f"      实际币数量: {actual_coin_amount:.4f} SOL (数量{contract_amount} × 规格{contract_size})")
        print(f"      实际持仓价值: ${actual_position_value:.2f} (币数量{actual_coin_amount:.4f} × 价格${current_price:.2f})")
        print(f"      实际所需保证金: ${actual_required_margin:.2f} (持仓价值${actual_position_value:.2f} ÷ {leverage}倍杠杆)")
        if actual_required_margin <= usdt_amount:
            print(f"      ✅ 验证通过: 所需保证金${actual_required_margin:.2f} ≤ 输入金额${usdt_amount:.2f}")
        else:
            print(f"      ⚠️  警告: 所需保证金${actual_required_margin:.2f} > 输入金额${usdt_amount:.2f} (可能因为最小下单量限制)")
        print(f"   {'-'*60}\n")
        
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
                
                # 🔴 检测到保证金不足错误，停止重试
                if isinstance(entry_order, dict) and entry_order.get('error') == 'insufficient_margin':
                    print(f"\n❌ 保证金不足，停止开仓")
                    print(f"   错误: {entry_order.get('message', 'Unknown')}")
                    break  # 停止循环
                
                # 🔴 如果买3会立即成交，尝试买4/买5
                if not entry_order:
                    print(f"   💡 买3价已穿过，尝试买4价...")
                    bid4 = self._get_bid_price(symbol, level=4)
                    if bid4:
                        print(f"   买4价: ${bid4:.2f}")
                        entry_order = self._place_limit_order(symbol, 'buy', amount, bid4, timeout=10)
                        
                        # 🔴 检测到保证金不足错误，停止重试
                        if isinstance(entry_order, dict) and entry_order.get('error') == 'insufficient_margin':
                            print(f"\n❌ 保证金不足，停止开仓")
                            print(f"   错误: {entry_order.get('message', 'Unknown')}")
                            break  # 停止循环
                    
                    if not entry_order:
                        print(f"   💡 买4价已穿过，尝试买5价...")
                        bid5 = self._get_bid_price(symbol, level=5)
                        if bid5:
                            print(f"   买5价: ${bid5:.2f}")
                            entry_order = self._place_limit_order(symbol, 'buy', amount, bid5, timeout=10)
                            
                            # 🔴 检测到保证金不足错误，停止重试
                            if isinstance(entry_order, dict) and entry_order.get('error') == 'insufficient_margin':
                                print(f"\n❌ 保证金不足，停止开仓")
                                print(f"   错误: {entry_order.get('message', 'Unknown')}")
                                break  # 停止循环
            
            # 如果还没成交，等待一小段时间再重试（但如果是保证金不足，已经break了）
            if not entry_order and attempt < max_attempts:
                # 🔴 检查是否是保证金不足导致的停止
                if isinstance(entry_order, dict) and entry_order.get('error') == 'insufficient_margin':
                    break  # 已经break了，这里不会执行
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
        
        # 🔴 不立即挂止损止盈单，等待开仓成交后再挂
        # 止损止盈价格会在开仓成交后通过定时检查机制挂单
        print(f"   💡 止损止盈单将在开仓成交后自动挂单")
        print(f"   📝 止损价格: ${stop_loss_price:.2f}" if stop_loss_price else "   📝 止损价格: 未设置")
        print(f"   📝 止盈价格: ${take_profit_price:.2f}" if take_profit_price else "   📝 止盈价格: 未设置")
        
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
        
        # 🔴 不立即挂止损止盈单，等待开仓成交后再挂
        # 止损止盈价格会在开仓成交后通过定时检查机制挂单
        print(f"   💡 止损止盈单将在开仓成交后自动挂单")
        print(f"   📝 止损价格: ${stop_loss_price:.2f}" if stop_loss_price else "   📝 止损价格: 未设置")
        print(f"   📝 止盈价格: ${take_profit_price:.2f}" if take_profit_price else "   📝 止盈价格: 未设置")
        
        print(f"{'='*60}\n")
        return result
    
    def _try_place_limit_order_immediately(self, symbol, side, amount, price):
        """
        立即尝试挂限价单（不等待成交，只检查是否能挂单）
        
        Args:
            symbol: 交易对
            side: 'buy' 或 'sell'
            amount: 合约张数（需要转换为币数量）
            price: 价格
        
        Returns:
            dict: 订单信息（如果成功），或 None（如果失败）
        """
        try:
            # 🔴 将合约张数转换为币数量（OKX API 需要币数量，而不是合约张数）
            contract_size, _ = self.get_contract_size(symbol)
            coin_amount = float(amount) * contract_size  # 币数量 = 合约张数 × 合约规格
            # 保留两位小数（OKX 要求）
            coin_amount = round(coin_amount, 2)
            
            # 检查是否会立即成交
            ticker = self.exchange.fetch_ticker(symbol)
            
            if side == 'buy':
                best_ask = ticker.get('ask', ticker['last'])
                if price >= best_ask:
                    print(f"   ⚠️  限价单会立即成交 (限价${price:.2f} >= 卖一${best_ask:.2f})")
                    print(f"   💡 无法挂限价单，将使用条件单")
                    return None
            else:
                best_bid = ticker.get('bid', ticker['last'])
                if price <= best_bid:
                    print(f"   ⚠️  限价单会立即成交 (限价${price:.2f} <= 买一${best_bid:.2f})")
                    print(f"   💡 无法挂限价单，将使用条件单")
                    return None
            
            # 尝试挂限价单（使用Post-Only，如果会立即成交会被拒绝）
            params = {
                'postOnly': True  # 只做Maker
            }
            
            if side == 'buy':
                params['posSide'] = 'long'
            else:
                params['posSide'] = 'short'
            
            # 🔴 打印详细的挂单参数
            print(f"\n   📋 【挂单参数详情】")
            print(f"      Symbol: {symbol}")
            print(f"      Side: {side}")
            print(f"      合约张数: {amount} 张")
            print(f"      合约规格: {contract_size} SOL/张")
            print(f"      币数量: {coin_amount} SOL (合约张数{amount} × 规格{contract_size})")
            print(f"      Price: ${price:.2f}")
            print(f"      Params: {params}")
            
            # 获取账户余额信息
            try:
                balance_info = self.get_balance()
                if balance_info:
                    print(f"      💰 账户余额: 总余额=${balance_info.get('total', 0):.2f}, 可用=${balance_info.get('free', 0):.2f}, 已用=${balance_info.get('used', 0):.2f}")
                
                # 🔴 计算需要的保证金
                leverage = getattr(self, 'leverage', TRADING_CONFIG.get('leverage', 1))
                position_value = coin_amount * price  # 实际持仓价值（币数量 × 价格）
                required_margin = position_value / leverage  # 所需保证金（持仓价值 ÷ 杠杆）
                
                print(f"      💰 持仓价值: ${position_value:.2f} (币数量{coin_amount} × 价格${price:.2f})")
                print(f"      💰 所需保证金: ${required_margin:.2f} (持仓价值${position_value:.2f} ÷ {leverage}倍杠杆)")
                if balance_info:
                    free_balance = balance_info.get('free', 0)
                    if free_balance < required_margin:
                        print(f"      ⚠️  可用余额不足: 需要${required_margin:.2f}, 可用${free_balance:.2f}, 差额=${required_margin - free_balance:.2f}")
                    else:
                        print(f"      ✅ 可用余额充足: 需要${required_margin:.2f}, 可用${free_balance:.2f}, 剩余=${free_balance - required_margin:.2f}")
            except Exception as e:
                print(f"      ⚠️  获取账户信息失败: {e}")
            
            print(f"   {'-'*60}\n")
            
            try:
                # 🔴 使用币数量而不是合约张数
                print(f"\n   📤 【OKX API调用详情】")
                print(f"      CCXT方法: create_limit_order")
                print(f"      参数:")
                print(f"         symbol: {symbol}")
                print(f"         side: {side}")
                print(f"         amount: {coin_amount} (币数量，类型: {type(coin_amount).__name__})")
                print(f"         price: {price} (类型: {type(price).__name__})")
                print(f"         params: {params}")
                print(f"      📊 计算过程:")
                print(f"         - 合约张数(输入): {amount} 张")
                print(f"         - 合约规格: {contract_size} SOL/张")
                print(f"         - 币数量(计算): {coin_amount} SOL = {amount} × {contract_size}")
                print(f"         - 价格: ${price:.2f}")
                print(f"      📋 CCXT可能转换为OKX API:")
                print(f"         POST /api/v5/trade/order")
                print(f"         请求体可能包含:")
                print(f"           - instId: {symbol}")
                print(f"           - tdMode: cross (全仓)")
                print(f"           - side: {side}")
                print(f"           - ordType: limit")
                print(f"           - sz: {coin_amount} (币数量)")
                print(f"           - px: {price}")
                print(f"           - posSide: {params.get('posSide', 'None')}")
                print(f"           - postOnly: {params.get('postOnly', False)}")
                print(f"   {'='*60}\n")
                
                order = self.exchange.create_limit_order(symbol, side, coin_amount, price, params)
                
                print(f"   ✅ API调用成功，返回订单ID: {order.get('id', 'N/A')}")
            except Exception as e1:
                error_msg = str(e1)
                print(f"\n   ❌ API调用失败: {error_msg}")
                print(f"   📋 错误详情: {type(e1).__name__}: {str(e1)}")
                
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"   🔄 检测到单向持仓模式，重试不带posSide...")
                    retry_params = params.copy()
                    del retry_params['posSide']
                    
                    print(f"\n   📤 【OKX API重试调用详情】")
                    print(f"      方法: create_limit_order")
                    print(f"      symbol: {symbol}")
                    print(f"      side: {side}")
                    print(f"      amount: {coin_amount} (币数量)")
                    print(f"      price: {price}")
                    print(f"      params: {retry_params} (已移除posSide)")
                    print(f"   {'='*60}\n")
                    
                    # 🔴 重试时也使用币数量，不是合约张数
                    order = self.exchange.create_limit_order(symbol, side, coin_amount, price, retry_params)
                    print(f"   ✅ 重试成功，返回订单ID: {order.get('id', 'N/A')}")
                elif '51008' in error_msg or 'post_only' in error_msg.lower() or 'Post only' in error_msg:
                    print(f"   ⚠️  Post-Only被拒绝（订单会立即成交）")
                    print(f"   💡 无法挂限价单，将使用条件单")
                    return None
                else:
                    raise e1
            
            # 立即检查订单状态
            try:
                order_status = self.exchange.fetch_order(order['id'], symbol)
                status = order_status.get('status', 'unknown')
                
                if status == 'closed':
                    print(f"   ⚠️  限价单已成交！成交价: ${order_status.get('average', 'unknown')}")
                    return order_status
                elif status == 'canceled':
                    print(f"   ⚠️  Post-Only限价单被系统撤销")
                    print(f"   💡 无法挂限价单，将使用条件单")
                    return None
                else:
                    print(f"   ✅ 限价单已挂: ID={order['id']}, 状态={status}")
                    return order_status
                    
            except Exception as e:
                print(f"   ⚠️  检查订单状态失败: {e}")
                # 如果无法确认状态，返回订单（可能成功）
                return order
                
        except Exception as e:
            print(f"   ❌ 挂限价单失败: {e}")
            return None
    
    def _place_limit_order(self, symbol, side, amount, price, timeout=30, check_immediate_fill=True):
        """
        下限价单并等待成交
        
        Args:
            symbol: 交易对
            side: 'buy' 或 'sell'
            amount: 合约张数（需要转换为币数量）
            price: 价格
            timeout: 超时时间（秒）
            check_immediate_fill: 是否检查立即成交（开仓时True，止损止盈时False）
        
        Returns:
            dict: 成交的订单信息，或 None
        """
        try:
            # 🔴 将合约张数转换为币数量（OKX API 需要币数量，而不是合约张数）
            contract_size, _ = self.get_contract_size(symbol)
            coin_amount = float(amount) * contract_size  # 币数量 = 合约张数 × 合约规格
            # 保留两位小数（OKX 要求）
            coin_amount = round(coin_amount, 2)
            
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
                # 🔴 使用币数量而不是合约张数
                print(f"\n   📤 【OKX API调用详情】")
                print(f"      CCXT方法: create_limit_order")
                print(f"      参数:")
                print(f"         symbol: {symbol}")
                print(f"         side: {side}")
                print(f"         amount: {coin_amount} (币数量，类型: {type(coin_amount).__name__})")
                print(f"         price: {price} (类型: {type(price).__name__})")
                print(f"         params: {params}")
                print(f"      📊 计算过程:")
                print(f"         - 合约张数(输入): {amount} 张")
                print(f"         - 合约规格: {contract_size} SOL/张")
                print(f"         - 币数量(计算): {coin_amount} SOL = {amount} × {contract_size}")
                print(f"         - 价格: ${price:.2f}")
                print(f"      📋 CCXT可能转换为OKX API:")
                print(f"         POST /api/v5/trade/order")
                print(f"         请求体可能包含:")
                print(f"           - instId: {symbol}")
                print(f"           - tdMode: cross (全仓)")
                print(f"           - side: {side}")
                print(f"           - ordType: limit")
                print(f"           - sz: {coin_amount} (币数量)")
                print(f"           - px: {price}")
                print(f"           - posSide: {params.get('posSide', 'None')}")
                print(f"   {'='*60}\n")
                
                order = self.exchange.create_limit_order(symbol, side, coin_amount, price, params)
                
                print(f"   ✅ API调用成功，返回订单ID: {order.get('id', 'N/A')}")
            except Exception as e1:
                error_msg = str(e1)
                print(f"\n   ❌ API调用失败: {error_msg}")
                print(f"   📋 错误详情: {type(e1).__name__}: {str(e1)}")
                
                if '51000' in str(e1) or 'posSide' in str(e1):
                    print(f"   🔄 检测到单向持仓模式")
                    # 🔴 重试时也使用币数量
                    print(f"\n   📤 【OKX API重试调用详情】")
                    print(f"      方法: create_limit_order")
                    print(f"      symbol: {symbol}")
                    print(f"      side: {side}")
                    print(f"      amount: {coin_amount} (币数量)")
                    print(f"      price: {price}")
                    print(f"      params: {{}} (无posSide)")
                    print(f"   {'='*60}\n")
                    
                    order = self.exchange.create_limit_order(symbol, side, coin_amount, price)
                    print(f"   ✅ 重试成功，返回订单ID: {order.get('id', 'N/A')}")
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
            error_msg = str(e)
            # 🔴 检测到"保证金不足"错误，停止重试
            if '51008' in error_msg or 'Insufficient' in error_msg or 'margin' in error_msg.lower():
                print(f"   ❌ 下限价单失败: 保证金不足")
                print(f"   💡 错误信息: {error_msg}")
                print(f"   ⚠️  停止重试，请检查账户可用保证金")
                # 🔴 返回特殊标记，让上层知道是保证金不足
                return {'error': 'insufficient_margin', 'message': error_msg}
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
    
    def open_long_with_limit_price(self, symbol, amount, limit_price, stop_loss_price=None, take_profit_price=None):
        """
        在指定价格（支撑位/阻力位）挂限价单开多单
        
        策略：
        1. 先尝试在指定价格挂限价单（不等待，立即尝试）
        2. 如果限价单无法挂单，立即降级为条件单
        3. 条件单加入监听队列，价格接近时自动优化为限价单
        
        Args:
            symbol: 交易对符号
            amount: 数量
            limit_price: 限价单价格（支撑位/阻力位价格）
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
            print(f"🧪 【测试模式】模拟在限价 ${limit_price:.2f} 开多单: {symbol}, 数量: {amount}")
            result['entry_order'] = {'id': 'TEST_ENTRY_LIMIT', 'status': 'simulated'}
            return result
        
        print(f"\n{'='*60}")
        print(f"📌 在指定价格挂限价单开多单: {symbol}")
        print(f"   限价: ${limit_price:.2f}")
        print(f"{'='*60}")
        
        # 🔴 先检查当前价格与支撑位的关系
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            print(f"   📊 当前价格: ${current_price:.2f}, 支撑位: ${limit_price:.2f}")
            
            # 🔴 做多：如果当前价格 <= 支撑位，说明价格已经回调到位，可以立即开仓
            if current_price <= limit_price:
                print(f"   ✅ 当前价格${current_price:.2f}已经低于/等于支撑位${limit_price:.2f}")
                print(f"   💡 价格已回调到位，立即开仓（使用买3/买4/买5价格）")
                # 使用立即开仓模式（买3/买4/买5价格）
                entry_order_result = self.open_long_with_limit_order(
                    symbol, amount, stop_loss_price, take_profit_price
                )
                if entry_order_result.get('entry_order'):
                    print(f"{'='*60}\n")
                    return entry_order_result
                else:
                    print(f"   ⚠️  立即开仓失败，降级为条件单")
                    # 继续执行条件单逻辑
            else:
                # 当前价格 > 支撑位，需要挂限价单等待价格回调
                print(f"   📊 当前价格${current_price:.2f}高于支撑位${limit_price:.2f}")
                print(f"   💡 需要挂限价单等待价格回调到支撑位")
        except Exception as e:
            print(f"   ⚠️  获取当前价格失败: {e}")
            print(f"   💡 尝试挂限价单...")
        
        # Step 1: 当前价格高于支撑位，尝试在支撑位挂限价单（等待价格回调）
        print(f"   📊 方案1: 尝试限价单 价格=${limit_price:.2f} (Maker手续费0.02%)")
        
        # 🔴 尝试立即挂限价单（不等待成交，只检查是否能挂单）
        entry_order = self._try_place_limit_order_immediately(
            symbol, 'buy', amount, limit_price
        )
        
        if entry_order:
            print(f"\n✅ 限价单已挂: 订单ID={entry_order['id']}")
            result['entry_order'] = entry_order
            
            # 🔴 不立即挂止损止盈单，等待开仓成交后再挂
            # 止损止盈价格会在开仓成交后通过定时检查机制挂单
            print(f"   💡 止损止盈单将在开仓成交后自动挂单")
            print(f"   📝 止损价格: ${stop_loss_price:.2f}" if stop_loss_price else "   📝 止损价格: 未设置")
            print(f"   📝 止盈价格: ${take_profit_price:.2f}" if take_profit_price else "   📝 止盈价格: 未设置")
            
            print(f"{'='*60}\n")
            return result
        
        # Step 2: 限价单无法挂单，立即降级为条件单
        print(f"\n   ⚠️  限价单无法挂单，立即降级为条件单")
        print(f"   📊 方案2: 使用条件单 (触发后Maker手续费0.02%)")
        
        try:
            # 获取当前价格，计算触发价
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # 做多：当价格下跌到支撑位时触发
            # 触发价应该略高于限价（例如：限价158.64，触发价158.65）
            # 这样价格跌到158.65时触发，然后挂158.64的买单
            trigger_buffer = max(limit_price * 0.0005, 0.1)  # 0.05%或最小0.1
            actual_trigger_price = limit_price + trigger_buffer
            
            print(f"   📊 多单条件单策略:")
            print(f"      触发价: ${actual_trigger_price:.2f} (略高于限价${limit_price:.2f})")
            print(f"      挂单价: ${limit_price:.2f}")
            print(f"   💡 执行逻辑: 价格跌至${actual_trigger_price:.2f}时触发 → 挂${limit_price:.2f}的买单")
            
            # 🔴 将合约张数转换为币数量（OKX API 需要币数量）
            contract_size, _ = self.get_contract_size(symbol)
            coin_amount = float(amount) * contract_size  # 币数量 = 合约张数 × 合约规格
            coin_amount = round(coin_amount, 2)  # 保留两位小数
            
            # 🔴 使用OKX的algo_order API创建开仓条件单（计划委托）
            # 注意：这不是止损止盈条件单，而是开仓条件单
            algo_params = {
                'instId': symbol,
                'tdMode': 'cross',
                'side': 'buy',
                'ordType': 'conditional',  # 条件单类型
                'sz': str(coin_amount),  # 🔴 币数量（不是合约张数）
                'triggerPx': str(actual_trigger_price),  # 触发价
                'orderPx': str(limit_price),  # 委托价（支撑位价格）
            }
            
            # 🔴 打印条件单参数详情
            print(f"\n   📋 【条件单参数详情】")
            print(f"      Symbol: {symbol}")
            print(f"      Side: buy")
            print(f"      合约张数: {amount} 张")
            print(f"      合约规格: {contract_size} SOL/张")
            print(f"      币数量: {coin_amount} SOL (合约张数{amount} × 规格{contract_size})")
            print(f"      触发价: ${actual_trigger_price:.2f}")
            print(f"      挂单价: ${limit_price:.2f}")
            print(f"      Params: {algo_params}")
            
            # 获取账户余额信息
            try:
                balance_info = self.get_balance()
                if balance_info:
                    print(f"      💰 账户余额: 总余额=${balance_info.get('total', 0):.2f}, 可用=${balance_info.get('free', 0):.2f}, 已用=${balance_info.get('used', 0):.2f}")
                
                # 🔴 计算需要的保证金（注意：amount 已经是计算好的合约张数）
                leverage = getattr(self, 'leverage', TRADING_CONFIG.get('leverage', 1))
                
                # 获取合约规格，计算实际持仓价值
                contract_size, _ = self.get_contract_size(symbol)
                coin_amount = float(amount) * contract_size  # 实际币数量
                position_value = coin_amount * limit_price  # 实际持仓价值（币数量 × 挂单价）
                required_margin = position_value / leverage  # 所需保证金（持仓价值 ÷ 杠杆）
                
                print(f"      💰 合约张数: {amount} 张")
                print(f"      💰 合约规格: {contract_size} SOL/张")
                print(f"      💰 实际币数量: {coin_amount:.4f} SOL (数量{amount} × 规格{contract_size})")
                print(f"      💰 持仓价值: ${position_value:.2f} (币数量{coin_amount:.4f} × 挂单价${limit_price:.2f})")
                print(f"      💰 所需保证金: ${required_margin:.2f} (持仓价值${position_value:.2f} ÷ {leverage}倍杠杆)")
                if balance_info:
                    free_balance = balance_info.get('free', 0)
                    if free_balance < required_margin:
                        print(f"      ⚠️  可用余额不足: 需要${required_margin:.2f}, 可用${free_balance:.2f}, 差额=${required_margin - free_balance:.2f}")
                    else:
                        print(f"      ✅ 可用余额充足: 需要${required_margin:.2f}, 可用${free_balance:.2f}, 剩余=${free_balance - required_margin:.2f}")
            except Exception as e:
                print(f"      ⚠️  获取账户信息失败: {e}")
            
            print(f"   {'-'*60}\n")
            
            # 动态处理posSide参数
            try:
                algo_params['posSide'] = 'long'
                response = self.exchange.private_post_trade_order_algo(algo_params)
            except Exception as e1:
                error_msg = str(e1)
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"   🔄 检测到单向持仓模式，重试不带posSide...")
                    if 'posSide' in algo_params:
                        del algo_params['posSide']
                    response = self.exchange.private_post_trade_order_algo(algo_params)
                else:
                    raise e1
            
            # 检查响应
            if response.get('code') == '0' and response.get('data'):
                order_data = response['data'][0]
                conditional_order_id = order_data.get('algoId') or order_data.get('ordId')
                order = {
                    'id': conditional_order_id,
                    'status': 'open',
                    'type': 'conditional',
                    'trigger_price': actual_trigger_price,
                    'limit_price': limit_price
                }
            else:
                error_msg = response.get('msg', 'Unknown error')
                raise Exception(f"创建条件单失败: {error_msg}")
            
            conditional_order_id = order['id']
            print(f"   ✅ 条件单已设置: 触发价=${actual_trigger_price:.2f}, 挂单价=${limit_price:.2f}, ID={conditional_order_id}")
            
            result['entry_order'] = {
                'id': conditional_order_id,
                'status': 'open',
                'type': 'conditional',
                'trigger_price': actual_trigger_price,
                'limit_price': limit_price
            }
            
            # 🔴 加入监听队列，价格接近时自动优化为限价单
            self.pending_entry_orders[symbol] = {
                'conditional_order_id': conditional_order_id,
                'limit_price': limit_price,
                'amount': amount,
                'direction': 'long',
                'stop_loss_price': stop_loss_price,
                'take_profit_price': take_profit_price,
                'order_type': 'conditional'
            }
            print(f"   🔔 已加入监听队列: 价格到达 ${limit_price * 0.997:.2f} - ${limit_price * 1.003:.2f} 时优化为限价单")
            
            # 🔴 注意：条件单挂单时，止损止盈暂不设置（需要等订单成交后）
            # 止损止盈价格已保存在 pending_entry_orders 中，订单成交后会自动设置
            print(f"   ⏳ 止损止盈将在开仓订单成交后自动设置")
            
            print(f"{'='*60}\n")
            return result
            
        except Exception as e:
            print(f"   ❌ 条件单失败: {e}")
            print(f"{'='*60}\n")
            return result
    
    def open_short_with_limit_price(self, symbol, amount, limit_price, stop_loss_price=None, take_profit_price=None):
        """
        在指定价格（支撑位/阻力位）挂限价单开空单
        
        策略：
        1. 先尝试在指定价格挂限价单（不等待，立即尝试）
        2. 如果限价单无法挂单，立即降级为条件单
        3. 条件单加入监听队列，价格接近时自动优化为限价单
        
        Args:
            symbol: 交易对符号
            amount: 数量
            limit_price: 限价单价格（支撑位/阻力位价格）
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
            print(f"🧪 【测试模式】模拟在限价 ${limit_price:.2f} 开空单: {symbol}, 数量: {amount}")
            result['entry_order'] = {'id': 'TEST_ENTRY_LIMIT', 'status': 'simulated'}
            return result
        
        print(f"\n{'='*60}")
        print(f"📌 在指定价格挂限价单开空单: {symbol}")
        print(f"   限价: ${limit_price:.2f}")
        print(f"{'='*60}")
        
        # 🔴 先检查当前价格与阻力位的关系
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            print(f"   📊 当前价格: ${current_price:.2f}, 阻力位: ${limit_price:.2f}")
            
            # 🔴 做空：如果当前价格 >= 阻力位，说明价格已经反弹到位，可以立即开仓
            if current_price >= limit_price:
                print(f"   ✅ 当前价格${current_price:.2f}已经高于/等于阻力位${limit_price:.2f}")
                print(f"   💡 价格已反弹到位，立即开仓（使用卖3/卖4/卖5价格）")
                # 使用立即开仓模式（卖3/卖4/卖5价格）
                entry_order_result = self.open_short_with_limit_order(
                    symbol, amount, stop_loss_price, take_profit_price
                )
                if entry_order_result.get('entry_order'):
                    print(f"{'='*60}\n")
                    return entry_order_result
                else:
                    print(f"   ⚠️  立即开仓失败，降级为条件单")
                    # 继续执行条件单逻辑
            else:
                # 当前价格 < 阻力位，需要挂限价单等待价格反弹
                print(f"   📊 当前价格${current_price:.2f}低于阻力位${limit_price:.2f}")
                print(f"   💡 需要挂限价单等待价格反弹到阻力位")
        except Exception as e:
            print(f"   ⚠️  获取当前价格失败: {e}")
            print(f"   💡 尝试挂限价单...")
        
        # Step 1: 当前价格低于阻力位，尝试在阻力位挂限价单（等待价格反弹）
        print(f"   📊 方案1: 尝试限价单 价格=${limit_price:.2f} (Maker手续费0.02%)")
        
        # 🔴 尝试立即挂限价单（不等待成交，只检查是否能挂单）
        entry_order = self._try_place_limit_order_immediately(
            symbol, 'sell', amount, limit_price
        )
        
        if entry_order:
            print(f"\n✅ 限价单已挂: 订单ID={entry_order['id']}")
            result['entry_order'] = entry_order
            
            # 🔴 不立即挂止损止盈单，等待开仓成交后再挂
            # 止损止盈价格会在开仓成交后通过定时检查机制挂单
            print(f"   💡 止损止盈单将在开仓成交后自动挂单")
            print(f"   📝 止损价格: ${stop_loss_price:.2f}" if stop_loss_price else "   📝 止损价格: 未设置")
            print(f"   📝 止盈价格: ${take_profit_price:.2f}" if take_profit_price else "   📝 止盈价格: 未设置")
            
            print(f"{'='*60}\n")
            return result
        
        # Step 2: 限价单无法挂单，立即降级为条件单
        print(f"\n   ⚠️  限价单无法挂单，立即降级为条件单")
        print(f"   📊 方案2: 使用条件单 (触发后Maker手续费0.02%)")
        
        try:
            # 获取当前价格，计算触发价
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # 做空：当价格上涨到阻力位时触发
            # 触发价应该略低于限价（例如：限价158.64，触发价158.63）
            # 这样价格涨到158.63时触发，然后挂158.64的卖单
            trigger_buffer = max(limit_price * 0.0005, 0.1)  # 0.05%或最小0.1
            actual_trigger_price = limit_price - trigger_buffer
            
            print(f"   📊 空单条件单策略:")
            print(f"      触发价: ${actual_trigger_price:.2f} (略低于限价${limit_price:.2f})")
            print(f"      挂单价: ${limit_price:.2f}")
            print(f"   💡 执行逻辑: 价格涨至${actual_trigger_price:.2f}时触发 → 挂${limit_price:.2f}的卖单")
            
            # 🔴 将合约张数转换为币数量（OKX API 需要币数量）
            contract_size, _ = self.get_contract_size(symbol)
            coin_amount = float(amount) * contract_size  # 币数量 = 合约张数 × 合约规格
            coin_amount = round(coin_amount, 2)  # 保留两位小数
            
            # 🔴 使用OKX的algo_order API创建开仓条件单（计划委托）
            # 注意：这不是止损止盈条件单，而是开仓条件单
            algo_params = {
                'instId': symbol,
                'tdMode': 'cross',
                'side': 'sell',
                'ordType': 'conditional',  # 条件单类型
                'sz': str(coin_amount),  # 🔴 币数量（不是合约张数）
                'triggerPx': str(actual_trigger_price),  # 触发价
                'orderPx': str(limit_price),  # 委托价（阻力位价格）
            }
            
            # 🔴 打印条件单参数详情
            print(f"\n   📋 【条件单参数详情】")
            print(f"      Symbol: {symbol}")
            print(f"      Side: sell")
            print(f"      合约张数: {amount} 张")
            print(f"      合约规格: {contract_size} SOL/张")
            print(f"      币数量: {coin_amount} SOL (合约张数{amount} × 规格{contract_size})")
            print(f"      触发价: ${actual_trigger_price:.2f}")
            print(f"      挂单价: ${limit_price:.2f}")
            print(f"      Params: {algo_params}")
            
            # 获取账户余额信息
            try:
                balance_info = self.get_balance()
                if balance_info:
                    print(f"      💰 账户余额: 总余额=${balance_info.get('total', 0):.2f}, 可用=${balance_info.get('free', 0):.2f}, 已用=${balance_info.get('used', 0):.2f}")
                
                # 🔴 计算需要的保证金（注意：amount 已经是计算好的合约张数）
                leverage = getattr(self, 'leverage', TRADING_CONFIG.get('leverage', 1))
                
                # 获取合约规格，计算实际持仓价值
                contract_size, _ = self.get_contract_size(symbol)
                coin_amount = float(amount) * contract_size  # 实际币数量
                position_value = coin_amount * limit_price  # 实际持仓价值（币数量 × 挂单价）
                required_margin = position_value / leverage  # 所需保证金（持仓价值 ÷ 杠杆）
                
                print(f"      💰 合约张数: {amount} 张")
                print(f"      💰 合约规格: {contract_size} SOL/张")
                print(f"      💰 实际币数量: {coin_amount:.4f} SOL (数量{amount} × 规格{contract_size})")
                print(f"      💰 持仓价值: ${position_value:.2f} (币数量{coin_amount:.4f} × 挂单价${limit_price:.2f})")
                print(f"      💰 所需保证金: ${required_margin:.2f} (持仓价值${position_value:.2f} ÷ {leverage}倍杠杆)")
                if balance_info:
                    free_balance = balance_info.get('free', 0)
                    if free_balance < required_margin:
                        print(f"      ⚠️  可用余额不足: 需要${required_margin:.2f}, 可用${free_balance:.2f}, 差额=${required_margin - free_balance:.2f}")
                    else:
                        print(f"      ✅ 可用余额充足: 需要${required_margin:.2f}, 可用${free_balance:.2f}, 剩余=${free_balance - required_margin:.2f}")
            except Exception as e:
                print(f"      ⚠️  获取账户信息失败: {e}")
            
            print(f"   {'-'*60}\n")
            
            # 动态处理posSide参数
            try:
                algo_params['posSide'] = 'short'
                response = self.exchange.private_post_trade_order_algo(algo_params)
            except Exception as e1:
                error_msg = str(e1)
                if '51000' in error_msg or 'posSide' in error_msg:
                    print(f"   🔄 检测到单向持仓模式，重试不带posSide...")
                    if 'posSide' in algo_params:
                        del algo_params['posSide']
                    response = self.exchange.private_post_trade_order_algo(algo_params)
                else:
                    raise e1
            
            # 检查响应
            if response.get('code') == '0' and response.get('data'):
                order_data = response['data'][0]
                conditional_order_id = order_data.get('algoId') or order_data.get('ordId')
                order = {
                    'id': conditional_order_id,
                    'status': 'open',
                    'type': 'conditional',
                    'trigger_price': actual_trigger_price,
                    'limit_price': limit_price
                }
            else:
                error_msg = response.get('msg', 'Unknown error')
                raise Exception(f"创建条件单失败: {error_msg}")
            
            conditional_order_id = order['id']
            print(f"   ✅ 条件单已设置: 触发价=${actual_trigger_price:.2f}, 挂单价=${limit_price:.2f}, ID={conditional_order_id}")
            
            result['entry_order'] = {
                'id': conditional_order_id,
                'status': 'open',
                'type': 'conditional',
                'trigger_price': actual_trigger_price,
                'limit_price': limit_price
            }
            
            # 🔴 加入监听队列，价格接近时自动优化为限价单
            self.pending_entry_orders[symbol] = {
                'conditional_order_id': conditional_order_id,
                'limit_price': limit_price,
                'amount': amount,
                'direction': 'short',
                'stop_loss_price': stop_loss_price,
                'take_profit_price': take_profit_price,
                'order_type': 'conditional'
            }
            print(f"   🔔 已加入监听队列: 价格到达 ${limit_price * 0.997:.2f} - ${limit_price * 1.003:.2f} 时优化为限价单")
            
            print(f"{'='*60}\n")
            return result
            
        except Exception as e:
            print(f"   ❌ 条件单失败: {e}")
            print(f"{'='*60}\n")
            return result
    
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
    
    def check_and_optimize_entry_orders(self):
        """检查监听队列，优化开仓条件单为限价单（每10秒调用）
        
        遍历pending_entry_orders队列：
        - 检查当前价格与目标限价的差距
        - 如果 ≤ 0.3%，取消条件单，重新执行挂单逻辑（先挂限价单，失败就挂条件单）
        """
        if not self.pending_entry_orders:
            return
        
        current_time = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{current_time}] 🔍 检查待优化的开仓条件单（队列：{len(self.pending_entry_orders)}个）")
        
        for symbol, pending in list(self.pending_entry_orders.items()):
            try:
                # 获取当前价格
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                limit_price = pending['limit_price']
                
                # 计算价差百分比
                price_diff_pct = abs(current_price - limit_price) / current_price * 100
                
                print(f"   📊 {symbol}: 当前价${current_price:.2f}, 目标价${limit_price:.2f}, 价差{price_diff_pct:.2f}%")
                
                # 🔴 先检查订单是否还存在
                order_id = pending.get('conditional_order_id')
                
                if order_id:
                    try:
                        # 查询条件单状态
                        params = {'ordType': 'conditional'}
                        response = self.exchange.private_get_trade_orders_algo_pending(params)
                        
                        order_exists = False
                        if response.get('code') == '0' and response.get('data'):
                            for algo_data in response['data']:
                                if str(algo_data.get('algoId', '')) == str(order_id):
                                    state = algo_data.get('state', 'live')
                                    print(f"   ✅ 找到条件单，状态: {state}")
                                    order_exists = True
                                    break
                        
                        if not order_exists:
                            print(f"   ⚠️  条件单不存在（可能已触发成交），检查是否已持仓...")
                            
                            # 🔴 检查是否有持仓（如果条件单已触发成交，应该已经有持仓了）
                            try:
                                positions = self.exchange.fetch_positions([symbol])
                                has_position = False
                                for pos in positions:
                                    try:
                                        contracts = float(pos.get('contracts', 0) or 0)
                                        size = float(pos.get('size', 0) or 0)
                                    except (ValueError, TypeError):
                                        contracts = 0
                                        size = 0
                                    
                                    if contracts > 0 or size > 0:
                                        has_position = True
                                        print(f"   ✅ 检测到持仓，条件单已成交！立即设置止损止盈...")
                                        
                                        # 🔴 设置止损止盈
                                        stop_loss_price = pending.get('stop_loss_price')
                                        take_profit_price = pending.get('take_profit_price')
                                        amount = pending.get('amount')
                                        direction = pending.get('direction')
                                        
                                        if stop_loss_price:
                                            print(f"   🛡️  设置止损单: ${stop_loss_price:.2f}")
                                            self._set_stop_loss_limit(
                                                symbol, direction, stop_loss_price, amount
                                            )
                                        
                                        if take_profit_price:
                                            print(f"   🎯 设置止盈单: ${take_profit_price:.2f}")
                                            self._set_take_profit_limit(
                                                symbol, direction, take_profit_price, amount
                                            )
                                        
                                        print(f"   ✅ 止损止盈单已设置完成")
                                        break
                            except Exception as e:
                                print(f"   ⚠️  检查持仓失败: {e}")
                            
                            # 从队列移除（无论是否成功设置止损止盈）
                            del self.pending_entry_orders[symbol]
                            continue
                            
                    except Exception as e:
                        error_msg = str(e)
                        if "51603" in error_msg or "Order does not exist" in error_msg or "51600" in error_msg:
                            print(f"   ⚠️  条件单不存在，从队列移除")
                            del self.pending_entry_orders[symbol]
                            continue
                        else:
                            print(f"   ⚠️  检查条件单状态失败: {e}")
                            continue
                
                # 如果价差 ≤ 0.3%，尝试优化
                if price_diff_pct <= 0.3:
                    print(f"   💡 价格接近目标价（≤0.3%），尝试优化为限价单...")
                    
                    # 🔴 先检查：如果限价单会失败（价格已触发），就不要优化
                    direction = pending['direction']
                    should_skip = False
                    
                    if direction == 'long':
                        # 做多：如果当前价 <= 目标价，已经触发了
                        if current_price <= limit_price:
                            print(f"   ⚠️  价格已触发 (当前价${current_price:.2f} <= 目标价${limit_price:.2f})")
                            print(f"   💡 保持条件单，不优化")
                            should_skip = True
                    else:
                        # 做空：如果当前价 >= 目标价，已经触发了
                        if current_price >= limit_price:
                            print(f"   ⚠️  价格已触发 (当前价${current_price:.2f} >= 目标价${limit_price:.2f})")
                            print(f"   💡 保持条件单，不优化")
                            should_skip = True
                    
                    if should_skip:
                        continue
                    
                    # 取消条件单
                    cancel_success = False
                    try:
                        if pending['conditional_order_id']:
                            self._cancel_conditional_order(pending['conditional_order_id'], symbol)
                            print(f"   ✅ 已取消条件单: {pending['conditional_order_id']}")
                            cancel_success = True
                    except Exception as e:
                        print(f"   ⚠️  取消条件单失败: {e}")
                        print(f"   💡 条件单可能已触发，跳过优化")
                        del self.pending_entry_orders[symbol]
                        continue
                    
                    # 🔴 只有取消成功才重新执行挂单逻辑
                    if cancel_success:
                        # 重新执行挂单逻辑（先挂限价单，失败就挂条件单）
                        amount = pending['amount']
                        stop_loss_price = pending.get('stop_loss_price')
                        take_profit_price = pending.get('take_profit_price')
                        
                        if direction == 'long':
                            result = self.open_long_with_limit_price(
                                symbol, amount, limit_price, stop_loss_price, take_profit_price
                            )
                        else:
                            result = self.open_short_with_limit_price(
                                symbol, amount, limit_price, stop_loss_price, take_profit_price
                            )
                        
                        # 检查结果
                        if result.get('entry_order'):
                            entry_order = result['entry_order']
                            if entry_order.get('type') == 'conditional':
                                # 仍然是条件单，更新队列中的ID
                                print(f"   💡 降级为条件单，继续监听")
                                self.pending_entry_orders[symbol]['conditional_order_id'] = entry_order['id']
                                self.pending_entry_orders[symbol]['order_type'] = 'conditional'
                            else:
                                # 成功挂上限价单：从队列移除
                                print(f"   ✅ 优化成功！已替换为限价单")
                                if symbol in self.pending_entry_orders:
                                    del self.pending_entry_orders[symbol]
                        else:
                            # 失败：移除队列（可能已经被触发了）
                            print(f"   ⚠️  挂单失败，从队列移除")
                            if symbol in self.pending_entry_orders:
                                del self.pending_entry_orders[symbol]
                
            except Exception as e:
                print(f"   ❌ 检查{symbol}失败: {e}")
                continue
        
        if self.pending_entry_orders:
            print(f"   📋 待优化开仓队列: {len(self.pending_entry_orders)}个")
        else:
            print(f"   ✅ 待优化开仓队列为空")
    
    def check_and_optimize_stop_orders(self):
        """检查监听队列，优化条件单为限价单（每10秒调用）
        
        遍历pending_stop_loss队列：
        - 检查当前价格与止损价的差距
        - 如果 ≤ 0.3%，取消条件单，挂限价单
        """
        # 🔴 同时检查开仓条件单队列
        self.check_and_optimize_entry_orders()
        
        # 🔴 即使队列为空也打印（让用户知道在运行）
        current_time = datetime.now().strftime('%H:%M:%S')
        
        if not self.pending_stop_loss:
            print(f"[{current_time}] 🔍 监听检查：待优化止损队列为空")
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

