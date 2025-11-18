#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OKX 实盘交易系统 - 支持止损止盈挂单
适合实盘交易，交易所自动监控止损止盈
"""

import sys
import os
import time
import signal
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trend_volumatic_dynamic_average_strategy import TrendVolumaticDynamicAverageStrategy
from okx_trader_v2 import OKXTraderV2  # 使用V2交易接口
from okx_config import TRADING_CONFIG
from strategy_configs import get_strategy_config
from database_service import DatabaseService
from database_config import LOCAL_DATABASE_CONFIG
from trade_logger import TradeLogger
from kline_buffer import KlineBuffer
from trading_database_service import TradingDatabaseService  # 🔴 新增：交易数据库服务


class LiveTradingBotWithStopOrders:
    """实盘交易机器人 - 支持止损止盈挂单"""
    
    @staticmethod
    def safe_float(value, default=0.0):
        """安全地将值转换为float，处理None值"""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def __init__(self, config, test_mode=True):
        """初始化"""
        self.config = config
        self.test_mode = test_mode
        self.is_running = False
        self.is_warmup_phase = True
        self.first_period_completed = False
        
        # 初始化日志
        self.logger = TradeLogger()
        
        # 🔴 使用V2交易接口（限价单优化版）
        leverage = TRADING_CONFIG.get('leverage', 1)
        try:
            self.trader = OKXTraderV2(test_mode=test_mode, leverage=leverage)
            
            # 验证API是否正确初始化
            if not hasattr(self.trader, 'exchange') or self.trader.exchange is None:
                print("❌ 警告: OKX API未正确初始化")
                print("   请检查 okx_config.py 中的API配置")
        except Exception as e:
            print(f"❌ 初始化OKX交易接口失败: {e}")
            raise
        
        # 初始化数据库服务（K线数据）
        try:
            self.db_service = DatabaseService(config=LOCAL_DATABASE_CONFIG)
        except Exception as e:
            print(f"⚠️  初始化K线数据库失败: {e}")
            print("   程序将继续运行，但预热功能将不可用")
            self.db_service = None
        
        # 🔴 初始化交易数据库服务（订单、交易记录），使用相同的数据库配置
        try:
            self.trading_db = TradingDatabaseService(db_config=LOCAL_DATABASE_CONFIG)
            print(f"✅ 交易数据库已连接: {LOCAL_DATABASE_CONFIG['database']}@{LOCAL_DATABASE_CONFIG['host']}")
        except Exception as e:
            print(f"⚠️  初始化交易数据库失败: {e}")
            print("   程序将继续运行，但订单记录功能将不可用")
            self.trading_db = None
        
        # 解析周期（如 '15m' -> 15）
        self.period_minutes = int(config['timeframe'].replace('m', '').replace('h', '')) if 'm' in config['timeframe'] else int(config['timeframe'].replace('h', '')) * 60
        
        # 🔴 初始化K线缓存管理器（缓存大小 = 周期分钟数）
        self.kline_buffer = KlineBuffer(buffer_size=self.period_minutes)
        
        # 初始化策略 - 基类不初始化，由子类实现
        # 子类应该覆盖整个 __init__ 方法并初始化策略
        self.strategy = None
        
        # 获取交易对符号
        self.symbol = TRADING_CONFIG['symbols'].get(config['long_coin'], 'BTC-USDT-SWAP')
        
        # 统计信息
        self.daily_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0,
        }
        
        # 🔴 记录当前持仓信息（用于更新止损）
        self.current_position = None
        self.current_position_side = None
        self.current_position_contracts = 0  # 🔴 当前持仓合约张数
        self.current_position_shares = 0
        self.current_trade_id = None  # 🔴 当前交易ID（用于关联数据库记录）
        self.current_entry_order_id = None  # 🔴 当前开仓订单ID
        self.current_stop_loss_order_id = None  # 🔴 当前止损单ID
        self.current_take_profit_order_id = None  # 🔴 当前止盈单ID
        
        # 🔴 记录当前挂单信息（用于比较金额）
        self.pending_entry_order_id = None  # 🔴 当前未成交的开仓订单ID
        self.pending_entry_amount = None  # 🔴 当前未成交的开仓订单币数量
        self.pending_entry_price = None  # 🔴 当前未成交的开仓订单价格
        
        # 🔴 记录待挂的止损止盈价格（等待开仓成交后挂单）
        self.pending_stop_loss_price = None  # 🔴 待挂的止损价格
        self.pending_take_profit_price = None  # 🔴 待挂的止盈价格
        self.pending_entry_side = None  # 🔴 待挂的开仓方向（'long' 或 'short'）
        
        # 🔴 从数据库恢复的止损止盈价格（用于同步到策略）
        self._restored_stop_loss_price = None
        self._restored_take_profit_price = None
        
        # 🔴 账户余额（使用可用余额，而不是总余额）
        self.account_balance = 0.0  # 可用余额（free）
        self.account_total_balance = 0.0  # 总余额（total）
        self.account_used_balance = 0.0  # 已用余额（used）
        
        self.logger.log(f"{'='*80}")
        self.logger.log(f"🛡️  实盘交易机器人 - 止损止盈挂单版")
        self.logger.log(f"{'='*80}")
        self.logger.log(f"📊 交易对: {self.symbol}")
        self.logger.log(f"⏰ 策略周期: {config['timeframe']}")
        self.logger.log(f"🧪 测试模式: {'是' if self.test_mode else '否'}")
        self.logger.log(f"🛡️  特性: 开仓自动挂止损止盈单")
        self.logger.log(f"{'='*80}\n")
    
    def warmup_strategy(self, warmup_days=60):
        """预热策略（与原版相同）"""
        self.logger.log(f"🔥 开始预热策略（{warmup_days}天数据）...")
        
        # 🔴 检查数据库是否可用
        if self.db_service is None:
            self.logger.log_warning("⚠️  K线数据库未连接，跳过预热")
            self.logger.log("💡 程序将从当前时刻开始积累数据")
            return
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=warmup_days)
        
        start_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            df = self.db_service.get_kline_data(
                self.config['long_coin'],
                start_str,
                end_str
            )
        except Exception as e:
            self.logger.log_error(f"获取K线数据失败: {e}")
            self.logger.log_warning("跳过预热，程序将从当前时刻开始积累数据")
            return
        
        if df.empty:
            self.logger.log_warning("未获取到预热数据")
            return
        
        self.logger.log(f"📊 获取到 {len(df)} 条历史数据")
        
        warmup_data = []
        for _, row in df.iterrows():
            warmup_data.append({
                'timestamp': row['timestamp'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close']
            })
        
        self.strategy.warmup_filter(warmup_data)
        self.logger.log("✅ 策略预热完成！")
        
        # 🔴 添加预热数据到缓存（只添加周期分钟数的数据）
        if not df.empty:
            cache_count = min(self.period_minutes, len(df))
            self.logger.log(f"📦 将预热数据的最后{cache_count}条添加到缓存...")
            
            for _, row in df.tail(cache_count).iterrows():
                row_time = row['timestamp']
                if hasattr(row_time, 'tz_localize'):
                    row_time = row_time.tz_localize(None)
                elif hasattr(row_time, 'tz'):
                    row_time = row_time.replace(tzinfo=None)
                
                self.kline_buffer.add_kline(
                    row_time,
                    row['open'],
                    row['high'],
                    row['low'],
                    row['close'],
                    row.get('volume', 0)
                )
        
        # 补充数据空缺（逻辑与原版相同）
        # ... 省略补充逻辑代码 ...
        
        self.is_warmup_phase = False
        self.logger.log(f"🎯 预热阶段结束，进入正式交易阶段\n")
        
        # 🔴 发送钉钉消息：预热完成，开始交易
        if hasattr(self.strategy, 'dingtalk_notifier') and self.strategy.dingtalk_notifier:
            try:
                # 🔴 发送消息前先获取最新账户余额
                try:
                    account_info = self.trader.get_account_info()
                    if account_info and 'balance' in account_info:
                        # 🔴 使用可用余额（free），而不是总余额（total）
                        current_balance = account_info['balance']['free']
                    else:
                        current_balance = self.account_balance  # 使用缓存的余额
                except Exception as e:
                    self.logger.log_warning(f"⚠️  获取账户余额失败，使用缓存值: {e}")
                    current_balance = self.account_balance
                
                current_time = datetime.now()
                time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
                
                # 构建预热完成消息
                title = f"🚀 交易系统启动完成"
                content = f"## 🚀 交易系统启动完成\n\n"
                content += f"**⏰ 启动时间**: {time_str}\n\n"
                content += f"---\n\n"
                content += f"**📊 交易对**: {self.symbol}\n\n"
                content += f"**⏰ 策略周期**: {self.config['timeframe']}\n\n"
                content += f"**🧪 测试模式**: {'是' if self.test_mode else '否'}\n\n"
                content += f"**💰 账户余额**: ${current_balance:,.2f} USDT\n\n"
                content += f"**📊 仓位比例**: {self.config.get('position_size_percentage', 100)}%\n\n"
                content += f"**💵 可用保证金**: ${current_balance * self.config.get('position_size_percentage', 100) / 100:,.2f} USDT\n\n"
                content += f"---\n\n"
                content += f"**🔥 预热数据**: {len(df)} 条历史数据\n\n"
                content += f"**📦 缓存数据**: {cache_count} 条K线数据\n\n"
                content += f"---\n\n"
                content += f"✅ **系统已准备就绪，开始监控市场并执行交易策略**\n\n"
                content += f"🛡️ **特性**: 开仓自动挂止损止盈单\n\n"
                
                # 发送消息
                result = self.strategy.dingtalk_notifier.send_message(title, content)
                if result and result.get('errcode') == 0:
                    self.logger.log(f"📱 预热完成钉钉消息发送成功")
                else:
                    self.logger.log_warning(f"⚠️  预热完成钉钉消息发送失败: {result}")
            except Exception as e:
                self.logger.log_error(f"❌ 发送预热完成钉钉消息失败: {e}")
                import traceback
                traceback.print_exc()
        else:
            self.logger.log(f"📱 钉钉通知器未配置，跳过预热完成消息")
    
    def execute_signal(self, signal):
        """执行交易信号 - 增强版"""
        self.logger.log_signal(signal)
        
        signal_type = signal['type']
        print(f"🔍 执行信号: {signal_type}, 测试模式: {self.test_mode}")
        
        # 🔴 开仓前检查：混合方案 - 检查OKX实际持仓 + 同步本地状态
        if signal_type in ['OPEN_LONG', 'OPEN_SHORT']:
            print(f"🚨 开仓前检查（混合方案）: {signal_type}")
            
            try:
                # 1. 查询OKX实际持仓
                positions = self.trader.exchange.fetch_positions([self.symbol])
                has_okx_position = self._check_okx_actual_positions(positions)
                
                if has_okx_position:
                    signal_direction = 'long' if signal_type == 'OPEN_LONG' else 'short'
                    print(f"❌ OKX实际有持仓，拒绝{signal_direction}开仓")
                    
                    # 🔴 打印OKX持仓详情
                    for pos in positions:
                        pos_symbol = pos.get('symbol', '')
                        pos_inst_id = pos.get('info', {}).get('instId', '')
                        contracts = self.safe_float(pos.get('contracts'))
                        size = self.safe_float(pos.get('size'))
                        notional = self.safe_float(pos.get('notional'))
                        side = pos.get('side', '')
                        
                        if contracts > 0 or size > 0 or notional > 0:
                            print(f"   📊 OKX持仓详情: {pos_symbol}/{pos_inst_id}, 方向: {side}, 数量: {contracts}")
                    
                    # 🔴 打印策略当前状态
                    print(f"   🔍 策略当前状态: position={self.strategy.position}, entry_price={self.strategy.entry_price}")
                    
                    # 🔴 同步OKX状态到本地（确保一致性）
                    self._sync_okx_to_local(positions)
                    return
                
                # 2. OKX无持仓，确保本地状态为空
                print(f"✅ OKX无持仓，可以开仓")
                if self.current_position:
                    print(f"🔄 清空本地持仓状态，确保一致性")
                    self._clear_position_state()
                
            except Exception as e:
                print(f"❌ 检查OKX持仓失败: {e}")
                # 为了安全起见，拒绝开仓
                signal_direction = 'long' if signal_type == 'OPEN_LONG' else 'short'
                self.logger.log_warning(f"⚠️  无法检查OKX持仓，拒绝{signal_direction}开仓信号（安全考虑）")
                return
        
        # 🔴 开仓 - 自动挂止损止盈单
        if signal_type == 'OPEN_LONG':
            position_shares = signal.get('position_shares', 0)
            invested_amount = signal.get('invested_amount', 0)
            
            entry_price = signal.get('price', 0)
            entry_type = signal.get('entry_type', 'immediate')  # 🔴 获取开仓类型：'limit' 或 'immediate'
            stop_loss = round(signal.get('stop_loss'), 1)  # SAR 止损位，保留1位小数
            take_profit = round(signal.get('take_profit'), 1)  # 固定止盈位，保留1位小数
            
            print(f"\n🔍 ========== OPEN_LONG 信号处理 ==========")
            print(f"🔍 信号价格: ${entry_price:.2f}")
            print(f"🔍 开仓类型: {entry_type} ({'支撑位/阻力位限价单' if entry_type == 'limit' else '立即挂单(买3/卖3)'})")
            print(f"🔍 止损价格: ${stop_loss:.1f}")
            print(f"🔍 止盈价格: ${take_profit:.1f}")
            
            # 🔴 风险收益比检查：止损比例不能比止盈比例小
            stop_loss_pct = abs(entry_price - stop_loss) / entry_price * 100
            take_profit_pct = abs(take_profit - entry_price) / entry_price * 100
            
            print(f"🔍 风险收益比检查:")
            print(f"   止损比例: {stop_loss_pct:.2f}%")
            print(f"   止盈比例: {take_profit_pct:.2f}%")
            
            if stop_loss_pct < take_profit_pct:
                print(f"❌ 风险收益比不合理，拒绝开仓:")
                print(f"   止损比例({stop_loss_pct:.2f}%) < 止盈比例({take_profit_pct:.2f}%)")
                print(f"   风险大于收益，不符合交易原则")
                self.logger.log_warning(f"⚠️  拒绝开多仓: 止损比例({stop_loss_pct:.2f}%) < 止盈比例({take_profit_pct:.2f}%)")
                return
            
            print(f"✅ 风险收益比合理: 止损比例({stop_loss_pct:.2f}%) >= 止盈比例({take_profit_pct:.2f}%)")
            
            # 🔴 开仓前更新账户余额，确保使用最新数据
            self._update_account_balance()
            
            # 🔴 position_size_percentage 表示使用的保证金占账户余额的百分比
            # 例如：20% 表示使用账户余额的20%作为保证金
            # 注意：calculate_contract_amount 内部会使用 95% 的安全缓冲，并乘以杠杆
            position_size_pct = self.config.get('position_size_percentage', 100) / 100
            leverage = TRADING_CONFIG.get('leverage', 1)
            
            # 🔴 检查可用保证金是否足够
            if self.account_balance <= 0:
                self.logger.log_error(f"❌ 可用保证金不足: ${self.account_balance:.2f} <= 0")
                self.logger.log_error(f"   总余额: ${getattr(self, 'account_total_balance', 0):.2f}")
                self.logger.log_error(f"   已用余额: ${getattr(self, 'account_used_balance', 0):.2f}")
                self.logger.log_error(f"   请检查账户余额或释放已占用的保证金")
                return
            
            # 直接使用账户余额的百分比作为保证金
            actual_invested = self.account_balance * position_size_pct
            
            # 🔴 再次检查：确保需要的保证金不超过可用余额
            if actual_invested > self.account_balance:
                self.logger.log_warning(f"⚠️  需要的保证金${actual_invested:.2f}超过可用余额${self.account_balance:.2f}")
                self.logger.log_warning(f"   自动调整为可用余额的100%: ${self.account_balance:.2f}")
                actual_invested = self.account_balance * 0.99  # 使用99%避免边界问题
            
            # 计算实际持仓价值（用于显示）
            # calculate_contract_amount 内部：safe_margin = actual_invested * 0.95, position_value = safe_margin * leverage
            safe_margin = actual_invested * 0.95
            actual_position_value = safe_margin * leverage
            
            print(f"💰 账户余额: 可用=${self.account_balance:.2f} | 总余额=${getattr(self, 'account_total_balance', 0):.2f} | 已用=${getattr(self, 'account_used_balance', 0):.2f}")
            print(f"💰 使用保证金: ${actual_invested:.2f} (可用余额${self.account_balance:.2f} × {position_size_pct*100}%)")
            print(f"💰 实际持仓价值: ${actual_position_value:.2f} (保证金${actual_invested:.2f} × 95% × {leverage}倍杠杆 = {actual_position_value/self.account_balance*100:.1f}%可用余额)")
            
            # 🔴 重新计算合约数量（从OKX获取合约规格）
            # 🔴 显式传入杠杆，确保使用配置的杠杆倍数
            contract_amount = self.trader.calculate_contract_amount(
                self.symbol,
                actual_invested,
                entry_price,
                leverage=leverage  # 🔴 显式传入杠杆，确保使用配置的杠杆倍数
            )
            contract_size, _ = self.trader.get_contract_size(self.symbol)
            coin_amount = round(contract_amount * contract_size, 2)
            
            print(f"🔍 准备开多单:")
            print(f"   交易对: {self.symbol}")
            print(f"   投入金额: ${actual_invested:.2f}")
            print(f"   当前价格: ${entry_price:.2f}")
            print(f"   合约张数: {contract_amount} 张 (~币数量 {coin_amount} {self.config.get('long_coin', 'coin')})")
            print(f"   止损价格: ${stop_loss:.2f}")
            print(f"   止盈价格: ${take_profit:.2f}")
            
            # 🔴 检查是否有未成交的挂单，比较金额
            should_place_new_order = True
            if self.pending_entry_order_id is not None:
                print(f"\n🔍 检测到已有未成交挂单:")
                print(f"   订单ID: {self.pending_entry_order_id}")
                print(f"   挂单币数量: {self.pending_entry_amount} {self.config.get('long_coin', 'coin')}")
                print(f"   挂单价格: ${self.pending_entry_price:.2f}")
                
                # 🔴 先检查订单是否还存在，并查询所有未成交订单检查是否有相同价格的挂单
                order_still_exists = False
                query_success = False
                same_price_order_exists = False
                
                try:
                    # 方法1: 尝试查询订单状态（可能是限价单或条件单）
                    try:
                        order_info = self.trader.exchange.fetch_order(self.pending_entry_order_id, self.symbol)
                        order_status = order_info.get('status', 'unknown')
                        query_success = True
                        if order_status in ['open', 'pending', 'new']:
                            order_still_exists = True
                            print(f"   ✅ 订单仍存在，状态: {order_status}")
                        else:
                            print(f"   ⚠️  订单已不存在或已成交，状态: {order_status}")
                    except Exception as e1:
                        # 如果不是普通订单，可能是条件单，尝试查询条件单
                        try:
                            # 查询条件单状态
                            params = {'ordType': 'conditional'}
                            response = self.trader.exchange.private_get_trade_orders_algo_pending(params)
                            query_success = True
                            if response.get('code') == '0' and response.get('data'):
                                found = False
                                for algo_data in response['data']:
                                    algo_id = algo_data.get('algoId', '')
                                    if str(algo_id) == str(self.pending_entry_order_id):
                                        found = True
                                        state = algo_data.get('state', '')
                                        if state == 'live':
                                            order_still_exists = True
                                            print(f"   ✅ 条件单仍存在，状态: {state}")
                                        else:
                                            print(f"   ⚠️  条件单已不存在，状态: {state}")
                                        break
                                if not found:
                                    print(f"   ⚠️  条件单不存在于待处理列表中")
                        except Exception as e2:
                            print(f"   ⚠️  查询条件单状态失败: {e2}")
                    
                    # 方法2: 查询所有未成交订单，检查是否有相同价格的挂单
                    if not order_still_exists:
                        try:
                            print(f"   🔍 查询所有未成交订单，检查是否有相同价格的挂单...")
                            open_orders = self.trader.exchange.fetch_open_orders(self.symbol)
                            
                            # 检查是否有相同价格的挂单（允许0.01的误差）
                            for order in open_orders:
                                order_price = self.safe_float(order.get('price'))
                                order_side = order.get('side', '').lower()
                                order_amount = self.safe_float(order.get('amount'))
                                
                                # 检查方向：做多应该是buy
                                if order_price and order_side == 'buy':
                                    price_diff = abs(order_price - entry_price)
                                    amount_diff = abs(order_amount - contract_amount) if order_amount else 999
                                    
                                    if price_diff < 0.01 and amount_diff < 0.01:
                                        same_price_order_exists = True
                                        print(f"   ✅ 发现相同价格的未成交挂单: 订单ID={order.get('id')}, 价格=${order_price:.2f}, 数量={order_amount}{self.config.get('long_coin', 'coin')}")
                                        # 更新记录的订单ID（可能订单ID变了，但价格和数量相同）
                                        if order.get('id') != self.pending_entry_order_id:
                                            print(f"   🔄 更新记录的订单ID: {self.pending_entry_order_id} → {order.get('id')}")
                                            self.pending_entry_order_id = order.get('id')
                                        break
                            
                            if not same_price_order_exists:
                                print(f"   ⚠️  未找到相同价格的未成交挂单")
                        except Exception as e3:
                            print(f"   ⚠️  查询未成交订单失败: {e3}")
                    
                    # 方法3: 查询条件单列表，检查是否有相同价格的挂单
                    if not order_still_exists and not same_price_order_exists:
                        try:
                            print(f"   🔍 查询所有条件单，检查是否有相同价格的挂单...")
                            params = {'ordType': 'conditional'}
                            response = self.trader.exchange.private_get_trade_orders_algo_pending(params)
                            if response.get('code') == '0' and response.get('data'):
                                for algo_data in response['data']:
                                    algo_id = algo_data.get('algoId', '')
                                    trigger_price = self.safe_float(algo_data.get('triggerPx'))
                                    order_price = self.safe_float(algo_data.get('orderPx'))
                                    algo_amount = self.safe_float(algo_data.get('sz'))
                                    side = algo_data.get('side', '').lower()
                                    
                                    # 检查方向：做多应该是buy
                                    # 使用触发价或委托价进行比较
                                    check_price = order_price if order_price else trigger_price
                                    
                                    if check_price and side == 'buy':
                                        price_diff = abs(check_price - entry_price)
                                        amount_diff = abs(algo_amount - contract_amount) if algo_amount else 999
                                        
                                        if price_diff < 0.01 and amount_diff < 0.01:
                                            same_price_order_exists = True
                                            print(f"   ✅ 发现相同价格的条件单: 订单ID={algo_id}, 价格=${check_price:.2f}, 数量={algo_amount}{self.config.get('long_coin', 'coin')}")
                                            # 更新记录的订单ID
                                            if str(algo_id) != str(self.pending_entry_order_id):
                                                print(f"   🔄 更新记录的订单ID: {self.pending_entry_order_id} → {algo_id}")
                                                self.pending_entry_order_id = algo_id
                                            break
                        except Exception as e4:
                            print(f"   ⚠️  查询条件单列表失败: {e4}")
                            
                except Exception as e:
                    print(f"   ⚠️  检查订单状态异常: {e}")
                
                # 🔴 判断是否应该跳过挂单
                if order_still_exists or same_price_order_exists:
                    # 订单存在或找到相同价格的挂单，比较金额和价格
                    print(f"   新信号金额: {coin_amount} {self.config.get('long_coin', 'coin')}")
                    print(f"   新信号价格: ${entry_price:.2f}")
                    
                    # 比较金额（允许0.01的误差，因为精度问题）
                    amount_diff = abs(self.pending_entry_amount - coin_amount)
                    price_diff = abs(self.pending_entry_price - entry_price)
                    
                    if amount_diff < 0.01 and price_diff < 0.01:
                        print(f"✅ 挂单币数量和价格一致，无需重新挂单")
                        print(f"   金额差异: {amount_diff:.4f} (≤ 0.01)")
                        print(f"   价格差异: ${price_diff:.2f} (≤ $0.01)")
                        should_place_new_order = False
                    else:
                        print(f"⚠️  挂单币数量或价格不一致，需要取消旧单并重新挂单")
                        print(f"   金额差异: {amount_diff:.4f}")
                        print(f"   价格差异: ${price_diff:.2f}")
                        
                        # 取消旧订单
                        try:
                            print(f"🔄 取消旧挂单: {self.pending_entry_order_id}")
                            # 检查订单类型（可能是限价单或条件单）
                            try:
                                # 先尝试作为普通订单取消
                                self.trader.exchange.cancel_order(self.pending_entry_order_id, self.symbol)
                                print(f"✅ 已取消旧挂单（限价单）")
                            except Exception as e1:
                                # 如果不是普通订单，可能是条件单
                                if 'conditional' in str(e1).lower() or 'algo' in str(e1).lower():
                                    print(f"🔄 尝试作为条件单取消...")
                                    self.trader._cancel_conditional_order(self.pending_entry_order_id, self.symbol)
                                    print(f"✅ 已取消旧挂单（条件单）")
                                else:
                                    print(f"⚠️  取消旧挂单失败: {e1}")
                                    # 继续执行，尝试挂新单
                        except Exception as e:
                            print(f"⚠️  取消旧挂单异常: {e}")
                            # 继续执行，尝试挂新单
                        
                        # 清空记录
                        self.pending_entry_order_id = None
                        self.pending_entry_amount = None
                        self.pending_entry_price = None
                        print(f"   🔄 清空挂单记录G")
                elif query_success:
                    # 查询成功但订单不存在，清空记录
                    print(f"   🔄 订单已不存在，清空挂单记录")
                    self.pending_entry_order_id = None
                    self.pending_entry_amount = None
                    self.pending_entry_price = None
                else:
                    # 查询失败，保留记录，不挂新单（避免重复挂单）
                    print(f"   ⚠️  查询订单状态失败，为安全起见保留记录，不挂新单")
                    print(f"   💡 等待下次检查时再确认订单状态")
                    should_place_new_order = False
            
            if not should_place_new_order:
                print(f"⏭️  跳过挂单，使用现有挂单")
                return
            
            print(f"🔍 开始调用OKX接口开多单...")
            
            # 🔴 根据开仓类型选择不同的挂单方式
            if entry_type == 'limit':
                # 支撑位/阻力位限价单：在指定价格挂限价单
                print(f"📌 【限价单模式】在支撑位/阻力位价格 ${entry_price:.2f} 挂限价单")
                result = self.trader.open_long_with_limit_price(
                    self.symbol,
                    contract_amount,
                    entry_price,  # 使用指定的支撑位/阻力位价格
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit
                )
            else:
                # 立即挂单模式：使用买3/卖3价格
                print(f"⚡ 【立即挂单模式】使用买3/卖3价格挂单")
                result = self.trader.open_long_with_stop_orders(
                    self.symbol, 
                    contract_amount,
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit
                )
            
            print(f"\n🔍 OKX开多单返回结果:")
            print(f"   入场订单: {result.get('entry_order')}")
            print(f"   止损订单: {result.get('stop_loss_order')} (将在开仓成交后挂单)")
            print(f"   止盈订单: {result.get('take_profit_order')} (将在开仓成交后挂单)")
            
            # 🔴 记录挂单信息和止盈止损价格（无论是否成交）
            if result.get('entry_order'):
                entry_order = result['entry_order']
                order_id = entry_order.get('id')
                order_status = entry_order.get('status', 'unknown')
                
                # 🔴 记录止盈止损价格（等待开仓成交后挂单）
                self.pending_stop_loss_price = stop_loss
                self.pending_take_profit_price = take_profit
                self.pending_entry_side = 'long'
                print(f"📝 记录待挂止损止盈价格: 止损=${stop_loss:.2f}, 止盈=${take_profit:.2f}")
                
                # 检查订单是否已成交
                if order_status == 'closed' or order_status == 'filled':
                    # 已成交，立即挂止损止盈单
                    print(f"✅ 开仓订单已成交，立即挂止损止盈单")
                    self._place_stop_orders_after_entry('long', coin_amount, stop_loss, take_profit)
                    # 清空挂单记录
                    self.pending_entry_order_id = None
                    self.pending_entry_amount = None
                    self.pending_entry_price = None
                    self.pending_stop_loss_price = None
                    self.pending_take_profit_price = None
                    self.pending_entry_side = None
                    print(f"   🔄 清空挂单记录H")
                else:
                    # 未成交，记录挂单信息
                    print(f"📝 记录挂单信息: 订单ID={order_id}, 币数量={coin_amount}{self.config.get('long_coin', 'coin')}, 价格=${entry_price:.2f}")
                    self.pending_entry_order_id = order_id
                    self.pending_entry_amount = coin_amount
                    self.pending_entry_price = entry_price
                    # 打印
                    print(f"   🔍 记录待挂挂单: 订单ID={self.pending_entry_order_id}")
            
            if result['entry_order']:
                self.current_position = 'long'
                self.current_position_side = 'long'
                self.current_position_contracts = contract_amount
                self.current_position_shares = coin_amount
                self.daily_stats['total_trades'] += 1
                
                self.logger.log(f"✅ 开多单成功")
                self.logger.log(f"   止损单: {result['stop_loss_order']['id'] if result['stop_loss_order'] else '未设置'}")
                self.logger.log(f"   止盈单: {result['take_profit_order']['id'] if result['take_profit_order'] else '未设置'}")
                
                # 🔴 同步真实交易数据到策略
                trade_data = {
                    'position': 'long',
                    'entry_price': entry_price,
                    'position_shares': coin_amount,
                    'stop_loss_price': stop_loss,
                    'take_profit_price': take_profit,
                    'invested_amount': actual_invested,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                trade_data['position_shares'] = coin_amount
                self.strategy.sync_real_trade_data(trade_data)
                
                # 🔴 保存开仓订单到数据库
                if self._is_trading_db_available():
                    try:
                        # 1. 保存开仓订单
                        entry_order_id = result['entry_order']['id']
                        self.trading_db.save_order(
                            order_id=entry_order_id,
                            symbol=self.symbol,
                            order_type='MARKET',
                            side='buy',
                            position_side='long',
                            amount=contract_amount,
                            price=entry_price,
                            status='filled',
                            invested_amount=actual_invested,
                            order_time=datetime.now(),
                            filled_time=datetime.now()
                        )
                        
                        # 2. 保存交易记录（无论止损单是否设置成功都要保存）
                        # 🔴 根据entry_type设置open_reason
                        open_reason = '标准VIDYA' if entry_type == 'limit' else '布林带角度'
                        trade_id = self.trading_db.save_trade(
                            symbol=self.symbol,
                            position_side='long',
                            entry_order_id=entry_order_id,
                            entry_price=entry_price,
                            entry_time=datetime.now(),
                            amount=contract_amount,
                            invested_amount=actual_invested,
                            status='open',
                            open_reason=open_reason  # 🔴 保存开仓原因
                        )
                        
                        # 🔴 保存到实例变量，供后续更新使用
                        self.current_trade_id = trade_id
                        self.current_entry_order_id = entry_order_id
                        
                        print(f"💾 已保存: 开仓订单({entry_order_id}) + 交易记录(ID={trade_id})")
                        
                        # 🔴 发送钉钉通知：开多单成功
                        if hasattr(self.strategy, 'dingtalk_notifier') and self.strategy.dingtalk_notifier:
                            try:
                                # 准备止损信息
                                stop_loss_info = None
                                if result['stop_loss_order']:
                                    stop_loss_info = {
                                        'price': stop_loss,
                                        'order_type': result['stop_loss_order'].get('_order_type', 'unknown'),
                                        'order_id': result['stop_loss_order']['id']
                                    }
                                
                                # 准备止盈信息
                                take_profit_info = None
                                if result['take_profit_order']:
                                    take_profit_info = {
                                        'price': take_profit,
                                        'order_type': result['take_profit_order'].get('_order_type', 'limit'),
                                        'order_id': result['take_profit_order']['id']
                                    }
                                
                                # 准备额外信息
                                leverage = TRADING_CONFIG.get('leverage', 1)
                                extra_info = {
                                    'invested_amount': actual_invested,
                                    'leverage': leverage
                                }
                                
                                # 发送通知
                                self.strategy.dingtalk_notifier.send_order_notification(
                                    order_type='OPEN_LONG',
                                    symbol=self.symbol,
                                    side='buy',
                                    amount=contract_amount,
                                    price=entry_price,
                                    stop_loss_info=stop_loss_info,
                                    take_profit_info=take_profit_info,
                                    order_result=result,
                                    extra_info=extra_info
                                )
                                print(f"📱 开多单钉钉通知已发送")
                            except Exception as e:
                                self.logger.log_warning(f"⚠️  发送开多单钉钉通知失败: {e}")
                        
                        # 3. 保存止损单到 okx_stop_orders（不保存到 okx_orders）
                        if result['stop_loss_order']:
                            stop_loss_order_id = result['stop_loss_order']['id']
                            
                            self.trading_db.save_stop_order(
                                order_id=stop_loss_order_id,
                                symbol=self.symbol,
                                trade_id=trade_id,
                                entry_order_id=entry_order_id,
                                order_type='STOP_LOSS',
                                position_side='long',
                                trigger_price=stop_loss,
                                amount=contract_amount,
                                status='active'
                            )
                            
                            self.current_stop_loss_order_id = stop_loss_order_id
                            print(f"💾 已保存: 止损单({stop_loss_order_id}) → okx_stop_orders")
                        
                        # 4. 保存止盈单到 okx_stop_orders（不保存到 okx_orders）
                        if result['take_profit_order']:
                            take_profit_order_id = result['take_profit_order']['id']
                            
                            self.trading_db.save_stop_order(
                                order_id=take_profit_order_id,
                                symbol=self.symbol,
                                trade_id=trade_id,
                                entry_order_id=entry_order_id,
                                order_type='TAKE_PROFIT',
                                position_side='long',
                                trigger_price=take_profit,
                                amount=contract_amount,
                                status='active'
                            )
                            
                            self.current_take_profit_order_id = take_profit_order_id
                            print(f"💾 已保存: 止盈单({take_profit_order_id}) → okx_stop_orders")
                        
                        print(f"✅ 所有订单已保存: okx_orders(开仓) + okx_stop_orders(止损/止盈)")
                    except Exception as e:
                        print(f"❌ 保存订单到数据库失败: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"⚠️  交易数据库未连接，跳过保存订单")
        
        elif signal_type == 'OPEN_SHORT':
            position_shares = signal.get('position_shares', 0)
            invested_amount = signal.get('invested_amount', 0)
            entry_price = signal.get('price', 0)
            entry_type = signal.get('entry_type', 'immediate')  # 🔴 获取开仓类型：'limit' 或 'immediate'
            stop_loss = round(signal.get('stop_loss'), 1)  # SAR 止损位，保留1位小数
            take_profit = round(signal.get('take_profit'), 1)  # 固定止盈位，保留1位小数
            
            print(f"\n🔍 ========== OPEN_SHORT 信号处理 ==========")
            print(f"🔍 信号价格: ${entry_price:.2f}")
            print(f"🔍 开仓类型: {entry_type} ({'支撑位/阻力位限价单' if entry_type == 'limit' else '立即挂单(买3/卖3)'})")
            print(f"🔍 止损价格: ${stop_loss:.1f}")
            print(f"🔍 止盈价格: ${take_profit:.1f}")
            
            # 🔴 风险收益比检查：止损比例不能比止盈比例小
            stop_loss_pct = abs(stop_loss - entry_price) / entry_price * 100
            take_profit_pct = abs(entry_price - take_profit) / entry_price * 100
            
            print(f"🔍 风险收益比检查:")
            print(f"   止损比例: {stop_loss_pct:.2f}%")
            print(f"   止盈比例: {take_profit_pct:.2f}%")
            
            if stop_loss_pct < take_profit_pct:
                print(f"❌ 风险收益比不合理，拒绝开仓:")
                print(f"   止损比例({stop_loss_pct:.2f}%) < 止盈比例({take_profit_pct:.2f}%)")
                print(f"   风险大于收益，不符合交易原则")
                self.logger.log_warning(f"⚠️  拒绝开空仓: 止损比例({stop_loss_pct:.2f}%) < 止盈比例({take_profit_pct:.2f}%)")
                return
            
            print(f"✅ 风险收益比合理: 止损比例({stop_loss_pct:.2f}%) >= 止盈比例({take_profit_pct:.2f}%)")
            
            # 🔴 开仓前更新账户余额，确保使用最新数据
            self._update_account_balance()
            
            # 🔴 position_size_percentage 表示使用的保证金占账户余额的百分比
            # 例如：20% 表示使用账户余额的20%作为保证金
            # 注意：calculate_contract_amount 内部会使用 95% 的安全缓冲，并乘以杠杆
            position_size_pct = self.config.get('position_size_percentage', 100) / 100
            leverage = TRADING_CONFIG.get('leverage', 1)
            
            # 🔴 检查可用保证金是否足够
            if self.account_balance <= 0:
                self.logger.log_error(f"❌ 可用保证金不足: ${self.account_balance:.2f} <= 0")
                self.logger.log_error(f"   总余额: ${getattr(self, 'account_total_balance', 0):.2f}")
                self.logger.log_error(f"   已用余额: ${getattr(self, 'account_used_balance', 0):.2f}")
                self.logger.log_error(f"   请检查账户余额或释放已占用的保证金")
                return
            
            # 直接使用账户余额的百分比作为保证金
            actual_invested = self.account_balance * position_size_pct
            
            # 🔴 再次检查：确保需要的保证金不超过可用余额
            if actual_invested > self.account_balance:
                self.logger.log_warning(f"⚠️  需要的保证金${actual_invested:.2f}超过可用余额${self.account_balance:.2f}")
                self.logger.log_warning(f"   自动调整为可用余额的100%: ${self.account_balance:.2f}")
                actual_invested = self.account_balance * 0.99  # 使用99%避免边界问题
            
            # 计算实际持仓价值（用于显示）
            # calculate_contract_amount 内部：safe_margin = actual_invested * 0.95, position_value = safe_margin * leverage
            safe_margin = actual_invested * 0.95
            actual_position_value = safe_margin * leverage
            
            print(f"💰 账户余额: 可用=${self.account_balance:.2f} | 总余额=${getattr(self, 'account_total_balance', 0):.2f} | 已用=${getattr(self, 'account_used_balance', 0):.2f}")
            print(f"💰 使用保证金: ${actual_invested:.2f} (可用余额${self.account_balance:.2f} × {position_size_pct*100}%)")
            print(f"💰 实际持仓价值: ${actual_position_value:.2f} (保证金${actual_invested:.2f} × 95% × {leverage}倍杠杆 = {actual_position_value/self.account_balance*100:.1f}%可用余额)")
            
            # 🔴 重新计算合约数量（从OKX获取合约规格）
            # 🔴 显式传入杠杆，确保使用配置的杠杆倍数
            contract_amount = self.trader.calculate_contract_amount(
                self.symbol,
                actual_invested,
                entry_price,
                leverage=leverage  # 🔴 显式传入杠杆，确保使用配置的杠杆倍数
            )
            contract_size, _ = self.trader.get_contract_size(self.symbol)
            coin_amount = round(contract_amount * contract_size, 2)
            
            print(f"🔍 准备开空单:")
            print(f"   交易对: {self.symbol}")
            print(f"   投入金额: ${actual_invested:.2f}")
            print(f"   当前价格: ${entry_price:.2f}")
            print(f"   合约张数: {contract_amount} 张 (~币数量 {coin_amount} {self.config.get('long_coin', 'coin')})")
            print(f"   止损价格: ${stop_loss:.2f}")
            print(f"   止盈价格: ${take_profit:.2f}")

            # 打印pending_entry_order_id
            print(f"   当前挂单ID: {self.pending_entry_order_id}")
            
            # 🔴 检查是否有未成交的挂单，比较金额
            should_place_new_order = True
            if self.pending_entry_order_id is not None:
                print(f"\n🔍 检测到已有未成交挂单:")
                print(f"   订单ID: {self.pending_entry_order_id}")
                print(f"   挂单币数量: {self.pending_entry_amount} {self.config.get('long_coin', 'coin')}")
                print(f"   挂单价格: ${self.pending_entry_price:.2f}")
                
                # 🔴 先检查订单是否还存在，并查询所有未成交订单检查是否有相同价格的挂单
                order_still_exists = False
                query_success = False
                same_price_order_exists = False
                
                try:
                    # 方法1: 尝试查询订单状态（可能是限价单或条件单）
                    try:
                        order_info = self.trader.exchange.fetch_order(self.pending_entry_order_id, self.symbol)
                        order_status = order_info.get('status', 'unknown')
                        query_success = True
                        if order_status in ['open', 'pending', 'new']:
                            order_still_exists = True
                            print(f"   ✅ 订单仍存在，状态: {order_status}")
                        else:
                            print(f"   ⚠️  订单已不存在或已成交，状态: {order_status}")
                    except Exception as e1:
                        # 如果不是普通订单，可能是条件单，尝试查询条件单
                        try:
                            # 查询条件单状态
                            params = {'ordType': 'conditional'}
                            response = self.trader.exchange.private_get_trade_orders_algo_pending(params)
                            query_success = True
                            if response.get('code') == '0' and response.get('data'):
                                found = False
                                for algo_data in response['data']:
                                    algo_id = algo_data.get('algoId', '')
                                    if str(algo_id) == str(self.pending_entry_order_id):
                                        found = True
                                        state = algo_data.get('state', '')
                                        if state == 'live':
                                            order_still_exists = True
                                            print(f"   ✅ 条件单仍存在，状态: {state}")
                                        else:
                                            print(f"   ⚠️  条件单已不存在，状态: {state}")
                                        break
                                if not found:
                                    print(f"   ⚠️  条件单不存在于待处理列表中")
                        except Exception as e2:
                            print(f"   ⚠️  查询条件单状态失败: {e2}")
                    
                    # 方法2: 查询所有未成交订单，检查是否有相同价格的挂单
                    if not order_still_exists:
                        try:
                            print(f"   🔍 查询所有未成交订单，检查是否有相同价格的挂单...")
                            open_orders = self.trader.exchange.fetch_open_orders(self.symbol)
                            
                            # 检查是否有相同价格的挂单（允许0.01的误差）
                            for order in open_orders:
                                order_price = self.safe_float(order.get('price'))
                                order_side = order.get('side', '').lower()
                                order_amount = self.safe_float(order.get('amount'))
                                
                                # 检查方向：做空应该是sell
                                if order_price and order_side == 'sell':
                                    price_diff = abs(order_price - entry_price)
                                    amount_diff = abs(order_amount - coin_amount) if order_amount else 999
                                    
                                    if price_diff < 0.01 and amount_diff < 0.01:
                                        same_price_order_exists = True
                                        print(f"   ✅ 发现相同价格的未成交挂单: 订单ID={order.get('id')}, 价格=${order_price:.2f}, 数量={order_amount}{self.config.get('long_coin', 'coin')}")
                                        # 更新记录的订单ID（可能订单ID变了，但价格和数量相同）
                                        if order.get('id') != self.pending_entry_order_id:
                                            print(f"   🔄 更新记录的订单ID: {self.pending_entry_order_id} → {order.get('id')}")
                                            self.pending_entry_order_id = order.get('id')
                                        break
                            
                            if not same_price_order_exists:
                                print(f"   ⚠️  未找到相同价格的未成交挂单")
                        except Exception as e3:
                            print(f"   ⚠️  查询未成交订单失败: {e3}")
                    
                    # 方法3: 查询条件单列表，检查是否有相同价格的挂单
                    if not order_still_exists and not same_price_order_exists:
                        try:
                            print(f"   🔍 查询所有条件单，检查是否有相同价格的挂单...")
                            params = {'ordType': 'conditional'}
                            response = self.trader.exchange.private_get_trade_orders_algo_pending(params)
                            if response.get('code') == '0' and response.get('data'):
                                for algo_data in response['data']:
                                    algo_id = algo_data.get('algoId', '')
                                    trigger_price = self.safe_float(algo_data.get('triggerPx'))
                                    order_price = self.safe_float(algo_data.get('orderPx'))
                                    algo_amount = self.safe_float(algo_data.get('sz'))
                                    side = algo_data.get('side', '').lower()
                                    
                                    # 检查方向：做空应该是sell
                                    # 使用触发价或委托价进行比较
                                    check_price = order_price if order_price else trigger_price
                                    
                                    if check_price and side == 'sell':
                                        price_diff = abs(check_price - entry_price)
                                        amount_diff = abs(algo_amount - coin_amount) if algo_amount else 999
                                        
                                        if price_diff < 0.01 and amount_diff < 0.01:
                                            same_price_order_exists = True
                                            print(f"   ✅ 发现相同价格的条件单: 订单ID={algo_id}, 价格=${check_price:.2f}, 数量={algo_amount}{self.config.get('long_coin', 'coin')}")
                                            # 更新记录的订单ID
                                            if str(algo_id) != str(self.pending_entry_order_id):
                                                print(f"   🔄 更新记录的订单ID: {self.pending_entry_order_id} → {algo_id}")
                                                self.pending_entry_order_id = algo_id
                                            break
                        except Exception as e4:
                            print(f"   ⚠️  查询条件单列表失败: {e4}")
                            
                except Exception as e:
                    print(f"   ⚠️  检查订单状态异常: {e}")
                
                # 🔴 判断是否应该跳过挂单
                if order_still_exists or same_price_order_exists:
                    # 订单存在或找到相同价格的挂单，比较金额和价格
                    print(f"   新信号金额: {coin_amount} {self.config.get('long_coin', 'coin')}")
                    print(f"   新信号价格: ${entry_price:.2f}")
                    
                    # 比较金额（允许0.01的误差，因为精度问题）
                    amount_diff = abs(self.pending_entry_amount - coin_amount)
                    price_diff = abs(self.pending_entry_price - entry_price)
                    
                    if amount_diff < 0.01 and price_diff < 0.01:
                        print(f"✅ 挂单币数量和价格一致，无需重新挂单")
                        print(f"   金额差异: {amount_diff:.4f} (≤ 0.01)")
                        print(f"   价格差异: ${price_diff:.2f} (≤ $0.01)")
                        should_place_new_order = False
                    else:
                        print(f"⚠️  挂单币数量或价格不一致，需要取消旧单并重新挂单")
                        print(f"   金额差异: {amount_diff:.4f}")
                        print(f"   价格差异: ${price_diff:.2f}")
                        
                        # 取消旧订单
                        try:
                            print(f"🔄 取消旧挂单: {self.pending_entry_order_id}")
                            # 检查订单类型（可能是限价单或条件单）
                            try:
                                # 先尝试作为普通订单取消
                                self.trader.exchange.cancel_order(self.pending_entry_order_id, self.symbol)
                                print(f"✅ 已取消旧挂单（限价单）")
                            except Exception as e1:
                                # 如果不是普通订单，可能是条件单
                                if 'conditional' in str(e1).lower() or 'algo' in str(e1).lower():
                                    print(f"🔄 尝试作为条件单取消...")
                                    self.trader._cancel_conditional_order(self.pending_entry_order_id, self.symbol)
                                    print(f"✅ 已取消旧挂单（条件单）")
                                else:
                                    print(f"⚠️  取消旧挂单失败: {e1}")
                                    # 继续执行，尝试挂新单
                        except Exception as e:
                            print(f"⚠️  取消旧挂单异常: {e}")
                            # 继续执行，尝试挂新单
                        
                        # 清空记录
                        self.pending_entry_order_id = None
                        self.pending_entry_amount = None
                        self.pending_entry_price = None
                        print(f"   🔄 清空挂单记录A")
                elif query_success:
                    # 查询成功但订单不存在，清空记录
                    print(f"   🔄 订单已不存在，清空挂单记录")
                    self.pending_entry_order_id = None
                    self.pending_entry_amount = None
                    self.pending_entry_price = None
                    print(f"   🔄 清空挂单记录B")
                else:
                    # 查询失败，保留记录，不挂新单（避免重复挂单）
                    print(f"   ⚠️  查询订单状态失败，为安全起见保留记录，不挂新单")
                    print(f"   💡 等待下次检查时再确认订单状态")
                    should_place_new_order = False
            
            if not should_place_new_order:
                print(f"⏭️  跳过挂单，使用现有挂单")
                return
            
            print(f"🔍 开始调用OKX接口开空单...")
            
            # 🔴 根据开仓类型选择不同的挂单方式
            if entry_type == 'limit':
                # 支撑位/阻力位限价单：在指定价格挂限价单
                print(f"📌 【限价单模式】在支撑位/阻力位价格 ${entry_price:.2f} 挂限价单")
                result = self.trader.open_short_with_limit_price(
                    self.symbol,
                    contract_amount,
                    entry_price,  # 使用指定的支撑位/阻力位价格
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit
                )
            else:
                # 立即挂单模式：使用买3/卖3价格
                print(f"⚡ 【立即挂单模式】使用买3/卖3价格挂单")
                result = self.trader.open_short_with_stop_orders(
                    self.symbol,
                    contract_amount,
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit
                )
            
            print(f"\n🔍 OKX开空单返回结果:")
            print(f"   入场订单: {result.get('entry_order')}")
            print(f"   止损订单: {result.get('stop_loss_order')} (将在开仓成交后挂单)")
            print(f"   止盈订单: {result.get('take_profit_order')} (将在开仓成交后挂单)")
            
            # 🔴 记录挂单信息和止盈止损价格（无论是否成交）
            if result.get('entry_order'):
                entry_order = result['entry_order']
                order_id = entry_order.get('id')
                order_status = entry_order.get('status', 'unknown')
                
                # 🔴 记录止盈止损价格（等待开仓成交后挂单）
                self.pending_stop_loss_price = stop_loss
                self.pending_take_profit_price = take_profit
                self.pending_entry_side = 'short'
                print(f"📝 记录待挂止损止盈价格: 止损=${stop_loss:.2f}, 止盈=${take_profit:.2f}")
                
                # 检查订单是否已成交
                if order_status == 'closed' or order_status == 'filled':
                    # 已成交，立即挂止损止盈单
                    print(f"✅ 开仓订单已成交，立即挂止损止盈单")
                    self._place_stop_orders_after_entry('short', coin_amount, stop_loss, take_profit)
                    # 清空挂单记录
                    self.pending_entry_order_id = None
                    self.pending_entry_amount = None
                    self.pending_entry_price = None
                    self.pending_stop_loss_price = None
                    self.pending_take_profit_price = None
                    self.pending_entry_side = None
                    print(f"   🔄 清空挂单记录C")
                else:
                    # 未成交，记录挂单信息
                    print(f"📝 记录挂单信息: 订单ID={order_id}, 币数量={coin_amount}{self.config.get('long_coin', 'coin')}, 价格=${entry_price:.2f}")
                    self.pending_entry_order_id = order_id
                    self.pending_entry_amount = coin_amount
                    self.pending_entry_price = entry_price
            
            if result['entry_order']:
                self.current_position = 'short'
                self.current_position_side = 'short'
                self.current_position_contracts = contract_amount
                self.current_position_shares = coin_amount
                self.daily_stats['total_trades'] += 1
                
                self.logger.log(f"✅ 开空单成功")
                self.logger.log(f"   止损单: {result['stop_loss_order']['id'] if result['stop_loss_order'] else '未设置'}")
                self.logger.log(f"   止盈单: {result['take_profit_order']['id'] if result['take_profit_order'] else '未设置'}")
                
                # 🔴 同步真实交易数据到策略
                trade_data = {
                    'position': 'short',
                    'entry_price': entry_price,
                    'position_shares': coin_amount,
                    'stop_loss_price': stop_loss,
                    'take_profit_price': take_profit,
                    'invested_amount': actual_invested,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                trade_data['position_shares'] = coin_amount
                self.strategy.sync_real_trade_data(trade_data)
                
                # 🔴 保存开仓订单到数据库
                if self._is_trading_db_available():
                    try:
                        # 1. 保存开仓订单
                        entry_order_id = result['entry_order']['id']
                        self.trading_db.save_order(
                            order_id=entry_order_id,
                            symbol=self.symbol,
                            order_type='MARKET',
                            side='sell',
                            position_side='short',
                            amount=contract_amount,
                            price=entry_price,
                            status='filled',
                            invested_amount=actual_invested,
                            order_time=datetime.now(),
                            filled_time=datetime.now()
                        )
                        
                        # 2. 保存交易记录（无论止损单是否设置成功都要保存）
                        # 🔴 根据entry_type设置open_reason
                        open_reason = '标准VIDYA' if entry_type == 'limit' else '布林带角度'
                        trade_id = self.trading_db.save_trade(
                            symbol=self.symbol,
                            position_side='short',
                            entry_order_id=entry_order_id,
                            entry_price=entry_price,
                            entry_time=datetime.now(),
                            amount=contract_amount,
                            invested_amount=actual_invested,
                            status='open',
                            open_reason=open_reason  # 🔴 保存开仓原因
                        )
                        
                        # 🔴 保存到实例变量，供后续更新使用
                        self.current_trade_id = trade_id
                        self.current_entry_order_id = entry_order_id
                        
                        print(f"💾 已保存: 开仓订单({entry_order_id}) + 交易记录(ID={trade_id})")
                        
                        # 3. 保存止损单到 okx_stop_orders（不保存到 okx_orders）
                        if result['stop_loss_order']:
                            stop_loss_order_id = result['stop_loss_order']['id']
                            
                            self.trading_db.save_stop_order(
                                order_id=stop_loss_order_id,
                                symbol=self.symbol,
                                trade_id=trade_id,
                                entry_order_id=entry_order_id,
                                order_type='STOP_LOSS',
                                position_side='short',
                                trigger_price=stop_loss,
                                amount=contract_amount,
                                status='active'
                            )
                            
                            self.current_stop_loss_order_id = stop_loss_order_id
                            print(f"💾 已保存: 止损单({stop_loss_order_id}) → okx_stop_orders")
                        
                        # 4. 保存止盈单到 okx_stop_orders（不保存到 okx_orders）
                        if result['take_profit_order']:
                            take_profit_order_id = result['take_profit_order']['id']
                            
                            self.trading_db.save_stop_order(
                                order_id=take_profit_order_id,
                                symbol=self.symbol,
                                trade_id=trade_id,
                                entry_order_id=entry_order_id,
                                order_type='TAKE_PROFIT',
                                position_side='short',
                                trigger_price=take_profit,
                                amount=contract_amount,
                                status='active'
                            )
                            
                            self.current_take_profit_order_id = take_profit_order_id
                            print(f"💾 已保存: 止盈单({take_profit_order_id}) → okx_stop_orders")
                        
                        print(f"✅ 所有订单已保存: okx_orders(开仓) + okx_stop_orders(止损/止盈)")
                    except Exception as e:
                        print(f"❌ 保存订单到数据库失败: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"⚠️  交易数据库未连接，跳过保存订单")
        
        # 🔴 平仓信号 - V2版本不处理（止损止盈单已挂在OKX，由OKX自动执行）
        elif signal_type in ['STOP_LOSS_LONG', 'TAKE_PROFIT_LONG', 'STOP_LOSS_SHORT', 'TAKE_PROFIT_SHORT']:
            profit_loss = signal.get('profit_loss', 0)
            exit_price = signal.get('price', 0)
            exit_timestamp = signal.get('exit_timestamp', datetime.now())
            exit_reason = signal.get('reason', signal_type)
            
            print(f"\n📊 ========== 平仓信号（仅记录，不执行） ==========")
            print(f"📊 信号类型: {signal_type}")
            print(f"📊 当前持仓: {self.current_position}")
            print(f"📊 持仓数量: {self.current_position_shares}")
            print(f"📊 平仓原因: {exit_reason}")
            print(f"💡 V2版本: 止损止盈单已挂在OKX，由交易所自动执行")
            print(f"💡 SAR转换信号会主动平仓并反手开仓")
            
            # 🔴 直接返回，不执行平仓操作
            return
            
            # 🔴 判断是否需要主动平仓
            # 如果原因包含"SAR方向转换"，说明不是止损/止盈单触发，需要主动平仓
            need_market_close = 'SAR方向转换' in exit_reason or 'SAR转' in exit_reason
            
            actual_exit_price = exit_price
            actual_exit_order_id = None
            
            if need_market_close and self.current_position:
                print(f"🔴 需要主动市价平仓: {self.current_position}")
                
                try:
                    # 发送市价平仓订单
                    if self.current_position == 'long':
                        params = {'posSide': 'long', 'reduceOnly': True}
                        close_order = self.trader.exchange.create_market_sell_order(
                            self.symbol, 
                            self.current_position_shares,
                            params
                        )
                    else:  # short
                        params = {'posSide': 'short', 'reduceOnly': True}
                        close_order = self.trader.exchange.create_market_buy_order(
                            self.symbol,
                            self.current_position_shares,
                            params
                        )
                    
                    print(f"✅ 市价平仓成功: 订单ID={close_order['id']}")
                    actual_exit_order_id = close_order['id']
                    
                    # 获取实际成交价格
                    time.sleep(1.0)  # 等待订单成交
                    order_info = self.trader.exchange.fetch_order(close_order['id'], self.symbol)
                    if order_info and order_info.get('average'):
                        actual_exit_price = float(order_info['average'])
                        print(f"📊 实际成交价格: ${actual_exit_price:.2f}")
                    
                except Exception as e:
                    print(f"❌ 市价平仓失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 取消所有止损止盈单
            self.trader.cancel_all_stop_orders(self.symbol)
            
            # 🔴 更新数据库中的交易记录 + 重新计算实际盈亏
            try:
                if self.current_trade_id and actual_exit_order_id:
                    print(f"💾 更新交易记录: trade_id={self.current_trade_id}")
                    
                    # 从数据库获取开仓信息
                    trade = self.trading_db.get_open_trade(self.symbol)
                    if trade:
                        entry_price_db = trade.entry_price
                        invested_amount = trade.invested_amount
                        amount = trade.amount
                        
                        # 🔴 计算实际盈亏（使用实际成交价格）
                        if self.current_position == 'long':
                            actual_profit_loss = (actual_exit_price - entry_price_db) * amount * 0.01
                        else:  # short
                            actual_profit_loss = (entry_price_db - actual_exit_price) * amount * 0.01
                        
                        # 估算手续费（开仓+平仓，taker费率0.05%）
                        entry_fee = invested_amount * 0.0005
                        exit_fee = invested_amount * 0.0005
                        funding_fee = 0.0  # 资金费暂时忽略
                        
                        total_fee = entry_fee + exit_fee + funding_fee
                        net_profit_loss = actual_profit_loss - total_fee
                        return_rate = (net_profit_loss / invested_amount) * 100
                        
                        print(f"📊 实际盈亏计算:")
                        print(f"   开仓价: ${entry_price_db:.2f}")
                        print(f"   平仓价: ${actual_exit_price:.2f}")
                        print(f"   数量: {amount}张")
                        print(f"   毛盈亏: ${actual_profit_loss:.2f}")
                        print(f"   手续费: ${total_fee:.2f}")
                        print(f"   净盈亏: ${net_profit_loss:.2f}")
                        print(f"   收益率: {return_rate:.2f}%")
                        
                        # 🔴 保存平仓订单到 okx_orders
                        self.trading_db.save_order(
                            order_id=actual_exit_order_id,
                            symbol=self.symbol,
                            order_type='MARKET',
                            side='sell' if self.current_position == 'long' else 'buy',
                            position_side=self.current_position,
                            amount=amount,
                            price=actual_exit_price,
                            status='filled',
                            parent_order_id=self.current_entry_order_id,
                            order_time=exit_timestamp,
                            filled_time=exit_timestamp
                        )
                        print(f"💾 已保存: 平仓订单({actual_exit_order_id}) → okx_orders")
                        
                        # 更新交易记录
                        self.trading_db.close_okx_trade(
                            trade_id=self.current_trade_id,
                            exit_order_id=actual_exit_order_id,
                            exit_price=actual_exit_price,
                            exit_time=exit_timestamp,
                            exit_reason=exit_reason,
                            entry_fee=entry_fee,
                            exit_fee=exit_fee,
                            funding_fee=funding_fee
                        )
                        
                        # 更新统计（使用实际盈亏）
                        self.daily_stats['total_pnl'] += net_profit_loss
                        if net_profit_loss > 0:
                            self.daily_stats['winning_trades'] += 1
                        else:
                            self.daily_stats['losing_trades'] += 1
                        
                        # 🔴 发送钉钉通知（使用实际盈亏）
                        if hasattr(self.strategy, 'dingtalk_notifier') and self.strategy.dingtalk_notifier:
                            profit_type = "盈利" if net_profit_loss > 0 else "亏损"
                            self.strategy.dingtalk_notifier.send_close_position_message(
                                position_side=self.current_position,
                                entry_price=entry_price_db,
                                exit_price=actual_exit_price,
                                profit_loss=net_profit_loss,
                                return_rate=return_rate,
                                reason=exit_reason
                            )
                        
                        self.logger.log(f"✅ 平仓完成: 实际盈亏 ${net_profit_loss:+,.2f} ({return_rate:+.2f}%)")
                    else:
                        print(f"⚠️  未找到开仓记录")
                else:
                    print(f"⚠️  缺少必要信息: trade_id={self.current_trade_id}, exit_order_id={actual_exit_order_id}")
                
            except Exception as e:
                print(f"❌ 更新交易记录失败: {e}")
                import traceback
                traceback.print_exc()
            
                # 更新统计（使用策略计算的盈亏作为fallback）
            self.daily_stats['total_pnl'] += profit_loss
            if profit_loss > 0:
                self.daily_stats['winning_trades'] += 1
            else:
                self.daily_stats['losing_trades'] += 1
            
            # 清空持仓记录
            self.current_position = None
            self.current_position_side = None
            self.current_position_contracts = 0
            self.current_position_shares = 0
            self.current_trade_id = None
            self.current_entry_order_id = None
            self.current_stop_loss_order_id = None
            self.current_take_profit_order_id = None
            
            # 🔴 同步清理策略对象的持仓状态（重要！）
            # 当OKX止损单触发时，策略对象并不知道，需要手动清理
            print(f"🔍 清理策略对象持仓状态: {self.strategy.position} → None")
            self.strategy.position = None
            self.strategy.entry_price = None
            self.strategy.stop_loss_level = None
            self.strategy.take_profit_level = None
            self.strategy.max_loss_level = None
            self.strategy.current_invested_amount = None
            self.strategy.position_shares = None
            
            # 🔴 平仓后立即更新账户余额
            self._update_account_balance()
            
            self.logger.log(f"✅ 平仓完成: 盈亏 ${profit_loss:+,.2f}")
        
        # 🔴 更新止损位
        elif signal_type == 'UPDATE_STOP_LOSS':
            # 🔴 从信号中获取新止损价（优先使用 new_stop_loss，兼容 price 字段）
            new_stop_loss = signal.get('new_stop_loss') or signal.get('price')
            new_stop_loss = round(new_stop_loss, 1) if new_stop_loss is not None else None  # 保留1位小数
            
            # 🔴 获取旧止损价（优先从信号，其次从策略）
            old_stop_loss = signal.get('old_stop_loss')
            if old_stop_loss is None:
                # 从策略获取当前止损价
                if hasattr(self.strategy, 'stop_loss_level') and self.strategy.stop_loss_level is not None:
                    old_stop_loss = self.strategy.stop_loss_level
                    print(f"   📊 从策略获取旧止损价: ${old_stop_loss:.2f}")
                else:
                    print(f"   ⚠️  策略中无止损价记录")
            
            old_stop_loss = round(old_stop_loss, 1) if old_stop_loss is not None else None  # 保留1位小数
            
            print(f"\n🔍 ========== UPDATE_STOP_LOSS 信号处理 ==========")
            print(f"🔍 当前持仓: {self.current_position}")
            print(f"🔍 新止损: {new_stop_loss}")
            print(f"🔍 旧止损: {old_stop_loss}")
            print(f"🔍 current_trade_id: {self.current_trade_id}")
            print(f"🔍 current_entry_order_id: {self.current_entry_order_id}")
            print(f"🔍 current_stop_loss_order_id: {self.current_stop_loss_order_id}")
            print(f"🔍 pending_entry_order_id: {self.pending_entry_order_id}")
            
            if not self.current_position:
                print(f"❌ 跳过止损更新: 当前无持仓")
                return
            
            if not new_stop_loss:
                print(f"❌ 跳过止损更新: 新止损价格为空")
                return
            
            # 🔴 检查是否有待成交的开仓订单
            if self.pending_entry_order_id is not None:
                print(f"⚠️  检测到有待成交的开仓订单: {self.pending_entry_order_id}")
                print(f"   💡 开仓订单还未成交，等待成交后再挂止损单")
                
                # 🔴 查询OKX实际持仓状态，确认是否真的没有持仓
                try:
                    positions = self.trader.exchange.fetch_positions([self.symbol])
                    has_okx_position = False
                    for pos in positions:
                        contracts = self.safe_float(pos.get('contracts'))
                        size = self.safe_float(pos.get('size'))
                        pos_side = pos.get('side', '')
                        
                        if (contracts > 0 or size > 0) and pos_side == self.current_position:
                            has_okx_position = True
                            print(f"   ✅ OKX有实际持仓: {pos_side}, 数量={contracts if contracts > 0 else size}张")
                            break
                    
                    if not has_okx_position:
                        print(f"   ❌ OKX无实际持仓，跳过挂止损单")
                        print(f"   💡 等待开仓订单成交后，通过定时检查机制自动挂止损单")
                        return
                    else:
                        print(f"   ✅ OKX有实际持仓，可以挂止损单")
                        # 清空待成交订单记录，因为已经有持仓了
                        self.pending_entry_order_id = None
                        self.pending_entry_amount = None
                        self.pending_entry_price = None
                        print(f"   🔄 清空待成交订单记录D")
                except Exception as e:
                    print(f"   ⚠️  查询OKX持仓状态失败: {e}")
                    print(f"   💡 为安全起见，跳过挂止损单，等待开仓订单成交后再挂")
                    return
            
            # 🔴 比较新旧止损价，如果有变化才更新
            if old_stop_loss is not None and abs(new_stop_loss - old_stop_loss) < 0.01:  # 价格差异小于0.01，认为是相同价格
                print(f"✅ 跳过止损更新: 新止损价${new_stop_loss:.2f}与旧止损价${old_stop_loss:.2f}相同，无需更新")
                return
            
            if old_stop_loss is not None:
                print(f"🔄 止损价变化: ${old_stop_loss:.2f} → ${new_stop_loss:.2f}")
            else:
                print(f"🔄 首次设置止损价: ${new_stop_loss:.2f}")
            
            if self.current_position and new_stop_loss:
                print(f"🔍 开始调用OKX接口更新止损...")
                # 撤销旧止损单，挂新止损单
                result = self.trader.update_stop_loss(
                    self.symbol,
                    self.current_position_side,
                    new_stop_loss,
                    self.current_position_shares
                )
                
                print(f"🔍 OKX接口返回结果: {result}")
                print(f"🔍 result类型: {type(result)}")
                
                # 🔴 先同步止损价格更新到策略（无论是否保存到数据库）
                if result:
                    # 更新策略中的止损价
                    self.strategy.sync_stop_loss_update(new_stop_loss)
                    print(f"✅ 策略止损价已更新: ${new_stop_loss:.2f}")
                
                # 🔴 保存止损单更新记录到数据库（只保存到okx_stop_orders，不保存到okx_orders）
                try:
                    print(f"🔍 检查保存条件:")
                    print(f"   - result存在: {result is not None}")
                    print(f"   - 'id' in result: {'id' in result if result else False}")
                    print(f"   - current_trade_id存在: {self.current_trade_id is not None}")
                    
                    # 🔴 获取订单ID（优先从 result 的 id 字段，如果没有则尝试从 result 本身获取）
                    order_id = None
                    if result:
                        if isinstance(result, dict):
                            order_id = result.get('id')
                        elif hasattr(result, 'id'):
                            order_id = result.id
                    
                    if order_id and self.current_trade_id:
                        print(f"💾 更新止损单记录: 旧止损=${old_stop_loss:.1f} → 新止损=${new_stop_loss:.1f}")
                        print(f"💾 trade_id={self.current_trade_id}, old_order_id={self.current_stop_loss_order_id}")
                        
                        new_order_id = order_id
                        
                        # 保存止损单更新记录到okx_stop_orders表
                        # 注意：okx_orders只记录实际成交的订单（开仓/平仓），不记录条件单
                        self.trading_db.save_stop_order(
                            order_id=new_order_id,
                            symbol=self.symbol,
                            trade_id=self.current_trade_id,
                            entry_order_id=self.current_entry_order_id,
                            order_type='STOP_LOSS',
                            position_side=self.current_position,
                            trigger_price=new_stop_loss,
                            amount=self.current_position_shares,
                            status='active',
                            old_trigger_price=old_stop_loss,
                            update_reason=signal.get('reason', '周期结束更新止损单')
                        )
                        
                        # 更新当前止损单ID
                        self.current_stop_loss_order_id = new_order_id
                        
                        print(f"💾 ✅ 止损单更新已保存到okx_stop_orders表: new_order_id={new_order_id}")
                    else:
                        print(f"❌ 保存条件不满足，跳过数据库保存")
                        if not result:
                            print(f"   原因: OKX接口返回为空")
                        elif 'id' not in result:
                            print(f"   原因: result中没有'id'字段")
                        elif not self.current_trade_id:
                            print(f"   原因: current_trade_id为空")
                        
                except Exception as e:
                    print(f"❌ 保存止损单更新失败: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"❌ 跳过止损更新:")
                if not self.current_position:
                    print(f"   原因: 当前无持仓")
                if not new_stop_loss:
                    print(f"   原因: 新止损价格为空")
                
            if new_stop_loss:
                self.logger.log(f"🔄 止损位已更新: ${new_stop_loss:.1f}")
    
    def check_stop_orders_status(self):
        """检查止损/止盈单状态（定期调用）
        
        比检查持仓更可靠，因为即使持仓立即换成新的，也能检测到旧订单的触发
        """
        # 只在有持仓且有止损单时检查
        if not self.current_position:
            return
        
        if not self.current_stop_loss_order_id and not self.current_take_profit_order_id:
            return
        
        try:
            # 检查止损单状态
            if self.current_stop_loss_order_id:
                try:
                    stop_order = self.trader.exchange.fetch_order(
                        self.current_stop_loss_order_id,
                        self.symbol
                    )
                    
                    # 如果止损单已触发（状态变为 closed/filled）或失败（状态为 error）
                    if stop_order['status'] in ['closed', 'filled', 'error']:
                        self.logger.log(f"🚨 检测到止损单触发: {self.current_stop_loss_order_id} (状态: {stop_order['status']})")
                        self._handle_stop_order_triggered(stop_order, 'STOP_LOSS')
                        return
                        
                except Exception as e:
                    error_msg = str(e)
                    # 如果订单不存在，说明可能已被触发并删除
                    if '51603' in error_msg or 'does not exist' in error_msg.lower():
                        self.logger.log(f"⚠️  止损单不存在(可能已触发): {self.current_stop_loss_order_id}")
                        # 通过查询持仓来确认是否已平仓
                        try:
                            positions = self.trader.exchange.fetch_positions([self.symbol])
                            has_position = any(
                                (self.safe_float(pos.get('contracts')) > 0 or 
                                 self.safe_float(pos.get('size')) > 0 or 
                                 self.safe_float(pos.get('notional')) > 0)
                                for pos in positions 
                                if (pos.get('symbol', '') == self.symbol or 
                                    pos.get('info', {}).get('instId', '') == self.symbol or
                                    pos.get('symbol', '') == self.symbol.replace('-', '/') or
                                    pos.get('info', {}).get('instId', '') == self.symbol.replace('-', '/') or
                                    pos.get('symbol', '') == self.symbol.replace('-', '/') + ':USDT' or
                                    pos.get('info', {}).get('instId', '') == self.symbol.replace('-', '/') + ':USDT')
                            )
                            
                            if not has_position:
                                self.logger.log(f"🚨 确认持仓已平，止损单已触发，但无法获取订单详情")
                                
                                # 清空状态
                                self._clear_position_state()
                                
                                # 🔴 平仓后更新账户余额
                                self._update_account_balance()
                                
                                return
                        except Exception as pos_e:
                            self.logger.log_error(f"查询持仓失败: {pos_e}")
                    else:
                        raise  # 其他错误继续抛出
            
            # 检查止盈单（如果有）
            if self.current_take_profit_order_id:
                try:
                    tp_order = self.trader.exchange.fetch_order(
                        self.current_take_profit_order_id,
                        self.symbol
                    )
                    
                    if tp_order['status'] in ['closed', 'filled', 'error']:
                        self.logger.log(f"🚨 检测到止盈单触发: {self.current_take_profit_order_id} (状态: {tp_order['status']})")
                        self._handle_stop_order_triggered(tp_order, 'TAKE_PROFIT')
                        return
                        
                except Exception as e:
                    error_msg = str(e)
                    # 如果订单不存在，说明可能已被触发并删除
                    if '51603' in error_msg or 'does not exist' in error_msg.lower():
                        self.logger.log(f"⚠️  止盈单不存在(可能已触发): {self.current_take_profit_order_id}")
                        # 通过查询持仓来确认是否已平仓
                        try:
                            positions = self.trader.exchange.fetch_positions([self.symbol])
                            has_position = any(
                                (self.safe_float(pos.get('contracts')) > 0 or 
                                 self.safe_float(pos.get('size')) > 0 or 
                                 self.safe_float(pos.get('notional')) > 0)
                                for pos in positions 
                                if (pos.get('symbol', '') == self.symbol or 
                                    pos.get('info', {}).get('instId', '') == self.symbol or
                                    pos.get('symbol', '') == self.symbol.replace('-', '/') or
                                    pos.get('info', {}).get('instId', '') == self.symbol.replace('-', '/') or
                                    pos.get('symbol', '') == self.symbol.replace('-', '/') + ':USDT' or
                                    pos.get('info', {}).get('instId', '') == self.symbol.replace('-', '/') + ':USDT')
                            )
                            
                            if not has_position:
                                self.logger.log(f"🚨 确认持仓已平，止盈单已触发，但无法获取订单详情")
                                
                                # 清空状态
                                self._clear_position_state()
                                
                                # 🔴 平仓后更新账户余额
                                self._update_account_balance()
                                
                                return
                        except Exception as pos_e:
                            self.logger.log_error(f"查询持仓失败: {pos_e}")
                    else:
                        raise  # 其他错误继续抛出
                    
        except Exception as e:
            self.logger.log_error(f"检查止盈/止损单状态失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _check_pending_close(self):
        """检查是否有待处理的平仓（在开仓前调用）
        
        如果发现旧仓位已被平仓但未处理，立即处理并更新数据库
        """
        try:
            if not self.current_stop_loss_order_id and not self.current_take_profit_order_id:
                print(f"⚠️  没有止损/止盈单记录，跳过检查")
                return
            
            # 查询旧的止损单状态
            if self.current_stop_loss_order_id:
                try:
                    stop_order = self.trader.exchange.fetch_order(
                        self.current_stop_loss_order_id,
                        self.symbol
                    )
                    
                    # 如果已触发但未处理
                    if stop_order['status'] in ['closed', 'filled', 'error']:
                        print(f"🚨 发现未处理的止损单触发，立即处理... (状态: {stop_order['status']})")
                        self._handle_stop_order_triggered(stop_order, 'STOP_LOSS')
                        return
                        
                except Exception as e:
                    error_msg = str(e)
                    # 如果订单不存在，说明可能已被触发并删除
                    if '51603' in error_msg or 'does not exist' in error_msg.lower():
                        print(f"⚠️  止损单不存在(可能已触发): {self.current_stop_loss_order_id}")
                        
                        # 🔴 只有在检测到OKX没有实际持仓时才清空持仓状态
                        try:
                            positions = self.trader.exchange.fetch_positions([self.symbol])
                            has_actual_position = any(
                                (self.safe_float(pos.get('contracts')) > 0 or 
                                 self.safe_float(pos.get('size')) > 0 or 
                                 self.safe_float(pos.get('notional')) > 0)
                                for pos in positions 
                                if (pos.get('symbol', '') == self.symbol or 
                                    pos.get('info', {}).get('instId', '') == self.symbol or
                                    pos.get('symbol', '') == self.symbol.replace('-', '/') or
                                    pos.get('info', {}).get('instId', '') == self.symbol.replace('-', '/') or
                                    pos.get('symbol', '') == self.symbol.replace('-', '/') + ':USDT' or
                                    pos.get('info', {}).get('instId', '') == self.symbol.replace('-', '/') + ':USDT')
                            )
                            
                            if not has_actual_position:
                                print(f"✅ 确认OKX无持仓，清空程序状态...")
                                self._clear_position_state()
                                self._update_account_balance()
                            else:
                                print(f"⚠️  OKX仍有持仓，不清空程序状态")
                        except Exception as pos_e:
                            print(f"❌ 检查OKX持仓失败: {pos_e}")
                            print(f"⚠️  为了安全，不清空程序状态")
                        
                        return
                    else:
                        raise  # 其他错误继续抛出
            
            # 查询止盈单状态
            if self.current_take_profit_order_id:
                try:
                    tp_order = self.trader.exchange.fetch_order(
                        self.current_take_profit_order_id,
                        self.symbol
                    )
                    
                    if tp_order['status'] in ['closed', 'filled', 'error']:
                        print(f"🚨 发现未处理的止盈单触发，立即处理... (状态: {tp_order['status']})")
                        self._handle_stop_order_triggered(tp_order, 'TAKE_PROFIT')
                        return
                        
                except Exception as e:
                    error_msg = str(e)
                    # 如果订单不存在，说明可能已被触发并删除
                    if '51603' in error_msg or 'does not exist' in error_msg.lower():
                        print(f"⚠️  止盈单不存在(可能已触发): {self.current_take_profit_order_id}")
                        
                        # 🔴 只有在检测到OKX没有实际持仓时才清空持仓状态
                        try:
                            positions = self.trader.exchange.fetch_positions([self.symbol])
                            has_actual_position = any(
                                (self.safe_float(pos.get('contracts')) > 0 or 
                                 self.safe_float(pos.get('size')) > 0 or 
                                 self.safe_float(pos.get('notional')) > 0)
                                for pos in positions 
                                if (pos.get('symbol', '') == self.symbol or 
                                    pos.get('info', {}).get('instId', '') == self.symbol or
                                    pos.get('symbol', '') == self.symbol.replace('-', '/') or
                                    pos.get('info', {}).get('instId', '') == self.symbol.replace('-', '/') or
                                    pos.get('symbol', '') == self.symbol.replace('-', '/') + ':USDT' or
                                    pos.get('info', {}).get('instId', '') == self.symbol.replace('-', '/') + ':USDT')
                            )
                            
                            if not has_actual_position:
                                print(f"✅ 确认OKX无持仓，清空程序状态...")
                                self._clear_position_state()
                                self._update_account_balance()
                            else:
                                print(f"⚠️  OKX仍有持仓，不清空程序状态")
                        except Exception as pos_e:
                            print(f"❌ 检查OKX持仓失败: {pos_e}")
                            print(f"⚠️  为了安全，不清空程序状态")
                        
                        return
                    else:
                        raise  # 其他错误继续抛出
            
            print(f"✅ 未发现未处理的平仓")
                    
        except Exception as e:
            print(f"❌ 检查待处理平仓失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _handle_stop_order_triggered(self, triggered_order, order_type):
        """处理止损/止盈单触发
        
        Args:
            triggered_order: OKX返回的订单信息
            order_type: 'STOP_LOSS' 或 'TAKE_PROFIT'
        """
        try:
            print(f"\n{'='*80}")
            print(f"🔔 处理{order_type}单触发")
            print(f"{'='*80}")
            
            # 获取平仓详情
            exit_order_id = triggered_order['id']
            exit_price = float(triggered_order.get('average', triggered_order.get('price', 0)))
            exit_time = datetime.fromtimestamp(triggered_order['timestamp'] / 1000) if triggered_order.get('timestamp') else datetime.now()
            exit_reason = f"{'止损' if order_type == 'STOP_LOSS' else '止盈'}单触发"
            
            print(f"📊 平仓信息:")
            print(f"   订单ID: {exit_order_id}")
            print(f"   平仓价: ${exit_price:.2f}")
            print(f"   平仓时间: {exit_time}")
            print(f"   原因: {exit_reason}")
            
            # 从数据库获取开仓信息
            trade = self.trading_db.get_open_trade(self.symbol)
            if not trade:
                print(f"❌ 未找到开仓记录，无法计算盈亏")
                # 仍然清空持仓状态
                self._clear_position_state()
                return
            
            entry_price_db = trade.entry_price
            invested_amount = trade.invested_amount
            amount = trade.amount
            
            # 🔴 计算实际盈亏
            if self.current_position == 'long':
                actual_profit_loss = (exit_price - entry_price_db) * amount * 0.01
            else:  # short
                actual_profit_loss = (entry_price_db - exit_price) * amount * 0.01
            
            # 获取手续费信息（从OKX订单信息中）
            fee_info = triggered_order.get('fee', {})
            exit_fee = float(fee_info.get('cost', 0)) if fee_info else invested_amount * 0.0005
            entry_fee = invested_amount * 0.0005  # 开仓手续费估算
            funding_fee = 0.0
            
            total_fee = entry_fee + exit_fee + funding_fee
            net_profit_loss = actual_profit_loss - total_fee
            return_rate = (net_profit_loss / invested_amount) * 100
            
            print(f"📊 盈亏计算:")
            print(f"   开仓价: ${entry_price_db:.2f}")
            print(f"   平仓价: ${exit_price:.2f}")
            print(f"   数量: {amount}张")
            print(f"   毛盈亏: ${actual_profit_loss:.2f}")
            print(f"   手续费: ${total_fee:.2f} (开仓${entry_fee:.2f} + 平仓${exit_fee:.2f})")
            print(f"   净盈亏: ${net_profit_loss:.2f}")
            print(f"   收益率: {return_rate:.2f}%")
            
            # 🔴 检查 okx_orders 表中是否已有平仓记录
            # （通过 exit_order_id 查询）
            try:
                existing_order = self.trading_db.session.query(
                    self.trading_db.OkxOrder
                ).filter_by(order_id=exit_order_id).first()
                
                if not existing_order:
                    print(f"💾 平仓订单不存在，保存到 okx_orders...")
                    # 保存平仓订单到 okx_orders
                    self.trading_db.save_order(
                        order_id=exit_order_id,
                        symbol=self.symbol,
                        order_type='MARKET',
                        side='sell' if self.current_position == 'long' else 'buy',
                        position_side=self.current_position,
                        amount=amount,
                        price=exit_price,
                        status='filled',
                        parent_order_id=self.current_entry_order_id,
                        order_time=exit_time,
                        filled_time=exit_time
                    )
                    print(f"✅ 已保存: 平仓订单({exit_order_id}) → okx_orders")
                else:
                    print(f"ℹ️  平仓订单已存在于 okx_orders")
                    
            except Exception as e:
                print(f"❌ 检查/保存平仓订单失败: {e}")
            
            # 🔴 更新交易记录
            self.trading_db.close_okx_trade(
                trade_id=self.current_trade_id,
                exit_order_id=exit_order_id,
                exit_price=exit_price,
                exit_time=exit_time,
                exit_reason=exit_reason,
                entry_fee=entry_fee,
                exit_fee=exit_fee,
                funding_fee=funding_fee
            )
            print(f"✅ 已更新: 交易记录(ID={self.current_trade_id}) → okx_trades")
            
            # 更新统计
            self.daily_stats['total_pnl'] += net_profit_loss
            if net_profit_loss > 0:
                self.daily_stats['winning_trades'] += 1
            else:
                self.daily_stats['losing_trades'] += 1
            
            # 🔴 发送钉钉通知
            if hasattr(self.strategy, 'dingtalk_notifier') and self.strategy.dingtalk_notifier:
                profit_type = "盈利" if net_profit_loss > 0 else "亏损"
                self.strategy.dingtalk_notifier.send_close_position_message(
                    position_side=self.current_position,
                    entry_price=entry_price_db,
                    exit_price=exit_price,
                    profit_loss=net_profit_loss,
                    return_rate=return_rate,
                    reason=exit_reason
                )
            
            self.logger.log(f"✅ {exit_reason}处理完成: 实际盈亏 ${net_profit_loss:+,.2f} ({return_rate:+.2f}%)")
            
            # 清空持仓记录
            self._clear_position_state()
            
            # 🔴 平仓后立即更新账户余额
            self._update_account_balance()
            
        except Exception as e:
            print(f"❌ 处理止损单触发失败: {e}")
            import traceback
            traceback.print_exc()
            # 仍然清空持仓状态，避免状态不一致
            self._clear_position_state()
    
    def _clear_position_state(self):
        """清空持仓状态（提取为独立方法）"""
        print(f"🧹 清空持仓状态...")
        
        # 清空机器人持仓记录
        self.current_position = None
        self.current_position_side = None
        self.current_position_contracts = 0  # 🔴 当前持仓合约张数
        self.current_position_shares = 0
        self.current_trade_id = None
        self.current_entry_order_id = None
        self.current_stop_loss_order_id = None
        self.current_take_profit_order_id = None
        
        # 🔴 清空挂单记录
        # self.pending_entry_order_id = None
        # self.pending_entry_amount = None
        # self.pending_entry_price = None
        # self.pending_stop_loss_price = None
        # self.pending_take_profit_price = None
        # self.pending_entry_side = None
        # print(f"   🔄 清空挂单记录E")
        
        # 🔴 同步持仓平仓到策略
        if hasattr(self, 'strategy'):
            self.strategy.sync_position_close("持仓平仓")
            self.strategy.current_invested_amount = None
            self.strategy.position_shares = None
            self.strategy.position = None
        
        print(f"✅ 持仓状态已清空")
    
    def _place_stop_orders_after_entry(self, side, amount, stop_loss_price, take_profit_price):
        """开仓成交后挂止损止盈单
        
        Args:
            side: 'long' 或 'short'
            amount: 实际成交币数量
            stop_loss_price: 止损价格
            take_profit_price: 止盈价格
        """
        try:
            print(f"\n{'='*60}")
            print(f"🛡️  开仓成交后挂止损止盈单")
            print(f"{'='*60}")
            print(f"   方向: {side}")
            print(f"   数量: {amount} {self.config.get('long_coin', 'coin')}")
            print(f"   止损: ${stop_loss_price:.2f}")
            print(f"   止盈: ${take_profit_price:.2f}")
            
            # 挂止损单
            if stop_loss_price and stop_loss_price > 0:
                stop_loss_order = self.trader._set_stop_loss_limit(
                    self.symbol, side, stop_loss_price, amount
                )
                if stop_loss_order:
                    self.current_stop_loss_order_id = stop_loss_order.get('id')
                    print(f"✅ 止损单已挂: {self.current_stop_loss_order_id}")
                else:
                    print(f"⚠️  止损单挂单失败")
            
            # 挂止盈单
            if take_profit_price and take_profit_price > 0:
                take_profit_order = self.trader._set_take_profit_limit(
                    self.symbol, side, take_profit_price, amount
                )
                if take_profit_order:
                    self.current_take_profit_order_id = take_profit_order.get('id')
                    print(f"✅ 止盈单已挂: {self.current_take_profit_order_id}")
                else:
                    print(f"⚠️  止盈单挂单失败")
            
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"❌ 挂止损止盈单失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _check_entry_order_filled(self):
        """检查开仓订单是否已成交（每30秒调用一次）"""
        try:
            # 如果没有待检查的挂单，直接返回
            if self.pending_entry_order_id is None:
                return
            
            print(f"\n🔍 【定时检查】检查开仓订单是否已成交: {self.pending_entry_order_id}")
            contract_size, _ = self.trader.get_contract_size(self.symbol)
            
            # 方法1: 查询订单状态
            order_filled = False
            actual_amount = None
            
            try:
                # 尝试查询订单状态（可能是限价单或条件单）
                try:
                    order_info = self.trader.exchange.fetch_order(self.pending_entry_order_id, self.symbol)
                    order_status = order_info.get('status', 'unknown')
                    filled_amount = order_info.get('filled', 0)
                    
                    if order_status in ['closed', 'filled']:
                        order_filled = True
                        actual_amount = filled_amount if filled_amount > 0 else self.pending_entry_amount
                        print(f"   ✅ 订单已成交: 状态={order_status}, 成交币数量={actual_amount}{self.config.get('long_coin', 'coin')}")
                    else:
                        print(f"   ⏳ 订单未成交: 状态={order_status}")
                except Exception as e1:
                    # 如果不是普通订单，可能是条件单，尝试查询条件单
                    try:
                        params = {'ordType': 'conditional'}
                        response = self.trader.exchange.private_get_trade_orders_algo_pending(params)
                        if response.get('code') == '0' and response.get('data'):
                            found = False
                            for algo_data in response['data']:
                                algo_id = algo_data.get('algoId', '')
                                if str(algo_id) == str(self.pending_entry_order_id):
                                    found = True
                                    state = algo_data.get('state', '')
                                    if state != 'live':
                                        # 条件单已触发或取消
                                        order_filled = True
                                        actual_amount = self.pending_entry_amount
                                        print(f"   ✅ 条件单已触发: 状态={state}")
                                    else:
                                        print(f"   ⏳ 条件单未触发: 状态={state}")
                                    break
                            if not found:
                                # 条件单不存在，可能已触发
                                order_filled = True
                                actual_amount = self.pending_entry_amount
                                print(f"   ✅ 条件单不存在，可能已触发")
                    except Exception as e2:
                        print(f"   ⚠️  查询条件单状态失败: {e2}")
            except Exception as e:
                print(f"   ⚠️  查询订单状态异常: {e}")
            
            # 方法2: 如果订单状态查询失败，查询OKX持仓状态
            if not order_filled:
                try:
                    positions = self.trader.exchange.fetch_positions([self.symbol])
                    for pos in positions:
                        contracts = self.safe_float(pos.get('contracts'))
                        size = self.safe_float(pos.get('size'))
                        pos_side = pos.get('side', '')
                        
                        # 检查是否有持仓，且方向匹配
                        if (contracts > 0 or size > 0) and pos_side == self.pending_entry_side:
                            order_filled = True
                            if contracts and contracts > 0:
                                contract_size = self.trader.get_contract_size(self.symbol)[0]
                                actual_amount = round(contracts * contract_size, 2)
                            else:
                                actual_amount = size
                            print(f"   ✅ 检测到持仓，开仓订单已成交: 币数量={actual_amount}{self.config.get('long_coin', 'coin')}, 方向={pos_side}")
                            break
                except Exception as e:
                    print(f"   ⚠️  查询持仓状态失败: {e}")
            
            # 如果订单已成交，挂止损止盈单
            if order_filled:
                print(f"   🎯 开仓订单已成交，开始挂止损止盈单")
                
                # 使用实际成交数量（如果查询到）或记录的挂单数量
                final_amount = actual_amount if actual_amount and actual_amount > 0 else self.pending_entry_amount
                
                if self.pending_stop_loss_price and self.pending_take_profit_price and self.pending_entry_side:
                    self._place_stop_orders_after_entry(
                        self.pending_entry_side,
                        final_amount,
                        self.pending_stop_loss_price,
                        self.pending_take_profit_price
                    )
                    
                    # 清空挂单记录
                    self.pending_entry_order_id = None
                    self.pending_entry_amount = None
                    self.pending_entry_price = None
                    self.pending_stop_loss_price = None
                    self.pending_take_profit_price = None
                    self.pending_entry_side = None
                    print(f"   ✅ 止损止盈单已挂，清空挂单记录F")
                else:
                    print(f"   ⚠️  缺少止损止盈价格信息，无法挂单")
            
        except Exception as e:
            print(f"❌ 检查开仓订单状态失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _print_position_status(self):
        """打印当前持仓状态（调试用）"""
        print(f"\n{'='*80}")
        print(f"📊 持仓状态检查 - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*80}")
        
        # 打印机器人持仓状态
        print(f"🤖 机器人状态:")
        print(f"   持仓方向: {self.current_position}")
        print(f"   持仓数量: {self.current_position_shares}{self.config.get('long_coin', 'coin')} (合约{self.current_position_contracts}张)")
        print(f"   交易ID: {self.current_trade_id}")
        print(f"   开仓订单ID: {self.current_entry_order_id}")
        print(f"   止损订单ID: {self.current_stop_loss_order_id}")
        print(f"   止盈订单ID: {self.current_take_profit_order_id}")
        
        # 打印策略持仓状态
        if hasattr(self, 'strategy'):
            strategy_status = self.strategy.get_current_status()
            print(f"\n📈 策略状态:")
            print(f"   策略持仓: {strategy_status.get('position')}")
            print(f"   策略开仓价: ${strategy_status.get('entry_price', 0):.2f}")
            print(f"   策略止损位: ${strategy_status.get('stop_loss_level', 0):.2f}")
            print(f"   策略止盈位: ${strategy_status.get('take_profit_level', 0):.2f}")
            print(f"   策略最大亏损位: ${strategy_status.get('max_loss_level', 0):.2f}")
            print(f"   策略投入金额: ${strategy_status.get('current_invested_amount', 0):.2f}")
            print(f"   策略持仓数量: {strategy_status.get('position_shares', 0)}")
            
            # 检查SAR值
            sar_value = strategy_status.get('sar_value')
            if sar_value:
                print(f"   当前SAR值: ${sar_value:.2f}")
            
            # 🔴 对比机器人和策略的持仓信息
            print(f"\n🔍 状态一致性检查:")
            position_match = (self.current_position == strategy_status.get('position'))
            shares_match = (abs(self.current_position_shares - strategy_status.get('position_shares', 0)) < 0.001)
            
            print(f"   持仓方向一致: {'✅' if position_match else '❌'} (机器人:{self.current_position} vs 策略:{strategy_status.get('position')})")
            print(f"   持仓数量一致: {'✅' if shares_match else '❌'} (机器人:{self.current_position_shares} vs 策略:{strategy_status.get('position_shares', 0)})")
            
            if not position_match or not shares_match:
                print(f"   ⚠️  状态不一致！需要同步")
            else:
                print(f"   ✅ 状态一致")
        
        # 检查OKX实际持仓
        try:
            if hasattr(self.trader, 'exchange') and self.trader.exchange:
                positions = self.trader.exchange.fetch_positions([self.symbol])
                okx_position = None
                for pos in positions:
                    if pos.get('symbol') == self.symbol.replace('-', '/') + ':USDT':
                        okx_position = pos
                        break
                
                print(f"\n🏦 OKX实际持仓:")
                if okx_position and float(okx_position.get('contracts', 0)) != 0:
                    print(f"   OKX持仓方向: {okx_position.get('side', 'unknown')}")
                    print(f"   OKX持仓数量: {okx_position.get('contracts', 0)}")
                    print(f"   OKX开仓价: ${okx_position.get('entryPrice', 0):.2f}")
                    print(f"   OKX未实现盈亏: ${okx_position.get('unrealizedPnl', 0):.2f}")
                    
                    # 🔴 对比OKX和本地状态
                    okx_side = 'long' if okx_position.get('side') == 'long' else 'short' if okx_position.get('side') == 'short' else None
                    okx_contracts = float(okx_position.get('contracts', 0))
                    
                    print(f"\n🔍 OKX vs 本地状态对比:")
                    print(f"   持仓方向一致: {'✅' if self.current_position == okx_side else '❌'} (本地:{self.current_position} vs OKX:{okx_side})")
                    print(f"   持仓数量一致: {'✅' if abs(self.current_position_shares - okx_contracts) < 0.001 else '❌'} (本地:{self.current_position_shares} vs OKX:{okx_contracts})")
                    
                    if self.current_position != okx_side or abs(self.current_position_shares - okx_contracts) >= 0.001:
                        print(f"   ⚠️  OKX与本地状态不一致！需要同步")
                else:
                    print(f"   OKX无持仓")
                    
                    # 如果OKX无持仓但本地有持仓
                    if self.current_position:
                        print(f"   ⚠️  本地有持仓但OKX无持仓！状态不一致")
        except Exception as e:
            print(f"\n🏦 OKX持仓检查失败: {e}")
        
        print(f"{'='*80}\n")
    
    def _update_account_balance(self):
        """更新账户余额（使用可用余额free，而不是总余额total）"""
        if not getattr(self.trader, 'exchange', None):
            self.logger.log_error("❌ OKX 交易接口未初始化，无法获取账户余额。请检查 API 配置。")
            return
        try:
            account_info = self.trader.get_account_info()
            if account_info:
                old_balance = self.account_balance
                # 🔴 使用可用余额（free），而不是总余额（total）
                # 总余额 = 可用余额 + 已用余额（已占用的保证金）
                self.account_balance = account_info['balance']['free']  # 可用余额
                self.account_total_balance = account_info['balance']['total']  # 总余额
                self.account_used_balance = account_info['balance']['used']  # 已用余额
                self.logger.log(f"💰 账户余额已更新: 可用=${self.account_balance:.2f} | 总余额=${self.account_total_balance:.2f} | 已用=${self.account_used_balance:.2f} "
                              f"(变化: ${self.account_balance - old_balance:+,.2f})")
            else:
                self.logger.log_warning("⚠️  获取账户信息失败，余额未更新")
        except Exception as e:
            self.logger.log_error(f"更新账户余额失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _sync_position_on_startup(self):
        """启动时同步OKX持仓状态到程序（混合方案）
        
        检查OKX是否有当前币种的持仓，如果有：
        1. 从数据库恢复交易记录
        2. 同步持仓状态到程序变量
        3. 同步策略对象的持仓状态
        """
        try:
            self.logger.log(f"\n{'='*80}")
            self.logger.log(f"🔄 启动时强制同步持仓状态（混合方案）...")
            self.logger.log(f"{'='*80}")
            
            # 1. 查询OKX实际持仓
            positions = self.trader.exchange.fetch_positions([self.symbol])
            
            has_okx_position = False
            okx_position_side = None
            okx_position_contracts = 0
            contract_size, _ = self.trader.get_contract_size(self.symbol)
            
            for pos in positions:
                # 检查是否匹配当前交易对（支持多种symbol格式）
                pos_symbol = pos.get('symbol', '')
                pos_inst_id = pos.get('info', {}).get('instId', '')
                
                # 检查多种可能的symbol格式
                symbol_match = (
                    pos_symbol == self.symbol or 
                    pos_inst_id == self.symbol or
                    pos_symbol == self.symbol.replace('-', '/') or
                    pos_inst_id == self.symbol.replace('-', '/') or
                    pos_symbol == self.symbol.replace('-', '/') + ':USDT' or
                    pos_inst_id == self.symbol.replace('-', '/') + ':USDT'
                )
                
                if symbol_match:
                    contracts = self.safe_float(pos.get('contracts'))
                    size = self.safe_float(pos.get('size'))
                    notional = self.safe_float(pos.get('notional'))
                    
                    # 使用contracts、size或notional来判断是否有持仓
                    if contracts > 0 or size > 0 or notional > 0:
                        has_okx_position = True
                        okx_position_side = pos.get('side', '').lower()
                        okx_position_contracts = contracts
                        coin_qty = round(okx_position_contracts * contract_size, 2)
                        self.logger.log(f"📊 检测到OKX持仓: {okx_position_side}, 合约{okx_position_contracts}张 ≈ {coin_qty}{self.config.get('long_coin', 'coin')}")
                        
                        # 🔴 同步到本地状态
                        self.current_position = okx_position_side
                        self.current_position_side = okx_position_side
                        self.current_position_contracts = okx_position_contracts
                        self.current_position_shares = coin_qty
                        
                        # 🔴 尝试从数据库恢复交易记录
                        self._restore_trade_from_database(okx_position_side)
                        
                        # 🔴 同步策略对象状态
                        self._sync_strategy_position_state(okx_position_side)
                        break
            
            if not has_okx_position:
                self.logger.log(f"✅ OKX无持仓，程序从空仓开始")
                # 🔴 确保本地状态为空
                self._clear_position_state()
                # 🔴 强制清空策略对象状态（重要！避免策略认为有持仓）
                if self.strategy:
                    self.logger.log(f"🔄 强制清空策略对象持仓状态（OKX无持仓）")
                    self.strategy.position = None
                    self.strategy.entry_price = None
                    self.strategy.stop_loss_level = None
                    self.strategy.take_profit_level = None
                    self.strategy.max_loss_level = None
                    self.strategy.position_shares = None
                    self.strategy.current_invested_amount = 0
                    self.strategy.waiting_for_dv_target = False
                    self.strategy.target_dv_percent = None
                    self.logger.log(f"✅ 策略状态已清空: position=None")
                self.logger.log(f"{'='*80}\n")
                return
            
            self.logger.log(f"✅ 启动时同步完成")
            self.logger.log(f"{'='*80}\n")
            
        except Exception as e:
            self.logger.log_error(f"❌ 启动时同步持仓状态失败: {e}")
            import traceback
            traceback.print_exc()
            self.logger.log_warning(f"⚠️  建议检查OKX持仓和数据库状态，必要时手动平仓")
    
    def _restore_trade_from_database(self, position_side):
        """从数据库恢复交易记录"""
        try:
            if not self._is_trading_db_available():
                self.logger.log_warning("⚠️  交易数据库未连接，无法恢复交易记录")
                return
            
            # 查询未平仓的交易记录
            trade = self.trading_db.get_open_trade(self.symbol)
            if trade:
                self.current_trade_id = trade.id
                self.current_entry_order_id = trade.entry_order_id
                self.logger.log(f"✅ 从数据库恢复交易记录: ID={trade.id}, 开仓价=${trade.entry_price:.2f}")
                
                # 查询止损止盈单记录
                session = self.trading_db.get_session()
                try:
                    from trading_database_models import OKXStopOrder
                    
                    stop_orders = session.query(OKXStopOrder).filter_by(
                        symbol=self.symbol,
                        trade_id=trade.id,
                        status='active'
                    ).all()
                    
                    stop_loss_price = None
                    take_profit_price = None
                    
                    for order in stop_orders:
                        if order.order_type == 'STOP_LOSS':
                            self.current_stop_loss_order_id = order.order_id
                            stop_loss_price = order.trigger_price  # 🔴 获取止损价格
                            self.logger.log(f"✅ 恢复止损单: {order.order_id}, 止损价=${stop_loss_price:.2f}")
                        elif order.order_type == 'TAKE_PROFIT':
                            self.current_take_profit_order_id = order.order_id
                            take_profit_price = order.trigger_price  # 🔴 获取止盈价格
                            self.logger.log(f"✅ 恢复止盈单: {order.order_id}, 止盈价=${take_profit_price:.2f}")
                    
                    # 🔴 保存止损止盈价格，供后续同步策略使用
                    if stop_loss_price is not None:
                        self._restored_stop_loss_price = stop_loss_price
                    if take_profit_price is not None:
                        self._restored_take_profit_price = take_profit_price
                            
                finally:
                    self.trading_db.close_session(session)
            else:
                self.logger.log_warning("⚠️  数据库中未找到对应的交易记录")
                
        except Exception as e:
            self.logger.log_error(f"❌ 恢复交易记录失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _sync_strategy_position_state(self, position_side):
        """同步策略对象的持仓状态"""
        try:
            if not self._is_trading_db_available():
                self.logger.log_warning("⚠️  交易数据库未连接，无法同步策略状态")
                return
            
            # 从数据库获取交易信息
            trade = self.trading_db.get_open_trade(self.symbol)
            if trade:
                print(f"   🔄 同步策略状态: {position_side}, 开仓价=${trade.entry_price:.2f}, 数量={trade.amount}")
                
                # 同步策略对象状态
                self.strategy.position = position_side
                self.strategy.entry_price = trade.entry_price
                self.strategy.position_shares = trade.amount
                self.strategy.current_invested_amount = trade.invested_amount
                
                print(f"   ✅ 策略状态已更新: position={self.strategy.position}, entry_price={self.strategy.entry_price}")
                
                # 🔴 优先使用从数据库恢复的止损止盈价格（如果存在）
                # 如果数据库中有止损止盈单记录，使用实际的触发价格
                if hasattr(self, '_restored_stop_loss_price') and self._restored_stop_loss_price is not None:
                    self.strategy.stop_loss_level = self._restored_stop_loss_price
                    print(f"   ✅ 使用数据库止损价: ${self._restored_stop_loss_price:.2f}")
                else:
                    # 如果没有数据库记录，使用固定百分比计算
                    if self.strategy.max_loss_pct > 0:
                        if position_side == 'long':
                            self.strategy.stop_loss_level = trade.entry_price * (1 - self.strategy.max_loss_pct / 100)
                        else:
                            self.strategy.stop_loss_level = trade.entry_price * (1 + self.strategy.max_loss_pct / 100)
                        print(f"   ⚠️  数据库无止损单记录，使用固定百分比计算: ${self.strategy.stop_loss_level:.2f}")
                
                # 🔴 同步最大亏损位（与止损位相同）
                if self.strategy.stop_loss_level is not None:
                    self.strategy.max_loss_level = self.strategy.stop_loss_level
                
                # 🔴 优先使用从数据库恢复的止盈价格（如果存在）
                if hasattr(self, '_restored_take_profit_price') and self._restored_take_profit_price is not None:
                    self.strategy.take_profit_level = self._restored_take_profit_price
                    print(f"   ✅ 使用数据库止盈价: ${self._restored_take_profit_price:.2f}")
                else:
                    # 如果没有数据库记录，使用固定百分比计算
                    if self.strategy.fixed_take_profit_pct > 0:
                        if position_side == 'long':
                            self.strategy.take_profit_level = trade.entry_price * (1 + self.strategy.fixed_take_profit_pct / 100)
                        else:
                            self.strategy.take_profit_level = trade.entry_price * (1 - self.strategy.fixed_take_profit_pct / 100)
                        print(f"   ⚠️  数据库无止盈单记录，使用固定百分比计算: ${self.strategy.take_profit_level:.2f}")
                
                self.logger.log(f"✅ 策略状态已同步: {position_side}, 开仓价=${trade.entry_price:.2f}, 止损=${self.strategy.stop_loss_level:.2f}, 止盈=${self.strategy.take_profit_level:.2f}")
            else:
                print(f"   ⚠️  未找到交易记录，无法同步策略状态")
                self.logger.log_warning("⚠️  无法同步策略状态：未找到交易记录")
                
        except Exception as e:
            self.logger.log_error(f"❌ 同步策略状态失败: {e}")
            import traceback
            traceback.print_exc()
    
    def periodic_sync_with_okx(self):
        """定期同步OKX状态（混合方案）
        
        每5分钟执行一次，确保本地状态与OKX实际状态一致
        """
        try:
            self.logger.log(f"\n{'='*60}")
            self.logger.log(f"🔄 定期同步OKX状态（混合方案）...")
            self.logger.log(f"{'='*60}")
            
            # 1. 查询OKX实际持仓
            positions = self.trader.exchange.fetch_positions([self.symbol])
            
            has_okx_position = False
            okx_position_side = None
            okx_position_contracts = 0
            
            for pos in positions:
                # 检查是否匹配当前交易对
                pos_symbol = pos.get('symbol', '')
                pos_inst_id = pos.get('info', {}).get('instId', '')
                
                symbol_match = (
                    pos_symbol == self.symbol or 
                    pos_inst_id == self.symbol or
                    pos_symbol == self.symbol.replace('-', '/') or
                    pos_inst_id == self.symbol.replace('-', '/') or
                    pos_symbol == self.symbol.replace('-', '/') + ':USDT' or
                    pos_inst_id == self.symbol.replace('-', '/') + ':USDT'
                )
                
                if symbol_match:
                    contracts = self.safe_float(pos.get('contracts'))
                    size = self.safe_float(pos.get('size'))
                    notional = self.safe_float(pos.get('notional'))
                    
                    if contracts > 0 or size > 0 or notional > 0:
                        has_okx_position = True
                        okx_position_side = pos.get('side', '').lower()
                        okx_position_contracts = contracts
                        break
            
            # 2. 检查本地状态
            local_has_position = self.current_position is not None
            
            self.logger.log(f"📊 状态对比:")
            self.logger.log(f"   OKX实际持仓: {okx_position_side if has_okx_position else '无'}")
            self.logger.log(f"   本地持仓状态: {self.current_position if local_has_position else '无'}")
            
            # 3. 状态不一致时进行同步
            if has_okx_position != local_has_position:
                self.logger.log(f"⚠️  检测到状态不一致，开始同步...")
                
                if has_okx_position:
                    # OKX有持仓，本地无持仓：同步到本地
                    self.logger.log(f"🔄 同步OKX持仓到本地: {okx_position_side}, {okx_position_contracts}张")
                    self.current_position = okx_position_side
                    self.current_position_side = okx_position_side
                    self.current_position_shares = okx_position_contracts
                    
                    # 尝试恢复交易记录
                    self._restore_trade_from_database(okx_position_side)
                    self._sync_strategy_position_state(okx_position_side)
                    
                else:
                    # OKX无持仓，本地有持仓：清空本地状态
                    self.logger.log(f"🔄 清空本地持仓状态（OKX已平仓）")
                    self._clear_position_state()
                    
            elif has_okx_position and local_has_position:
                # 两边都有持仓，检查数量是否一致
                if abs(self.current_position_shares - okx_position_contracts) > 0.1:
                    contract_size = self.trader.get_contract_size(self.symbol)[0]
                    coin_qty = round(okx_position_contracts * contract_size, 2)
                    self.logger.log(f"⚠️  持仓数量不一致: 本地{self.current_position_contracts}张 (≈{self.current_position_shares}{self.config.get('long_coin', 'coin')}) vs OKX{okx_position_contracts}张")
                    self.logger.log(f"🔄 以OKX为准，更新本地数量")
                    self.current_position_shares = okx_position_contracts
                    
                    # 同步策略对象
                    if hasattr(self.strategy, 'position_shares'):
                        self.strategy.position_shares = okx_position_contracts
            
            self.logger.log(f"✅ 定期同步完成")
            self.logger.log(f"{'='*60}\n")
            
        except Exception as e:
            self.logger.log_error(f"❌ 定期同步失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _check_okx_actual_positions(self, positions):
        """检查OKX实际持仓"""
        for pos in positions:
            # 检查是否匹配当前交易对
            pos_symbol = pos.get('symbol', '')
            pos_inst_id = pos.get('info', {}).get('instId', '')
            
            symbol_match = (
                pos_symbol == self.symbol or 
                pos_inst_id == self.symbol or
                pos_symbol == self.symbol.replace('-', '/') or
                pos_inst_id == self.symbol.replace('-', '/') or
                pos_symbol == self.symbol.replace('-', '/') + ':USDT' or
                pos_inst_id == self.symbol.replace('-', '/') + ':USDT'
            )
            
            if symbol_match:
                contracts = self.safe_float(pos.get('contracts'))
                size = self.safe_float(pos.get('size'))
                notional = self.safe_float(pos.get('notional'))
                
                # 使用contracts、size或notional来判断是否有持仓
                if contracts > 0 or size > 0 or notional > 0:
                    return True
        return False
    
    def _sync_okx_to_local(self, positions):
        """同步OKX状态到本地"""
        try:
            for pos in positions:
                # 检查是否匹配当前交易对
                pos_symbol = pos.get('symbol', '')
                pos_inst_id = pos.get('info', {}).get('instId', '')
                
                symbol_match = (
                    pos_symbol == self.symbol or 
                    pos_inst_id == self.symbol or
                    pos_symbol == self.symbol.replace('-', '/') or
                    pos_inst_id == self.symbol.replace('-', '/') or
                    pos_symbol == self.symbol.replace('-', '/') + ':USDT' or
                    pos_inst_id == self.symbol.replace('-', '/') + ':USDT'
                )
                
                if symbol_match:
                    contracts = self.safe_float(pos.get('contracts'))
                    size = self.safe_float(pos.get('size'))
                    notional = self.safe_float(pos.get('notional'))
                    
                    if contracts > 0 or size > 0 or notional > 0:
                        position_side = pos.get('side', '').lower()
                        print(f"🔄 同步OKX持仓到本地: {position_side}, {contracts}张")
                        
                        # 同步到本地状态
                        self.current_position = position_side
                        self.current_position_side = position_side
                        self.current_position_shares = contracts
                        
                        # 尝试恢复交易记录
                        self._restore_trade_from_database(position_side)
                        self._sync_strategy_position_state(position_side)
                        break
        except Exception as e:
            print(f"❌ 同步OKX状态到本地失败: {e}")
    
    def sync_open_trades_with_okx(self):
        """同步数据库持仓状态与OKX实际持仓（每1分钟执行 - 测试用）
        
        检查本地数据库中状态为 'open' 的交易记录，与OKX实际持仓对比，
        如果发现不一致（本地显示持仓但OKX已平仓），则更新数据库
        """
        session = None
        try:
            self.logger.log(f"\n{'='*60}")
            self.logger.log(f"🔄 开始同步数据库持仓状态...")
            self.logger.log(f"{'='*60}")
            
            trades_data = []  # 初始化
            
            # 1. 从数据库查询所有 status='open' 的交易记录
            try:
                # 使用 get_session() 方法获取会话
                session = self.trading_db.get_session()
                
                # 导入模型
                from trading_database_models import OKXTrade
                
                open_trades = session.query(OKXTrade).filter_by(
                    symbol=self.symbol,
                    status='open'
                ).all()
                
                if not open_trades:
                    self.logger.log(f"✅ 数据库中没有待同步的持仓记录")
                    return
                
                # 🔴 先提取所有需要的数据到字典列表，避免SQLAlchemy session detached错误
                trades_data = []
                for trade in open_trades:
                    trades_data.append({
                        'id': trade.id,
                        'position_side': trade.position_side,
                        'entry_order_id': trade.entry_order_id,
                        'entry_price': trade.entry_price,
                        'entry_time': trade.entry_time,
                        'amount': trade.amount,
                        'invested_amount': trade.invested_amount
                    })
                
                self.logger.log(f"📊 数据库中有 {len(trades_data)} 条未平仓记录:")
                for trade_data in trades_data:
                    self.logger.log(f"   - 交易ID={trade_data['id']}, {trade_data['position_side']}, "
                                  f"开仓订单={trade_data['entry_order_id']}, "
                                  f"开仓价=${trade_data['entry_price']:.2f}, "
                                  f"数量={trade_data['amount']}张")
                
            except Exception as e:
                self.logger.log_error(f"查询本地持仓记录失败: {e}")
                import traceback
                traceback.print_exc()
                return
            
            # 2. 查询OKX实际持仓状态
            try:
                positions = self.trader.exchange.fetch_positions([self.symbol])
                
                # 🔍 添加详细的调试信息
                self.logger.log(f"🔍 调用OKX API获取持仓信息...")
                self.logger.log(f"📋 OKX API返回的持仓数据:")
                self.logger.log(f"   查询的交易对: {self.symbol}")
                self.logger.log(f"   返回的持仓数量: {len(positions)}")
                
                for i, pos in enumerate(positions):
                    self.logger.log(f"   持仓 #{i+1}:")
                    self.logger.log(f"     symbol: {pos.get('symbol')}")
                    self.logger.log(f"     side: {pos.get('side')}")
                    self.logger.log(f"     contracts: {pos.get('contracts')}")
                    self.logger.log(f"     size: {pos.get('size')}")
                    self.logger.log(f"     notional: {pos.get('notional')}")
                    self.logger.log(f"     margin: {pos.get('margin')}")
                    self.logger.log(f"     unrealizedPnl: {pos.get('unrealizedPnl')}")
                    self.logger.log(f"     percentage: {pos.get('percentage')}")
                    self.logger.log(f"     markPrice: {pos.get('markPrice')}")
                    self.logger.log(f"     entryPrice: {pos.get('entryPrice')}")
                    self.logger.log(f"     timestamp: {pos.get('timestamp')}")
                    self.logger.log(f"     datetime: {pos.get('datetime')}")
                    self.logger.log(f"     info: {pos.get('info', {})}")
                
                # 过滤出有持仓的记录（contracts > 0）
                has_okx_position = False
                has_okx_long_position = False
                has_okx_short_position = False
                okx_long_contracts = 0
                okx_short_contracts = 0
                
                for pos in positions:
                    # 🔍 检查多种可能的symbol格式
                    pos_symbol = pos.get('symbol', '')
                    pos_inst_id = pos.get('info', {}).get('instId', '')
                    
                    # 检查是否匹配当前交易对
                    symbol_match = (
                        pos_symbol == self.symbol or 
                        pos_inst_id == self.symbol or
                        pos_symbol == self.symbol.replace('-', '/') or
                        pos_inst_id == self.symbol.replace('-', '/')
                    )
                    
                    if symbol_match:
                        contracts = self.safe_float(pos.get('contracts'))
                        size = self.safe_float(pos.get('size'))
                        notional = self.safe_float(pos.get('notional'))
                        
                        self.logger.log(f"🔍 匹配的交易对持仓:")
                        self.logger.log(f"   contracts: {contracts}")
                        self.logger.log(f"   size: {size}")
                        self.logger.log(f"   notional: {notional}")
                        
                        # 使用contracts、size或notional来判断是否有持仓
                        if contracts > 0 or size > 0 or notional > 0:
                            has_okx_position = True
                            side = pos.get('side', '').lower()
                            
                            if side == 'long':
                                has_okx_long_position = True
                                okx_long_contracts = contracts
                            elif side == 'short':
                                has_okx_short_position = True
                                okx_short_contracts = contracts
                            
                            self.logger.log(f"📊 OKX实际持仓: {side}, {contracts}张")
                
                if not has_okx_position:
                    self.logger.log(f"📊 OKX实际持仓: 无")
                else:
                    position_info = []
                    if has_okx_long_position:
                        position_info.append(f"多单{okx_long_contracts}张")
                    if has_okx_short_position:
                        position_info.append(f"空单{okx_short_contracts}张")
                    self.logger.log(f"📊 OKX实际持仓: {', '.join(position_info)}")
                    
            except Exception as e:
                self.logger.log_error(f"查询OKX持仓失败: {e}")
                return
            
            # 3. 如果OKX没有持仓，但本地有未平仓记录，说明已被平仓
            if not has_okx_position and len(trades_data) > 0:
                self.logger.log(f"\n⚠️  发现不一致: 本地有{len(trades_data)}条未平仓记录，但OKX无持仓")
                self.logger.log(f"💡 将尝试查找平仓订单并更新数据库记录")
                
                synced_count = 0
                for trade_data in trades_data:
                    self.logger.log(f"\n🔍 处理交易ID={trade_data['id']} ({trade_data['position_side']})")
                    
                    try:
                        # 查询开仓订单号对应的订单详情
                        entry_order_id = trade_data['entry_order_id']
                        self.logger.log(f"   开仓订单: {entry_order_id}")
                        
                        # 查询订单历史，寻找平仓订单
                        exit_order_id = None
                        exit_price = None
                        exit_time = None
                        
                        try:
                            # 获取最近的已成交订单（时间在开仓之后的）
                            # 注意：OKX不支持fetchOrders()，需要使用fetchClosedOrders()
                            since_timestamp = int(trade_data['entry_time'].timestamp() * 1000)
                            recent_orders = self.trader.exchange.fetch_closed_orders(
                                self.symbol,
                                since=since_timestamp,
                                limit=20
                            )
                            
                            self.logger.log(f"   📋 查询到 {len(recent_orders)} 条订单记录")
                            
                            # 查找平仓订单：方向相反，状态已成交
                            trade_side = trade_data['position_side'].lower()
                            for idx, order in enumerate(recent_orders):
                                # 🔍 打印每个订单的完整详情
                                self.logger.log(f"\n   📄 订单 #{idx+1}:")
                                self.logger.log(f"      订单ID: {order.get('id')}")
                                self.logger.log(f"      交易对: {order.get('symbol')}")
                                self.logger.log(f"      类型: {order.get('type')} ({order.get('side')})")
                                self.logger.log(f"      状态: {order.get('status')}")
                                self.logger.log(f"      价格: {order.get('price')}")
                                self.logger.log(f"      平均价: {order.get('average')}")
                                self.logger.log(f"      数量: {order.get('amount')}")
                                self.logger.log(f"      已成交: {order.get('filled')}")
                                self.logger.log(f"      剩余: {order.get('remaining')}")
                                self.logger.log(f"      成交金额: {order.get('cost')}")
                                if order.get('timestamp'):
                                    order_time = datetime.fromtimestamp(order['timestamp'] / 1000)
                                    self.logger.log(f"      时间: {order_time}")
                                if order.get('fee'):
                                    self.logger.log(f"      手续费: {order.get('fee')}")
                                self.logger.log(f"      原始数据: {order}")
                                
                                if order['status'] == 'closed' and order['id'] != entry_order_id:
                                    # 多单平仓是卖出，空单平仓是买入
                                    is_close_order = (
                                        (trade_side == 'long' and order['side'] == 'sell') or
                                        (trade_side == 'short' and order['side'] == 'buy')
                                    )
                                    
                                    if is_close_order:
                                        exit_order_id = order['id']
                                        exit_price = float(order.get('average', order.get('price', 0)))
                                        exit_time = datetime.fromtimestamp(order['timestamp'] / 1000) if order.get('timestamp') else datetime.now()
                                        self.logger.log(f"\n   ✅ 找到平仓订单: {exit_order_id}, 价格=${exit_price:.2f}")
                                        break
                            
                            if not exit_order_id:
                                self.logger.log(f"   ⚠️  未找到平仓订单，跳过更新（等待下次同步）")
                                # 🔴 不使用估算值，等待下次同步时再检查
                                continue  # 跳过这条记录，处理下一条
                                
                        except Exception as order_e:
                            self.logger.log(f"   ❌ 查询订单失败: {order_e}")
                            self.logger.log(f"   ⚠️  跳过更新（等待下次同步）")
                            # 🔴 查询失败，不更新数据库，等待下次同步
                            continue  # 跳过这条记录，处理下一条
                        
                        # 🔴 只有找到真实的平仓订单才更新数据库
                        if exit_order_id and exit_price:
                            # 计算盈亏
                            if trade_data['position_side'].lower() == 'long':
                                profit_loss = (exit_price - trade_data['entry_price']) * trade_data['amount'] * 0.01
                            else:
                                profit_loss = (trade_data['entry_price'] - exit_price) * trade_data['amount'] * 0.01
                            
                            # 估算手续费
                            entry_fee = trade_data['invested_amount'] * 0.0005
                            exit_fee = trade_data['invested_amount'] * 0.0005
                            funding_fee = 0.0
                            
                            self.trading_db.close_okx_trade(
                                trade_id=trade_data['id'],
                                exit_order_id=exit_order_id,
                                exit_price=exit_price,
                                exit_time=exit_time,
                                exit_reason="系统同步检测到已平仓",
                                entry_fee=entry_fee,
                                exit_fee=exit_fee,
                                funding_fee=funding_fee
                            )
                            
                            self.logger.log(f"   ✅ 已更新数据库: 平仓价=${exit_price:.2f}, 盈亏=${profit_loss:.2f}")
                            synced_count += 1
                            
                    except Exception as update_e:
                        self.logger.log_error(f"   ❌ 更新失败: {update_e}")
                        import traceback
                        traceback.print_exc()
                
                self.logger.log(f"\n{'='*60}")
                self.logger.log(f"✅ 同步完成: 更新了 {synced_count}/{len(trades_data)} 条记录")
                self.logger.log(f"{'='*60}\n")
            else:
                self.logger.log(f"✅ 状态一致，无需同步")
                self.logger.log(f"{'='*60}\n")
            
        except Exception as e:
            self.logger.log_error(f"同步持仓状态失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 关闭数据库会话
            if session:
                self.trading_db.close_session(session)
    
    def _is_trading_db_available(self):
        """检查交易数据库是否可用"""
        return self.trading_db is not None
    
    def _save_indicator_signal(self, result, timestamp, open_price, high_price, low_price, close_price, volume):
        """保存指标信号到数据库"""
        # 检查数据库是否可用
        if not self._is_trading_db_available():
            return
            
        print(f"🔍 _save_indicator_signal被调用: timestamp={timestamp}")
        try:
            # 提取指标数据
            sar_result = result.get('sar_result', {})
            print(f"🔍 sar_result keys: {list(sar_result.keys()) if sar_result else 'None'}")
            
            # 从ATR计算器获取ATR数据
            atr_info = self.strategy.atr_calculator.get_atr_volatility_ratio() if hasattr(self, 'strategy') else {}
            
            # 从EMA计算器获取EMA数据
            ema_info = self.strategy.ema_calculator.get_ema_info() if hasattr(self, 'strategy') else {}
            
            # 辅助函数：保留两位小数
            def round_value(val):
                if val is None:
                    return None
                if isinstance(val, (int, float)):
                    return round(val, 2)
                return val
            
            # 构建指标字典（使用正确的字段名，数值保留两位小数）
            indicators_dict = {
                'sar': {
                    'value': round_value(sar_result.get('sar_value')),
                    'direction': sar_result.get('trend_direction'),  # 'up' 或 'down'
                    'sar_direction': sar_result.get('sar_direction'),  # 1 或 -1
                    'sar_rising': sar_result.get('sar_rising'),
                    'sar_falling': sar_result.get('sar_falling'),
                    'bars_since_turn_up': sar_result.get('bars_since_turn_up', 0),
                    'bars_since_turn_down': sar_result.get('bars_since_turn_down', 0)
                },
                'bollinger': {
                    'upper': round_value(sar_result.get('upper')),
                    'basis': round_value(sar_result.get('basis')),
                    'lower': round_value(sar_result.get('lower')),
                    'width': round_value(sar_result.get('bollinger_width')),
                    'quarter_width': round_value(sar_result.get('quarter_bollinger_width')),
                    'regressive_ma': round_value(sar_result.get('regressive_ma'))
                },
                'rsi': {
                    'value': round_value(sar_result.get('rsi')),  # 注意：是'rsi'不是'rsi_value'
                    'period': 14  # VIDYA策略使用默认RSI周期
                },
                'atr': {
                    'atr_3': round_value(atr_info.get('atr_3')),
                    'atr_14': round_value(atr_info.get('atr_14')),
                    'ratio': round_value(atr_info.get('atr_ratio')),
                    'is_filter_passed': atr_info.get('is_atr_filter_passed')
                },
                'ema': {
                    'ema24': round_value(ema_info.get('ema24')),
                    'ema50': round_value(ema_info.get('ema50')),
                    'ema100': round_value(ema_info.get('ema100')),
                    'previous_ema24': round_value(ema_info.get('previous_ema24')),
                    'is_long_signal': ema_info.get('is_long_signal'),
                    'is_short_signal': ema_info.get('is_short_signal')
                }
            }
            
            print(f"🔍 构建的指标字典: {indicators_dict}")
            
            # 提取信号信息
            signal_type = None
            signal_reason = None
            if result.get('signals'):
                first_signal = result['signals'][0]
                signal_type = first_signal.get('type')
                signal_reason = first_signal.get('reason')
            
            # 获取当前持仓信息
            position = self.strategy.position
            entry_price = self.strategy.entry_price if position else None
            stop_loss_level = self.strategy.stop_loss_level if position else None
            take_profit_level = self.strategy.take_profit_level if position else None
            
            # 保存到数据库
            print(f"🔍 准备调用trading_db.save_indicator_signal...")
            print(f"   symbol={self.symbol}, timeframe={self.config['timeframe']}")
            print(f"   position={position}, signal_type={signal_type}")
            
            signal_id = self.trading_db.save_indicator_signal(
                timestamp=timestamp,
                symbol=self.symbol,
                timeframe=self.config['timeframe'],
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                indicators_dict=indicators_dict,
                signal_type=signal_type,
                signal_reason=signal_reason,
                position=position,
                entry_price=entry_price,
                stop_loss_level=stop_loss_level,
                take_profit_level=take_profit_level
            )
            
            print(f"✅ 保存成功! signal_id={signal_id}")
            
            if signal_id and signal_type:
                print(f"💾 指标信号已保存到数据库: ID={signal_id}, 类型={signal_type}")
            elif signal_id:
                print(f"💾 指标数据已保存到数据库: ID={signal_id}")
            
        except Exception as e:
            print(f"❌ 保存指标信号到数据库失败: {e}")
            import traceback
            traceback.print_exc()
    
    def check_and_fill_missing_data(self):
        """主动检查并补充缺失数据（每分钟05秒触发）
        
        - 检查最近3分钟的数据完整性
        - 如果有缺失，尝试从API拉取（最多3次重试）
        - 🔴 如果补充的是周期末尾数据，立即触发指标计算
        """
        try:
            current_time = datetime.now()
            
            # 获取缓存中所有的时间戳
            if len(self.kline_buffer.klines) == 0:
                self.logger.log_warning("🔍 缓存为空，跳过检查")
                return
            
            # 检查最近3分钟的数据
            # 🔴 标准化缓存中的时间戳（去掉秒和微秒）
            recent_klines = list(self.kline_buffer.klines)[-3:] if len(self.kline_buffer.klines) >= 3 else list(self.kline_buffer.klines)
            cached_times = {kline['timestamp'].replace(second=0, microsecond=0) for kline in recent_klines}
            
            # 计算应该存在的时间点（最近3分钟）
            expected_times = []
            for i in range(1, 4):  # 检查最近3分钟
                expected_time = (current_time - timedelta(minutes=i)).replace(second=0, microsecond=0)
                expected_times.append(expected_time)
            
            # 找出缺失的时间点
            missing_times = []
            for expected_time in expected_times:
                # 🔴 确保时间戳标准化后再比较
                normalized_expected = expected_time.replace(second=0, microsecond=0)
                if normalized_expected not in cached_times:
                    missing_times.append(normalized_expected)
            
            if not missing_times:
                # self.logger.log("✅ 数据完整性检查通过")
                return
            
            # 发现数据缺失，尝试补充
            self.logger.log_warning(f"🔍 发现数据缺失: {[t.strftime('%H:%M') for t in missing_times]}")
            
            # 记录补充的数据（用于后续触发策略计算）
            filled_klines = []
            
            # 3次重试机制
            for attempt in range(1, 4):
                try:
                    self.logger.log(f"📥 尝试从API拉取数据 (第{attempt}/3次)...")
                    
                    # 从API获取最近10条1分钟K线数据
                    api_klines = self.trader.get_latest_klines(self.symbol, '1m', limit=10)
                    
                    if not api_klines:
                        self.logger.log_warning(f"❌ API返回数据为空")
                        if attempt < 3:
                            time.sleep(1)  # 等待1秒后重试
                            continue
                        else:
                            break
                    
                    # 补充缺失的数据
                    added_count = 0
                    for kline in api_klines:
                        kline_time = datetime.fromtimestamp(kline[0] / 1000)
                        # 🔴 标准化时间戳（去掉秒和微秒，只保留到分钟）
                        normalized_kline_time = kline_time.replace(second=0, microsecond=0)
                        
                        # 只补充缺失的时间点（使用标准化后的时间戳比较）
                        if normalized_kline_time in missing_times:
                            buffer_size = self.kline_buffer.add_kline(
                                normalized_kline_time,  # 使用标准化后的时间戳
                                kline[1],  # open
                                kline[2],  # high
                                kline[3],  # low
                                kline[4],  # close
                                kline[5] if len(kline) > 5 else 0  # volume
                            )
                            
                            # 🔴 无论是否成功添加到缓存（可能重复），都记录这条数据
                            # 因为后续需要检查是否为周期末尾并触发策略
                            filled_klines.append({
                                'timestamp': normalized_kline_time,  # 使用标准化后的时间戳
                                'open': kline[1],
                                'high': kline[2],
                                'low': kline[3],
                                'close': kline[4],
                                'volume': kline[5] if len(kline) > 5 else 0
                            })
                            
                            if buffer_size != -1:  # 成功添加
                                added_count += 1
                                self.logger.log(f"✅ 补充数据: {normalized_kline_time.strftime('%H:%M')} "
                                              f"收盘:${kline[4]:.2f}")
                            else:
                                self.logger.log(f"ℹ️  数据已存在: {normalized_kline_time.strftime('%H:%M')} "
                                              f"收盘:${kline[4]:.2f} (将检查是否需要触发策略)")
                    
                    # 🔴 只要找到了缺失数据（无论是否重复），就检查是否需要触发策略
                    if filled_klines:
                        if added_count > 0:
                            self.logger.log(f"✅ 成功补充 {added_count} 条新数据")
                        else:
                            self.logger.log(f"ℹ️  缺失数据已存在于缓存，检查是否需要触发策略...")
                        
                        # 🔴 处理补充的数据：无论是否是周期末尾，都要更新策略（包括Delta Volume计算）
                        for filled_kline in filled_klines:
                            minute = filled_kline['timestamp'].minute
                            is_period_last_minute = (minute + 1) % self.period_minutes == 0
                            
                            print(f"🔍 检查补充数据: {filled_kline['timestamp'].strftime('%H:%M')}")
                            print(f"   分钟: {minute}, 周期: {self.period_minutes}")
                            print(f"   (分钟+1) % 周期 = ({minute}+1) % {self.period_minutes} = {(minute + 1) % self.period_minutes}")
                            print(f"   是周期末尾: {is_period_last_minute}")
                            print(f"   首周期完成: {self.first_period_completed}")
                            
                            # 🔴 如果是首周期且是周期末尾，先设置首周期完成标志
                            if is_period_last_minute and not self.first_period_completed:
                                self.first_period_completed = True
                                self.logger.log(f"\n🎯 首个完整周期完成（通过数据补充检测）")
                                self.logger.log(f"✅ 从下一个周期开始处理交易信号\n")
                            
                            # 🔴 无论是否是周期末尾，都要调用策略更新（计算Delta Volume等）
                            if self.first_period_completed:
                                if is_period_last_minute:
                                    # 周期末尾：触发K线生成和策略计算
                                    self.logger.log(f"🎯 补充了周期末尾数据 ({filled_kline['timestamp'].strftime('%H:%M')}), 立即触发K线聚合和指标计算...")
                                    next_minute = filled_kline['timestamp'] + timedelta(minutes=1)
                                    result = self.strategy.update(
                                        next_minute,
                                        filled_kline['close'],
                                        filled_kline['close'],
                                        filled_kline['close'],
                                        filled_kline['close'],
                                        0
                                    )
                                else:
                                    # 非周期末尾：正常更新策略（主要是Delta Volume计算）
                                    self.logger.log(f"📊 补充了非周期末尾数据 ({filled_kline['timestamp'].strftime('%H:%M')}), 更新策略（包括Delta Volume计算）...")
                                    result = self.strategy.update(
                                        filled_kline['timestamp'],
                                        filled_kline['open'],
                                        filled_kline['high'],
                                        filled_kline['low'],
                                        filled_kline['close'],
                                        filled_kline.get('volume', 0)
                                    )
                                
                                # 保存指标信号到数据库（只在有SAR结果时）
                                if result and 'sar_result' in result:
                                    kline_timestamp = result.get('kline_timestamp', filled_kline['timestamp'])
                                    self._save_indicator_signal(
                                        result, 
                                        kline_timestamp, 
                                        filled_kline['open'], 
                                        filled_kline['high'], 
                                        filled_kline['low'], 
                                        filled_kline['close'], 
                                        filled_kline.get('volume', 0)
                                    )
                                
                                # 处理交易信号（只在首个完整周期完成后）
                                if result and result.get('signals'):
                                    for signal in result['signals']:
                                        self.execute_signal(signal)
                            else:
                                # 🔴 首个完整周期未完成时，也要更新策略（计算Delta Volume，但不处理交易信号）
                                self.logger.log(f"📊 补充了数据 ({filled_kline['timestamp'].strftime('%H:%M')}), 更新策略（计算Delta Volume，等待首个完整周期）...")
                                result = self.strategy.update(
                                    filled_kline['timestamp'],
                                    filled_kline['open'],
                                    filled_kline['high'],
                                    filled_kline['low'],
                                    filled_kline['close'],
                                    filled_kline.get('volume', 0)
                                )
                        
                        # 🔴 补充数据后，验证数据是否已正确添加到缓存
                        # 避免下次检查时再次发现"缺失"
                        if added_count > 0:
                            # 重新获取缓存中的时间戳（标准化后）
                            updated_recent_klines = list(self.kline_buffer.klines)[-3:] if len(self.kline_buffer.klines) >= 3 else list(self.kline_buffer.klines)
                            updated_cached_times = {kline['timestamp'].replace(second=0, microsecond=0) for kline in updated_recent_klines}
                            
                            # 验证补充的数据是否真的在缓存中
                            for filled_kline in filled_klines:
                                filled_time = filled_kline['timestamp'].replace(second=0, microsecond=0)
                                if filled_time not in updated_cached_times:
                                    self.logger.log_warning(f"⚠️  警告: 补充的数据 {filled_time.strftime('%H:%M')} 未正确添加到缓存")
                                else:
                                    self.logger.log(f"✅ 验证: 补充的数据 {filled_time.strftime('%H:%M')} 已正确添加到缓存")
                        
                        return  # 补充成功，退出
                    else:
                        self.logger.log_warning(f"⚠️  未找到需要补充的数据")
                        if attempt < 3:
                            time.sleep(1)
                            continue
                        else:
                            break
                    
                except Exception as e:
                    self.logger.log_error(f"第{attempt}次拉取失败: {e}")
                    if attempt < 3:
                        time.sleep(1)  # 等待1秒后重试
                    else:
                        self.logger.log_error(f"❌ 3次尝试均失败，放弃补充")
                        
        except Exception as e:
            self.logger.log_error(f"数据完整性检查失败: {e}")
            import traceback
            traceback.print_exc()
    
    def run_once(self):
        """运行一次更新（与原版类似，但不需要检测平仓触发）"""
        try:
            klines = self.trader.get_latest_klines(self.symbol, '1m', limit=10)
            
            if not klines or len(klines) < 2:
                return False
            
            kline = klines[-2]
            timestamp = datetime.fromtimestamp(kline[0] / 1000)
            
            # 检查重复数据
            buffer_status = self.kline_buffer.get_buffer_status()
            if buffer_status['size'] > 0:
                last_cached_time = buffer_status['last_time']
                if isinstance(last_cached_time, str):
                    last_cached_time = datetime.strptime(last_cached_time, '%Y-%m-%d %H:%M')
                
                time_gap_minutes = int((timestamp - last_cached_time).total_seconds() / 60)
                
                if time_gap_minutes > 1:
                    self.logger.log_warning(f"⚠️  检测到数据遗漏: {last_cached_time.strftime('%H:%M')} → {timestamp.strftime('%H:%M')}")
                    self.logger.log("🔄 将在下一个05秒检查点补充数据")
            
            open_price = kline[1]
            high_price = kline[2]
            low_price = kline[3]
            close_price = kline[4]
            volume = kline[5] if len(kline) > 5 else 0
            
            # 🔴 标准化时间戳（去掉秒和微秒，只保留到分钟）
            normalized_timestamp = timestamp.replace(second=0, microsecond=0)
            
            buffer_size = self.kline_buffer.add_kline(
                normalized_timestamp, open_price, high_price, low_price, close_price, volume
            )
            
            if buffer_size == -1:
                return True
            
            self.logger.log(
                f"[{timestamp.strftime('%H:%M')}] "
                f"开:${open_price:.2f} 高:${high_price:.2f} "
                f"低:${low_price:.2f} 收:${close_price:.2f} "
                f"量:{volume:.2f} | 缓存:{buffer_size}条"
            )
            
            is_period_last_minute = (timestamp.minute + 1) % self.period_minutes == 0
            
            if is_period_last_minute:
                if not self.first_period_completed:
                    self.first_period_completed = True
                    self.logger.log(f"\n🎯 首个完整周期完成")
                    self.logger.log(f"✅ 从下一个周期开始处理交易信号\n")
            
            # 🔴 策略更新（交易所会自动监控止损止盈，程序只负责更新SAR止损位）
            result = {'signals': []}
            
            if self.first_period_completed:
                # 🔴 在调用策略update之前，先验证并同步OKX持仓状态（避免策略基于错误状态生成信号）
                try:
                    positions = self.trader.exchange.fetch_positions([self.symbol])
                    has_okx_position = self._check_okx_actual_positions(positions)
                    
                    # 如果OKX无持仓，但策略状态显示有持仓，先清空策略状态
                    if not has_okx_position and self.strategy.position is not None:
                        self.logger.log_warning(f"⚠️  【更新前验证】OKX无持仓，但策略状态显示有持仓({self.strategy.position})")
                        self.logger.log(f"🔄 清空策略持仓状态，避免生成错误的UPDATE_STOP_LOSS信号")
                        self.strategy.position = None
                        self.strategy.entry_price = None
                        self.strategy.stop_loss_level = None
                        self.strategy.take_profit_level = None
                        self.strategy.max_loss_level = None
                        self.strategy.position_shares = None
                        self.strategy.current_invested_amount = 0
                        self.strategy.waiting_for_dv_target = False
                        self.strategy.target_dv_percent = None
                        # 同时清空本地状态
                        if self.current_position is not None:
                            self._clear_position_state()
                except Exception as e:
                    self.logger.log_warning(f"⚠️  更新前验证持仓状态失败: {e}")
                
                # 🔴 周期末尾：只触发K线生成，不做两次update
                if is_period_last_minute:
                    next_minute = timestamp + timedelta(minutes=1)
                    self.logger.log(f"⏰ 周期末尾，触发K线生成并基于完整周期判断...")
                    # 触发K线生成，策略会基于完整的周期K线来判断
                    result = self.strategy.update(
                        next_minute,
                        close_price,
                        close_price,
                        close_price,
                        close_price,
                        0
                    )
                else:
                    # 🔴 非周期末尾：正常更新（主要是持仓期间的止损更新）
                    result = self.strategy.update(
                        timestamp,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        volume
                    )
                
                # 🔴 保存指标信号到数据库
                if result and 'sar_result' in result:
                    # 使用周期K线的开始时间（如5m: 15:25:00），而不是当前1分钟的时间（15:29:00）
                    kline_timestamp = result.get('kline_timestamp', timestamp)
                    self._save_indicator_signal(result, kline_timestamp, open_price, high_price, low_price, close_price, volume)
                
                # 🔴 处理交易信号
                if result and result.get('signals'):
                    # 🔴 在周期结束时，先验证实际持仓状态，确保策略状态与OKX一致
                    has_okx_position = False
                    if is_period_last_minute:
                        try:
                            positions = self.trader.exchange.fetch_positions([self.symbol])
                            has_okx_position = self._check_okx_actual_positions(positions)
                            
                            # 如果OKX无持仓，但策略状态显示有持仓，清空策略状态
                            if not has_okx_position and self.strategy.position is not None:
                                self.logger.log_warning(f"⚠️  检测到状态不一致：OKX无持仓，但策略状态显示有持仓({self.strategy.position})")
                                self.logger.log(f"🔄 清空策略持仓状态，确保一致性")
                                self.strategy.position = None
                                self.strategy.entry_price = None
                                self.strategy.stop_loss_level = None
                                self.strategy.take_profit_level = None
                                self.strategy.position_shares = None
                        except Exception as e:
                            self.logger.log_warning(f"⚠️  验证持仓状态失败: {e}")
                    
                    # 🔴 过滤信号：如果没有实际持仓，过滤掉UPDATE_STOP_LOSS信号
                    filtered_signals = []
                    for signal in result['signals']:
                        if signal.get('type') == 'UPDATE_STOP_LOSS':
                            # 检查是否有实际持仓
                            if not has_okx_position and self.current_position is None:
                                self.logger.log_warning(f"⚠️  过滤UPDATE_STOP_LOSS信号：无实际持仓")
                                continue
                        filtered_signals.append(signal)
                    
                    for signal in filtered_signals:
                        self.execute_signal(signal)
                        
            elif is_period_last_minute:
                result = self.strategy.update(
                    timestamp,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume
                )
                
                next_minute = timestamp + timedelta(minutes=1)
                self.logger.log(f"⏰ 周期末尾，立即触发K线生成...")
                result = self.strategy.update(
                    next_minute,
                    close_price,
                    close_price,
                    close_price,
                    close_price,
                    0
                )
                
                if result['signals']:
                    self.logger.log(f"⚠️  等待首个完整周期结束，暂不处理信号")
            
            return True
            
        except Exception as e:
            self.logger.log_error(f"更新失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def start(self):
        """启动实盘交易"""
        self.logger.log("🚀 启动实盘交易 - 止损止盈挂单版...")
        
        # 🔴 设置杠杆（即使是1倍也要设置，确保账户杠杆与配置一致）
        leverage = TRADING_CONFIG.get('leverage', 1)
        margin_mode = TRADING_CONFIG.get('margin_mode', 'cross')
        
        self.logger.log(f"⚙️  设置杠杆: {leverage}x, 模式: {margin_mode}")
        if self.trader.set_leverage(self.symbol, leverage, margin_mode):
            # 设置成功后，确保 trader 的 leverage 属性与配置一致
            self.trader.leverage = leverage
            self.logger.log(f"✅ 杠杆已设置并同步: {leverage}x")
        else:
            self.logger.log_warning(f"⚠️  杠杆设置失败，但继续运行（使用初始化时的杠杆: {self.trader.leverage}x）")
        
        # 预热策略
        self.warmup_strategy()
        
        # 🔴 检查API是否正确初始化
        if not hasattr(self.trader, 'exchange') or self.trader.exchange is None:
            self.logger.log_error("❌ OKX API未正确初始化！")
            self.logger.log_error("   请检查 okx_config.py 中的API配置：")
            self.logger.log_error("   - API_KEY")
            self.logger.log_error("   - API_SECRET")
            self.logger.log_error("   - API_PASSWORD")
            self.logger.log_error("   - test_mode 设置")
            self.logger.log_error("\n程序无法继续运行，请修复配置后重试。")
            return  # 🔴 直接返回，不启动交易循环
        
        # 🔴 获取并初始化账户余额
        try:
            account_info = self.trader.get_account_info()
            if account_info and 'balance' in account_info:
                # 🔴 使用可用余额（free），而不是总余额（total）
                self.account_balance = account_info['balance']['free']  # 可用余额
                self.account_total_balance = account_info['balance']['total']  # 总余额
                self.account_used_balance = account_info['balance']['used']  # 已用余额
                self.logger.log(f"💰 账户余额: 可用=${self.account_balance:,.2f} | 总余额=${self.account_total_balance:,.2f} | 已用=${self.account_used_balance:,.2f} USDT")
                self.logger.log(f"📊 仓位比例: {self.config.get('position_size_percentage', 100)}%")
                self.logger.log(f"💵 可用保证金: ${self.account_balance * self.config.get('position_size_percentage', 100) / 100:,.2f} USDT\n")
            else:
                self.logger.log_error("❌ 无法获取账户信息！")
                self.logger.log_error("   可能原因：")
                self.logger.log_error("   1. API权限不足（需要交易权限）")
                self.logger.log_error("   2. API Key错误或已过期")
                self.logger.log_error("   3. 网络连接问题")
                self.logger.log_error("\n程序无法继续运行，请检查API配置。")
                return  # 🔴 直接返回，不启动交易循环
        except Exception as e:
            self.logger.log_error(f"❌ 获取账户信息异常: {e}")
            self.logger.log_error("程序无法继续运行，请检查API配置。")
            import traceback
            traceback.print_exc()
            return  # 🔴 直接返回，不启动交易循环
        
        # 🔴 启动时同步OKX持仓状态到程序（必须成功，否则可能导致状态不一致）
        try:
            self.logger.log(f"\n{'='*80}")
            self.logger.log(f"🔍 【启动检查】开始验证持仓状态...")
            self.logger.log(f"{'='*80}")
            
            self._sync_position_on_startup()
            
            # 🔴 验证同步结果：检查策略状态是否与本地状态一致（以OKX实际持仓为准）
            if self.strategy:
                # 🔴 再次查询OKX实际持仓，确保状态一致
                try:
                    positions = self.trader.exchange.fetch_positions([self.symbol])
                    has_okx_position_final = self._check_okx_actual_positions(positions)
                    
                    if not has_okx_position_final:
                        # OKX确实无持仓，强制清空所有状态
                        if self.strategy.position is not None:
                            self.logger.log_warning(f"⚠️  OKX无持仓，但策略状态显示有持仓({self.strategy.position})")
                            self.logger.log(f"🔄 强制清空策略持仓状态（以OKX为准）")
                            self.strategy.position = None
                            self.strategy.entry_price = None
                            self.strategy.stop_loss_level = None
                            self.strategy.take_profit_level = None
                            self.strategy.max_loss_level = None
                            self.strategy.position_shares = None
                            self.strategy.current_invested_amount = 0
                            self.strategy.waiting_for_dv_target = False
                            self.strategy.target_dv_percent = None
                            self.logger.log(f"✅ 策略状态已清空")
                        
                        # 确保本地状态也为空
                        if self.current_position is not None:
                            self.logger.log(f"🔄 清空本地持仓状态")
                            self._clear_position_state()
                    else:
                        # OKX有持仓，检查策略状态是否一致
                        if self.current_position is None and self.strategy.position is not None:
                            self.logger.log_warning(f"⚠️  检测到状态不一致：本地无持仓，但策略状态显示有持仓({self.strategy.position})")
                            self.logger.log(f"🔄 清空策略持仓状态（以OKX为准）")
                            self.strategy.position = None
                            self.strategy.entry_price = None
                            self.strategy.stop_loss_level = None
                            self.strategy.take_profit_level = None
                            self.strategy.max_loss_level = None
                            self.strategy.position_shares = None
                            self.strategy.current_invested_amount = 0
                        elif self.current_position is not None and self.strategy.position is None:
                            self.logger.log_warning(f"⚠️  检测到状态不一致：本地有持仓({self.current_position})，但策略状态显示无持仓")
                            self.logger.log(f"🔄 同步策略状态到本地持仓")
                            self._sync_strategy_position_state(self.current_position)
                    
                    self.logger.log(f"✅ 启动检查完成: OKX持仓={has_okx_position_final}, 本地持仓={self.current_position}, 策略持仓={self.strategy.position}")
                except Exception as e:
                    self.logger.log_error(f"❌ 验证持仓状态失败: {e}")
                    # 为了安全，如果验证失败，清空策略状态
                    if self.strategy.position is not None:
                        self.logger.log_warning(f"⚠️  验证失败，为安全起见清空策略持仓状态")
                        self.strategy.position = None
                        self.strategy.entry_price = None
                        self.strategy.stop_loss_level = None
                        self.strategy.take_profit_level = None
                        self.strategy.max_loss_level = None
                        self.strategy.position_shares = None
                        self.strategy.current_invested_amount = 0
            
        except Exception as e:
            self.logger.log_error(f"❌ 启动时同步持仓状态失败: {e}")
            import traceback
            traceback.print_exc()
            self.logger.log_error("⚠️  警告：持仓状态同步失败，可能导致状态不一致！")
            self.logger.log_error("   建议：")
            self.logger.log_error("   1. 检查API配置是否正确")
            self.logger.log_error("   2. 检查网络连接")
            self.logger.log_error("   3. 手动检查OKX持仓状态")
            self.logger.log_error("   4. 必要时手动清空策略状态")
            # 🔴 不继续运行，因为状态不一致可能导致错误交易
            self.logger.log_error("\n程序将退出，请修复问题后重试。")
            return
        
        self.is_running = True
        self.logger.log(f"⏰ 每分钟01-05秒更新，{self.config['timeframe']}周期整点触发策略")
        self.logger.log(f"🔍 每分钟08-13秒主动检查数据完整性（紧跟正常更新，确保周期末尾数据完整）")
        self.logger.log(f"🔔 每分钟18-23秒检查止损/止盈单状态（有持仓时）")
        self.logger.log(f"🔄 每5分钟定期同步OKX状态（混合方案）")
        self.logger.log(f"🔍 每10秒检查并优化止损单（V2混合方案 - 条件单→限价单）")
        self.logger.log(f"⏱️  每30秒检查开仓订单是否已成交，成交后自动挂止损止盈单")
        self.logger.log(f"🔄 开始监控市场...\n")
        
        last_update_minute = None
        last_check_minute = None
        last_stop_check_minute = None
        last_periodic_sync_time = None  # 记录上次定期同步时间
        last_optimize_check_time = None  # 🔴 记录上次止损单优化检查时间
        
        while self.is_running:
            try:
                current_time = datetime.now()
                current_minute = current_time.replace(second=0, microsecond=0)
                current_second = current_time.second
                
                # 🔴 每分钟1-5秒：正常更新数据
                should_update = (
                    1 <= current_second <= 5 and
                    (last_update_minute is None or current_minute > last_update_minute)
                )
                
                if should_update:
                    success = self.run_once()
                    if success:
                        last_update_minute = current_minute
                
                # 🔍 每分钟05-09秒：主动检查数据完整性（预热完成后才开始检查）
                # 紧跟在01-05秒正常更新之后，确保周期末尾数据完整并及时触发策略
                should_check = (
                    not self.is_warmup_phase and
                    5 <= current_second <= 9 and
                    (last_check_minute is None or current_minute > last_check_minute)
                )
                
                if should_check:
                    self.logger.log(f"⏰ 触发数据完整性检查 (当前: {current_time.strftime('%H:%M:%S')})")
                    self.check_and_fill_missing_data()
                    last_check_minute = current_minute
                
                # 🔔 每分钟18-23秒：检查止损/止盈单状态（仅在有持仓时）
                # should_check_stop = (
                #     not self.is_warmup_phase and
                #     self.current_position and  # 只在有持仓时检查
                #     18 <= current_second <= 23 and
                #     (last_stop_check_minute is None or current_minute > last_stop_check_minute)
                # )
                
                # if should_check_stop:
                #     # self.logger.log(f"🔔 检查止损/止盈单状态...")
                #     self.check_stop_orders_status()
                #     last_stop_check_minute = current_minute
                
                # 🔄 每5分钟：定期同步OKX状态（混合方案）
                should_periodic_sync = (
                    not self.is_warmup_phase and
                    (last_periodic_sync_time is None or (current_time - last_periodic_sync_time).total_seconds() >= 300)  # 5分钟 = 300秒
                )
                
                if should_periodic_sync:
                    self.periodic_sync_with_okx()
                    last_periodic_sync_time = current_time
                
                # 🔴 每10秒：检查并优化止损单和开仓条件单（V2混合方案）
                should_optimize_check = (
                    not self.is_warmup_phase and
                    hasattr(self.trader, 'check_and_optimize_stop_orders') and
                    (last_optimize_check_time is None or (current_time - last_optimize_check_time).total_seconds() >= 10)  # 10秒
                )
                
                if should_optimize_check:
                    self.trader.check_and_optimize_stop_orders()
                    last_optimize_check_time = current_time
                
                # 🔴 每30秒：检查开仓订单是否已成交，如果成交则挂止损止盈单
                last_entry_check_time = getattr(self, '_last_entry_check_time', None)
                should_check_entry = (
                    not self.is_warmup_phase and
                    self.pending_entry_order_id is not None and
                    (last_entry_check_time is None or (current_time - last_entry_check_time).total_seconds() >= 30)  # 30秒
                )
                
                if should_check_entry:
                    self._check_entry_order_filled()
                    self._last_entry_check_time = current_time
                
                # 📊 每分钟30-35秒：打印持仓信息（调试用）
                should_print_position = (
                    not self.is_warmup_phase and
                    30 <= current_second <= 35 and
                    (last_update_minute is None or current_minute > last_update_minute)
                )
                
                if should_print_position:
                    self._print_position_status()
                
                time.sleep(1)
                
            except KeyboardInterrupt:
                self.logger.log("\n⚠️  收到停止信号...")
                self.stop()
                break
            except Exception as e:
                self.logger.log_error(f"运行错误: {e}")
                time.sleep(10)
    
    def stop(self):
        """停止"""
        self.logger.log("🛑 停止实盘交易...")
        self.is_running = False
        
        # 显示统计
        stats = self.daily_stats
        win_rate = (stats['winning_trades'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0
        
        self.logger.log(f"\n{'='*80}")
        self.logger.log(f"📊 今日统计")
        self.logger.log(f"{'='*80}")
        self.logger.log(f"交易: {stats['total_trades']}次 | "
                       f"盈: {stats['winning_trades']}次 | "
                       f"亏: {stats['losing_trades']}次 | "
                       f"胜率: {win_rate:.1f}%")
        self.logger.log(f"累计盈亏: ${stats['total_pnl']:+,.2f}")
        self.logger.log(f"{'='*80}\n")
        
        if self.db_service:
            self.db_service.disconnect()
        
        self.logger.log("✅ 已停止")


def main():
    """主程序"""
    
    print(f"\n{'='*80}")
    print(f"🛡️  OKX 实盘交易系统 - 止损止盈挂单版")
    print(f"💡 特性: 开仓自动挂单 | SAR止损动态更新 | 交易所自动监控")
    print(f"{'='*80}\n")
    
    config = get_strategy_config()
    
    print(f"📊 配置: {config['long_coin']} | {config['timeframe']} | "
          f"止盈{config['fixed_take_profit_pct']}% | 杠杆{TRADING_CONFIG.get('leverage', 1)}x")
    print(f"💡 模式: {'模拟盘' if TRADING_CONFIG['mode'] == 'paper' else '实盘'} | "
          f"测试: {'是' if TRADING_CONFIG['test_mode'] else '否'}\n")
    
    bot = LiveTradingBotWithStopOrders(config=config, test_mode=TRADING_CONFIG['test_mode'])
    
    def signal_handler(sig, frame):
        print(f"\n⚠️  收到退出信号...")
        bot.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot.start()

if __name__ == '__main__':
    main()