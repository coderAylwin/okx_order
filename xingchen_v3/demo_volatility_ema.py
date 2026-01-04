#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from strategy_configs import get_strategy_config, print_config_info

def demo_volatility_ema_config():
    """演示波动率EMA配置"""
    print("🎯 波动率EMA平滑功能演示")
    print("=" * 60)
    
    # 显示配置信息
    print_config_info()
    
    print("\n📊 功能说明:")
    print("1. 计算布林带宽度/中轨的比值作为波动率指标")
    print("2. 使用EMA对波动率比值进行平滑处理")
    print("3. 在开仓时比较当前波动率与EMA平滑值")
    print("4. 只有当当前波动率 ≥ 阈值倍数 × EMA平滑值时才允许开仓")
    
    print("\n🔧 配置参数说明:")
    config = get_strategy_config()
    print(f"  📏 volatility_ema_period: {config['volatility_ema_period']} - EMA平滑周期")
    print(f"  🎯 volatility_threshold: {config['volatility_threshold']} - 波动率阈值倍数")
    
    print("\n💡 使用场景:")
    print("  - 避免在低波动率环境下开仓（减少假信号）")
    print("  - 只在市场波动足够大时才进行交易")
    print("  - 提高交易信号的质量和可靠性")
    
    print("\n📈 计算逻辑:")
    print("  1. 波动率比值 = 布林带宽度 / 布林带中轨")
    print("  2. 波动率EMA = EMA(波动率比值, volatility_ema_period)")
    print("  3. 波动率比较 = 当前波动率比值 / 波动率EMA")
    print("  4. 开仓条件 = SAR方向改变 AND 波动率比较 ≥ volatility_threshold")
    
    print("\n✅ 功能已集成到策略中，可以开始回测！")

if __name__ == "__main__":
    demo_volatility_ema_config()
