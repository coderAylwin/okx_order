#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
from datetime import datetime, timedelta

class VolatilityCalculator:
    """独立的波动率计算器 - 支持不同周期的波动率计算"""
    
    def __init__(self, volatility_timeframe='6h', length=14, mult=2.0, ema_period=90):
        """
        初始化波动率计算器
        
        Args:
            volatility_timeframe: 波动率计算周期 (如 '6h', '8h', '1d')
            length: 布林带EMA周期
            mult: 布林带标准差倍数
            ema_period: 波动率EMA平滑周期
        """
        self.volatility_timeframe = volatility_timeframe
        self.length = length
        self.mult = mult
        self.ema_period = ema_period
        
        # 数据存储
        self.minute_data = []  # 存储1分钟数据
        self.kline_data = []   # 存储聚合后的K线数据
        
        # 布林带相关历史数据
        self.close_history = []
        self.basis_history = []
        
        # 中轨变化率相关数据（只存储最近3个值）
        self.basis_change_history = []  # 存储最近3个中轨值
        self.basis_change_rate = 0  # 当前中轨变化率
        
        # 波动率相关数据
        self.volatility_ratio_history = []
        self.volatility_ema = None
        
        # 预热状态
        self.is_warmed_up = False
        self.required_warmup = max(200, length * 4 + ema_period * 2)
        
        # 初始化缓存值
        self._cached_ratio_vs_ema = 0
        self._cached_info = {
            'volatility_ratio': 0,
            'volatility_ema': None,
            'volatility_ratio_vs_ema': 0,
            'basis_change_rate': 0,
            'is_warmed_up': self.is_warmed_up,
            'timeframe': self.volatility_timeframe
        }
        
        print(f"📊 波动率计算器初始化: {volatility_timeframe}周期 | EMA:{length} | 倍数:{mult} | 平滑:{ema_period}")
    
    def timeframe_to_minutes(self, timeframe):
        """将时间周期字符串转换为分钟数"""
        timeframe_map = {
            '5m': 5, '15m': 15, '30m': 30, '1h': 60,
            '2h': 120, '4h': 240, '6h': 360, '8h': 480, '12h': 720, '1d': 1440
        }
        return timeframe_map.get(timeframe, 360)
    
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
        elif minutes == 360:  # 6小时
            hour = timestamp.hour
            period_hour = (hour // 6) * 6
            return timestamp.replace(hour=period_hour, minute=0, second=0, microsecond=0)
        elif minutes == 480:  # 8小时
            hour = timestamp.hour
            period_hour = (hour // 8) * 8
            return timestamp.replace(hour=period_hour, minute=0, second=0, microsecond=0)
        elif minutes == 720:  # 12小时
            hour = timestamp.hour
            period_hour = (hour // 12) * 12
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
    
    def _calculate_stdev(self, values, mean, period):
        """计算标准差"""
        if len(values) < period:
            n = len(values)
            recent_values = values
        else:
            n = period
            recent_values = values[-period:]
            
        if n <= 1:
            return 0
            
        variance = sum((x - mean) ** 2 for x in recent_values) / n
        return math.sqrt(variance)
    
    def update(self, timestamp, close_price):
        """
        更新1分钟数据并计算波动率
        
        Args:
            timestamp: 时间戳
            close_price: 收盘价
            
        Returns:
            dict: 包含波动率信息的字典
        """
        # 存储1分钟数据
        self.minute_data.append({
            'timestamp': timestamp,
            'close': close_price
        })
        
        # 保持数据量合理
        if len(self.minute_data) > 10000:
            self.minute_data = self.minute_data[-5000:]
        
        # 检查是否需要生成新的K线
        minutes = self.timeframe_to_minutes(self.volatility_timeframe)
        period_start = self._calculate_period_start(timestamp, minutes)
        
        # 检查是否是新周期
        if not self.kline_data or self.kline_data[-1]['timestamp'] != period_start:
            # 新周期开始，保存上一个周期的数据
            if self.kline_data:
                self._calculate_volatility_for_kline(self.kline_data[-1])
            
            # 开始新周期
            self.kline_data.append({
                'timestamp': period_start,
                'close': close_price
            })
            
            # 保持K线数据量合理
            if len(self.kline_data) > 1000:
                self.kline_data = self.kline_data[-500:]
        else:
            # 更新当前周期的收盘价
            self.kline_data[-1]['close'] = close_price
        
        # 返回当前波动率信息（使用缓存值，避免重复计算）
        return self._get_cached_volatility_info()
    
    def _calculate_volatility_for_kline(self, kline):
        """为单个K线计算波动率"""
        close_price = kline['close']
        
        # 存储历史数据
        self.close_history.append(close_price)
        if len(self.close_history) > self.length * 2:
            self.close_history = self.close_history[-self.length * 2:]
        
        # 计算布林带
        if len(self.close_history) >= self.length:
            # 1. 计算布林带中轨 (EMA)
            basis = self._calculate_ema(self.close_history, self.length)
            self.basis_history.append(basis)
            if len(self.basis_history) > 50:
                self.basis_history = self.basis_history[-50:]
            
            # 2. 计算标准差和布林带上下轨
            stdev = self._calculate_stdev(self.close_history, basis, self.length)
            upper = basis + self.mult * stdev
            lower = basis - self.mult * stdev
            
            # 3. 计算布林带宽度
            bollinger_width = upper - lower
            
            # 4. 计算波动率比值（布林带宽度/中轨）
            volatility_ratio = bollinger_width / basis if basis > 0 else 0
            print(f"  🔍 当前波动率比值: {volatility_ratio:.4f}倍")
            self.volatility_ratio_history.append(volatility_ratio)
            if len(self.volatility_ratio_history) > self.ema_period * 2:
                self.volatility_ratio_history = self.volatility_ratio_history[-self.ema_period * 2:]
            
            # 5. 计算波动率EMA
            if len(self.volatility_ratio_history) >= self.ema_period:
                self.volatility_ema = self._calculate_ema(self.volatility_ratio_history, self.ema_period)
                # 更新缓存值
                self._update_cached_values()
            
            # 6. 计算中轨变化率
            self._calculate_basis_change_rate()
            
            # 检查预热状态
            if not self.is_warmed_up and len(self.volatility_ratio_history) >= self.required_warmup:
                self.is_warmed_up = True
                print(f"✅ 波动率计算器预热完成！({self.volatility_timeframe}周期)")
            
            # 更新缓存信息
            self._update_cached_info()
    
    def _get_current_volatility_info(self):
        """获取当前波动率信息"""
        if not self.volatility_ratio_history:
            return {
                'volatility_ratio': 0,
                'volatility_ema': None,
                'volatility_ratio_vs_ema': 0,
                'is_warmed_up': self.is_warmed_up,
                'timeframe': self.volatility_timeframe
            }
        
        # 使用最新的波动率比值
        current_volatility_ratio = self.volatility_ratio_history[-1]
        
        # 计算波动率比较（当前值/EMA值）
        volatility_ratio_vs_ema = 0
        if self.volatility_ema and self.volatility_ema > 0:
            volatility_ratio_vs_ema = current_volatility_ratio / self.volatility_ema
        
        return {
            'volatility_ratio': current_volatility_ratio,
            'volatility_ema': self.volatility_ema,
            'volatility_ratio_vs_ema': volatility_ratio_vs_ema,
            'is_warmed_up': self.is_warmed_up,
            'timeframe': self.volatility_timeframe
        }
    
    def _get_cached_volatility_info(self):
        """获取缓存的波动率信息（高性能版本）"""
        return self._cached_info
    
    def get_volatility_ratio_vs_ema(self):
        """获取当前波动率比值（用于与阈值比较）"""
        return self._cached_ratio_vs_ema
    
    def get_volatility_ratio(self):
        """获取当前波动率比值（布林带宽度/中轨）"""
        if not self.volatility_ratio_history:
            return 0
        return self.volatility_ratio_history[-1]
    
    def get_basis_change_rate(self):
        """获取当前中轨变化率（用于与阈值比较）"""
        return self.basis_change_rate
    
    def is_basis_change_sufficient(self, threshold):
        """检查中轨变化率是否足够（用于开仓判断）"""
        if not self.is_warmed_up:
            return False
        return self.get_basis_change_rate() >= threshold
    
    def _update_cached_values(self):
        """更新缓存值"""
        if self.volatility_ema and self.volatility_ema > 0 and self.volatility_ratio_history:
            self._cached_ratio_vs_ema = self.volatility_ratio_history[-1] / self.volatility_ema
        else:
            self._cached_ratio_vs_ema = 0
    
    def _calculate_basis_change_rate(self):
        """计算中轨变化率"""
        # 存储当前中轨值
        if self.basis_history:
            current_basis = self.basis_history[-1]
            self.basis_change_history.append(current_basis)
            
            # 只保留最近3个值
            if len(self.basis_change_history) > 3:
                self.basis_change_history = self.basis_change_history[-3:]
            
            # 计算变化率：(T - T-2) / 3
            if len(self.basis_change_history) >= 3:
                change = self.basis_change_history[-1] - self.basis_change_history[0]  # T - T-2
                self.basis_change_rate = abs(change / 3)  # |(T - T-2) / 3|
            else:
                self.basis_change_rate = 0
    
    def _update_cached_info(self):
        """更新缓存信息"""
        self._cached_info.update({
            'volatility_ratio': self.volatility_ratio_history[-1] if self.volatility_ratio_history else 0,
            'volatility_ema': self.volatility_ema,
            'volatility_ratio_vs_ema': self._cached_ratio_vs_ema,
            'basis_change_rate': self.basis_change_rate,
            'is_warmed_up': self.is_warmed_up,
            'timeframe': self.volatility_timeframe
        })
    
    def is_volatility_sufficient(self, threshold):
        """检查波动率是否足够（用于开仓判断）"""
        if not self.is_warmed_up:
            return False
        return self.get_volatility_ratio_vs_ema() >= threshold
    
    def get_volatility_info(self):
        """获取完整的波动率信息"""
        return self._get_current_volatility_info()
    
    def warmup_with_historical_data(self, historical_data):
        """使用历史数据预热波动率计算器"""
        if not historical_data:
            print("⚠️  没有历史数据可用于预热波动率计算器")
            return
        
        print(f"🔥 开始使用 {len(historical_data)} 条历史数据预热波动率计算器...")
        
        for i, data in enumerate(historical_data):
            timestamp = data.get('timestamp')
            close_price = data.get('close', 0)
            
            self.update(timestamp, close_price)
            
            if (i + 1) % 1000 == 0:
                print(f"    波动率预热进度: {i+1}/{len(historical_data)}")
        
        print(f"✅ 波动率计算器预热完成！")


# 使用示例
if __name__ == "__main__":
    # 创建6小时波动率计算器
    volatility_calc = VolatilityCalculator(
        volatility_timeframe='6h',
        length=14,
        mult=2.0,
        ema_period=90
    )
    
    # 模拟一些数据
    print("\n📊 模拟数据更新...")
    from datetime import datetime, timedelta
    
    base_time = datetime(2025, 1, 1, 0, 0, 0)
    base_price = 100000
    
    for i in range(1000):
        timestamp = base_time + timedelta(minutes=i)
        close_price = base_price + i * 10 + (i % 10) * 100  # 模拟价格波动
        
        result = volatility_calc.update(timestamp, close_price)
        
        if i % 100 == 0:
            print(f"  更新 {i}: 时间={timestamp.strftime('%H:%M')}, 价格={close_price:.2f}")
            print(f"    波动率比值: {result['volatility_ratio']:.4f}")
            print(f"    波动率EMA: {result['volatility_ema']:.4f if result['volatility_ema'] else 'N/A'}")
            print(f"    波动率比较: {result['volatility_ratio_vs_ema']:.2f}倍")
            print(f"    预热状态: {result['is_warmed_up']}")
            print()
    
    print("✅ 测试完成！")
