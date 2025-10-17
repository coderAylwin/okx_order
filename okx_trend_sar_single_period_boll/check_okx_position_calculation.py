#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证OKX合约张数计算
查询实际的账户信息和可开仓张数
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from okx_trader_enhanced import OKXTraderEnhanced
from okx_config import TRADING_CONFIG

def check_okx_calculation():
    """检查OKX的真实计算方式"""
    
    print("="*80)
    print("OKX 合约张数计算验证")
    print("="*80)
    
    # 初始化交易接口
    trader = OKXTraderEnhanced(test_mode=False, leverage=2)
    
    symbol = 'ETH-USDT-SWAP'
    
    # 1. 获取账户余额
    print("\n【1. 账户余额】")
    balance = trader.get_balance()
    if balance:
        print(f"总余额: {balance['total']:.2f} USDT")
        print(f"可用余额: {balance['free']:.2f} USDT")
        print(f"已用余额: {balance['used']:.2f} USDT")
    
    # 2. 获取当前持仓
    print("\n【2. 当前持仓】")
    position = trader.get_position(symbol)
    if position:
        print(f"持仓方向: {position['side']}")
        print(f"持仓数量: {position['contracts']} 张")
        print(f"开仓价: {position['entry_price']:.2f}")
        print(f"未实现盈亏: {position['unrealized_pnl']:.2f}")
        print(f"杠杆: {position['leverage']}x")
    else:
        print("无持仓")
    
    # 3. 获取最新价格
    print("\n【3. 最新价格】")
    try:
        ticker = trader.exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        print(f"当前价格: {current_price:.2f} USDT")
    except Exception as e:
        print(f"获取价格失败: {e}")
        current_price = None
    
    # 4. 获取合约规格
    print("\n【4. 合约规格】")
    contract_size = trader.get_contract_size(symbol)
    print(f"每张合约: {contract_size} ETH")
    
    # 5. 获取杠杆设置
    print("\n【5. 杠杆设置】")
    try:
        # 查询杠杆
        leverage_info = trader.exchange.private_get_account_leverage_info({'instId': symbol})
        if leverage_info.get('code') == '0' and leverage_info.get('data'):
            lever_data = leverage_info['data'][0]
            print(f"多头杠杆: {lever_data.get('lever')}x")
            print(f"保证金模式: {lever_data.get('mgnMode')}")
    except Exception as e:
        print(f"获取杠杆信息失败: {e}")
    
    # 6. 计算可开张数（理论值）
    print("\n【6. 理论计算（基于代码）】")
    if balance and current_price:
        available_balance = balance['free']
        leverage = 2
        
        print(f"\n方式1: 使用全部可用余额")
        print(f"  可用余额: {available_balance:.2f} USDT")
        print(f"  杠杆: {leverage}x")
        print(f"  购买力: {available_balance * leverage:.2f} USDT")
        print(f"  可购ETH: {(available_balance * leverage) / current_price:.4f} ETH")
        max_contracts = int((available_balance * leverage) / current_price / contract_size)
        print(f"  可开张数: {max_contracts} 张")
        
        print(f"\n方式2: 使用50U保证金")
        margin_50 = 50
        print(f"  保证金: {margin_50:.2f} USDT")
        print(f"  杠杆: {leverage}x")
        print(f"  购买力: {margin_50 * leverage:.2f} USDT")
        print(f"  可购ETH: {(margin_50 * leverage) / current_price:.4f} ETH")
        contracts_50 = int((margin_50 * leverage) / current_price / contract_size)
        print(f"  可开张数: {contracts_50} 张")
    
    # 7. 查询OKX实际的可开仓数量
    print("\n【7. OKX实际可开仓】")
    try:
        # 查询最大可开仓数量
        max_size = trader.exchange.private_get_account_max_size({
            'instId': symbol,
            'tdMode': 'cross',  # 全仓模式
        })
        
        if max_size.get('code') == '0' and max_size.get('data'):
            max_data = max_size['data'][0]
            print(f"最大可开多单: {max_data.get('maxBuy')} 张")
            print(f"最大可开空单: {max_data.get('maxSell')} 张")
    except Exception as e:
        print(f"查询最大可开仓失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 8. 验证计算公式
    print("\n【8. 公式验证】")
    if balance and current_price:
        available = balance['free']
        print(f"\nOKX公式（推测）：")
        print(f"可开张数 = 可用余额 × 杠杆 ÷ 当前价格 ÷ 每张合约ETH数")
        print(f"         = {available:.2f} × 2 ÷ {current_price:.2f} ÷ {contract_size}")
        print(f"         = {(available * 2 / current_price / contract_size):.4f}")
        print(f"         = {int(available * 2 / current_price / contract_size)} 张（向下取整）")
    
    print("\n" + "="*80)
    print("验证完成")
    print("="*80)

if __name__ == '__main__':
    check_okx_calculation()

