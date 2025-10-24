#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def get_strategy_config():
    """获取单周期SAR策略配置"""
    config = {
        # 基础配置
        'long_coin': 'ETH',
        'initial_capital': 100000,
        'position_size_percentage': 10,
        
        # 回测时间范围
        'start_date': '2025-09-01 00:00:00',
        'end_date': '2025-10-21 19:10:00',
        
        # 单周期SAR策略参数
        'timeframe': '15m',
        'length': 14,
        'damping': 0.9,
        
        # SAR参数
        'sar_start': 0.005,
        'sar_increment': 0.005,
        'sar_maximum': 0.04,
        
        # 布林带参数
        'mult': 2.0,
        
        # 波动率计算器参数
        'volatility_timeframe': '4h',  # 波动率计算周期
        'volatility_length': 7,  # 布林带EMA周期
        'volatility_mult': 2.0,  # 布林带标准差倍数
        'volatility_ema_period': 90,  # 波动率EMA平滑周期
        'volatility_threshold': 0.6,  # 波动率阈值倍数（当前值/EMA值）
        'basis_change_threshold': 50,  # 中轨变化率阈值（低于此值不开仓）
        
        # 止盈止损配置
        'fixed_take_profit_pct': 0.55,  # 固定止盈百分比（0表示无固定止盈）
        'max_loss_pct': 0,  # 最大亏损百分比（0表示无最大亏损限制）
        
        # 🔴 钉钉消息推送配置
        'dingtalk_webhook': 'https://oapi.dingtalk.com/robot/send?access_token=8eecf36111e7448c7dc26244f33e69d0bdd12cfb7b53457882ea725069d74cc1',
        'dingtalk_secret': 'SEC8f4556064e9c31374422530eab63a65561f2bac0b8d1c3e7cfcaa2b8b4d44686',  # 加签密钥
    }
    
    return config

def print_config_info():
    """打印策略配置信息"""
    config = get_strategy_config()
    
    print("=" * 60)
    print("📊 单周期SAR策略配置信息")
    print("=" * 60)
    
    print(f"🪙  交易币种: {config['long_coin']}")
    print(f"💰 初始资金: ${config['initial_capital']:,}")
    print(f"📊 仓位比例: {config['position_size_percentage']}%")
    print(f"📅 回测开始: {config['start_date']}")
    print(f"📅 回测结束: {config['end_date']}")
    
    print(f"\n🔧 SAR策略参数:")
    print(f"  ⏰ 时间周期: {config['timeframe']}")
    print(f"  📏 EMA周期: {config['length']}")
    print(f"  🔄 回归阻尼: {config['damping']}")
    print(f"  📈 标准差倍数: {config['mult']}")
    
    print(f"\n🎯 SAR指标参数:")
    print(f"  🚀 起始值: {config['sar_start']}")
    print(f"  📈 递增值: {config['sar_increment']}")
    print(f"  🔝 最大值: {config['sar_maximum']}")
    
    print(f"\n📊 波动率计算器参数:")
    print(f"  ⏰ 计算周期: {config['volatility_timeframe']}")
    print(f"  📏 布林带周期: {config['volatility_length']}")
    print(f"  📈 标准差倍数: {config['volatility_mult']}")
    print(f"  📊 EMA平滑周期: {config['volatility_ema_period']}")
    print(f"  🎯 波动率阈值: {config['volatility_threshold']}倍")
    print(f"  📈 中轨变化率阈值: {config['basis_change_threshold']} (低于此值不开仓)")
    
    print(f"\n💰 止盈止损配置:")
    if config['fixed_take_profit_pct'] > 0:
        print(f"  🎯 固定止盈: {config['fixed_take_profit_pct']}%")
    else:
        print(f"  🎯 固定止盈: 禁用")
    if config['max_loss_pct'] > 0:
        print(f"  🛑 最大亏损: {config['max_loss_pct']}%")
    else:
        print(f"  🛑 最大亏损: 禁用")
    print(f"  🛡️  动态止损: SAR线跟随")
    
    print(f"\n📱 消息推送配置:")
    if config.get('dingtalk_webhook'):
        print(f"  ✅ 钉钉推送: 已启用")
    else:
        print(f"  ❌ 钉钉推送: 未配置")
    
    print("=" * 60)