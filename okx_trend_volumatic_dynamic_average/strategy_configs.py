#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def get_strategy_config():
    """获取纯VIDYA策略配置"""
    config = {
        # 基础配置
        'long_coin': 'SOL',
        'initial_capital': 100000,
        'position_size_percentage': 20,  # 全仓模式
        
        # 回测时间范围
        'start_date': '2025-01-01 00:00:00',
        'end_date': '2025-10-22 23:59:59',
        
        # 时间周期
        'timeframe': '5m',
        
        # 🔴 标准VIDYA指标参数
        'vidya_length': 18,           # VIDYA基础周期（类似EMA周期）
        'vidya_momentum': 15,           # CMO计算的动量周期
        'vidya_smooth': 15,            # 最终SMA平滑周期
        'vidya_band_distance': 5.0,    # ATR带宽距离因子
        'vidya_atr_period': 200,       # ATR计算周期
        'vidya_pivot_left': 3,         # 枢轴点左侧K线数量
        'vidya_pivot_right': 3,        # 枢轴点右侧K线数量
        
        # 🔴 固定周期Delta Volume配置
        'delta_volume_period': 14,     # 固定周期长度（使用最近N个K线）
        
        # 🔴 开仓条件配置（独立开关，开启的条件必须全部满足）
        'entry_condition_trend_breakthrough': False,   # 趋势突破（价格突破上下轨）
        'entry_condition_arrow_signal': False,        # 箭头信号（趋势转换）
        'entry_condition_vidya_slope': False,         # VIDYA斜率倾斜
        'entry_condition_delta_volume': False,         # Delta Volume支持
        'entry_condition_ema_120_slope': False,       # 🔴 EMA120斜率过滤（方向一致）
        
        # 📐 布林带中轨角度计算器配置（基于30分钟K线，整点开仓）
        # 🚀 激进配置：快速捕捉大行情，更敏感
        'enable_bb_angle_entry': True,             # 是否启用布林带角度独立开仓
        'bb_midline_period': 14,                    # EMA中轨周期 = 7根K线(3.5小时@30m) - 快速响应
        'bb_angle_window_size': 10,                 # 角度窗口 = 7根K线(3.5小时@30m) - 短期趋势
        'bb_angle_threshold': 0.04,                # 角度阈值 = 0.05° - 更敏感（3.5小时≈0.6%涨幅）
        'bb_r_squared_threshold': 0.65,            # R²阈值 = 0.45 - 允许波动，大行情初期也能抓住
        'bb_stop_loss_lock_periods': 3,            # 止损后锁定周期数（包含当前周期，实际等待4个完整周期=2小时）
        
        # 波动率计算器参数
        'volatility_timeframe': '4h',  # 波动率计算周期
        'volatility_length': 7,  # 布林带EMA周期
        'volatility_mult': 2.0,  # 布林带标准差倍数
        'volatility_ema_period': 90,  # 波动率EMA平滑周期
        'volatility_threshold': 0.6,  # 波动率阈值倍数（当前值/EMA值）
        'basis_change_threshold': 50,  # 中轨变化率阈值（低于此值不开仓）
        
        # 止盈止损配置
        'fixed_take_profit_pct': 1.5,  # 固定止盈百分比（0表示无固定止盈）
        'max_loss_pct': 2.5,  # 最大亏损百分比（0表示无最大亏损限制）
        
        # 🔴 钉钉消息推送配置
        'dingtalk_webhook': 'https://oapi.dingtalk.com/robot/send?access_token=75a73d165e1bb67a0ac6ff47562c67f8fcefda96375f39bab551e5bcd64b182d',
        'dingtalk_secret': 'SECbb23c0e4a7fc5b9fcaf8ea16fd1138a9e4194073f13faca083a3caf990a300a0',  # 加签密钥
    }
    
    return config

def print_config_info():
    """打印策略配置信息"""
    config = get_strategy_config()
    
    # print("=" * 60)
    # print("📊 纯VIDYA策略配置信息")
    # print("=" * 60)
    
    # print(f"🪙  交易币种: {config['long_coin']}")
    # print(f"💰 初始资金: ${config['initial_capital']:,}")
    # print(f"📊 仓位比例: {config['position_size_percentage']}%")
    # print(f"📅 回测开始: {config['start_date']}")
    # print(f"📅 回测结束: {config['end_date']}")
    
    # print(f"\n🔧 基础参数:")
    # print(f"  ⏰ 时间周期: {config['timeframe']}")
    
    # print(f"\n💫 VIDYA指标参数:")
    # print(f"  📏 VIDYA周期: {config['vidya_length']}")
    # print(f"  📊 动量周期: {config['vidya_momentum']}")
    # print(f"  ✨ 平滑周期: {config['vidya_smooth']}")
    # print(f"  📏 ATR带宽距离: {config['vidya_band_distance']}")
    # print(f"  📊 ATR周期: {config['vidya_atr_period']}")
    # print(f"  🔍 枢轴点左侧: {config['vidya_pivot_left']}")
    # print(f"  🔍 枢轴点右侧: {config['vidya_pivot_right']}")
    # print(f"  📊 固定周期Delta Volume: {config['delta_volume_period']}个K线")
    
    # print(f"\n🎯 开仓条件配置（开启的条件必须全部满足）:")
    # print(f"  1️⃣ 趋势突破: {'✅开启' if config['entry_condition_trend_breakthrough'] else '❌关闭'}")
    # print(f"  2️⃣ 箭头信号: {'✅开启' if config['entry_condition_arrow_signal'] else '❌关闭'}")
    # print(f"  3️⃣ VIDYA斜率: {'✅开启' if config['entry_condition_vidya_slope'] else '❌关闭'}")
    # print(f"  4️⃣ Delta Volume: {'✅开启' if config['entry_condition_delta_volume'] else '❌关闭'}")
    # print(f"  5️⃣ EMA120斜率: {'✅开启' if config['entry_condition_ema_120_slope'] else '❌关闭'}")
    
    # print(f"\n📊 波动率计算器参数:")
    # print(f"  ⏰ 计算周期: {config['volatility_timeframe']}")
    # print(f"  📏 布林带周期: {config['volatility_length']}")
    # print(f"  📈 标准差倍数: {config['volatility_mult']}")
    # print(f"  📊 EMA平滑周期: {config['volatility_ema_period']}")
    # print(f"  🎯 波动率阈值: {config['volatility_threshold']}倍")
    # print(f"  📈 中轨变化率阈值: {config['basis_change_threshold']} (低于此值不开仓)")
    
    # print(f"\n💰 止盈止损配置:")
    # if config['fixed_take_profit_pct'] > 0:
    #     print(f"  🎯 固定止盈: {config['fixed_take_profit_pct']}%")
    # else:
    #     print(f"  🎯 固定止盈: 禁用")
    # if config['max_loss_pct'] > 0:
    #     print(f"  🛑 最大亏损: {config['max_loss_pct']}%")
    # else:
    #     print(f"  🛑 最大亏损: 禁用")
    # print(f"  🛡️  动态止损: VIDYA趋势线跟随")
    
    # print("=" * 60)