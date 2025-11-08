#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
检查OKX账户余额和保证金状态
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from okx_trader_enhanced import OKXTraderEnhanced
from okx_config import TRADING_CONFIG

def check_account_balance():
    """检查账户余额和保证金状态"""
    
    print("="*80)
    print("OKX 账户余额和保证金检查")
    print("="*80)
    
    # 初始化交易接口
    trader = OKXTraderEnhanced(test_mode=TRADING_CONFIG['test_mode'], leverage=3)
    
    symbol = 'ETH-USDT-SWAP'
    
    # 1. 获取详细账户余额
    print("\n【1. 详细账户余额】")
    try:
        balance = trader.get_balance()
        if balance:
            print(f"总余额: {balance['total']:.2f} USDT")
            print(f"可用余额: {balance['free']:.2f} USDT")
            print(f"已用余额: {balance['used']:.2f} USDT")
            
            # 检查可用余额是否足够
            if balance['free'] < 500:
                print(f"⚠️  可用余额不足500 USDT，当前只有 {balance['free']:.2f} USDT")
        else:
            print("❌ 无法获取余额信息")
            return
    except Exception as e:
        print(f"❌ 获取余额失败: {e}")
        return
    
    # 2. 获取原始余额信息（更详细）
    print("\n【2. 原始余额信息】")
    try:
        raw_balance = trader.exchange.fetch_balance()
        print("原始余额数据:")
        for currency, amounts in raw_balance.items():
            if currency == 'USDT' or (isinstance(amounts, dict) and 'USDT' in amounts):
                print(f"  {currency}: {amounts}")
    except Exception as e:
        print(f"❌ 获取原始余额失败: {e}")
    
    # 3. 获取当前持仓
    print("\n【3. 当前持仓】")
    try:
        positions = trader.exchange.fetch_positions([symbol])
        has_position = False
        for pos in positions:
            if pos['symbol'] == symbol:
                contracts = float(pos.get('contracts', 0))
                if contracts > 0:
                    has_position = True
                    print(f"持仓方向: {pos.get('side', 'unknown')}")
                    print(f"持仓数量: {contracts} 张")
                    print(f"开仓价: {pos.get('entryPrice', 0):.2f}")
                    print(f"未实现盈亏: {pos.get('unrealizedPnl', 0):.2f}")
                    print(f"保证金: {pos.get('initialMargin', 0):.2f}")
                    print(f"杠杆: {pos.get('leverage', 0)}x")
                    break
        
        if not has_position:
            print("无持仓")
    except Exception as e:
        print(f"❌ 获取持仓失败: {e}")
    
    # 4. 获取最新价格
    print("\n【4. 最新价格】")
    try:
        ticker = trader.exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        print(f"当前价格: {current_price:.2f} USDT")
    except Exception as e:
        print(f"❌ 获取价格失败: {e}")
        current_price = None
    
    # 5. 计算实际可开仓数量
    print("\n【5. 实际可开仓计算】")
    if balance and current_price:
        available_balance = balance['free']
        leverage = 3
        
        print(f"可用余额: {available_balance:.2f} USDT")
        print(f"杠杆: {leverage}x")
        
        # 保守计算：留出10%的缓冲
        safe_balance = available_balance * 0.9
        print(f"安全余额(90%): {safe_balance:.2f} USDT")
        
        # 计算可开张数
        contract_size = 0.1  # ETH-USDT-SWAP
        position_value = safe_balance * leverage
        coin_amount = position_value / current_price
        max_contracts = coin_amount / contract_size
        
        # 向下取整到0.01
        max_contracts = int(max_contracts * 100) / 100
        
        print(f"最大仓位价值: {position_value:.2f} USDT")
        print(f"可购ETH数量: {coin_amount:.4f} ETH")
        print(f"建议最大张数: {max_contracts} 张")
        
        # 计算实际所需保证金
        required_margin = (max_contracts * contract_size * current_price) / leverage
        print(f"实际所需保证金: {required_margin:.2f} USDT")
        
        if required_margin > available_balance:
            print(f"⚠️  所需保证金({required_margin:.2f}) > 可用余额({available_balance:.2f})")
            # 重新计算更小的张数
            max_safe_contracts = int((available_balance * leverage / current_price / contract_size) * 100) / 100
            print(f"建议调整张数为: {max_safe_contracts} 张")
        else:
            print(f"✅ 保证金充足")
    
    # 6. 检查账户配置
    print("\n【6. 账户配置检查】")
    try:
        # 检查杠杆设置
        leverage_info = trader.exchange.private_get_account_leverage_info({'instId': symbol})
        if leverage_info.get('code') == '0' and leverage_info.get('data'):
            lever_data = leverage_info['data'][0]
            print(f"当前杠杆: {lever_data.get('lever')}x")
            print(f"保证金模式: {lever_data.get('mgnMode')}")
            print(f"持仓模式: {lever_data.get('posMode')}")
    except Exception as e:
        print(f"❌ 获取杠杆信息失败: {e}")
    
    # 7. 建议
    print("\n【7. 建议】")
    if balance and balance['free'] < 500:
        print("🔧 解决方案:")
        print("1. 增加账户余额到至少 600 USDT")
        print("2. 或者降低仓位比例到 80% 或更低")
        print("3. 或者降低杠杆倍数到 2x")
        print("4. 检查是否有其他未平仓的订单占用保证金")
    else:
        print("✅ 账户余额充足，可以正常交易")

if __name__ == '__main__':
    check_account_balance()
