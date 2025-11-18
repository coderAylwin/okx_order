#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
交易数据库服务类
提供数据的增删改查操作
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime
import json
from trading_database_models import (
    Base, IndicatorSignal, OKXOrder, OKXTrade, OKXStopOrder,
    create_all_tables
)


class TradingDatabaseService:
    """交易数据库服务"""
    
    def __init__(self, db_config=None):
        """初始化数据库连接
        
        Args:
            db_config: 数据库配置字典，如果为None则使用默认的本地MySQL配置
                {
                    'host': 'localhost',
                    'port': 3306,
                    'user': 'root',
                    'password': 'your_password',
                    'database': 'trading_db',
                    'charset': 'utf8mb4'
                }
        """
        # 使用默认配置或自定义配置
        if db_config is None:
            # 尝试从database_config导入配置
            try:
                from database_config import LOCAL_DATABASE_CONFIG
                db_config = LOCAL_DATABASE_CONFIG
            except:
                # 使用默认配置
                db_config = {
                    'host': 'localhost',
                    'port': 3306,
                    'user': 'root',
                    'password': '',
                    'database': 'trading_db',
                    'charset': 'utf8mb4'
                }
        
        # 构建MySQL连接字符串
        connection_string = (
            f"mysql+pymysql://{db_config['user']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
            f"?charset={db_config.get('charset', 'utf8mb4')}"
        )
        
        self.engine = create_engine(connection_string, echo=False, pool_pre_ping=True)
        self.SessionLocal = scoped_session(sessionmaker(bind=self.engine))
        
        # 不自动创建表（表已经通过SQL创建）
        # create_all_tables(self.engine)
        print(f"✅ 交易数据库服务初始化成功: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    
    def get_session(self):
        """获取数据库会话"""
        return self.SessionLocal()
    
    def close_session(self, session):
        """关闭会话"""
        session.close()
    
    # ==================== 指标信号表操作 ====================
    
    def save_indicator_signal(self, timestamp, symbol, timeframe, 
                             open_price, high_price, low_price, close_price, volume,
                             indicators_dict, signal_type=None, signal_reason=None,
                             position=None, entry_price=None, stop_loss_level=None, 
                             take_profit_level=None):
        """保存指标信号数据
        
        Args:
            timestamp: 时间戳
            symbol: 交易对
            timeframe: 周期
            open_price, high_price, low_price, close_price: 价格数据
            volume: 成交量
            indicators_dict: 指标字典（将被转为JSON）
            signal_type: 信号类型
            signal_reason: 信号原因
            position: 持仓方向
            entry_price: 开仓价格
            stop_loss_level: 止损位
            take_profit_level: 止盈位
        
        Returns:
            signal_id: 保存的信号ID
        """
        session = self.get_session()
        try:
            # 🔴 价格保留两位小数
            open_price = round(open_price, 2) if open_price is not None else None
            high_price = round(high_price, 2) if high_price is not None else None
            low_price = round(low_price, 2) if low_price is not None else None
            close_price = round(close_price, 2) if close_price is not None else None
            entry_price = round(entry_price, 2) if entry_price is not None else None
            stop_loss_level = round(stop_loss_level, 2) if stop_loss_level is not None else None
            take_profit_level = round(take_profit_level, 2) if take_profit_level is not None else None
            
            signal = IndicatorSignal(
                timestamp=timestamp,
                symbol=symbol,
                timeframe=timeframe,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                indicators=indicators_dict,  # SQLAlchemy会自动转为JSON
                signal_type=signal_type,
                signal_reason=signal_reason,
                position=position,
                entry_price=entry_price,
                stop_loss_level=stop_loss_level,
                take_profit_level=take_profit_level
            )
            
            session.add(signal)
            session.commit()
            signal_id = signal.id
            
            print(f"✅ 保存指标信号: ID={signal_id}, 时间={timestamp}, 信号={signal_type}")
            return signal_id
            
        except Exception as e:
            session.rollback()
            print(f"❌ 保存指标信号失败: {e}")
            return None
        finally:
            self.close_session(session)
    
    # ==================== OKX订单表操作 ====================
    
    def save_okx_order(self, order_id, symbol, order_type, side, position_side,
                      amount, price=None, average_price=None, filled=0, status='open',
                      signal_id=None, trade_id=None, parent_order_id=None,
                      invested_amount=None, order_time=None, filled_time=None):
        """保存OKX订单
        
        Returns:
            order_db_id: 数据库中的订单ID
        """
        session = self.get_session()
        try:
            # 🔴 价格保留两位小数
            price = round(price, 2) if price is not None else None
            average_price = round(average_price, 2) if average_price is not None else None
            invested_amount = round(invested_amount, 2) if invested_amount is not None else None
            
            order = OKXOrder(
                order_id=order_id,
                symbol=symbol,
                order_type=order_type,
                side=side,
                position_side=position_side,
                amount=amount,
                price=price,
                average_price=average_price,
                filled=filled,
                status=status,
                signal_id=signal_id,
                trade_id=trade_id,
                parent_order_id=parent_order_id,
                invested_amount=invested_amount,
                order_time=order_time,
                filled_time=filled_time
            )
            
            session.add(order)
            session.commit()
            order_db_id = order.id
            
            print(f"✅ 保存OKX订单: ID={order_db_id}, OKX订单ID={order_id}, 类型={order_type}")
            return order_db_id
            
        except Exception as e:
            session.rollback()
            print(f"❌ 保存OKX订单失败: {e}")
            return None
        finally:
            self.close_session(session)
    
    def update_okx_order_status(self, order_id, status, filled=None, average_price=None, filled_time=None):
        """更新OKX订单状态"""
        session = self.get_session()
        try:
            order = session.query(OKXOrder).filter_by(order_id=order_id).first()
            if order:
                order.status = status
                if filled is not None:
                    order.filled = filled
                if average_price is not None:
                    order.average_price = average_price
                if filled_time is not None:
                    order.filled_time = filled_time
                
                session.commit()
                print(f"✅ 更新订单状态: {order_id} -> {status}")
                return True
            else:
                print(f"⚠️  未找到订单: {order_id}")
                return False
        except Exception as e:
            session.rollback()
            print(f"❌ 更新订单状态失败: {e}")
            return False
        finally:
            self.close_session(session)
    
    # ==================== OKX交易记录表操作 ====================
    
    def create_okx_trade(self, symbol, position_side, entry_order_id, entry_price,
                        entry_time, amount, invested_amount, entry_signal_id=None, open_reason=None):
        """创建OKX交易记录（开仓时调用）
        
        Args:
            open_reason: 开仓原因，'标准VIDYA' 或 '布林带角度'
        
        Returns:
            trade_id: 交易记录ID
        """
        session = self.get_session()
        try:
            # 🔴 价格保留两位小数
            entry_price = round(entry_price, 2) if entry_price is not None else None
            invested_amount = round(invested_amount, 2) if invested_amount is not None else None
            
            trade = OKXTrade(
                symbol=symbol,
                position_side=position_side,
                entry_signal_id=entry_signal_id,
                entry_order_id=entry_order_id,
                entry_price=entry_price,
                entry_time=entry_time,
                amount=amount,
                invested_amount=invested_amount,
                status='open',
                open_reason=open_reason  # 🔴 保存开仓原因
            )
            
            session.add(trade)
            session.commit()
            trade_id = trade.id
            
            print(f"✅ 创建交易记录: ID={trade_id}, {position_side}, 价格={entry_price}")
            return trade_id
            
        except Exception as e:
            session.rollback()
            print(f"❌ 创建交易记录失败: {e}")
            return None
        finally:
            self.close_session(session)
    
    def close_okx_trade(self, trade_id, exit_order_id, exit_price, exit_time,
                       exit_reason, exit_signal_id=None,
                       entry_fee=0, exit_fee=0, funding_fee=0):
        """关闭OKX交易记录（平仓时调用，从OKX获取费用数据）
        
        Args:
            trade_id: 交易ID
            exit_order_id: 平仓订单ID
            exit_price: 平仓价格
            exit_time: 平仓时间
            exit_reason: 平仓原因
            exit_signal_id: 平仓信号ID
            entry_fee: 开仓手续费（从OKX获取）
            exit_fee: 平仓手续费（从OKX获取）
            funding_fee: 资金费用（从OKX获取）
        
        Returns:
            bool: 是否成功
        """
        session = self.get_session()
        try:
            trade = session.query(OKXTrade).filter_by(id=trade_id).first()
            if not trade:
                print(f"⚠️  未找到交易记录: {trade_id}")
                return False
            
            # 🔴 价格保留两位小数
            exit_price = round(exit_price, 2) if exit_price is not None else None
            entry_fee = round(entry_fee, 2) if entry_fee is not None else 0
            exit_fee = round(exit_fee, 2) if exit_fee is not None else 0
            funding_fee = round(funding_fee, 2) if funding_fee is not None else 0
            
            # 更新平仓信息
            trade.exit_order_id = exit_order_id
            trade.exit_price = exit_price
            trade.exit_time = exit_time
            trade.exit_reason = exit_reason
            trade.exit_signal_id = exit_signal_id
            
            # 更新费用
            trade.entry_fee = entry_fee
            trade.exit_fee = exit_fee
            trade.funding_fee = funding_fee
            trade.total_fee = round(entry_fee + exit_fee + funding_fee, 2)
            
            # 计算盈亏（保留两位小数）
            if trade.position_side == 'long':
                trade.profit_loss = round((exit_price - trade.entry_price) * trade.amount * 0.01, 2)  # 0.01 ETH/张
            else:  # short
                trade.profit_loss = round((trade.entry_price - exit_price) * trade.amount * 0.01, 2)
            
            trade.net_profit_loss = round(trade.profit_loss - trade.total_fee, 2)
            trade.profit_loss_pct = round((trade.profit_loss / trade.invested_amount) * 100, 2)
            trade.return_rate = round((trade.net_profit_loss / trade.invested_amount) * 100, 2)
            
            # 计算持仓时长
            holding_duration = (exit_time - trade.entry_time).total_seconds()
            trade.holding_duration = int(holding_duration)
            
            # 更新状态
            trade.status = 'closed'
            
            session.commit()
            
            print(f"✅ 关闭交易记录: ID={trade_id}, 盈亏={trade.net_profit_loss:.2f} USDT, 收益率={trade.return_rate:.2f}%")
            return True
            
        except Exception as e:
            session.rollback()
            print(f"❌ 关闭交易记录失败: {e}")
            return False
        finally:
            self.close_session(session)
    
    def get_open_trade(self, symbol=None):
        """获取当前打开的交易记录"""
        session = self.get_session()
        try:
            query = session.query(OKXTrade).filter_by(status='open')
            if symbol:
                query = query.filter_by(symbol=symbol)
            trade = query.first()
            return trade
        finally:
            self.close_session(session)
    
    # ==================== OKX止损止盈记录表操作 ====================
    
    def save_okx_stop_order(self, order_id, symbol, trade_id, entry_order_id,
                           order_type, position_side, trigger_price, amount,
                           signal_id=None, order_price=None, status='active',
                           old_trigger_price=None, update_reason=None):
        """保存OKX止损止盈记录
        
        Args:
            old_trigger_price: 旧触发价（用于动态更新）
            update_reason: 更新原因（用于动态更新）
        
        Returns:
            stop_order_id: 止损止盈记录ID
        """
        session = self.get_session()
        try:
            # 🔴 价格保留两位小数
            trigger_price = round(trigger_price, 2) if trigger_price is not None else None
            order_price = round(order_price, 2) if order_price is not None else None
            old_trigger_price = round(old_trigger_price, 2) if old_trigger_price is not None else None
            
            stop_order = OKXStopOrder(
                order_id=order_id,
                symbol=symbol,
                trade_id=trade_id,
                signal_id=signal_id,
                entry_order_id=entry_order_id,
                order_type=order_type,
                position_side=position_side,
                trigger_price=trigger_price,
                order_price=order_price,
                status=status,
                amount=amount,
                old_trigger_price=old_trigger_price,
                update_reason=update_reason
            )
            
            session.add(stop_order)
            session.commit()
            stop_order_id = stop_order.id
            
            if old_trigger_price:
                print(f"✅ 保存止损止盈记录（更新）: ID={stop_order_id}, 类型={order_type}, {old_trigger_price:.2f}->{trigger_price:.2f}")
            else:
                print(f"✅ 保存止损止盈记录: ID={stop_order_id}, 类型={order_type}, 触发价={trigger_price}")
            return stop_order_id
            
        except Exception as e:
            session.rollback()
            print(f"❌ 保存止损止盈记录失败: {e}")
            return None
        finally:
            self.close_session(session)
    
    def update_stop_order(self, order_id, new_trigger_price, update_reason, signal_id=None):
        """更新止损止盈单（动态更新时调用）"""
        session = self.get_session()
        try:
            stop_order = session.query(OKXStopOrder).filter_by(order_id=order_id).first()
            if stop_order:
                stop_order.old_trigger_price = stop_order.trigger_price
                stop_order.trigger_price = new_trigger_price
                stop_order.update_reason = update_reason
                stop_order.update_count += 1
                if signal_id:
                    stop_order.signal_id = signal_id
                
                session.commit()
                print(f"✅ 更新止损止盈单: {order_id}, {stop_order.old_trigger_price:.2f} -> {new_trigger_price:.2f}")
                return True
            else:
                print(f"⚠️  未找到止损止盈单: {order_id}")
                return False
        except Exception as e:
            session.rollback()
            print(f"❌ 更新止损止盈单失败: {e}")
            return False
        finally:
            self.close_session(session)
    
    def update_stop_order_status(self, order_id, status, triggered_at=None, canceled_at=None):
        """更新止损止盈单状态"""
        session = self.get_session()
        try:
            stop_order = session.query(OKXStopOrder).filter_by(order_id=order_id).first()
            if stop_order:
                stop_order.status = status
                if triggered_at:
                    stop_order.triggered_at = triggered_at
                if canceled_at:
                    stop_order.canceled_at = canceled_at
                
                session.commit()
                print(f"✅ 更新止损止盈单状态: {order_id} -> {status}")
                return True
            else:
                print(f"⚠️  未找到止损止盈单: {order_id}")
                return False
        except Exception as e:
            session.rollback()
            print(f"❌ 更新止损止盈单状态失败: {e}")
            return False
        finally:
            self.close_session(session)
    
    # ==================== 简化方法名（别名） ====================
    
    def save_order(self, **kwargs):
        """保存订单（save_okx_order的别名）"""
        return self.save_okx_order(**kwargs)
    
    def save_trade(self, **kwargs):
        """保存交易记录（create_okx_trade的别名）
        注意：忽略status参数，因为create_okx_trade会自动设置为'open'
        """
        # 移除status参数（如果存在），因为create_okx_trade会自动设置
        kwargs.pop('status', None)
        return self.create_okx_trade(**kwargs)
    
    def save_stop_order(self, **kwargs):
        """保存止损止盈记录（save_okx_stop_order的别名）"""
        return self.save_okx_stop_order(**kwargs)

