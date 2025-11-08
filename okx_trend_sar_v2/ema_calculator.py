#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
from datetime import datetime, timedelta

class EMACalculator:
    """独立的EMA计算器 - 计算24、50、100周期EMA"""
    
    def __init__(self, ema_timeframe='1h', ema_periods=[24, 50, 100]):
        """
        初始化EMA计算器
        
        Args:
            ema_timeframe: EMA计算周期 (如 '1h', '2h', '4h')
            ema_periods: EMA周期列表 [24, 50, 100]
        """
        self.ema_timeframe = ema_timeframe
        self.ema_periods = ema_periods  # [24, 50, 100]
        
        # 数据存储
        self.ema_kline_data = []  # 存储EMA计算的K线数据
        
        # EMA 相关数据
        self.ema_values = {}  # 存储各周期EMA值 {24: [values], 50: [values], 100: [values]}
        self.current_ema = {}  # 当前EMA值 {24: value, 50: value, 100: value}
        self.previous_ema = {}  # 前一个EMA值 {24: value, 50: value, 100: value}
        
        # 预热状态
        self.is_warmed_up = False
        self.required_warmup = max(200, max(ema_periods) * 2)
        self.warmup_data_count = 0
    
    def timeframe_to_minutes(self, timeframe):
        """将时间周期字符串转换为分钟数"""
        timeframe_map = {
            '5m': 5, '15m': 15, '30m': 30, '1h': 60,
            '2h': 120, '4h': 240, '8h': 480, '1d': 1440
        }
        return timeframe_map.get(timeframe, 60)
    
    def _calculate_period_start(self, timestamp, minutes):
        """计算时间周期的开始时间"""
        if minutes == 5:
            minute = timestamp.minute
            period_minute = (minute // 5) * 5
            return timestamp.replace(minute=period_minute, second=0, microsecond=0)
        elif minutes == 15:
            minute = timestamp.minute
            if minute < 15:
                return timestamp.replace(minute=0, second=0, microsecond=0)
            elif minute < 30:
                return timestamp.replace(minute=15, second=0, microsecond=0)
            elif minute < 45:
                return timestamp.replace(minute=30, second=0, microsecond=0)
            else:
                return timestamp.replace(minute=45, second=0, microsecond=0)
        elif minutes == 30:
            minute = timestamp.minute
            if minute < 30:
                return timestamp.replace(minute=0, second=0, microsecond=0)
            else:
                return timestamp.replace(minute=30, second=0, microsecond=0)
        elif minutes == 60:
            return timestamp.replace(minute=0, second=0, microsecond=0)
        elif minutes == 120:
            hour = timestamp.hour
            period_hour = (hour // 2) * 2
            return timestamp.replace(hour=period_hour, minute=0, second=0, microsecond=0)
        elif minutes == 240:
            hour = timestamp.hour
            period_hour = (hour // 4) * 4
            return timestamp.replace(hour=period_hour, minute=0, second=0, microsecond=0)
        elif minutes == 480:
            hour = timestamp.hour
            period_hour = (hour // 8) * 8
            return timestamp.replace(hour=period_hour, minute=0, second=0, microsecond=0)
        elif minutes == 1440:
            return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            return timestamp
    
    def _calculate_ema(self, values, period):
        """计算EMA"""
        if not values:
            return 0
        if len(values) < period:
            return sum(values) / len(values)
        
        sma_seed = sum(values[:period]) / period
        k = 2.0 / (period + 1)
        ema = sma_seed
        
        for i in range(period, len(values)):
            ema = k * values[i] + (1 - k) * ema
        
        return ema
    
    def _calculate_ema_for_period(self, period):
        """计算指定周期的EMA"""
        if period not in self.ema_values or len(self.ema_values[period]) < period:
            return 0
        
        values = self.ema_values[period]
        return self._calculate_ema(values, period)
    
    def _update_ema_values(self, close_price):
        """更新EMA值"""
        # 为每个EMA周期添加新的收盘价
        for period in self.ema_periods:
            if period not in self.ema_values:
                self.ema_values[period] = []
            
            self.ema_values[period].append(close_price)
            
            # 保持历史数据长度
            if len(self.ema_values[period]) > period * 2:
                self.ema_values[period] = self.ema_values[period][-period * 2:]
            
            # 计算当前EMA值
            if len(self.ema_values[period]) >= period:
                # 保存前一个值
                if period in self.current_ema:
                    self.previous_ema[period] = self.current_ema[period]
                
                # 计算新的EMA值
                self.current_ema[period] = self._calculate_ema_for_period(period)
    
    def update(self, timestamp, close_price):
        """更新EMA计算器"""
        self.warmup_data_count += 1
        
        # 检查预热状态
        if not self.is_warmed_up and self.warmup_data_count >= self.required_warmup:
            self.is_warmed_up = True
            print(f"    ✅ EMA计算器预热完成！({self.ema_timeframe}周期)")
        
        # 更新EMA值（使用配置的周期）
        ema_minutes = self.timeframe_to_minutes(self.ema_timeframe)
        ema_period_start = self._calculate_period_start(timestamp, ema_minutes)
        
        # 检查是否是EMA计算周期
        if not self.ema_kline_data or self.ema_kline_data[-1]['timestamp'] != ema_period_start:
            # 新EMA周期开始
            if self.ema_kline_data:
                # 更新EMA值
                self._update_ema_values(self.ema_kline_data[-1]['close'])
            
            # 开始新EMA周期
            self.ema_kline_data.append({
                'timestamp': ema_period_start,
                'close': close_price
            })
            
            # 保持EMA K线数据量合理
            if len(self.ema_kline_data) > 200:
                self.ema_kline_data = self.ema_kline_data[-100:]
        else:
            # 更新当前EMA周期的收盘价
            self.ema_kline_data[-1]['close'] = close_price
        
        return self.get_ema_info()
    
    def is_ema_long_signal(self):
        """检查是否满足EMA多单开仓条件"""
        if not self.is_warmed_up:
            return False
        
        # 检查是否有足够的EMA数据
        for period in self.ema_periods:
            if period not in self.current_ema or self.current_ema[period] == 0:
                return False
        
        # 检查EMA排列：24EMA > 50EMA > 100EMA
        ema24 = self.current_ema[24]
        ema50 = self.current_ema[50]
        ema100 = self.current_ema[100]
        
        if not (ema24 > ema50 > ema100):
            return False
        
        # 检查24EMA上升：当前值 > 前一个值
        if 24 not in self.previous_ema or self.previous_ema[24] == 0:
            return False
        
        return ema24 > self.previous_ema[24]
    
    def is_ema_short_signal(self):
        """检查是否满足EMA空单开仓条件"""
        if not self.is_warmed_up:
            return False
        
        # 检查是否有足够的EMA数据
        for period in self.ema_periods:
            if period not in self.current_ema or self.current_ema[period] == 0:
                return False
        
        # 检查EMA排列：24EMA < 50EMA < 100EMA
        ema24 = self.current_ema[24]
        ema50 = self.current_ema[50]
        ema100 = self.current_ema[100]
        
        if not (ema24 < ema50 < ema100):
            return False
        
        # 检查24EMA下降：当前值 < 前一个值
        if 24 not in self.previous_ema or self.previous_ema[24] == 0:
            return False
        
        return ema24 < self.previous_ema[24]
    
    def get_ema_info(self):
        """获取EMA信息"""
        return {
            'ema24': self.current_ema.get(24, 0),
            'ema50': self.current_ema.get(50, 0),
            'ema100': self.current_ema.get(100, 0),
            'previous_ema24': self.previous_ema.get(24, 0),
            'is_long_signal': self.is_ema_long_signal(),
            'is_short_signal': self.is_ema_short_signal(),
            'is_warmed_up': self.is_warmed_up
        }
    
    def get_current_status(self):
        """获取当前状态"""
        return {
            'is_warmed_up': self.is_warmed_up,
            'warmup_data_count': self.warmup_data_count,
            'required_warmup': self.required_warmup,
            'ema_timeframe': self.ema_timeframe,
            'ema_periods': self.ema_periods
        }
