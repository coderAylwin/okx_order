#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置检查工具
在运行实盘前检查所有配置是否正确
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from okx_config import OKX_API_CONFIG, TRADING_CONFIG
from strategy_configs import get_strategy_config
from database_config import LOCAL_DATABASE_CONFIG


def check_okx_api_config():
    """检查OKX API配置"""
    print(f"\n{'='*80}")
    print(f"🔍 检查 OKX API 配置...")
    print(f"{'='*80}\n")
    
    issues = []
    
    # 检查必填字段
    if OKX_API_CONFIG['api_key'] == 'YOUR_API_KEY':
        issues.append("❌ API Key 未配置（仍为默认值）")
    else:
        print(f"✅ API Key: {OKX_API_CONFIG['api_key'][:10]}...")
    
    if OKX_API_CONFIG['secret'] == 'YOUR_SECRET_KEY':
        issues.append("❌ Secret Key 未配置")
    else:
        print(f"✅ Secret Key: 已配置")
    
    if OKX_API_CONFIG['password'] == 'YOUR_PASSWORD':
        issues.append("❌ Password 未配置")
    else:
        print(f"✅ Password: 已配置")
    
    return issues


def check_trading_config():
    """检查交易配置"""
    print(f"\n{'='*80}")
    print(f"🔍 检查交易配置...")
    print(f"{'='*80}\n")
    
    issues = []
    warnings = []
    
    # 检查模式
    mode = TRADING_CONFIG['mode']
    test_mode = TRADING_CONFIG['test_mode']
    
    print(f"💡 交易模式: {mode}")
    print(f"🧪 测试模式: {test_mode}")
    
    if mode == 'live' and test_mode:
        warnings.append("⚠️  实盘模式但启用了测试模式（不会实际下单）")
    
    if mode == 'live' and not test_mode:
        warnings.append("🔴 【警告】实盘模式且测试模式关闭（会实际下单！）")
    
    # 检查风险控制
    max_position = TRADING_CONFIG['max_position_value']
    print(f"💰 最大持仓价值: ${max_position:,.2f}")
    
    if max_position > 50000:
        warnings.append(f"⚠️  最大持仓价值较大: ${max_position:,.2f}")
    
    # 检查更新间隔
    interval = TRADING_CONFIG['update_interval']
    print(f"⏰ 更新间隔: {interval}秒")
    
    if interval < 30:
        warnings.append(f"⚠️  更新间隔太短可能触发API限流: {interval}秒")
    
    return issues, warnings


def check_strategy_config():
    """检查策略配置"""
    print(f"\n{'='*80}")
    print(f"🔍 检查策略配置...")
    print(f"{'='*80}\n")
    
    issues = []
    warnings = []
    
    config = get_strategy_config()
    
    print(f"🪙  交易币种: {config['long_coin']}")
    print(f"⏰ 时间周期: {config['timeframe']}")
    print(f"💰 初始资金: ${config['initial_capital']:,.2f}")
    print(f"📊 仓位比例: {config['position_size_percentage']}%")
    print(f"🎯 固定止盈: {config['fixed_take_profit_pct']}%")
    if config.get('max_stop_loss_pct', 0) > 0:
        print(f"🛡️  最大止损: {config['max_stop_loss_pct']}% (双重止损机制)")
    else:
        print(f"🛡️  最大止损: 禁用")
    
    # 检查止盈止损设置
    if config['fixed_take_profit_pct'] == 0 and config.get('max_stop_loss_pct', 0) == 0:
        warnings.append("⚠️  未设置止盈和止损（高风险！）")
    
    if config['position_size_percentage'] == 100:
        warnings.append("⚠️  使用全仓模式（高风险！）")
    
    return issues, warnings


def check_database_config():
    """检查数据库配置"""
    print(f"\n{'='*80}")
    print(f"🔍 检查数据库配置...")
    print(f"{'='*80}\n")
    
    issues = []
    
    print(f"🗄️  数据库: {LOCAL_DATABASE_CONFIG['database']}")
    print(f"🌐 主机: {LOCAL_DATABASE_CONFIG['host']}:{LOCAL_DATABASE_CONFIG['port']}")
    print(f"👤 用户: {LOCAL_DATABASE_CONFIG['user']}")
    
    # 尝试连接数据库
    try:
        from database_service import DatabaseService
        db = DatabaseService(**LOCAL_DATABASE_CONFIG)
        print(f"✅ 数据库连接成功")
        db.disconnect()
    except Exception as e:
        issues.append(f"❌ 数据库连接失败: {e}")
    
    return issues


def main():
    """主程序"""
    
    print(f"\n{'='*80}")
    print(f"🔍 OKX 实盘交易系统 - 配置检查工具")
    print(f"{'='*80}")
    
    all_issues = []
    all_warnings = []
    
    # 1. 检查OKX API配置
    okx_issues = check_okx_api_config()
    all_issues.extend(okx_issues)
    
    # 2. 检查交易配置
    trading_issues, trading_warnings = check_trading_config()
    all_issues.extend(trading_issues)
    all_warnings.extend(trading_warnings)
    
    # 3. 检查策略配置
    strategy_issues, strategy_warnings = check_strategy_config()
    all_issues.extend(strategy_issues)
    all_warnings.extend(strategy_warnings)
    
    # 4. 检查数据库配置
    db_issues = check_database_config()
    all_issues.extend(db_issues)
    
    # 显示总结
    print(f"\n{'='*80}")
    print(f"📊 检查结果总结")
    print(f"{'='*80}\n")
    
    if all_issues:
        print(f"❌ 发现 {len(all_issues)} 个问题:")
        for issue in all_issues:
            print(f"  {issue}")
        print(f"\n⚠️  请修复以上问题后再运行实盘！")
    else:
        print(f"✅ 未发现配置问题")
    
    if all_warnings:
        print(f"\n⚠️  发现 {len(all_warnings)} 个警告:")
        for warning in all_warnings:
            print(f"  {warning}")
        print(f"\n💡 建议检查以上警告项")
    
    if not all_issues and not all_warnings:
        print(f"\n🎉 所有配置检查通过！")
        print(f"✅ 可以运行实盘交易")
    
    print(f"\n{'='*80}\n")
    
    # 返回状态码
    return 0 if not all_issues else 1


if __name__ == '__main__':
    sys.exit(main())

