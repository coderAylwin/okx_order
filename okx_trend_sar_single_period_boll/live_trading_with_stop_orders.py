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
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trend_sar_single_period_boll_strategy import TrendSarStrategy
from okx_trader_enhanced import OKXTraderEnhanced  # 使用增强版
from okx_config import TRADING_CONFIG
from strategy_configs import get_strategy_config
from database_service import DatabaseService
from database_config import LOCAL_DATABASE_CONFIG
from trade_logger import TradeLogger
from kline_buffer import KlineBuffer
from trading_database_service import TradingDatabaseService  # 🔴 新增：交易数据库服务


class LiveTradingBotWithStopOrders:
    """实盘交易机器人 - 支持止损止盈挂单"""
    
    def __init__(self, config, test_mode=True):
        """初始化"""
        self.config = config
        self.test_mode = test_mode
        self.is_running = False
        self.is_warmup_phase = True
        self.first_period_completed = False
        
        # 初始化日志
        self.logger = TradeLogger()
        
        # 🔴 使用增强版交易接口
        leverage = TRADING_CONFIG.get('leverage', 1)
        self.trader = OKXTraderEnhanced(test_mode=test_mode, leverage=leverage)
        
        # 初始化数据库服务（K线数据）
        self.db_service = DatabaseService(config=LOCAL_DATABASE_CONFIG)
        
        # 🔴 初始化交易数据库服务（订单、交易记录），使用相同的数据库配置
        self.trading_db = TradingDatabaseService(db_config=LOCAL_DATABASE_CONFIG)
        print(f"✅ 交易数据库已连接: {LOCAL_DATABASE_CONFIG['database']}@{LOCAL_DATABASE_CONFIG['host']}")
        
        # 解析周期（如 '15m' -> 15）
        self.period_minutes = int(config['timeframe'].replace('m', '').replace('h', '')) if 'm' in config['timeframe'] else int(config['timeframe'].replace('h', '')) * 60
        
        # 🔴 初始化K线缓存管理器（缓存大小 = 周期分钟数）
        self.kline_buffer = KlineBuffer(buffer_size=self.period_minutes)
        
        # 初始化策略
        self.strategy = TrendSarStrategy(
            timeframe=config['timeframe'],
            length=config['length'],
            damping=config['damping'],
            sar_start=config['sar_start'],
            sar_increment=config['sar_increment'],
            sar_maximum=config['sar_maximum'],
            mult=config['mult'],
            initial_capital=config['initial_capital'],
            position_size_percentage=config['position_size_percentage'],
            fixed_take_profit_pct=config['fixed_take_profit_pct'],
            max_loss_pct=config['max_loss_pct'],
            volatility_timeframe=config['volatility_timeframe'],
            volatility_length=config['volatility_length'],
            volatility_mult=config['volatility_mult'],
            volatility_ema_period=config['volatility_ema_period'],
            volatility_threshold=config['volatility_threshold'],
            basis_change_threshold=config['basis_change_threshold'],
            dingtalk_webhook=config.get('dingtalk_webhook'),
            dingtalk_secret=config.get('dingtalk_secret')
        )
        
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
        self.current_position_shares = 0
        self.current_trade_id = None  # 🔴 当前交易ID（用于关联数据库记录）
        self.current_entry_order_id = None  # 🔴 当前开仓订单ID
        self.current_stop_loss_order_id = None  # 🔴 当前止损单ID
        self.current_take_profit_order_id = None  # 🔴 当前止盈单ID
        
        self.logger.log(f"{'='*80}")
        self.logger.log(f"🛡️  实盘交易机器人 - 止损止盈挂单版")
        self.logger.log(f"{'='*80}")
        self.logger.log(f"📊 交易对: {self.symbol}")
        self.logger.log(f"⏰ 策略周期: {config['timeframe']}")
        self.logger.log(f"🧪 测试模式: {'是' if self.test_mode else '否'}")
        self.logger.log(f"🛡️  特性: 开仓自动挂止损止盈单 | SAR止损动态更新")
        self.logger.log(f"{'='*80}\n")
    
    def warmup_strategy(self, warmup_days=60):
        """预热策略（与原版相同）"""
        self.logger.log(f"🔥 开始预热策略（{warmup_days}天数据）...")
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=warmup_days)
        
        start_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
        
        df = self.db_service.get_kline_data(
            self.config['long_coin'],
            start_str,
            end_str
        )
        
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
    
    def execute_signal(self, signal):
        """执行交易信号 - 增强版"""
        self.logger.log_signal(signal)
        
        signal_type = signal['type']
        print(f"🔍 执行信号: {signal_type}, 测试模式: {self.test_mode}")
        
        # 🔴 开仓前检查：如果有持仓记录但收到开仓信号，检查是否有未处理的平仓
        if signal_type in ['OPEN_LONG', 'OPEN_SHORT']:
            if self.current_position:
                print(f"⚠️  检测到有持仓记录({self.current_position})但收到开仓信号，检查是否有未处理的平仓...")
                self._check_pending_close()
        
        # 🔴 开仓 - 自动挂止损止盈单
        if signal_type == 'OPEN_LONG':
            position_shares = signal.get('position_shares', 0)
            invested_amount = signal.get('invested_amount', 0)
            
            entry_price = signal.get('price', 0)
            stop_loss = round(signal.get('stop_loss'), 1)  # SAR 止损位，保留1位小数
            take_profit = round(signal.get('take_profit'), 1)  # 固定止盈位，保留1位小数
            
            print(f"\n🔍 ========== OPEN_LONG 信号处理 ==========")
            print(f"🔍 信号价格: ${entry_price:.2f}")
            print(f"🔍 止损价格: ${stop_loss:.1f}")
            print(f"🔍 止盈价格: ${take_profit:.1f}")
            
            # 🔴 使用配置中的固定资金量（initial_capital），而不是账户总余额
            # 因为账户余额可能分配给多个策略
            strategy_capital = self.config.get('initial_capital', 500)
            position_size_pct = self.config.get('position_size_percentage', 100) / 100
            actual_invested = strategy_capital * position_size_pct
            
            print(f"💰 策略分配资金: ${strategy_capital:.2f}")
            print(f"💰 实际投入金额: ${actual_invested:.2f} (策略资金${strategy_capital:.2f} × {position_size_pct*100}%)")
            
            # 🔴 重新计算合约数量（从OKX获取合约规格）
            contract_amount = self.trader.calculate_contract_amount(
                self.symbol,
                actual_invested,
                entry_price
            )
            
            print(f"🔍 准备开多单:")
            print(f"   交易对: {self.symbol}")
            print(f"   投入金额: ${actual_invested:.2f}")
            print(f"   当前价格: ${entry_price:.2f}")
            print(f"   合约张数: {contract_amount}")
            print(f"   止损价格: ${stop_loss:.2f}")
            print(f"   止盈价格: ${take_profit:.2f}")
            print(f"🔍 开始调用OKX接口开多单...")
            
            # 调用增强版接口：开仓 + 挂单一次完成
            result = self.trader.open_long_with_stop_orders(
                self.symbol, 
                contract_amount,
                stop_loss_price=stop_loss,
                take_profit_price=take_profit
            )
            
            print(f"\n🔍 OKX开多单返回结果:")
            print(f"   入场订单: {result.get('entry_order')}")
            print(f"   止损订单: {result.get('stop_loss_order')}")
            print(f"   止盈订单: {result.get('take_profit_order')}")
            
            if result['entry_order']:
                self.current_position = 'long'
                self.current_position_side = 'long'
                self.current_position_shares = contract_amount
                self.daily_stats['total_trades'] += 1
                
                self.logger.log(f"✅ 开多单成功")
                self.logger.log(f"   止损单: {result['stop_loss_order']['id'] if result['stop_loss_order'] else '未设置'}")
                self.logger.log(f"   止盈单: {result['take_profit_order']['id'] if result['take_profit_order'] else '未设置'}")
                
                # 🔴 保存开仓订单到数据库
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
                    trade_id = self.trading_db.save_trade(
                        symbol=self.symbol,
                        position_side='long',
                        entry_order_id=entry_order_id,
                        entry_price=entry_price,
                        entry_time=datetime.now(),
                        amount=contract_amount,
                        invested_amount=actual_invested,
                        status='open'
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
        
        elif signal_type == 'OPEN_SHORT':
            position_shares = signal.get('position_shares', 0)
            invested_amount = signal.get('invested_amount', 0)
            entry_price = signal.get('price', 0)
            stop_loss = round(signal.get('stop_loss'), 1)  # SAR 止损位，保留1位小数
            take_profit = round(signal.get('take_profit'), 1)  # 固定止盈位，保留1位小数
            
            print(f"\n🔍 ========== OPEN_SHORT 信号处理 ==========")
            print(f"🔍 信号价格: ${entry_price:.2f}")
            print(f"🔍 止损价格: ${stop_loss:.1f}")
            print(f"🔍 止盈价格: ${take_profit:.1f}")
            
            # 🔴 使用配置中的固定资金量（initial_capital），而不是账户总余额
            # 因为账户余额可能分配给多个策略
            strategy_capital = self.config.get('initial_capital', 500)
            position_size_pct = self.config.get('position_size_percentage', 100) / 100
            actual_invested = strategy_capital * position_size_pct
            
            print(f"💰 策略分配资金: ${strategy_capital:.2f}")
            print(f"💰 实际投入金额: ${actual_invested:.2f} (策略资金${strategy_capital:.2f} × {position_size_pct*100}%)")
            
            # 🔴 重新计算合约数量（从OKX获取合约规格）
            contract_amount = self.trader.calculate_contract_amount(
                self.symbol,
                actual_invested,
                entry_price
            )
            
            print(f"🔍 准备开空单:")
            print(f"   交易对: {self.symbol}")
            print(f"   投入金额: ${actual_invested:.2f}")
            print(f"   当前价格: ${entry_price:.2f}")
            print(f"   合约张数: {contract_amount}")
            print(f"   止损价格: ${stop_loss:.2f}")
            print(f"   止盈价格: ${take_profit:.2f}")
            print(f"🔍 开始调用OKX接口开空单...")
            
            result = self.trader.open_short_with_stop_orders(
                self.symbol,
                contract_amount,
                stop_loss_price=stop_loss,
                take_profit_price=take_profit
            )
            
            print(f"\n🔍 OKX开空单返回结果:")
            print(f"   入场订单: {result.get('entry_order')}")
            print(f"   止损订单: {result.get('stop_loss_order')}")
            print(f"   止盈订单: {result.get('take_profit_order')}")
            
            if result['entry_order']:
                self.current_position = 'short'
                self.current_position_side = 'short'
                self.current_position_shares = contract_amount
                self.daily_stats['total_trades'] += 1
                
                self.logger.log(f"✅ 开空单成功")
                self.logger.log(f"   止损单: {result['stop_loss_order']['id'] if result['stop_loss_order'] else '未设置'}")
                self.logger.log(f"   止盈单: {result['take_profit_order']['id'] if result['take_profit_order'] else '未设置'}")
                
                # 🔴 保存开仓订单到数据库
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
                    trade_id = self.trading_db.save_trade(
                        symbol=self.symbol,
                        position_side='short',
                        entry_order_id=entry_order_id,
                        entry_price=entry_price,
                        entry_time=datetime.now(),
                        amount=contract_amount,
                        invested_amount=actual_invested,
                        status='open'
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
        
        # 🔴 平仓 - 主动市价平仓或OKX自动平仓
        elif signal_type in ['STOP_LOSS_LONG', 'TAKE_PROFIT_LONG', 'STOP_LOSS_SHORT', 'TAKE_PROFIT_SHORT']:
            profit_loss = signal.get('profit_loss', 0)
            exit_price = signal.get('price', 0)
            exit_timestamp = signal.get('exit_timestamp', datetime.now())
            exit_reason = signal.get('reason', signal_type)
            
            print(f"\n🔍 ========== 平仓信号处理 ==========")
            print(f"🔍 信号类型: {signal_type}")
            print(f"🔍 当前持仓: {self.current_position}")
            print(f"🔍 持仓数量: {self.current_position_shares}")
            print(f"🔍 平仓原因: {exit_reason}")
            
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
                        close_order = self.trader.exchange.create_market_sell_order(
                            self.symbol, 
                            self.current_position_shares
                        )
                    else:  # short
                        close_order = self.trader.exchange.create_market_buy_order(
                            self.symbol,
                            self.current_position_shares
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
            
            self.logger.log(f"✅ 平仓完成: 盈亏 ${profit_loss:+,.2f}")
        
        # 🔴 更新 SAR 止损位
        elif signal_type == 'UPDATE_STOP_LOSS':
            new_stop_loss = round(signal.get('new_stop_loss'), 1) if signal.get('new_stop_loss') else None  # 保留1位小数
            old_stop_loss = round(signal.get('old_stop_loss'), 1) if signal.get('old_stop_loss') else None  # 保留1位小数
            
            print(f"\n🔍 ========== UPDATE_STOP_LOSS 信号处理 ==========")
            print(f"🔍 当前持仓: {self.current_position}")
            print(f"🔍 新止损: {new_stop_loss}")
            print(f"🔍 旧止损: {old_stop_loss}")
            print(f"🔍 current_trade_id: {self.current_trade_id}")
            print(f"🔍 current_entry_order_id: {self.current_entry_order_id}")
            print(f"🔍 current_stop_loss_order_id: {self.current_stop_loss_order_id}")
            
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
                
                # 🔴 保存止损单更新记录到数据库（只保存到okx_stop_orders，不保存到okx_orders）
                try:
                    print(f"🔍 检查保存条件:")
                    print(f"   - result存在: {result is not None}")
                    print(f"   - 'id' in result: {'id' in result if result else False}")
                    print(f"   - current_trade_id存在: {self.current_trade_id is not None}")
                    
                    if result and 'id' in result and self.current_trade_id:
                        print(f"💾 更新止损单记录: 旧止损=${old_stop_loss:.1f} → 新止损=${new_stop_loss:.1f}")
                        print(f"💾 trade_id={self.current_trade_id}, old_order_id={self.current_stop_loss_order_id}")
                        
                        new_order_id = result['id']
                        
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
                            update_reason=signal.get('reason', 'SAR动态止损更新')
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
                    
                    # 如果止损单已触发（状态变为 closed/filled）
                    if stop_order['status'] in ['closed', 'filled']:
                        self.logger.log(f"🚨 检测到止损单触发: {self.current_stop_loss_order_id}")
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
                                float(pos.get('contracts', 0)) > 0 
                                for pos in positions 
                                if pos['symbol'] == self.symbol
                            )
                            
                            if not has_position:
                                self.logger.log(f"🚨 确认持仓已平，止损单已触发，但无法获取订单详情")
                                # 无法获取订单详情，只能清空状态
                                self._clear_position_state()
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
                    
                    if tp_order['status'] in ['closed', 'filled']:
                        self.logger.log(f"🚨 检测到止盈单触发: {self.current_take_profit_order_id}")
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
                                float(pos.get('contracts', 0)) > 0 
                                for pos in positions 
                                if pos['symbol'] == self.symbol
                            )
                            
                            if not has_position:
                                self.logger.log(f"🚨 确认持仓已平，止盈单已触发，但无法获取订单详情")
                                # 无法获取订单详情，只能清空状态
                                self._clear_position_state()
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
                    if stop_order['status'] in ['closed', 'filled']:
                        print(f"🚨 发现未处理的止损单触发，立即处理...")
                        self._handle_stop_order_triggered(stop_order, 'STOP_LOSS')
                        return
                        
                except Exception as e:
                    error_msg = str(e)
                    # 如果订单不存在，说明可能已被触发并删除
                    if '51603' in error_msg or 'does not exist' in error_msg.lower():
                        print(f"⚠️  止损单不存在(可能已触发): {self.current_stop_loss_order_id}")
                        print(f"🧹 清空持仓状态，继续开新仓...")
                        self._clear_position_state()
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
                    
                    if tp_order['status'] in ['closed', 'filled']:
                        print(f"🚨 发现未处理的止盈单触发，立即处理...")
                        self._handle_stop_order_triggered(tp_order, 'TAKE_PROFIT')
                        return
                        
                except Exception as e:
                    error_msg = str(e)
                    # 如果订单不存在，说明可能已被触发并删除
                    if '51603' in error_msg or 'does not exist' in error_msg.lower():
                        print(f"⚠️  止盈单不存在(可能已触发): {self.current_take_profit_order_id}")
                        print(f"🧹 清空持仓状态，继续开新仓...")
                        self._clear_position_state()
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
        self.current_position_shares = 0
        self.current_trade_id = None
        self.current_entry_order_id = None
        self.current_stop_loss_order_id = None
        self.current_take_profit_order_id = None
        
        # 清理策略对象的持仓状态
        if hasattr(self, 'strategy'):
            self.strategy.position = None
            self.strategy.entry_price = None
            self.strategy.stop_loss_level = None
            self.strategy.take_profit_level = None
            self.strategy.max_loss_level = None
            self.strategy.current_invested_amount = None
            self.strategy.position_shares = None
        
        print(f"✅ 持仓状态已清空")
    
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
                
                # 过滤出有持仓的记录（contracts > 0）
                has_okx_position = False
                for pos in positions:
                    if pos['symbol'] == self.symbol:
                        contracts = float(pos.get('contracts', 0))
                        if contracts > 0:
                            has_okx_position = True
                            side = pos.get('side', '').lower()
                            self.logger.log(f"📊 OKX实际持仓: {side}, {contracts}张")
                            break
                
                if not has_okx_position:
                    self.logger.log(f"📊 OKX实际持仓: 无")
                    
            except Exception as e:
                self.logger.log_error(f"查询OKX持仓失败: {e}")
                return
            
            # 3. 如果OKX没有持仓，但本地有未平仓记录，说明已被平仓
            if not has_okx_position and len(trades_data) > 0:
                self.logger.log(f"\n⚠️  发现不一致: 本地有{len(trades_data)}条未平仓记录，但OKX无持仓")
                
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
    
    def _save_indicator_signal(self, result, timestamp, open_price, high_price, low_price, close_price, volume):
        """保存指标信号到数据库"""
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
                    'period': self.strategy.sar_indicator.rsi_period if hasattr(self, 'strategy') else None
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
        """主动检查并补充缺失数据（每分钟08秒触发）
        
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
            recent_klines = list(self.kline_buffer.klines)[-3:] if len(self.kline_buffer.klines) >= 3 else list(self.kline_buffer.klines)
            cached_times = {kline['timestamp'] for kline in recent_klines}
            
            # 计算应该存在的时间点（最近3分钟）
            expected_times = []
            for i in range(1, 4):  # 检查最近3分钟
                expected_time = (current_time - timedelta(minutes=i)).replace(second=0, microsecond=0)
                expected_times.append(expected_time)
            
            # 找出缺失的时间点
            missing_times = []
            for expected_time in expected_times:
                if expected_time not in cached_times:
                    missing_times.append(expected_time)
            
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
                        
                        # 只补充缺失的时间点
                        if kline_time in missing_times:
                            buffer_size = self.kline_buffer.add_kline(
                                kline_time,
                                kline[1],  # open
                                kline[2],  # high
                                kline[3],  # low
                                kline[4],  # close
                                kline[5] if len(kline) > 5 else 0  # volume
                            )
                            
                            # 🔴 无论是否成功添加到缓存（可能重复），都记录这条数据
                            # 因为后续需要检查是否为周期末尾并触发策略
                            filled_klines.append({
                                'timestamp': kline_time,
                                'open': kline[1],
                                'high': kline[2],
                                'low': kline[3],
                                'close': kline[4],
                                'volume': kline[5] if len(kline) > 5 else 0
                            })
                            
                            if buffer_size != -1:  # 成功添加
                                added_count += 1
                                self.logger.log(f"✅ 补充数据: {kline_time.strftime('%H:%M')} "
                                              f"收盘:${kline[4]:.2f}")
                            else:
                                self.logger.log(f"ℹ️  数据已存在: {kline_time.strftime('%H:%M')} "
                                              f"收盘:${kline[4]:.2f} (将检查是否需要触发策略)")
                    
                    # 🔴 只要找到了缺失数据（无论是否重复），就检查是否需要触发策略
                    if filled_klines:
                        if added_count > 0:
                            self.logger.log(f"✅ 成功补充 {added_count} 条新数据")
                        else:
                            self.logger.log(f"ℹ️  缺失数据已存在于缓存，检查是否需要触发策略...")
                        
                        # 🔴 检查补充的数据中是否包含周期末尾数据
                        # 例如：5分钟周期，如果补充的是11:39的数据，才触发策略计算
                        # 如果补充的是11:37或11:38，则不触发（等到周期完整后再触发）
                        for filled_kline in filled_klines:
                            minute = filled_kline['timestamp'].minute
                            is_period_last_minute = (minute + 1) % self.period_minutes == 0
                            
                            print(f"🔍 检查补充数据: {filled_kline['timestamp'].strftime('%H:%M')}")
                            print(f"   分钟: {minute}, 周期: {self.period_minutes}")
                            print(f"   (分钟+1) % 周期 = ({minute}+1) % {self.period_minutes} = {(minute + 1) % self.period_minutes}")
                            print(f"   是周期末尾: {is_period_last_minute}")
                            print(f"   首周期完成: {self.first_period_completed}")
                            
                            if is_period_last_minute and self.first_period_completed:
                                self.logger.log(f"🎯 补充了周期末尾数据 ({filled_kline['timestamp'].strftime('%H:%M')}), 立即触发K线聚合和指标计算...")
                                
                                # 触发K线生成和策略计算
                                next_minute = filled_kline['timestamp'] + timedelta(minutes=1)
                                result = self.strategy.update(
                                    next_minute,
                                    filled_kline['close'],
                                    filled_kline['close'],
                                    filled_kline['close'],
                                    filled_kline['close'],
                                    0
                                )
                                
                                # 保存指标信号到数据库
                                if result and 'sar_result' in result:
                                    kline_timestamp = result.get('kline_timestamp', filled_kline['timestamp'])
                                    self._save_indicator_signal(
                                        result, 
                                        kline_timestamp, 
                                        filled_kline['open'], 
                                        filled_kline['high'], 
                                        filled_kline['low'], 
                                        filled_kline['close'], 
                                        filled_kline['volume']
                                    )
                                
                                # 处理交易信号
                                if result and result.get('signals'):
                                    for signal in result['signals']:
                                        self.execute_signal(signal)
                        
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
            
            buffer_size = self.kline_buffer.add_kline(
                timestamp, open_price, high_price, low_price, close_price, volume
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
                    for signal in result['signals']:
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
        
        # 设置杠杆
        leverage = TRADING_CONFIG.get('leverage', 1)
        margin_mode = TRADING_CONFIG.get('margin_mode', 'cross')
        
        if leverage > 1:
            self.logger.log(f"⚙️  设置杠杆: {leverage}x, 模式: {margin_mode}")
            self.trader.set_leverage(self.symbol, leverage, margin_mode)
        
        # 预热策略
        self.warmup_strategy()
        
        # 显示账户信息
        account_info = self.trader.get_account_info()
        if account_info:
            self.logger.log(f"💰 账户余额: ${account_info['balance']['total']:,.2f} USDT\n")
        
        self.is_running = True
        self.logger.log(f"⏰ 每分钟01-05秒更新，{self.config['timeframe']}周期整点触发策略")
        self.logger.log(f"🔍 每分钟08-13秒主动检查数据完整性（紧跟正常更新，确保周期末尾数据完整）")
        self.logger.log(f"🔔 每分钟18-23秒检查止损/止盈单状态（有持仓时）")
        self.logger.log(f"🔄 每1分钟同步数据库持仓状态与OKX（测试模式）")
        self.logger.log(f"🔄 开始监控市场...\n")
        
        last_update_minute = None
        last_check_minute = None
        last_stop_check_minute = None
        last_sync_time = None  # 记录上次同步时间
        
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
                
                # 🔍 每分钟08-13秒：主动检查数据完整性（预热完成后才开始检查）
                # 紧跟在01-05秒正常更新之后，确保周期末尾数据完整并及时触发策略
                should_check = (
                    not self.is_warmup_phase and
                    8 <= current_second <= 13 and
                    (last_check_minute is None or current_minute > last_check_minute)
                )
                
                if should_check:
                    self.logger.log(f"⏰ 触发数据完整性检查 (当前: {current_time.strftime('%H:%M:%S')})")
                    self.check_and_fill_missing_data()
                    last_check_minute = current_minute
                
                # 🔔 每分钟18-23秒：检查止损/止盈单状态（仅在有持仓时）
                should_check_stop = (
                    not self.is_warmup_phase and
                    self.current_position and  # 只在有持仓时检查
                    18 <= current_second <= 23 and
                    (last_stop_check_minute is None or current_minute > last_stop_check_minute)
                )
                
                if should_check_stop:
                    # self.logger.log(f"🔔 检查止损/止盈单状态...")
                    self.check_stop_orders_status()
                    last_stop_check_minute = current_minute
                
                # 🔄 每1分钟：同步数据库持仓状态与OKX实际持仓（测试模式）
                should_sync = (
                    not self.is_warmup_phase and
                    (last_sync_time is None or (current_time - last_sync_time).total_seconds() >= 60)  # 1分钟 = 60秒
                )
                
                if should_sync:
                    self.sync_open_trades_with_okx()
                    last_sync_time = current_time
                
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