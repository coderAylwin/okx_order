#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K线数据缓存管理器
负责缓存1分钟K线数据，并在需要时聚合成指定周期
"""

from datetime import datetime, timedelta
from collections import deque


class KlineBuffer:
    """K线数据缓存管理器"""
    
    def __init__(self, buffer_size=50):
        """初始化
        
        Args:
            buffer_size: 缓存大小（建议设置为周期分钟数，如15分钟周期设置15）
        """
        self.buffer_size = buffer_size
        self.klines = deque(maxlen=buffer_size)  # 使用deque自动维护大小（超出自动删除最老的）
        
        print(f"📦 K线缓存管理器已初始化，缓存大小: {buffer_size}条（超出自动删除最老数据）")
    
    def add_kline(self, timestamp, open_price, high_price, low_price, close_price, volume=0):
        """添加一条1分钟K线到缓存
        
        Args:
            timestamp: 时间戳（datetime对象）
            open_price: 开盘价
            high_price: 最高价
            low_price: 最低价
            close_price: 收盘价
            volume: 成交量
            
        Returns:
            int: 当前缓存大小，如果重复返回 -1
        """
        # 🔴 检查是否已存在相同时间的K线
        if len(self.klines) > 0:
            last_kline = self.klines[-1]
            if last_kline['timestamp'] == timestamp:
                # 时间重复，不添加
                return -1
        
        kline = {
            'timestamp': timestamp,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        }
        
        self.klines.append(kline)
        
        return len(self.klines)
    
    def get_latest_n_klines(self, n):
        """获取最近N条K线
        
        Args:
            n: 需要的K线数量
        
        Returns:
            list: K线列表，如果数据不足返回None
        """
        if len(self.klines) < n:
            return None
        
        return list(self.klines)[-n:]
    
    def check_data_continuity(self, klines):
        """检查K线数据的连续性
        
        Args:
            klines: K线列表
        
        Returns:
            dict: {
                'is_continuous': bool,
                'missing_minutes': list,
                'reason': str
            }
        """
        if not klines or len(klines) < 2:
            return {
                'is_continuous': False,
                'missing_minutes': [],
                'reason': f'数据不足: {len(klines)}条'
            }
        
        missing_minutes = []
        
        for i in range(1, len(klines)):
            prev_time = klines[i-1]['timestamp']
            curr_time = klines[i]['timestamp']
            
            # 计算时间差（应该是1分钟）
            time_diff = (curr_time - prev_time).total_seconds() / 60
            
            if time_diff > 1.1:  # 允许0.1分钟误差
                # 找出缺失的分钟
                expected_time = prev_time + timedelta(minutes=1)
                while expected_time < curr_time:
                    missing_minutes.append(expected_time.strftime('%H:%M'))
                    expected_time += timedelta(minutes=1)
        
        is_continuous = len(missing_minutes) == 0
        reason = '数据连续' if is_continuous else f'缺失{len(missing_minutes)}条: {missing_minutes}'
        
        return {
            'is_continuous': is_continuous,
            'missing_minutes': missing_minutes,
            'reason': reason
        }
    
    def aggregate_to_period(self, period_minutes=15):
        """将缓存的1分钟K线聚合成指定周期
        
        Args:
            period_minutes: 周期分钟数（如15, 30, 60）
        
        Returns:
            dict: 聚合后的K线，如果数据不足或不连续返回None
        """
        # 检查是否有足够数据
        if len(self.klines) < period_minutes:
            print(f"⚠️  数据不足以聚合{period_minutes}分钟周期: 当前{len(self.klines)}条")
            return None
        
        # 获取最近N条
        recent_klines = self.get_latest_n_klines(period_minutes)
        
        if not recent_klines:
            return None
        
        # 检查数据连续性
        continuity = self.check_data_continuity(recent_klines)
        
        if not continuity['is_continuous']:
            print(f"⚠️  数据不连续: {continuity['reason']}")
            return None
        
        # 聚合K线数据
        first_kline = recent_klines[0]
        last_kline = recent_klines[-1]
        
        aggregated = {
            'timestamp': first_kline['timestamp'],
            'open': first_kline['open'],
            'high': max([k['high'] for k in recent_klines]),
            'low': min([k['low'] for k in recent_klines]),
            'close': last_kline['close'],
            'volume': sum([k['volume'] for k in recent_klines])
        }
        
        return aggregated
    
    def should_update_strategy(self, current_time, period_minutes=15):
        """判断是否应该更新策略（是否到达周期整点）
        
        Args:
            current_time: 当前时间（datetime对象）
            period_minutes: 周期分钟数
        
        Returns:
            bool: 是否应该更新
        """
        # 判断是否是周期整点（如15分钟周期：16:00, 16:15, 16:30, 16:45）
        minute = current_time.minute
        
        if period_minutes == 15:
            return minute % 15 == 0
        elif period_minutes == 30:
            return minute % 30 == 0
        elif period_minutes == 60:
            return minute == 0
        else:
            # 其他周期，每分钟都更新
            return True
    
    def get_buffer_status(self):
        """获取缓存状态
        
        Returns:
            dict: 缓存状态信息
        """
        if not self.klines:
            return {
                'size': 0,
                'first_time': None,
                'last_time': None,
                'is_full': False
            }
        
        return {
            'size': len(self.klines),
            'first_time': self.klines[0]['timestamp'].strftime('%Y-%m-%d %H:%M'),
            'last_time': self.klines[-1]['timestamp'].strftime('%Y-%m-%d %H:%M'),
            'is_full': len(self.klines) >= self.buffer_size
        }

