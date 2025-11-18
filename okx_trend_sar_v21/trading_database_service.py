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
    Base, IndicatorSignal, OKXTradeOrder, OKXTrade, OKXStopOrder,
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
    
    # ==================== OKX交易订单表（okx_trade_orders）操作 ====================
    
    def save_okx_order(self, order_id, symbol, order_type=None, side=None, position_side=None,
                      amount=None, price=None, average_price=None, filled=0, status='open',
                      signal_id=None, trade_id=None, parent_order_id=None,
                      invested_amount=None, order_time=None, filled_time=None,
                      strategy_name=None, leverage=1,
                      stop_loss_order_id=None, stop_profit_order_id=None,
                      exit_reason=None, exit_signal_id=None,
                      trade_fee=0, funding_fee=0, total_fee=None):
        """创建或更新 okx_trade_orders 记录
        
        兼容旧的 save_okx_order 调用：
        - parent_order_id 为空视为开仓记录
        - parent_order_id 不为空视为更新对应开仓记录的平仓信息
        """
        session = self.get_session()
        try:
            entry_time = order_time or datetime.now()
            entry_price = round(price, 2) if price is not None else 0.0
            invested_amount = round(invested_amount, 2) if invested_amount is not None else 0.0
            leverage = leverage or 1
            total_fee = total_fee if total_fee is not None else 0
            total_fee = round(total_fee, 4)
            trade_fee = round(trade_fee or 0, 4)
            funding_fee = round(funding_fee or 0, 4)

            if parent_order_id:
                # 平仓/更新
                record = session.query(OKXTradeOrder).filter_by(order_id=parent_order_id).first()
                if not record:
                    print(f"⚠️  未找到对应的开仓记录(order_id={parent_order_id})，无法更新平仓信息")
                    session.rollback()
                    return None

                record.exit_price = round(price, 2) if price is not None else record.exit_price
                record.exit_time = filled_time or order_time or datetime.now()
                record.exit_reason = exit_reason or status or record.exit_reason
                if exit_signal_id:
                    record.exit_signal_id = exit_signal_id
                if stop_loss_order_id:
                    record.stop_loss_order_id = stop_loss_order_id
                if stop_profit_order_id:
                    record.stop_profit_order_id = stop_profit_order_id
                if status:
                    record.status = status
                record.trade_fee = trade_fee or record.trade_fee
                record.funding_fee = funding_fee or record.funding_fee
                record.total_fee = total_fee or record.total_fee
                session.commit()
                print(f"✅ 更新交易订单(平仓信息): 开仓ID={parent_order_id}, 平仓单={order_id}")
                return record.id

            # 开仓记录
            record = session.query(OKXTradeOrder).filter_by(order_id=order_id).first()
            if not record:
                record = OKXTradeOrder(
                    strategy_name=strategy_name,
                    symbol=symbol,
                    position_side=position_side,
                    entry_signal_id=signal_id,
                    order_id=order_id,
                    entry_price=entry_price,
                    entry_time=entry_time,
                    exit_price=entry_price,
                    exit_time=entry_time,
                    amount=amount,
                    leverage=leverage,
                    invested_amount=invested_amount,
                    trade_fee=0,
                    funding_fee=0,
                    total_fee=0,
                    status='open',
                    stop_loss_order_id=stop_loss_order_id,
                    stop_profit_order_id=stop_profit_order_id,
                    max_price=entry_price,
                    min_price=entry_price,
                    max_rate=0.0,  # 开仓时收益率为0
                    min_rate=0.0,  # 开仓时收益率为0
                )
                session.add(record)
                session.commit()
                print(f"✅ 记录开仓订单: OKX订单ID={order_id}, {position_side}, 价格={entry_price}")
                return record.id
            else:
                # 已存在则更新基础信息
                record.strategy_name = strategy_name or record.strategy_name
                record.symbol = symbol
                record.position_side = position_side
                record.entry_signal_id = signal_id or record.entry_signal_id
                record.entry_price = entry_price
                record.entry_time = entry_time
                record.amount = amount
                record.leverage = leverage
                record.invested_amount = invested_amount
                record.stop_loss_order_id = stop_loss_order_id or record.stop_loss_order_id
                record.stop_profit_order_id = stop_profit_order_id or record.stop_profit_order_id
                if record.max_price is None or entry_price > record.max_price:
                    record.max_price = entry_price
                    record.max_price_time = entry_time.strftime('%Y-%m-%d %H:%M:%S')
                    # 计算最高价对应的收益率
                    if position_side == 'long':
                        record.max_rate = round((entry_price - record.entry_price) / record.entry_price * 100, 4) if record.entry_price and record.entry_price > 0 else 0.0
                    else:  # short
                        record.max_rate = round((record.entry_price - entry_price) / record.entry_price * 100, 4) if record.entry_price and record.entry_price > 0 else 0.0
                if record.min_price is None or entry_price < record.min_price:
                    record.min_price = entry_price
                    record.min_price_time = entry_time.strftime('%Y-%m-%d %H:%M:%S')
                    # 计算最低价对应的收益率
                    if position_side == 'long':
                        record.min_rate = round((entry_price - record.entry_price) / record.entry_price * 100, 4) if record.entry_price and record.entry_price > 0 else 0.0
                    else:  # short
                        record.min_rate = round((record.entry_price - entry_price) / record.entry_price * 100, 4) if record.entry_price and record.entry_price > 0 else 0.0
                session.commit()
                print(f"✅ 更新开仓订单: OKX订单ID={order_id}, {position_side}, 价格={entry_price}")
                return record.id

        except Exception as e:
            session.rollback()
            print(f"❌ 保存交易订单失败: {e}")
            return None
        finally:
            self.close_session(session)

    def update_okx_order_status(self, order_id, status, filled=None, average_price=None, filled_time=None):
        """更新 okx_trade_orders 的状态字段"""
        session = self.get_session()
        try:
            record = session.query(OKXTradeOrder).filter_by(order_id=order_id).first()
            if not record:
                print(f"⚠️  未找到交易订单: {order_id}")
                return False

            record.status = status
            if filled_time:
                record.exit_time = filled_time
            session.commit()
            print(f"✅ 更新交易订单状态: {order_id} -> {status}")
            return True
        except Exception as e:
            session.rollback()
            print(f"❌ 更新交易订单状态失败: {e}")
            return False
        finally:
            self.close_session(session)
    
    def update_trade_order_price_range(self, order_id, high_price, low_price, kline_timestamp):
        """更新持仓订单的最高价和最低价（使用1分钟K线数据）
        
        Args:
            order_id: 开仓订单ID（okx_trade_orders.order_id）
            high_price: K线最高价
            low_price: K线最低价
            kline_timestamp: K线时间戳（datetime对象）
        
        Returns:
            bool: 是否成功更新
        """
        session = self.get_session()
        try:
            record = session.query(OKXTradeOrder).filter_by(order_id=order_id).first()
            if not record:
                # 不打印警告，因为可能订单还未创建或已平仓
                return False
            
            # 只更新状态为 'open' 的订单
            if record.status != 'open':
                return False
            
            updated = False
            kline_time_str = kline_timestamp.strftime('%Y-%m-%d %H:%M:%S') if kline_timestamp else None
            
            # 需要开仓价格和持仓方向来计算收益率
            if record.entry_price is None or record.entry_price <= 0:
                # 如果没有开仓价格，无法计算收益率
                return False
            
            # 更新最高价
            if record.max_price is None or high_price > record.max_price:
                record.max_price = round(high_price, 2)
                record.max_price_time = kline_time_str
                
                # 计算最高价对应的收益率
                if record.position_side == 'long':
                    # 多单：最高价对应最高收益率
                    record.max_rate = round((high_price - record.entry_price) / record.entry_price * 100, 4)
                else:  # short
                    # 空单：最高价对应最低收益率（可能是负数）
                    record.max_rate = round((record.entry_price - high_price) / record.entry_price * 100, 4)
                
                updated = True
            
            # 更新最低价
            if record.min_price is None or low_price < record.min_price:
                record.min_price = round(low_price, 2)
                record.min_price_time = kline_time_str
                
                # 计算最低价对应的收益率
                if record.position_side == 'long':
                    # 多单：最低价对应最低收益率（可能是负数）
                    record.min_rate = round((low_price - record.entry_price) / record.entry_price * 100, 4)
                else:  # short
                    # 空单：最低价对应最高收益率
                    record.min_rate = round((record.entry_price - low_price) / record.entry_price * 100, 4)
                
                updated = True
            
            if updated:
                session.commit()
                # 只在有更新时打印日志（避免日志过多）
                # print(f"✅ 更新持仓价格范围: order_id={order_id}, 最高={record.max_price}({record.max_rate:.2f}%), 最低={record.min_price}({record.min_rate:.2f}%)")
            
            return updated
            
        except Exception as e:
            session.rollback()
            print(f"❌ 更新持仓价格范围失败: {e}")
            return False
        finally:
            self.close_session(session)
    
    # ==================== OKX交易记录表操作 ====================
    
    def create_okx_trade(self, symbol, position_side, entry_order_id, entry_price,
                        entry_time, amount, invested_amount, entry_signal_id=None,
                        strategy_name=None, leverage=1,
                        stop_loss_order_id=None, stop_profit_order_id=None):
        """创建OKX交易记录（开仓时调用）
        
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
                status='open'
            )
            
            session.add(trade)
            session.commit()
            trade_id = trade.id

            # 同步写入 okx_trade_orders（以 entry_order_id 为唯一标识）
            self.save_okx_order(
                order_id=entry_order_id,
                symbol=symbol,
                order_type='ENTRY',
                side='buy' if position_side == 'long' else 'sell',
                position_side=position_side,
                amount=amount,
                price=entry_price,
                invested_amount=invested_amount,
                order_time=entry_time,
                strategy_name=strategy_name,
                leverage=leverage,
                signal_id=entry_signal_id,
                stop_loss_order_id=stop_loss_order_id,
                stop_profit_order_id=stop_profit_order_id
            )

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

            # 同步更新 okx_trade_orders
            trade_order = session.query(OKXTradeOrder).filter_by(order_id=trade.entry_order_id).first()
            if trade_order:
                trade_order.exit_price = exit_price
                trade_order.exit_time = exit_time
                trade_order.exit_reason = exit_reason
                trade_order.exit_signal_id = exit_signal_id
                trade_order.trade_fee = round(exit_fee or 0, 4)
                trade_order.funding_fee = round(funding_fee or 0, 4)
                trade_order.total_fee = round(entry_fee + exit_fee + funding_fee, 4)
                trade_order.profit_loss = trade.profit_loss
                trade_order.net_profit_loss = trade.net_profit_loss
                trade_order.profit_loss_pct = trade.profit_loss_pct
                trade_order.return_rate = trade.return_rate
                trade_order.holding_duration = trade.holding_duration
                trade_order.status = 'closed'
            
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
        """保存交易订单（兼容旧接口）"""
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

