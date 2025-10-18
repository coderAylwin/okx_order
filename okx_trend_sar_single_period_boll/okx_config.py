#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OKX API 配置文件
请妥善保管API密钥，不要泄露！
"""

# OKX API 配置
OKX_API_CONFIG = {
    'api_key': 'a1ffa3fd-834c-4ed8-8f1a-aa83aceaa892',           # 替换为你的 API Key
    'secret': '3968DCAB3420DFEF2110FD451625E61F',          # 替换为你的 Secret Key
    'password': 'g:68YsKuPnn4zf)vuAm,CO5J',          # 替换为你的 API Password
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',            # 默认交易类型：swap（永续合约）
    }
}
# OKX_API_CONFIG = {
#     'api_key': '3afaa787-5b41-4662-8a19-d08f593b8cba',           # 替换为你的 API Key
#     'secret': 'D2E84F55B79E8786556A304EB778AC36',          # 替换为你的 Secret Key
#     'password': 'Ayw.72203991',          # 替换为你的 API Password
#     'enableRateLimit': True,
#     'options': {
#         'defaultType': 'swap',            # 默认交易类型：swap（永续合约）
#     }
# }

# 交易配置
TRADING_CONFIG = {
    'mode': 'live',  # 'paper'=模拟盘, 'live'=实盘
    'test_mode': False,  # True=测试模式（只打印不下单）, False=实际下单（⚠️ 谨慎！）
    
    # 交易对配置
    'symbols': {
        'BTC': 'BTC-USDT-SWAP',  # BTC永续合约
        'ETH': 'ETH-USDT-SWAP',  # ETH永续合约
        'SOL': 'SOL-USDT-SWAP',  # SOL永续合约
    },
    
    # 杠杆配置
    'leverage': 3,              # 杠杆倍数（1-125），建议1-5倍
    'margin_mode': 'cross',     # 保证金模式：'cross'=全仓, 'isolated'=逐仓
    
    # 风险控制
    'max_position_value': 10000,  # 最大持仓价值（USDT）
    'min_order_size': 0.001,      # 最小下单量
    'max_retry': 3,                # API调用最大重试次数
    
    # 数据更新间隔
    'update_interval': 60,  # 秒，建议60秒（1分钟更新一次）
}

# 通知配置（可选）
NOTIFICATION_CONFIG = {
    'enable_email': False,
    'enable_wechat': False,
    'enable_telegram': False,
}

