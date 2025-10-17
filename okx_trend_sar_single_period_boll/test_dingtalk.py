#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试钉钉消息推送功能
"""

from dingtalk_notifier import DingTalkNotifier
from datetime import datetime

def test_dingtalk_notifications():
    """测试钉钉推送功能"""
    
    # 钉钉webhook地址
    webhook_url = 'https://oapi.dingtalk.com/robot/send?access_token=8eecf36111e7448c7dc26244f33e69d0bdd12cfb7b53457882ea725069d74cc1'
    
    # 🔴 加签密钥（如果机器人设置了加签）
    secret = 'SEC8f4556064e9c31374422530eab63a65561f2bac0b8d1c3e7cfcaa2b8b4d44686'
    
    # 创建推送器（带加签）
    notifier = DingTalkNotifier(webhook_url, secret)
    
    print("=" * 60)
    print("📱 开始测试钉钉消息推送")
    print("=" * 60)
    
    # 测试1: 指标更新消息（无持仓）
    print("\n🔔 测试1: 发送指标更新消息（无持仓）")
    sar_result = {
        'sar_value': 2500.50,
        'sar_rising': True,
        'rsi': 55.32,
        'upper': 2550.00,
        'basis': 2500.00,
        'lower': 2450.00
    }
    
    notifier.send_indicator_update(
        timestamp=datetime.now(),
        timeframe='15m',
        sar_result=sar_result,
        position_info=None
    )
    
    # 测试2: 指标更新消息（有持仓）
    print("\n🔔 测试2: 发送指标更新消息（有持仓）")
    position_info = {
        'position': 'long',
        'entry_price': 2480.00,
        'current_price': 2510.00,
        'stop_loss_level': 2460.00,
        'take_profit_level': 2520.00
    }
    
    notifier.send_indicator_update(
        timestamp=datetime.now(),
        timeframe='15m',
        sar_result=sar_result,
        position_info=position_info
    )
    
    # 测试3: 开多单消息
    print("\n🔔 测试3: 发送开多单消息")
    position_info = {
        'invested_amount': 50000.00,
        'position_shares': 20.0,
        'stop_loss': 2460.00,
        'take_profit': 2520.00,
        'max_loss': 2440.00
    }
    
    notifier.send_open_position(
        timestamp=datetime.now(),
        direction='long',
        entry_price=2480.00,
        reason="SAR转多开仓 | 条件：SAR方向short→long | RSI过滤：55.32≤70",
        position_info=position_info
    )
    
    # 测试4: 开空单消息
    print("\n🔔 测试4: 发送开空单消息")
    position_info = {
        'invested_amount': 50000.00,
        'position_shares': 20.0,
        'stop_loss': 2540.00,
        'take_profit': 2480.00,
        'max_loss': None
    }
    
    notifier.send_open_position(
        timestamp=datetime.now(),
        direction='short',
        entry_price=2520.00,
        reason="SAR转空开仓 | 条件：SAR方向long→short | RSI过滤：45.68≥30",
        position_info=position_info
    )
    
    # 测试5: 盈利平仓消息
    print("\n🔔 测试5: 发送盈利平仓消息")
    notifier.send_close_position(
        timestamp=datetime.now(),
        position_type='long',
        entry_price=2480.00,
        exit_price=2520.00,
        profit_loss=800.00,
        return_rate=1.61,
        reason="多单固定止盈 | 条件：价格$2520.00≥止盈位$2520.00"
    )
    
    # 测试6: 亏损平仓消息
    print("\n🔔 测试6: 发送亏损平仓消息")
    notifier.send_close_position(
        timestamp=datetime.now(),
        position_type='short',
        entry_price=2520.00,
        exit_price=2540.00,
        profit_loss=-400.00,
        return_rate=-0.79,
        reason="空单SAR亏损平仓 | 条件：价格$2540.00≥SAR止损$2540.00"
    )
    
    print("\n" + "=" * 60)
    print("✅ 测试完成！请检查钉钉群消息")
    print("=" * 60)

if __name__ == "__main__":
    test_dingtalk_notifications()

