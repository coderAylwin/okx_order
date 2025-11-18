#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OKX订单状态同步器
定期从OKX获取订单状态并更新到数据库
"""

import ccxt
from datetime import datetime
from okx_config import OKX_API_CONFIG


class OKXOrderSync:
    """OKX订单状态同步器"""
    
    def __init__(self, exchange=None):
        """初始化
        
        Args:
            exchange: ccxt交易所实例（可选）
        """
        if exchange:
            self.exchange = exchange
        else:
            self.exchange = ccxt.okx(OKX_API_CONFIG)
            self.exchange.load_markets()
        
        print("✅ OKX订单状态同步器初始化成功")
    
    def get_order_status(self, order_id, symbol):
        """从OKX获取订单状态
        
        Args:
            order_id: OKX订单ID
            symbol: 交易对符号
        
        Returns:
            dict: {
                'status': 订单状态,
                'filled': 已成交数量,
                'average_price': 成交均价,
                'filled_time': 成交时间,
                'fee': 手续费
            }
        """
        try:
            print(f"📡 查询订单状态: {order_id}")
            
            # 方法1: 使用fetch_order
            try:
                order = self.exchange.fetch_order(order_id, symbol)
                
                if order:
                    status_map = {
                        'open': 'open',
                        'closed': 'filled',
                        'canceled': 'canceled',
                        'cancelled': 'canceled',
                        'expired': 'canceled',
                        'rejected': 'canceled'
                    }
                    
                    okx_status = order.get('status', 'open')
                    mapped_status = status_map.get(okx_status, okx_status)
                    
                    result = {
                        'status': mapped_status,
                        'filled': order.get('filled', 0),
                        'average_price': order.get('average', None),
                        'filled_time': datetime.fromtimestamp(order.get('timestamp', 0) / 1000) if order.get('timestamp') else None,
                        'fee': order.get('fee', {}).get('cost', 0) if order.get('fee') else 0
                    }
                    
                    print(f"✅ 订单状态: {mapped_status}")
                    return result
                    
            except Exception as e1:
                print(f"⚠️  方法1失败: {e1}")
            
            # 方法2: 使用private API查询订单历史
            try:
                params = {
                    'instId': symbol,
                    'ordId': order_id,
                }
                response = self.exchange.private_get_trade_orders_history(params)
                
                if response.get('code') == '0' and response.get('data'):
                    order_data = response['data'][0]
                    
                    # OKX订单状态映射
                    # canceled: 撤单成功
                    # live: 等待成交
                    # partially_filled: 部分成交
                    # filled: 完全成交
                    status_map = {
                        'canceled': 'canceled',
                        'live': 'open',
                        'partially_filled': 'open',
                        'filled': 'filled'
                    }
                    
                    okx_state = order_data.get('state', 'live')
                    mapped_status = status_map.get(okx_state, okx_state)
                    
                    result = {
                        'status': mapped_status,
                        'filled': float(order_data.get('accFillSz', 0)),
                        'average_price': float(order_data.get('avgPx', 0)) if order_data.get('avgPx') else None,
                        'filled_time': datetime.fromtimestamp(int(order_data.get('uTime', 0)) / 1000) if order_data.get('uTime') else None,
                        'fee': abs(float(order_data.get('fee', 0)))
                    }
                    
                    print(f"✅ 订单状态（API）: {mapped_status}")
                    return result
                    
            except Exception as e2:
                print(f"⚠️  方法2失败: {e2}")
            
            # 如果都失败，返回None
            print(f"❌ 无法获取订单状态")
            return None
            
        except Exception as e:
            print(f"❌ 获取订单状态失败: {e}")
            return None
    
    def get_algo_order_status(self, algo_order_id, symbol):
        """获取条件单（止损止盈单）状态
        
        Args:
            algo_order_id: 条件单ID
            symbol: 交易对符号
        
        Returns:
            dict: {
                'status': 订单状态,
                'trigger_price': 触发价格,
                'triggered_at': 触发时间,
                'canceled_at': 取消时间
            }
        """
        try:
            print(f"📡 查询条件单状态: {algo_order_id}")
            
            # 方法1: 查询活跃的条件单
            try:
                params = {
                    'instId': symbol,
                    'algoId': algo_order_id,
                }
                response = self.exchange.private_get_trade_orders_algo_pending(params)
                
                if response.get('code') == '0' and response.get('data'):
                    algo_data = response['data'][0]
                    
                    # 条件单状态: live, effective, canceled, order_failed
                    state = algo_data.get('state', 'live')
                    
                    status_map = {
                        'live': 'active',
                        'effective': 'active',
                        'canceled': 'canceled',
                        'order_failed': 'canceled'
                    }
                    
                    result = {
                        'status': status_map.get(state, state),
                        'trigger_price': float(algo_data.get('slTriggerPx', 0)) or float(algo_data.get('tpTriggerPx', 0)),
                        'triggered_at': None,
                        'canceled_at': None
                    }
                    
                    print(f"✅ 条件单状态: {result['status']}")
                    return result
                    
            except Exception as e1:
                print(f"⚠️  查询活跃条件单失败: {e1}")
            
            # 方法2: 查询历史条件单（已触发或已取消）
            try:
                params = {
                    'instId': symbol,
                    'algoId': algo_order_id,
                }
                response = self.exchange.private_get_trade_orders_algo_history(params)
                
                if response.get('code') == '0' and response.get('data'):
                    algo_data = response['data'][0]
                    
                    state = algo_data.get('state', '')
                    
                    # triggered: 已触发
                    # canceled: 已撤销
                    # effective: 已生效
                    status_map = {
                        'triggered': 'triggered',
                        'canceled': 'canceled',
                        'effective': 'triggered'
                    }
                    
                    result = {
                        'status': status_map.get(state, state),
                        'trigger_price': float(algo_data.get('slTriggerPx', 0)) or float(algo_data.get('tpTriggerPx', 0)),
                        'triggered_at': datetime.fromtimestamp(int(algo_data.get('triggerTime', 0)) / 1000) if algo_data.get('triggerTime') and algo_data.get('triggerTime') != '0' else None,
                        'canceled_at': datetime.fromtimestamp(int(algo_data.get('cTime', 0)) / 1000) if state == 'canceled' and algo_data.get('cTime') else None
                    }
                    
                    print(f"✅ 条件单状态（历史）: {result['status']}")
                    return result
                    
            except Exception as e2:
                print(f"⚠️  查询历史条件单失败: {e2}")
            
            print(f"❌ 无法获取条件单状态")
            return None
            
        except Exception as e:
            print(f"❌ 获取条件单状态失败: {e}")
            return None
    
    def sync_order_to_db(self, order_id, symbol, db_service):
        """同步普通订单状态到数据库
        
        Args:
            order_id: OKX订单ID
            symbol: 交易对符号
            db_service: 数据库服务实例
        
        Returns:
            bool: 是否成功
        """
        try:
            status_info = self.get_order_status(order_id, symbol)
            
            if status_info:
                success = db_service.update_okx_order_status(
                    order_id=order_id,
                    status=status_info['status'],
                    filled=status_info['filled'],
                    average_price=status_info['average_price'],
                    filled_time=status_info['filled_time']
                )
                
                if success:
                    print(f"✅ 订单状态已同步到数据库: {order_id} -> {status_info['status']}")
                    return True
                else:
                    print(f"❌ 订单状态同步失败: {order_id}")
                    return False
            else:
                print(f"⚠️  无法获取订单状态，跳过同步")
                return False
                
        except Exception as e:
            print(f"❌ 同步订单状态异常: {e}")
            return False
    
    def sync_stop_order_to_db(self, algo_order_id, symbol, db_service):
        """同步止损止盈单状态到数据库
        
        Args:
            algo_order_id: 条件单ID
            symbol: 交易对符号
            db_service: 数据库服务实例
        
        Returns:
            bool: 是否成功
        """
        try:
            status_info = self.get_algo_order_status(algo_order_id, symbol)
            
            if status_info:
                success = db_service.update_stop_order_status(
                    order_id=algo_order_id,
                    status=status_info['status'],
                    triggered_at=status_info.get('triggered_at'),
                    canceled_at=status_info.get('canceled_at')
                )
                
                if success:
                    print(f"✅ 条件单状态已同步到数据库: {algo_order_id} -> {status_info['status']}")
                    return True
                else:
                    print(f"❌ 条件单状态同步失败: {algo_order_id}")
                    return False
            else:
                print(f"⚠️  无法获取条件单状态，跳过同步")
                return False
                
        except Exception as e:
            print(f"❌ 同步条件单状态异常: {e}")
            return False
    
    def sync_open_trade_orders(self, symbol, db_service):
        """同步所有打开交易的订单状态
        
        Args:
            symbol: 交易对符号
            db_service: 数据库服务实例
        """
        try:
            print(f"\n🔄 开始同步打开交易的订单状态...")
            
            # 获取当前打开的交易
            open_trade = db_service.get_open_trade(symbol)
            
            if not open_trade:
                print("✅ 没有打开的交易，无需同步")
                return
            
            print(f"📊 找到打开的交易: ID={open_trade.id}, {open_trade.position_side}")
            
            # 同步开仓订单
            print(f"\n1️⃣ 同步开仓订单: {open_trade.entry_order_id}")
            self.sync_order_to_db(open_trade.entry_order_id, symbol, db_service)
            
            # 同步止损止盈单
            print(f"\n2️⃣ 同步止损止盈单...")
            session = db_service.get_session()
            try:
                from trading_database_models import OKXStopOrder
                stop_orders = session.query(OKXStopOrder).filter_by(
                    trade_id=open_trade.id,
                    status='active'
                ).all()
                
                for stop_order in stop_orders:
                    print(f"\n   同步 {stop_order.order_type}: {stop_order.order_id}")
                    self.sync_stop_order_to_db(stop_order.order_id, symbol, db_service)
                    
            finally:
                db_service.close_session(session)
            
            print(f"\n✅ 订单状态同步完成")
            
        except Exception as e:
            print(f"❌ 同步订单状态失败: {e}")


# 测试代码
if __name__ == '__main__':
    """测试订单状态同步功能"""
    
    print("🧪 测试OKX订单状态同步功能\n")
    
    sync = OKXOrderSync()
    
    print("=" * 60)
    print("提示: 需要实际的订单ID才能测试同步功能")
    print("=" * 60)
    print("\n在实盘交易中，系统会自动同步订单状态")
    print("同步时机:")
    print("  1. 下单后立即同步")
    print("  2. 每分钟定期同步活跃订单")
    print("  3. 平仓后同步所有相关订单")
    
    print("\n✅ 测试完成！")

