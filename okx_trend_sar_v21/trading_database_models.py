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
    okx_trade_orders_entry = relationship(
        'OKXTradeOrder',
        foreign_keys='OKXTradeOrder.entry_signal_id',
        back_populates='entry_signal'
    )
    okx_trade_orders_exit = relationship(
        'OKXTradeOrder',
        foreign_keys='OKXTradeOrder.exit_signal_id',
        back_populates='exit_signal'
    )

    @property
    def okx_orders(self):
        """兼容旧代码访问方式，返回开仓关联列表"""
        return self.okx_trade_orders_entry
    entry_trades = relationship('OKXTrade', foreign_keys='OKXTrade.entry_signal_id', back_populates='entry_signal')
    exit_trades = relationship('OKXTrade', foreign_keys='OKXTrade.exit_signal_id', back_populates='exit_signal')
    okx_stop_orders = relationship('OKXStopOrder', back_populates='signal')


class OKXTradeOrder(Base):
    """OKX交易记录表：记录完整的交易周期（开仓+平仓）"""
    __tablename__ = 'okx_trade_orders'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    strategy_name = Column(String(255), nullable=True, comment='策略名称')
    symbol = Column(String(50), nullable=False, index=True, comment='交易对符号')
    position_side = Column(String(10), nullable=False, comment='持仓方向：long/short')

    # 信号关联
    entry_signal_id = Column(Integer, ForeignKey('indicator_signals.id', ondelete='SET NULL'), nullable=True, index=True, comment='开仓信号ID')
    exit_signal_id = Column(Integer, ForeignKey('indicator_signals.id', ondelete='SET NULL'), nullable=True, index=True, comment='平仓信号ID')

    order_id = Column(String(100), nullable=False, unique=True, index=True, comment='OKX订单ID')

    entry_price = Column(Float, nullable=True, comment='开仓价格')
    entry_time = Column(DateTime, nullable=True, comment='开仓时间')
    exit_price = Column(Float, nullable=False, comment='平仓价格')
    exit_time = Column(DateTime, nullable=False, comment='平仓时间')
    exit_reason = Column(String(100), nullable=True, comment='平仓原因：STOP_LOSS/TAKE_PROFIT/SAR_STOP等')

    amount = Column(Float, nullable=False, comment='合约数量（张）')
    leverage = Column(Integer, nullable=True, default=1, comment='杠杆倍数')
    invested_amount = Column(Float, nullable=False, comment='保证金（USDT）')

    trade_fee = Column(Float, nullable=False, default=0, comment='平仓手续费（USDT）')
    funding_fee = Column(Float, nullable=False, default=0, comment='资金费用（USDT）')
    total_fee = Column(Float, nullable=False, default=0, comment='总费用=开仓费+平仓费+资金费')

    profit_loss = Column(Float, nullable=True, comment='盈亏金额（USDT），未扣除费用')
    net_profit_loss = Column(Float, nullable=True, comment='净盈亏（USDT），扣除费用后')
    profit_loss_pct = Column(Float, nullable=True, comment='盈亏百分比')
    return_rate = Column(Float, nullable=True, comment='收益率（净盈亏/投入金额）')
    holding_duration = Column(Integer, nullable=True, comment='持仓时长（秒）')

    status = Column(String(20), nullable=False, default='open', index=True,
                    comment='交易状态：live/canceled/open/closed')

    created_at = Column(DateTime, default=datetime.now, nullable=False, comment='记录创建时间（挂单时）')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='记录更新时间')

    max_price = Column(Float, nullable=True, comment='最高价格')
    max_rate = Column(Float, nullable=True, comment='最大收益率')
    max_price_time = Column(String(255), nullable=True, comment='最高价格时间')
    min_price = Column(Float, nullable=True, comment='最低价格')
    min_rate = Column(Float, nullable=True, comment='最小收益率')
    min_price_time = Column(String(255), nullable=True, comment='最低价格时间')

    stop_profit_order_id = Column(String(255), nullable=True, comment='止盈订单ID')
    stop_loss_order_id = Column(String(255), nullable=True, comment='止损订单ID')

    # 关联
    entry_signal = relationship('IndicatorSignal', foreign_keys=[entry_signal_id], back_populates='okx_trade_orders_entry')
    exit_signal = relationship('IndicatorSignal', foreign_keys=[exit_signal_id], back_populates='okx_trade_orders_exit')

# 兼容旧代码引用
OKXOrder = OKXTradeOrder


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

