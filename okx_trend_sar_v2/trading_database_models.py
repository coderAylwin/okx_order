#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
交易数据库模型定义
包含：指标信号表、OKX订单表、OKX交易记录表、OKX止损止盈记录表
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class IndicatorSignal(Base):
    """指标信号表"""
    __tablename__ = 'indicator_signals'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 基础信息
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    
    # 价格数据
    open_price = Column(Float, nullable=False)
    high_price = Column(Float, nullable=False)
    low_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=False)
    volume = Column(Float, default=0)
    
    # 指标数据（JSON格式存储）
    indicators = Column(JSON, nullable=True)
    
    # 信号
    signal_type = Column(String(50), nullable=True, index=True)
    signal_reason = Column(Text, nullable=True)
    
    # 持仓状态快照
    position = Column(String(10), nullable=True)  # long/short/None
    entry_price = Column(Float, nullable=True)
    stop_loss_level = Column(Float, nullable=True)
    take_profit_level = Column(Float, nullable=True)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    
    # 关系
    okx_orders = relationship('OKXOrder', back_populates='signal')
    entry_trades = relationship('OKXTrade', foreign_keys='OKXTrade.entry_signal_id', back_populates='entry_signal')
    exit_trades = relationship('OKXTrade', foreign_keys='OKXTrade.exit_signal_id', back_populates='exit_signal')
    okx_stop_orders = relationship('OKXStopOrder', back_populates='signal')


class OKXOrder(Base):
    """OKX订单表"""
    __tablename__ = 'okx_orders'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # OKX订单信息
    order_id = Column(String(100), nullable=False, unique=True, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    order_type = Column(String(50), nullable=False)  # MARKET/LIMIT/STOP_LOSS/TAKE_PROFIT
    side = Column(String(10), nullable=False)  # buy/sell
    position_side = Column(String(10), nullable=False)  # long/short
    
    # 订单数量和价格
    amount = Column(Float, nullable=False)  # 合约数量（张）
    price = Column(Float, nullable=True)
    average_price = Column(Float, nullable=True)
    filled = Column(Float, default=0)
    
    # 订单状态
    status = Column(String(20), nullable=False, index=True)  # open/closed/canceled/filled
    
    # 关联ID
    signal_id = Column(Integer, ForeignKey('indicator_signals.id'), nullable=True, index=True)
    trade_id = Column(Integer, ForeignKey('okx_trades.id'), nullable=True, index=True)
    parent_order_id = Column(String(100), nullable=True)
    
    # 订单金额
    invested_amount = Column(Float, nullable=True)
    
    # 时间戳
    order_time = Column(DateTime, nullable=True)
    filled_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # 关系
    signal = relationship('IndicatorSignal', back_populates='okx_orders')
    trade = relationship('OKXTrade', back_populates='orders')


class OKXTrade(Base):
    """OKX交易记录表"""
    __tablename__ = 'okx_trades'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 基础信息
    symbol = Column(String(50), nullable=False, index=True)
    position_side = Column(String(10), nullable=False)  # long/short
    
    # 关联信号ID
    entry_signal_id = Column(Integer, ForeignKey('indicator_signals.id'), nullable=True, index=True)
    exit_signal_id = Column(Integer, ForeignKey('indicator_signals.id'), nullable=True, index=True)
    
    # 开仓信息
    entry_order_id = Column(String(100), nullable=False)
    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    
    # 平仓信息
    exit_order_id = Column(String(100), nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    exit_reason = Column(String(100), nullable=True)
    
    # 交易结果
    amount = Column(Float, nullable=False)  # 合约数量
    invested_amount = Column(Float, nullable=False)
    
    # 费用数据（从OKX获取）
    entry_fee = Column(Float, default=0)
    exit_fee = Column(Float, default=0)
    funding_fee = Column(Float, default=0)  # 可正可负
    total_fee = Column(Float, default=0)
    
    # 盈亏计算
    profit_loss = Column(Float, nullable=True)
    net_profit_loss = Column(Float, nullable=True)  # 净盈亏
    profit_loss_pct = Column(Float, nullable=True)
    return_rate = Column(Float, nullable=True)
    
    # 持仓时长
    holding_duration = Column(Integer, nullable=True)  # 秒
    
    # 状态
    status = Column(String(20), nullable=False, default='open', index=True)  # open/closed
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # 关系
    entry_signal = relationship('IndicatorSignal', foreign_keys=[entry_signal_id], back_populates='entry_trades')
    exit_signal = relationship('IndicatorSignal', foreign_keys=[exit_signal_id], back_populates='exit_trades')
    orders = relationship('OKXOrder', back_populates='trade')
    stop_orders = relationship('OKXStopOrder', back_populates='trade')


class OKXStopOrder(Base):
    """OKX止损止盈记录表"""
    __tablename__ = 'okx_stop_orders'
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # OKX订单信息
    order_id = Column(String(100), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    
    # 关联ID
    trade_id = Column(Integer, ForeignKey('okx_trades.id'), nullable=False, index=True)
    signal_id = Column(Integer, ForeignKey('indicator_signals.id'), nullable=True, index=True)
    entry_order_id = Column(String(100), nullable=False)
    
    # 止损止盈类型
    order_type = Column(String(20), nullable=False)  # STOP_LOSS/TAKE_PROFIT
    position_side = Column(String(10), nullable=False)  # long/short
    
    # 价格信息
    trigger_price = Column(Float, nullable=False)
    order_price = Column(Float, nullable=True)
    
    # 订单状态
    status = Column(String(20), nullable=False, index=True)  # active/triggered/canceled/updated
    
    # 数量
    amount = Column(Float, nullable=False)
    
    # 动态更新记录
    old_trigger_price = Column(Float, nullable=True)
    update_reason = Column(String(200), nullable=True)
    update_count = Column(Integer, default=0)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    triggered_at = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    
    # 关系
    trade = relationship('OKXTrade', back_populates='stop_orders')
    signal = relationship('IndicatorSignal', back_populates='okx_stop_orders')


def create_all_tables(engine):
    """创建所有表"""
    Base.metadata.create_all(engine)
    print("✅ 所有数据库表创建成功！")


def drop_all_tables(engine):
    """删除所有表（谨慎使用）"""
    Base.metadata.drop_all(engine)
    print("⚠️  所有数据库表已删除！")

