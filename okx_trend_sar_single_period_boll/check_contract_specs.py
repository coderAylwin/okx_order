#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
查询OKX合约规格
包括最小下单量、合约面值等信息
"""

import ccxt
from okx_config import OKX_API_CONFIG, TRADING_CONFIG

def check_contract_specs():
    """查询合约规格"""
    
    try:
        # 初始化OKX交易所
        exchange = ccxt.okx(OKX_API_CONFIG)
        
        if TRADING_CONFIG['mode'] == 'paper':
            exchange.set_sandbox_mode(True)
            print("📍 模式: 模拟盘")
        else:
            print("📍 模式: 实盘")
        
        # 加载市场信息
        print("\n正在加载市场信息...")
        markets = exchange.load_markets()
        
        # 查询ETH永续合约 (CCXT格式)
        symbol = 'ETH/USDT:USDT'
        
        if symbol not in markets:
            print(f"❌ 未找到 {symbol}")
            print("\n可用的ETH相关合约:")
            for s in markets.keys():
                if 'ETH' in s and 'SWAP' in str(markets[s].get('type', '')):
                    print(f"  - {s}")
            return
        
        market = markets[symbol]
        
        print(f"\n{'='*80}")
        print(f"📊 {symbol} 合约规格")
        print(f"{'='*80}")
        
        # 基本信息
        print(f"\n【基本信息】")
        print(f"交易对ID: {market.get('id')}")
        print(f"交易对符号: {market.get('symbol')}")
        print(f"合约类型: {market.get('type')}")
        print(f"是否激活: {market.get('active')}")
        
        # 合约规格
        print(f"\n【合约规格】")
        print(f"合约面值: {market.get('contractSize')} ETH/张")
        print(f"  说明: 每1张合约代表 {market.get('contractSize')} ETH")
        
        # 下单限制
        limits = market.get('limits', {})
        amount_limits = limits.get('amount', {})
        
        print(f"\n【下单限制】")
        print(f"最小下单量: {amount_limits.get('min')} 张")
        print(f"最大下单量: {amount_limits.get('max')} 张")
        
        # 精度
        precision = market.get('precision', {})
        print(f"\n【精度要求】")
        print(f"数量精度: {precision.get('amount')} 位小数")
        print(f"价格精度: {precision.get('price')} 位小数")
        
        # 其他限制
        cost_limits = limits.get('cost', {})
        print(f"\n【金额限制】")
        print(f"最小金额: {cost_limits.get('min')} USDT")
        print(f"最大金额: {cost_limits.get('max')} USDT")
        
        # 实际示例
        print(f"\n{'='*80}")
        print(f"💡 实际示例（假设ETH价格4000 USDT）")
        print(f"{'='*80}")
        
        price = 4000
        min_size = amount_limits.get('min', 0.1)
        contract_size = market.get('contractSize', 0.01)
        
        min_value = min_size * contract_size * price
        
        print(f"\n最小下单:")
        print(f"  {min_size} 张 × {contract_size} ETH/张 = {min_size * contract_size} ETH")
        print(f"  {min_size * contract_size} ETH × {price} USDT = {min_value} USDT（名义价值）")
        
        # 不同杠杆下的保证金
        print(f"\n不同杠杆下的保证金需求:")
        for leverage in [1, 2, 5, 10]:
            margin = min_value / leverage
            print(f"  {leverage}x 杠杆: {margin:.2f} USDT")
        
        print(f"\n{'='*80}")
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    check_contract_specs()

