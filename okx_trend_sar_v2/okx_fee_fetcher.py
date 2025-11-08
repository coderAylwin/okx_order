#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OKX费用获取器
从OKX API获取交易手续费和资金费用
"""

import ccxt
from datetime import datetime
from okx_config import OKX_API_CONFIG


class OKXFeeFetcher:
    """OKX费用获取器"""
    
    def __init__(self, exchange=None):
        """初始化
        
        Args:
            exchange: ccxt交易所实例（可选，如果不提供则创建新实例）
        """
        if exchange:
            self.exchange = exchange
        else:
            self.exchange = ccxt.okx(OKX_API_CONFIG)
            self.exchange.load_markets()
        
        print("✅ OKX费用获取器初始化成功")
    
    def get_order_fee(self, order_id, symbol):
        """获取订单手续费
        
        Args:
            order_id: OKX订单ID
            symbol: 交易对符号
        
        Returns:
            float: 手续费（USDT）
        """
        try:
            # 🔴 测试OKX API获取订单详情
            print(f"📡 获取订单手续费: {order_id}")
            
            # 方法1：通过fetch_order获取
            try:
                order = self.exchange.fetch_order(order_id, symbol)
                
                if order and 'fee' in order:
                    fee = order['fee']
                    if fee and 'cost' in fee:
                        fee_amount = float(fee['cost'])
                        fee_currency = fee.get('currency', 'USDT')
                        
                        print(f"✅ 订单手续费: {fee_amount} {fee_currency}")
                        return fee_amount
                    
            except Exception as e1:
                print(f"⚠️  方法1失败: {e1}")
            
            # 方法2：通过private API获取订单历史
            try:
                params = {
                    'instId': symbol,
                    'ordId': order_id,
                }
                response = self.exchange.private_get_trade_orders_history(params)
                
                if response.get('code') == '0' and response.get('data'):
                    order_data = response['data'][0]
                    fee = float(order_data.get('fee', 0))
                    fee_currency = order_data.get('feeCcy', 'USDT')
                    
                    print(f"✅ 订单手续费（API): {abs(fee)} {fee_currency}")
                    return abs(fee)
                    
            except Exception as e2:
                print(f"⚠️  方法2失败: {e2}")
            
            # 如果都失败，返回0
            print(f"⚠️  无法获取订单手续费，返回0")
            return 0.0
            
        except Exception as e:
            print(f"❌ 获取订单手续费失败: {e}")
            return 0.0
    
    def get_funding_fee(self, symbol, start_time, end_time):
        """获取资金费用
        
        Args:
            symbol: 交易对符号
            start_time: 开始时间（datetime对象）
            end_time: 结束时间（datetime对象）
        
        Returns:
            float: 资金费用总额（USDT，可正可负）
        """
        try:
            # 🔴 测试OKX API获取资金费用
            print(f"📡 获取资金费用: {symbol}, {start_time} ~ {end_time}")
            
            # 转换时间戳为毫秒
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000)
            
            # 使用OKX API获取资金费用历史
            # https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-bills-details-last-3-months
            try:
                params = {
                    'instId': symbol,
                    'type': '8',  # 8 = funding fee
                    'begin': str(start_ts),
                    'end': str(end_ts),
                }
                
                response = self.exchange.private_get_account_bills(params)
                
                if response.get('code') == '0' and response.get('data'):
                    total_funding_fee = 0.0
                    funding_count = 0
                    
                    for bill in response['data']:
                        fee = float(bill.get('bal', 0))
                        total_funding_fee += fee
                        funding_count += 1
                    
                    print(f"✅ 资金费用: {total_funding_fee:.4f} USDT ({funding_count}次)")
                    return total_funding_fee
                else:
                    print(f"⚠️  未找到资金费用记录")
                    return 0.0
                    
            except Exception as api_e:
                print(f"⚠️  API调用失败: {api_e}")
                return 0.0
            
        except Exception as e:
            print(f"❌ 获取资金费用失败: {e}")
            return 0.0
    
    def get_trade_fees(self, entry_order_id, exit_order_id, symbol, 
                      entry_time, exit_time):
        """获取一笔交易的所有费用
        
        Args:
            entry_order_id: 开仓订单ID
            exit_order_id: 平仓订单ID
            symbol: 交易对
            entry_time: 开仓时间
            exit_time: 平仓时间
        
        Returns:
            dict: {
                'entry_fee': 开仓手续费,
                'exit_fee': 平仓手续费,
                'funding_fee': 资金费用,
                'total_fee': 总费用
            }
        """
        print(f"\n{'='*60}")
        print(f"🔍 获取交易费用详情")
        print(f"{'='*60}")
        
        # 获取开仓手续费
        entry_fee = self.get_order_fee(entry_order_id, symbol)
        
        # 获取平仓手续费
        exit_fee = self.get_order_fee(exit_order_id, symbol)
        
        # 获取资金费用
        funding_fee = self.get_funding_fee(symbol, entry_time, exit_time)
        
        # 计算总费用
        total_fee = entry_fee + exit_fee + funding_fee
        
        result = {
            'entry_fee': entry_fee,
            'exit_fee': exit_fee,
            'funding_fee': funding_fee,
            'total_fee': total_fee
        }
        
        print(f"\n📊 费用汇总:")
        print(f"   开仓手续费: {entry_fee:.4f} USDT")
        print(f"   平仓手续费: {exit_fee:.4f} USDT")
        print(f"   资金费用:   {funding_fee:.4f} USDT")
        print(f"   总费用:     {total_fee:.4f} USDT")
        print(f"{'='*60}\n")
        
        return result


# 测试代码
if __name__ == '__main__':
    """测试OKX费用获取功能"""
    
    print("🧪 测试OKX费用获取功能\n")
    
    fetcher = OKXFeeFetcher()
    
    # 测试获取订单手续费（需要替换为实际的订单ID）
    print("=" * 60)
    print("测试1: 获取订单手续费")
    print("=" * 60)
    # fee = fetcher.get_order_fee('订单ID', 'ETH-USDT-SWAP')
    print("提示: 需要实际的订单ID才能测试\n")
    
    # 测试获取资金费用
    print("=" * 60)
    print("测试2: 获取资金费用")
    print("=" * 60)
    from datetime import timedelta
    end_time = datetime.now()
    start_time = end_time - timedelta(days=1)
    # funding = fetcher.get_funding_fee('ETH-USDT-SWAP', start_time, end_time)
    print("提示: 需要实际的持仓才能测试\n")
    
    print("✅ 测试完成！")

