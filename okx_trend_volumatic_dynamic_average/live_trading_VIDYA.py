#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OKX 实盘交易系统 V2 - VIDYA策略版
使用限价单策略节省手续费
"""

import sys
import os
import time
import signal
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trend_volumatic_dynamic_average_strategy import TrendVolumaticDynamicAverageStrategy
from okx_trader_v2 import OKXTraderV2  # 🔴 使用V2交易接口
from okx_config import TRADING_CONFIG
from strategy_configs import get_strategy_config
from database_service import DatabaseService
from database_config import LOCAL_DATABASE_CONFIG
from trade_logger import TradeLogger
from kline_buffer import KlineBuffer
from trading_database_service import TradingDatabaseService

# 🔴 导入原版的LiveTradingBotWithStopOrders类作为基类
from live_trading_with_stop_orders import LiveTradingBotWithStopOrders


class LiveTradingBotVIDYA(LiveTradingBotWithStopOrders):
    """实盘交易机器人 V2 - VIDYA策略版（使用限价单策略）"""
    
    def __init__(self, config, test_mode=True):
        """初始化 - 覆盖trader的初始化"""
        # 不调用父类__init__，因为我们要替换trader
        self.config = config
        self.test_mode = test_mode
        self.is_running = False
        self.is_warmup_phase = True
        self.first_period_completed = False
        
        # 初始化日志
        self.logger = TradeLogger()
        
        # 🔴 使用V2交易接口
        leverage = TRADING_CONFIG.get('leverage', 1)
        try:
            self.trader = OKXTraderV2(test_mode=test_mode, leverage=leverage)
            
            # 验证API是否正确初始化
            if not hasattr(self.trader, 'exchange') or self.trader.exchange is None:
                print("❌ 警告: OKX API未正确初始化")
                print("   请检查 okx_config.py 中的API配置")
        except Exception as e:
            print(f"❌ 初始化OKX交易接口V2失败: {e}")
            raise
        
        # 初始化数据库服务（K线数据）
        try:
            self.db_service = DatabaseService(config=LOCAL_DATABASE_CONFIG)
        except Exception as e:
            print(f"⚠️  初始化K线数据库失败: {e}")
            print("   程序将继续运行，但预热功能将不可用")
            self.db_service = None
        
        # 🔴 初始化交易数据库服务
        try:
            self.trading_db = TradingDatabaseService(db_config=LOCAL_DATABASE_CONFIG)
            print(f"✅ 交易数据库已连接: {LOCAL_DATABASE_CONFIG['database']}@{LOCAL_DATABASE_CONFIG['host']}")
        except Exception as e:
            print(f"⚠️  初始化交易数据库失败: {e}")
            print("   程序将继续运行，但订单记录功能将不可用")
            self.trading_db = None
        
        # 解析周期
        self.period_minutes = int(config['timeframe'].replace('m', '').replace('h', '')) if 'm' in config['timeframe'] else int(config['timeframe'].replace('h', '')) * 60
        
        # 🔴 初始化K线缓存管理器
        self.kline_buffer = KlineBuffer(buffer_size=self.period_minutes)
        
        # 初始化策略 - VIDYA策略
        self.strategy = TrendVolumaticDynamicAverageStrategy(
            timeframe=config['timeframe'],
            initial_capital=config['initial_capital'],
            position_size_percentage=config['position_size_percentage'],
            fixed_take_profit_pct=config['fixed_take_profit_pct'],
            max_loss_pct=config['max_loss_pct'],
            volatility_timeframe=config['volatility_timeframe'],
            volatility_length=config['volatility_length'],
            volatility_mult=config['volatility_mult'],
            volatility_ema_period=config['volatility_ema_period'],
            volatility_threshold=config['volatility_threshold'],
            vidya_length=config['vidya_length'],
            vidya_momentum=config['vidya_momentum'],
            vidya_smooth=config['vidya_smooth'],
            vidya_band_distance=config['vidya_band_distance'],
            vidya_atr_period=config['vidya_atr_period'],
            vidya_pivot_left=config['vidya_pivot_left'],
            vidya_pivot_right=config['vidya_pivot_right'],
            delta_volume_period=config['delta_volume_period'],
            entry_condition_trend_breakthrough=config['entry_condition_trend_breakthrough'],
            entry_condition_arrow_signal=config['entry_condition_arrow_signal'],
            entry_condition_vidya_slope=config['entry_condition_vidya_slope'],
            entry_condition_delta_volume=config['entry_condition_delta_volume'],
            entry_condition_ema_120_slope=config['entry_condition_ema_120_slope'],
            enable_bb_angle_entry=config['enable_bb_angle_entry'],
            bb_midline_period=config['bb_midline_period'],
            bb_angle_window_size=config['bb_angle_window_size'],
            bb_angle_threshold=config['bb_angle_threshold'],
            bb_r_squared_threshold=config['bb_r_squared_threshold'],
            bb_stop_loss_lock_periods=config['bb_stop_loss_lock_periods'],
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
            'maker_orders': 0,  # 🔴 V2新增：Maker订单数
            'taker_orders': 0,  # 🔴 V2新增：Taker订单数
            'saved_fees': 0.0,  # 🔴 V2新增：节省的手续费
        }
        
        # 🔴 记录当前持仓信息
        self.current_position = None
        self.current_position_side = None
        self.current_position_shares = 0
        self.current_trade_id = None
        self.current_entry_order_id = None
        self.current_stop_loss_order_id = None
        self.current_take_profit_order_id = None
        
        # 🔴 账户余额
        self.account_balance = 0.0
        
        self.logger.log(f"{'='*80}")
        self.logger.log(f"🛡️  实盘交易机器人 V2 - VIDYA策略版")
        self.logger.log(f"{'='*80}")
        self.logger.log(f"📊 交易对: {self.symbol}")
        self.logger.log(f"⏰ 策略周期: {config['timeframe']}")
        self.logger.log(f"🧪 测试模式: {'是' if self.test_mode else '否'}")
        self.logger.log(f"💰 V2特性: 智能挂单 | 每10秒重试 | 节省60%手续费 | Maker手续费0.02%")
        self.logger.log(f"{'='*80}\n")


def main():
    """主程序"""
    
    print(f"\n{'='*80}")
    print(f"🛡️  OKX 实盘交易系统 V2 - VIDYA策略版")
    print(f"💡 特性: 智能挂单 | 持续重试直到成交 | 节省60%手续费")
    print(f"{'='*80}\n")
    
    config = get_strategy_config()
    
    print(f"📊 配置: {config['long_coin']} | {config['timeframe']} | "
          f"止盈{config['fixed_take_profit_pct']}% | 杠杆{TRADING_CONFIG.get('leverage', 1)}x")
    print(f"💡 模式: {'模拟盘' if TRADING_CONFIG['mode'] == 'paper' else '实盘'} | "
          f"测试: {'是' if TRADING_CONFIG['test_mode'] else '否'}\n")
    
    print(f"⚠️  V2版本说明:")
    print(f"   - 开仓使用限价单（买3/卖3），每10秒检查并重新挂单")
    print(f"   - 持续挂单直到成交，最多尝试30次（5分钟）")
    print(f"   - 价格穿透自动降级到买4/卖4、买5/卖5")
    print(f"   - 止损止盈使用限价单，价格接近时触发")
    print(f"   - Maker手续费: 0.02% vs Taker手续费: 0.05%")
    print(f"   - 预期节省60%手续费\n")
    
    bot = LiveTradingBotVIDYA(config=config, test_mode=TRADING_CONFIG['test_mode'])
    
    def signal_handler(sig, frame):
        print(f"\n⚠️  收到退出信号...")
        bot.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot.start()

if __name__ == '__main__':
    main()

