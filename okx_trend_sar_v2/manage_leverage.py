#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
杠杆管理工具
用于查看和设置OKX交易对的杠杆倍数
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from okx_trader import OKXTrader
from okx_config import TRADING_CONFIG


def main():
    """主程序"""
    
    print(f"\n{'='*80}")
    print(f"⚙️  OKX 杠杆管理工具")
    print(f"{'='*80}\n")
    
    # 初始化交易接口
    trader = OKXTrader(test_mode=TRADING_CONFIG['test_mode'])
    
    # 获取所有交易对
    symbols = TRADING_CONFIG['symbols']
    
    print(f"📊 当前配置的交易对:\n")
    
    # 查询每个交易对的杠杆信息
    for coin, symbol in symbols.items():
        print(f"🪙  {coin} ({symbol}):")
        
        leverage_info = trader.get_leverage(symbol)
        if leverage_info:
            print(f"   📊 当前杠杆: {leverage_info['leverage']}x")
            print(f"   📊 保证金模式: {leverage_info['margin_mode']}")
        else:
            print(f"   ❌ 无法获取杠杆信息")
        print()
    
    # 询问是否要修改杠杆
    print(f"{'='*80}")
    response = input(f"是否要修改杠杆倍数？(y/n): ").strip().lower()
    
    if response != 'y':
        print(f"❌ 已取消")
        return
    
    # 选择交易对
    print(f"\n请选择交易对:")
    for i, (coin, symbol) in enumerate(symbols.items(), 1):
        print(f"  {i}) {coin} ({symbol})")
    
    try:
        choice = int(input(f"\n输入选项 (1-{len(symbols)}): "))
        if choice < 1 or choice > len(symbols):
            print(f"❌ 无效选项")
            return
        
        selected_coin = list(symbols.keys())[choice - 1]
        selected_symbol = symbols[selected_coin]
        
    except ValueError:
        print(f"❌ 无效输入")
        return
    
    # 输入杠杆倍数
    try:
        new_leverage = int(input(f"请输入杠杆倍数 (1-125): "))
        if new_leverage < 1 or new_leverage > 125:
            print(f"❌ 杠杆倍数必须在 1-125 之间")
            return
    except ValueError:
        print(f"❌ 无效输入")
        return
    
    # 选择保证金模式
    print(f"\n请选择保证金模式:")
    print(f"  1) 全仓 (cross)")
    print(f"  2) 逐仓 (isolated)")
    
    try:
        mode_choice = int(input(f"\n输入选项 (1-2): "))
        margin_mode = 'cross' if mode_choice == 1 else 'isolated'
    except ValueError:
        print(f"❌ 无效输入")
        return
    
    # 确认修改
    print(f"\n{'='*80}")
    print(f"⚠️  即将修改杠杆设置:")
    print(f"   交易对: {selected_symbol}")
    print(f"   杠杆倍数: {new_leverage}x")
    print(f"   保证金模式: {margin_mode}")
    print(f"{'='*80}")
    
    confirm = input(f"\n确认修改？(yes/no): ").strip().lower()
    if confirm != 'yes':
        print(f"❌ 已取消")
        return
    
    # 执行修改
    success = trader.set_leverage(selected_symbol, new_leverage, margin_mode)
    
    if success:
        print(f"\n✅ 杠杆修改成功！")
        
        # 验证修改结果
        leverage_info = trader.get_leverage(selected_symbol)
        if leverage_info:
            print(f"\n📊 修改后的杠杆信息:")
            print(f"   杠杆倍数: {leverage_info['leverage']}x")
            print(f"   保证金模式: {leverage_info['margin_mode']}")
    else:
        print(f"\n❌ 杠杆修改失败！")
    
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()

