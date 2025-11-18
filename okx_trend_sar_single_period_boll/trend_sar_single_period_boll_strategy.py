#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
from datetime import datetime, timedelta
from volatility_calculator import VolatilityCalculator
from ema_calculator import EMACalculator
from dingtalk_notifier import DingTalkNotifier

def timeframe_to_minutes(timeframe):
    """将时间周期字符串转换为分钟数"""
    timeframe_map = {
        '5m': 5, '15m': 15, '20m': 20, '24m': 24, '30m': 30, '1h': 60,
        '2h': 120, '4h': 240, '8h': 480, '1d': 1440
    }
    return timeframe_map.get(timeframe, 30)

def minutes_to_timeframe(minutes):
    """将分钟数转换为时间周期字符串"""
    if minutes < 60:
        return f"{minutes}m"
    elif minutes < 1440:
        hours = minutes // 60
        return f"{hours}h"
    else:
        days = minutes // 1440
        return f"{days}d"

class TrendFilterTimeframeManager:
    """时间周期管理器 - 处理1分钟数据聚合到指定时间周期"""
    
    def __init__(self, timeframe='30m'):
        self.timeframe = timeframe
        self.kline_data = []
        self.current_period = None
        self.current_open = None
        self.current_high = None  
        self.current_low = None
        self.current_close = None
        self.current_volume = 0  # 添加成交量字段
        
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
        elif minutes == 20:
            minute = timestamp.minute
            if minute < 20:
                return timestamp.replace(minute=0, second=0, microsecond=0)
            elif minute < 40:
                return timestamp.replace(minute=20, second=0, microsecond=0)
            else:
                return timestamp.replace(minute=40, second=0, microsecond=0)
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
    
    def get_timeframe_minutes(self):
        """获取时间周期对应的分钟数"""
        timeframe_minutes = {
            '5m': 5, '15m': 15, '20m': 20, '30m': 30, '1h': 60,
            '2h': 120, '4h': 240, '8h': 480, '1d': 1440
        }
        return timeframe_minutes.get(self.timeframe, 30)
    
    def update_kline_data(self, timestamp, open_price, high_price, low_price, close_price, volume=0):
        """更新K线数据（处理1分钟数据聚合）"""
        minutes = self.get_timeframe_minutes()
        period_start = self._calculate_period_start(timestamp, minutes)
        
        # DEBUG: 打印周期判断的关键变量
        try:
            print(f"[TM] update_kline_data | ts={timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                  f"| minutes={minutes} | period_start={period_start.strftime('%Y-%m-%d %H:%M:%S') if hasattr(period_start,'strftime') else period_start} "
                  f"| current_period(before)={self.current_period.strftime('%Y-%m-%d %H:%M:%S') if hasattr(self.current_period,'strftime') else self.current_period}")
        except Exception:
            pass
        
        if self.current_period is None or period_start != self.current_period:
            # 保存上一个周期的K线数据
            if (self.current_period is not None and self.current_open is not None):
                # DEBUG: 周期切换，输出上一周期信息
                try:
                    print(f"[TM] period change detected → emit previous kline "
                          f"| prev_period={self.current_period.strftime('%Y-%m-%d %H:%M:%S') if hasattr(self.current_period,'strftime') else self.current_period} "
                          f"| open={self.current_open} high={self.current_high} low={self.current_low} close={self.current_close} vol={self.current_volume}")
                except Exception:
                    pass
                kline_data = {
                    'timestamp': self.current_period,
                    'open': self.current_open,
                    'high': self.current_high,
                    'low': self.current_low,
                    'close': self.current_close,
                    'volume': self.current_volume
                }
                self.kline_data.append(kline_data)
                new_kline = kline_data.copy()
            else:
                new_kline = None
            
            # 开始新周期
            self.current_period = period_start
            self.current_open = open_price
            self.current_high = high_price
            self.current_low = low_price
            self.current_close = close_price
            self.current_volume = volume  # 重置成交量
            
            # DEBUG: 新周期设定后打印
            try:
                print(f"[TM] new current_period={self.current_period.strftime('%Y-%m-%d %H:%M:%S') if hasattr(self.current_period,'strftime') else self.current_period} "
                      f"| first_tick O/H/L/C/V={open_price}/{high_price}/{low_price}/{close_price}/{volume}")
            except Exception:
                pass
            
            return new_kline
        else:
            # 更新当前周期的数据
            if self.current_high is not None:
                self.current_high = max(self.current_high, high_price)
            if self.current_low is not None:
                self.current_low = min(self.current_low, low_price)
            self.current_close = close_price
            self.current_volume += volume  # 累加成交量
            
            return None

class ATRCalculator:
    """
    ATR计算器 - 计算平均真实波幅（Average True Range）
    """
    
    def __init__(self):
        """初始化ATR计算器"""
        self.high_prices = []         # 最高价历史
        self.low_prices = []          # 最低价历史
        self.close_prices = []        # 收盘价历史
        self.atr_periods = []         # 存储14个周期的ATR值列表
        
    def _calculate_atr(self, high_prices, low_prices, close_prices, period):
        """
        计算ATR（平均真实波幅）
        
        Args:
            high_prices: 最高价序列
            low_prices: 最低价序列  
            close_prices: 收盘价序列
            period: ATR周期
            
        Returns:
            float: ATR值
        """
        if len(high_prices) < 2:
            return 0.0
        
        # 计算真实波幅TR：max(high - low, high - prev_close, prev_close - low)
        tr_values = []
        
        for i in range(1, len(high_prices)):
            high = high_prices[i]
            low = low_prices[i]
            prev_close = close_prices[i-1]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(prev_close - low)
            )
            tr_values.append(tr)
        
        # 计算ATR：TR的平均值
        if len(tr_values) >= period:
            return sum(tr_values[-period:]) / period
        elif len(tr_values) > 0:
            return sum(tr_values) / len(tr_values)
        else:
            return 0.0
    
    def _calculate_tr(self, high_prices, low_prices, close_prices):
        """
        计算当前K线的真实波幅TR
        
        Args:
            high_prices: 最高价序列
            low_prices: 最低价序列  
            close_prices: 收盘价序列
            
        Returns:
            float: 当前K线的TR值
        """
        if len(high_prices) < 2:
            return 0.0
        
        # 获取当前K线的数据
        current_high = high_prices[-1]
        current_low = low_prices[-1]
        prev_close = close_prices[-2]
        
        # 计算TR：max(high - low, high - prev_close, prev_close - low)
        tr = max(
            current_high - current_low,
            abs(current_high - prev_close),
            abs(prev_close - current_low)
        )
        
        return tr
    
    def update_accumulate(self, close_price, high_price=None, low_price=None):
        """
        累积ATR计算数据（只存储数据，不计算）
        
        Args:
            close_price: 收盘价
            high_price: 最高价
            low_price: 最低价
        """
        self.close_prices.append(close_price)
        
        if high_price is not None:
            self.high_prices.append(high_price)
        if low_price is not None:
            self.low_prices.append(low_price)
        
        # 保持历史数据长度
        max_history = 100
        if len(self.close_prices) > max_history:
            self.close_prices = self.close_prices[-max_history:]
            self.high_prices = self.high_prices[-max_history:]
            self.low_prices = self.low_prices[-max_history:]
    
    def update_kline_end(self, close_price, high_price=None, low_price=None):
        """
        当新K线生成时的ATR计算
        
        Args:
            close_price: 收盘价
            high_price: 最高价
            low_price: 最低价
        """
        self.close_prices.append(close_price)
        
        if high_price is not None:
            self.high_prices.append(high_price)
        if low_price is not None:
            self.low_prices.append(low_price)
        
        # 保持历史数据长度
        max_history = 100
        if len(self.close_prices) > max_history:
            self.close_prices = self.close_prices[-max_history:]
            self.high_prices = self.high_prices[-max_history:]
            self.low_prices = self.low_prices[-max_history:]
        
        # 更新ATR计算
        self._update_atr_calculation()
    
    def update(self, close_price, high_price=None, low_price=None):
        """
        更新ATR计算（兼容性方法）
        
        Args:
            close_price: 收盘价
            high_price: 最高价
            low_price: 最低价
        """
        self.close_prices.append(close_price)
        
        if high_price is not None:
            self.high_prices.append(high_price)
        if low_price is not None:
            self.low_prices.append(low_price)
        
        # 保持历史数据长度
        max_history = 100
        if len(self.close_prices) > max_history:
            self.close_prices = self.close_prices[-max_history:]
            self.high_prices = self.high_prices[-max_history:]
            self.low_prices = self.low_prices[-max_history:]
        
        # 更新ATR计算
        self._update_atr_calculation()
    
    def _update_atr_calculation(self):
        """更新ATR计算"""
        # 确保有足够的数据计算ATR
        if len(self.high_prices) < 2 or len(self.low_prices) < 2:
            return
        
        # 计算当前K线的TR值（真实波幅）
        current_tr = self._calculate_tr(self.high_prices, self.low_prices, self.close_prices)
        if current_tr > 0:
            # 添加到TR周期列表，保持最多14个值
            self.atr_periods.append(current_tr)
            if len(self.atr_periods) > 14:
                self.atr_periods = self.atr_periods[-14:]
        
        # 打印ATR计算结果（显示当前周期的计算）
        if len(self.atr_periods) > 0:
            current_tr_value = self.atr_periods[-1]
            print(f"    📊 ATR当前周期TR: {current_tr_value:.6f}")
            
            # 如果累积数据足够，显示3周期和14周期的ATR平均值
            if len(self.atr_periods) >= 3:
                atr_3_avg = sum(self.atr_periods[-3:]) / 3
                print(f"        3周期ATR平均: {atr_3_avg:.6f}")
            
            if len(self.atr_periods) >= 14:
                atr_14_avg = sum(self.atr_periods) / 14
                print(f"        14周期ATR平均: {atr_14_avg:.6f}")
                if len(self.atr_periods) >= 3:
                    atr_3_avg = sum(self.atr_periods[-3:]) / 3
                    atr_ratio = atr_3_avg / atr_14_avg if atr_14_avg > 0 else 0
                    print(f"        波动率比率: {atr_ratio:.4f} (3周期/14周期)")
                    # 打印14周期全部波动率
                    print(f"        14周期全部波动率: {self.atr_periods}")
                    # 判断是否通过过滤条件
                    # if atr_ratio <= 1.3:
                    #     print(f"        ✅ ATR波动率: 通过过滤 ({atr_ratio:.4f} ≤ 1.3)")
                    # else:
                    #     print(f"        ❌ ATR波动率: 过高 ({atr_ratio:.4f} > 1.3)")
    
    def get_atr_volatility_ratio(self):
        """
        检查ATR波动率过滤条件
        
        Returns:
            dict: 包含ATR过滤结果的字典
        """
        # 检查是否有足够的ATR数据
        if len(self.atr_periods) < 3:
            return {
                'atr_14': 0.0,
                'atr_3': 0.0,
                'atr_ratio': 0.0,
                'is_atr_filter_passed': False,
                'reason': f'ATR数据不足，需要至少3个周期，当前: {len(self.atr_periods)}'
            }
        
        # 计算最近3个周期的ATR平均值
        if len(self.atr_periods) >= 3:
            atr_3 = sum(self.atr_periods[-3:]) / 3
        else:
            atr_3 = sum(self.atr_periods) / len(self.atr_periods)
        
        # 计算最近14个周期或其实际数据的ATR平均值
        if len(self.atr_periods) >= 14:
            atr_14 = sum(self.atr_periods) / 14
        else:
            atr_14 = sum(self.atr_periods) / len(self.atr_periods)
        
        # 计算比率
        atr_ratio = atr_3 / atr_14 if atr_14 > 0 else 0
        
        # 检查是否通过ATR过滤（比率 > 1.3时不通过）
        is_filter_passed = atr_ratio <= 1.3
        
        reason = 'ATR波动率过滤通过' if is_filter_passed else f'ATR波动率过高: {atr_ratio:.2f} > 1.3'
        
        return {
            'atr_14': atr_14,
            'atr_3': atr_3, 
            'atr_ratio': atr_ratio,
            'is_atr_filter_passed': is_filter_passed,
            'reason': reason
        }
    
class SarBollingerBandsIndicator:
    """SAR + Bollinger Bands with Regressive MA 指标实现"""
    
    def __init__(self, length=14, mult=2.0, basis_ma_length=14, regression_factor=0.9,
                 sar_start=0.01, sar_increment=0.01, sar_maximum=0.04):
        self.length = length
        self.mult = mult
        self.basis_ma_length = basis_ma_length
        self.regression_factor = regression_factor
        self.sar_start = sar_start
        self.sar_increment = sar_increment
        self.sar_maximum = sar_maximum
        
        # 布林带相关历史数据
        self.close_history = []
        self.basis_history = []
        self.basis_ma_history = []
        
        # SAR相关状态
        self.sar_value = None
        self.sar_af = self.sar_start
        self.sar_ep = None
        self.sar_direction = 1
        self.sar_history = []
        
        # SAR转向记录
        self.sar_turn_up_bar = None
        self.sar_turn_down_bar = None
        self.current_bar_index = 0
        
        # RSI相关数据
        self.rsi_period = length  # 使用与SAR相同的周期
        self.rsi_values = []  # 存储RSI历史值
        self.current_rsi = 0  # 当前RSI值
        self.price_changes = []  # 价格变化数组
        
        # 预热状态标记
        self.is_warmed_up = False
        self.warmup_data_count = 0
        ema_convergence = length * 4
        double_ema_convergence = basis_ma_length * 4
        sar_stabilization = 50
        self.required_warmup = max(200, ema_convergence + double_ema_convergence + sar_stabilization)
        
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
    
    def _calculate_sma(self, values, period):
        """计算SMA"""
        if len(values) < period:
            return sum(values) / len(values) if values else 0
        return sum(values[-period:]) / period
    
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
    
    def _calculate_rsi(self, prices, period):
        """计算RSI"""
        if len(prices) < 2:
            return 50  # 默认中性值
        
        # 重新计算所有价格变化（确保数据一致性）
        self.price_changes = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            self.price_changes.append(change)
        
        # 保持价格变化数组长度
        if len(self.price_changes) > period * 2:
            self.price_changes = self.price_changes[-period * 2:]
        
        if len(self.price_changes) < period:
            return 50  # 数据不足，返回中性值
        
        # 计算最近period期的价格变化
        recent_changes = self.price_changes[-period:]
        
        # 分离上涨和下跌
        gains = [max(change, 0) for change in recent_changes]
        losses = [max(-change, 0) for change in recent_changes]
        
        # 计算平均上涨和下跌
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        # 避免除零
        if avg_loss == 0:
            return 100
        
        # 计算RS
        rs = avg_gain / avg_loss
        
        # 计算RSI
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _update_sar(self, high, low, close):
        """更新SAR值"""
        if self.sar_value is None:
            # 智能判断初始方向
            self.sar_direction = 1 if close >= (high + low) / 2 else -1

            if self.sar_direction == 1:
                self.sar_value = low
                self.sar_ep = high
            else:
                self.sar_value = high  
                self.sar_ep = low

            self.sar_af = self.sar_start
            # 保存前值用于保护计算
            self.prev_high, self.prev_low = high, low
            
            return self.sar_value
        
        prev_sar = self.sar_value
        prev_high, prev_low = self.prev_high, self.prev_low
        
        if self.sar_direction == 1:  # 上升趋势
            if high > self.sar_ep:
                self.sar_ep = high
                self.sar_af = min(self.sar_af + self.sar_increment, self.sar_maximum)
            
            # 计算新SAR
            self.sar_value = prev_sar + self.sar_af * (self.sar_ep - prev_sar)

            # 保护：SAR不能高于最近两个K线的最低点
            self.sar_value = min(self.sar_value, low, prev_low)
            
            if low <= self.sar_value:
                self.sar_direction = -1
                self.sar_value = max(self.sar_ep, high)  # 使用EP和当前高的最大值
                self.sar_ep = low
                self.sar_af = self.sar_start
                self.sar_turn_down_bar = self.current_bar_index
        else:  # 下降趋势
            if low < self.sar_ep:
                self.sar_ep = low
                self.sar_af = min(self.sar_af + self.sar_increment, self.sar_maximum)
            
            # 计算新SAR
            self.sar_value = prev_sar - self.sar_af * (prev_sar - self.sar_ep)

            # 保护：SAR不能低于最近两个K线的最高点
            self.sar_value = max(self.sar_value, high, prev_high)
            
            if high >= self.sar_value:
                self.sar_direction = 1
                self.sar_value = min(self.sar_ep, low)  # 使用EP和当前低的最小值
                self.sar_ep = high
                self.sar_af = self.sar_start
                self.sar_turn_up_bar = self.current_bar_index

        # 更新前值
        self.prev_high, self.prev_low = high, low
        
        return self.sar_value
    
    def update(self, close_price, high_price=None, low_price=None):
        """更新SAR + Bollinger Bands指标"""
        self.warmup_data_count += 1
        self.current_bar_index += 1
        
        # 检查预热状态
        if not self.is_warmed_up and self.warmup_data_count >= self.required_warmup:
            self.is_warmed_up = True
            print(f"    ✅ SAR指标预热完成！")
        
        # 统一的指标计算逻辑（预热和正式交易期间都执行）
        # 存储历史数据
        self.close_history.append(close_price)
        if len(self.close_history) > self.length * 2:
            self.close_history = self.close_history[-self.length * 2:]
        
        # 1. 计算布林带 basis (EMA)
        basis = self._calculate_ema(self.close_history, self.length)
        self.basis_history.append(basis)
        if len(self.basis_history) > self.basis_ma_length * 2:
            self.basis_history = self.basis_history[-self.basis_ma_length * 2:]
        
        # 2. 计算标准差和布林带上下轨
        stdev = self._calculate_stdev(self.close_history, basis, self.length)
        upper = basis + self.mult * stdev
        lower = basis - self.mult * stdev
        
        # 3. 计算布林带中轨的MA (EMA)
        basis_ma = self._calculate_ema(self.basis_history, self.basis_ma_length)
        self.basis_ma_history.append(basis_ma)
        if len(self.basis_ma_history) > 50:
            self.basis_ma_history = self.basis_ma_history[-50:]
        
        # 4. 应用回归阻尼：将MA向中轨线性回归
        regressive_ma = (self.regression_factor * basis_ma) + ((1 - self.regression_factor) * basis)
        
        # 5. 计算RSI（只在有足够数据时计算）
        if len(self.close_history) >= self.rsi_period:
            old_rsi = self.current_rsi
            self.current_rsi = self._calculate_rsi(self.close_history, self.rsi_period)
            self.rsi_values.append(self.current_rsi)
            if len(self.rsi_values) > self.rsi_period * 2:
                self.rsi_values = self.rsi_values[-self.rsi_period * 2:]
            
            # RSI 调试信息（只在预热完成后显示）
            # if self.is_warmed_up:
            #     print(f"    🔍 RSI更新: {old_rsi:.2f} → {self.current_rsi:.2f} (价格数量: {len(self.close_history)})")
        else:
            self.current_rsi = 50  # 数据不足时使用中性值
        
        # 6. 更新SAR
        if high_price is not None and low_price is not None:
            sar_value = self._update_sar(high_price, low_price, close_price)
            self.sar_history.append(sar_value)
            if len(self.sar_history) > 50:
                self.sar_history = self.sar_history[-50:]
        else:
            sar_value = self.sar_value
        
        # 7. 检测SAR转向
        sar_rising = self.sar_direction == 1
        sar_falling = self.sar_direction == -1
        
        # 8. 计算布林带宽度
        bollinger_width = upper - lower
        quarter_bollinger_width = bollinger_width / 4.0
        
        # 9. 计算从SAR转向后经过的周期数
        bars_since_turn_up = 0
        bars_since_turn_down = 0
        
        if self.sar_turn_up_bar is not None:
            bars_since_turn_up = self.current_bar_index - self.sar_turn_up_bar
        if self.sar_turn_down_bar is not None:
            bars_since_turn_down = self.current_bar_index - self.sar_turn_down_bar
        
        # 10. 生成信号
        bull_signal = sar_rising
        bear_signal = sar_falling
        
        # 调试信息
        if self.is_warmed_up:
            # print(f"    📊 SAR值: {sar_value:.2f} | 方向: {'上升' if sar_rising else '下降'}")
            # print(f"    📈 布林带: 上轨{upper:.2f} | 中轨{basis:.2f} | 下轨{lower:.2f}")
            # print(f"    📏 布林带宽度: {bollinger_width:.2f} | 1/4宽度: {quarter_bollinger_width:.2f}")
            # print(f"    🔧 中轨MA (basis_ma): {basis_ma:.2f}")
            # print(f"    💫 回归MA: {regressive_ma:.2f} = {self.regression_factor:.1f}×{basis_ma:.2f} + {1-self.regression_factor:.1f}×{basis:.2f}")
            # print(f"    📊 RSI: {self.current_rsi:.2f} (周期{self.rsi_period})")
            # print(f"    🔍 SAR转向: 上升{bars_since_turn_up}期 | 下降{bars_since_turn_down}期")
            
            if sar_rising:
                signal_status = f"✅ 看多信号 (SAR上升)"
            elif sar_falling:
                signal_status = f"✅ 看空信号 (SAR下降)"
            else:
                signal_status = "❓ SAR方向不明确"
                
            print(f"    🎯 信号状态: {signal_status}")
            print(f"    🎯 最终信号: 看多={bull_signal} | 看空={bear_signal}")
        # else:
        #     # 预热期间的简化调试信息
        #     print(f"    🔥 SAR预热中 {self.warmup_data_count}/{self.required_warmup} | SAR: {sar_value:.2f} | RSI: {self.current_rsi:.2f}")
        
        return {
            'sar_value': sar_value,
            'basis': basis, 'upper': upper, 'lower': lower,
            'regressive_ma': regressive_ma,
            'bollinger_width': bollinger_width,
            'quarter_bollinger_width': quarter_bollinger_width,
            'bull_signal': bull_signal, 'bear_signal': bear_signal,
            'sar_direction': self.sar_direction,
            'sar_rising': sar_rising, 'sar_falling': sar_falling,
            'bars_since_turn_up': bars_since_turn_up,
            'bars_since_turn_down': bars_since_turn_down,
            'trend_direction': 'up' if sar_rising else 'down',
            'rsi': self.current_rsi,
            'rsi_values': self.rsi_values.copy(),
            'is_warmed_up': self.is_warmed_up  # 添加预热状态标识
        }
    
    def get_stop_loss_level(self):
        """获取止损位（SAR线的当前值）"""
        return self.sar_value

class TrendSarStrategy:
    """单周期SAR策略管理器"""
    
    def __init__(self, timeframe='30m', length=14, damping=0.9, bands=1.0,
                 sar_start=0.02, sar_increment=0.02, sar_maximum=0.2,
                 mult=2.0, initial_capital=100000, position_size_percentage=100, 
                 fixed_take_profit_pct=2.0, max_stop_loss_pct=0,
                 volatility_timeframe='6h', volatility_length=14, volatility_mult=2.0, 
                 volatility_ema_period=90, volatility_threshold=0.8, **kwargs):
        """初始化单周期SAR策略"""
        self.timeframe = timeframe
        
        # 初始化单时间周期管理器和指标
        self.timeframe_manager = TrendFilterTimeframeManager(timeframe)
        
        # 初始化SAR指标（移除波动率相关参数）
        self.sar_indicator = SarBollingerBandsIndicator(
            length, mult, length, damping,
            sar_start, sar_increment, sar_maximum
        )
        
        # 初始化独立的波动率计算器
        self.volatility_calculator = VolatilityCalculator(
            volatility_timeframe=volatility_timeframe,
            length=volatility_length,
            mult=volatility_mult,
            ema_period=volatility_ema_period
        )
        self.volatility_threshold = volatility_threshold
        self.basis_change_threshold = kwargs.get('basis_change_threshold', 180)
        
        # 初始化EMA计算器
        self.ema_calculator = EMACalculator(
            ema_timeframe=kwargs.get('ema_timeframe', '1h'),
            ema_periods=kwargs.get('ema_periods', [24, 50, 100])
        )
        
        # 初始化ATR计算器
        self.atr_calculator = ATRCalculator()
        
        # 🔴 初始化Delta Volume相关属性（固定周期）
        delta_volume_period = kwargs.get('delta_volume_period', 14)  # 默认14个周期
        self.delta_volume_period = delta_volume_period
        self.buy_volume_history = []   # 每根完整周期K线的买入量历史（按整个周期K线涨跌判断）
        self.sell_volume_history = []  # 每根完整周期K线的卖出量历史（按整个周期K线涨跌判断）
        self.current_kline_volume = 0  # 当前周期K线累积的总成交量（每周期重置）
        self.current_period_buy_volume = 0   # 当前周期内按分钟实时分类的买入量（未完成周期使用）
        self.current_period_sell_volume = 0  # 当前周期内按分钟实时分类的卖出量（未完成周期使用）
        self.delta_volume_fixed = 0    # 固定周期Delta Volume值
        self.delta_volume_percent_fixed = 0  # 固定周期Delta Volume百分比
        
        # 🔴 Delta Volume止损阈值配置
        self.delta_volume_stop_loss_threshold = kwargs.get('delta_volume_stop_loss_threshold', 0.6)  # 默认60%
        print(f"📊 Delta Volume配置: 周期={delta_volume_period}, 止损阈值={self.delta_volume_stop_loss_threshold*100:.0f}%")
        
        # 🔴 初始化钉钉推送器
        dingtalk_webhook = kwargs.get('dingtalk_webhook', None)
        dingtalk_secret = kwargs.get('dingtalk_secret', None)
        print(f"🔍 钉钉配置调试: webhook={dingtalk_webhook}, secret={dingtalk_secret}")
        if dingtalk_webhook:
            self.dingtalk_notifier = DingTalkNotifier(dingtalk_webhook, dingtalk_secret)
            if dingtalk_secret:
                print(f"📱 钉钉消息推送已启用（加签模式）")
            else:
                print(f"📱 钉钉消息推送已启用")
        else:
            self.dingtalk_notifier = None
            print(f"📱 钉钉消息推送未配置")
        
        print(f"📊 单周期SAR策略模式: 主周期({timeframe})")
        
        # 向后兼容
        self.trend_filter = self.sar_indicator
        
        # 资金配置
        self.initial_capital = initial_capital
        self.position_size_percentage = position_size_percentage
        self.cash_balance = initial_capital
        
        # 止盈止损配置
        self.fixed_take_profit_pct = fixed_take_profit_pct
        self.max_stop_loss_pct = max_stop_loss_pct  # 最大止损百分比（与SAR止损对比选择更近的，同时也作为硬性保护位）
        
        # 单周期交易状态
        self.position = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None
        self.current_invested_amount = None
        self.position_shares = None
        
        # 单周期趋势方向跟踪
        self.current_trend_direction = None
        self.previous_trend_direction = None
        
        # 🔴 预热模式标志（预热期间不进行交易）
        self.is_warmup_mode = True
        
        # 交易统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.win_rate = 0.0
        
    def warmup_filter(self, historical_data):
        """使用历史数据预热单周期SAR指标"""
        if not historical_data:
            print("⚠️  没有历史数据可用于预热")
            return
            
        print(f"🔥 开始使用 {len(historical_data)} 条历史数据预热单周期SAR指标和波动率计算器...")
        
        kline_count = 0
        
        for i, data in enumerate(historical_data):
            timestamp = data.get('timestamp')
            open_price = data.get('open', 0)
            high_price = data.get('high', 0)
            low_price = data.get('low', 0)
            close_price = data.get('close', 0)
            
            # 预热波动率计算器（使用1分钟数据）
            self.volatility_calculator.update(timestamp, close_price)
            
            # 预热EMA计算器（使用1分钟数据）
            self.ema_calculator.update(timestamp, close_price)
            
            # 🔴 预热ATR计算器（每分钟累积数据）
            self.atr_calculator.update_accumulate(close_price, high_price, low_price)
            
            # 预热主周期（volume 可能没有，使用 0）
            volume = data.get('volume', 0)
            
            # 🔴 预热阶段也累积成交量并按分钟分类（用于Delta Volume计算）
            if volume > 0:
                self.current_kline_volume += volume
                # 预热阶段也按1分钟K线涨跌实时分类
                if close_price > open_price:
                    self.current_period_buy_volume += volume
                elif close_price < open_price:
                    self.current_period_sell_volume += volume
            
            # 🔴 预热阶段：每条1分钟数据都计算Delta Volume（模拟正式交易逻辑）
            # 这样预热和正式交易可以无缝衔接
            self._update_fixed_delta_volume(timestamp=timestamp, current_price=close_price)
            
            new_kline = self.timeframe_manager.update_kline_data(
                timestamp, open_price, high_price, low_price, close_price, volume
            )
            
            if new_kline is not None:
                kline_count += 1
                
                # 🔴 在周期K线生成时，保存上一根K线的成交量（按涨跌分类到Delta Volume历史）
                prev_volume = self.current_kline_volume if self.current_kline_volume > 0 else new_kline.get('volume', 0)
                if prev_volume > 0:
                    # 从new_kline中获取上一根K线的数据（new_kline就是刚保存的上一根K线）
                    prev_open = new_kline['open']
                    prev_close = new_kline['close']
                    
                    if prev_close > prev_open:
                        # 阳线：总成交量归为买入量
                        self.buy_volume_history.append(prev_volume)
                        self.sell_volume_history.append(0)
                        kline_type = "阳线(买入)"
                    elif prev_close < prev_open:
                        # 阴线：总成交量归为卖出量
                        self.buy_volume_history.append(0)
                        self.sell_volume_history.append(prev_volume)
                        kline_type = "阴线(卖出)"
                    else:
                        # 十字星：不计入买卖量
                        self.buy_volume_history.append(0)
                        self.sell_volume_history.append(0)
                        kline_type = "十字星(不计)"
                    
                    # 只保留最近N个周期
                    if len(self.buy_volume_history) > self.delta_volume_period:
                        self.buy_volume_history = self.buy_volume_history[-self.delta_volume_period:]
                        self.sell_volume_history = self.sell_volume_history[-self.delta_volume_period:]
                    
                    # 🔴 预热阶段调试信息（仅显示前5个和后5个K线，避免刷屏）
                    if kline_count <= 5 or (kline_count > 5 and len(self.buy_volume_history) <= 5):
                        print(f"    📊 【预热-Delta Volume】K线#{kline_count}完成，保存: {kline_type} Open={prev_open:.2f}, Close={prev_close:.2f}, Vol={prev_volume:,.0f} | 历史长度={len(self.buy_volume_history)}")
                elif new_kline.get('volume', 0) == 0:
                    # 如果成交量为0，也保存（十字星）
                    self.buy_volume_history.append(0)
                    self.sell_volume_history.append(0)
                    if len(self.buy_volume_history) > self.delta_volume_period:
                        self.buy_volume_history = self.buy_volume_history[-self.delta_volume_period:]
                        self.sell_volume_history = self.sell_volume_history[-self.delta_volume_period:]
                
                # 重置当前周期K线累积和分类（开始新的聚合周期）
                self.current_kline_volume = 0
                self.current_period_buy_volume = 0
                self.current_period_sell_volume = 0
                
                # 🔴 在周期K线生成时更新ATR计算
                self.atr_calculator.update_kline_end(
                    new_kline['close'],
                    new_kline['high'],
                    new_kline['low']
                )
                
                result = self.sar_indicator.update(
                    new_kline['close'], 
                    new_kline['high'], 
                    new_kline['low']
                )
                
                # 🔴 预热期间也同步更新趋势方向（不触发交易）
                try:
                    dummy_signal_info = {'signals': [], 'timestamp': new_kline['timestamp']}
                    self._check_trend_change(result, new_kline['open'], dummy_signal_info)
                except Exception as _:
                    # 预热阶段仅同步方向，忽略异常以免中断
                    pass
                
                # 打印周期K线信息（仅前10个，避免刷屏）
                if kline_count <= 10:
                    # 计算时间范围
                    timeframe_minutes = self.timeframe_manager.get_timeframe_minutes()
                    kline_end_time = new_kline['timestamp'] + timedelta(minutes=timeframe_minutes-1, seconds=59)
                    
                    print(f"\n    🟢 {self.timeframe} K线 #{kline_count}")
                    print(f"       ⏰ 时间: {new_kline['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"       📅 周期: {new_kline['timestamp'].strftime('%H:%M')} - {kline_end_time.strftime('%H:%M')}")
                    print(f"       📊 开:${new_kline['open']:.2f} 高:${new_kline['high']:.2f} "
                          f"低:${new_kline['low']:.2f} 收:${new_kline['close']:.2f} 量:{new_kline['volume']:.2f}")
                    print(f"       📈 SAR:{result['sar_value']:.2f} RSI:{result['rsi']:.2f}")
                elif kline_count == 11:
                    print(f"\n    ... (省略中间K线，继续预热中) ...")
            
            # if (i + 1) % 100 == 0:
            #     print(f"    预热进度: {i+1}/{len(historical_data)} | {self.timeframe} K线: {kline_count}个")
        
        print(f"\n✅ 单周期预热完成！")
        print(f"  📊 {self.timeframe}周期: {kline_count}个K线")
        
        # 🔴 显示Delta Volume预热结果
        print(f"\n  📊 Delta Volume预热结果:")
        print(f"    历史K线数: {len(self.buy_volume_history)}/{self.delta_volume_period}")
        if len(self.buy_volume_history) > 0:
            total_buy_prewarm = sum(self.buy_volume_history)
            total_sell_prewarm = sum(self.sell_volume_history)
            print(f"    总买入量: {total_buy_prewarm:,.0f}")
            print(f"    总卖出量: {total_sell_prewarm:,.0f}")
            print(f"    当前K线累积成交量: {self.current_kline_volume:,.0f}")
        else:
            print(f"    ⚠️  警告: Delta Volume历史数据为空，请检查预热数据是否包含成交量字段")
        
        # 显示最后一个K线的信息
        if self.timeframe_manager.current_period is not None:
            timeframe_minutes = self.timeframe_manager.get_timeframe_minutes()
            kline_end_time = self.timeframe_manager.current_period + timedelta(minutes=timeframe_minutes-1, seconds=59)
            
            print(f"\n  🔹 最后一个周期:")
            print(f"     ⏰ 时间: {self.timeframe_manager.current_period.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"     📅 周期: {self.timeframe_manager.current_period.strftime('%H:%M')} - {kline_end_time.strftime('%H:%M')}")
            print(f"     📊 开:${self.timeframe_manager.current_open:.2f} 高:${self.timeframe_manager.current_high:.2f} "
                  f"低:${self.timeframe_manager.current_low:.2f} 收:${self.timeframe_manager.current_close:.2f} "
                  f"量:{self.timeframe_manager.current_volume:.2f}")
        
        # 🔴 预热完成，启用交易模式
        self.is_warmup_mode = False
        print(f"\n🔄 预热完成，启用交易模式...")
        print(f"   当前趋势方向: {self.current_trend_direction}")
        print(f"   当前持仓状态: {self.position} (预热期间未进行交易)")
        print(f"\n📊 单周期SAR策略已准备好，当前趋势={self.current_trend_direction}，等待开仓机会！")
    
    def _update_fixed_delta_volume(self, timestamp=None, current_price=None):
        """
        每1分钟更新固定周期Delta Volume计算
        
        计算逻辑：
        - Delta Volume周期 = delta_volume_period（例如14个周期）
        - 取前(N-1)个完整周期K线的成交量（例如前13个完整15m K线）
        - 加上当前第N个周期K线内按分钟实时分类的买卖量（未完成周期）
        - 公式：Delta% = (买入总量 - 卖出总量) / 平均成交量 × 100
        - 当第N个周期K线完成后，该K线的成交量会按整个周期K线涨跌保存到历史中
        
        注意：
        - timestamp参数是显示时间（当前实际时间，例如14:58的数据显示为14:59）
        - 已完成的周期K线：按整个周期K线涨跌判断（收盘>开盘=买入，收盘<开盘=卖出）
        - 当前未完成的周期K线：按每分钟的1分钟K线涨跌实时分类
        """
        # 🔴 明显的打印：每次调用都打印，方便观察
        # 预热期间简化日志，正式交易期间详细日志
        time_str = timestamp.strftime('%H:%M:%S') if timestamp else 'N/A'
        if not self.is_warmup_mode:
            # 正式交易模式：详细日志
            print(f"\n{'='*60}")
            print(f"📊 【Delta Volume计算】开始 - 时间: {time_str}")
            print(f"{'='*60}")
        # 预热模式：不打印分隔线，减少日志输出
        
        # 1. 计算前(N-1)个完整周期K线的买卖量（固定值）
        if len(self.buy_volume_history) > 0:
            # 取前N-1个完整K线（例如：14个周期 = 前13个完整K线 + 当前第14个K线）
            history_count = min(self.delta_volume_period - 1, 
                              len(self.buy_volume_history))
            # 取最后N-1个（即最新的N-1个完整周期）
            total_buy_history = sum(self.buy_volume_history[-history_count:])
            total_sell_history = sum(self.sell_volume_history[-history_count:])
        else:
            total_buy_history = 0
            total_sell_history = 0
            history_count = 0
        
        # 2. 当前第N个周期K线内按分钟实时分类的买卖量（未完成周期使用）
        # 注意：当前周期未完成时，使用按分钟分类的买卖量；周期完成后会按整个周期K线涨跌保存到历史
        
        # 3. 计算总买卖量：历史(N-1)个完整周期（固定） + 当前周期内按分钟分类的买卖量（实时）
        total_buy = total_buy_history + self.current_period_buy_volume
        total_sell = total_sell_history + self.current_period_sell_volume
        
        # 计算Delta Volume
        avg_volume = (total_buy + total_sell) / 2
        if avg_volume > 0:
            self.delta_volume_fixed = total_buy - total_sell
            self.delta_volume_percent_fixed = (total_buy - total_sell) / avg_volume * 100
        else:
            self.delta_volume_fixed = 0
            self.delta_volume_percent_fixed = 0
        
        # 🔴 打印计算结果（预热期间简化，正式交易期间详细）
        if self.is_warmup_mode:
            # 预热模式：只打印关键信息
            print(f"📊 【预热-Delta Volume】时间: {time_str} | Delta%: {self.delta_volume_percent_fixed:+.2f}% | 历史K线: {len(self.buy_volume_history)}/{self.delta_volume_period}")
        else:
            # 正式交易模式：详细日志
            print(f"📊 【Delta Volume计算结果】")
            print(f"   Delta%: {self.delta_volume_percent_fixed:+.2f}%")
            print(f"   Delta值: {self.delta_volume_fixed:,.0f}")
            
            # 🔴 区分显示历史成交量和当前周期按分钟分类的买卖量
            print(f"   📊 历史成交量（固定，前{history_count}个完整周期K线）:")
            print(f"      - 历史买入量: {total_buy_history:,.0f}")
            print(f"      - 历史卖出量: {total_sell_history:,.0f}")
            print(f"      - 历史总成交量: {total_buy_history + total_sell_history:,.0f}")
            
            if self.current_kline_volume > 0:
                print(f"   📊 当前周期（未完成，按分钟实时分类）:")
                print(f"      - 当前周期总成交量: {self.current_kline_volume:,.0f} (累积中)")
                print(f"      - 按分钟分类买入量: {self.current_period_buy_volume:,.0f} (上涨1分钟K线的成交量)")
                print(f"      - 按分钟分类卖出量: {self.current_period_sell_volume:,.0f} (下跌1分钟K线的成交量)")
            
            print(f"   📊 合计（用于Delta计算）:")
            print(f"      - 总买入量: {total_buy:,.0f} (历史{total_buy_history:,.0f} + 当前周期{self.current_period_buy_volume:,.0f})")
            print(f"      - 总卖出量: {total_sell:,.0f} (历史{total_sell_history:,.0f} + 当前周期{self.current_period_sell_volume:,.0f})")
            print(f"      - 平均成交量: {avg_volume:,.0f}")
            print(f"   历史K线数: {len(self.buy_volume_history)}/{self.delta_volume_period}")
            print(f"   持仓状态: {self.position if self.position else '无持仓'}")
            price_str = f"${current_price:.2f}" if current_price is not None else "N/A"
            print(f"   当前价格: {price_str}")
        
        # 🔴 推送Delta Volume更新（每分钟都推送，只要有钉钉推送器和时间戳，且不在预热模式）
        # 即使没有成交量数据也推送，可以告诉用户当前状态
        
        # 🔴 预热模式不推送，正式交易模式才推送
        if self.is_warmup_mode:
            # 预热模式：不推送，不打印推送状态（减少日志）
            pass
        elif self.dingtalk_notifier and timestamp is not None:
            # 🔴 推送状态检查（只在正式交易模式）
            print(f"\n📤 【Delta Volume推送状态检查】")
            print(f"   钉钉推送器: ✅ 已初始化")
            print(f"   时间戳: ✅ 有效")
            try:
                print(f"\n📤 【Delta Volume推送】开始推送钉钉消息...")
                result = self.dingtalk_notifier.send_delta_volume_update(
                    timestamp=timestamp,
                    delta_volume_percent=self.delta_volume_percent_fixed,
                    delta_volume_period=self.delta_volume_period,
                    stop_loss_threshold=self.delta_volume_stop_loss_threshold,
                    position=self.position,
                    current_price=current_price,
                    total_buy_volume=total_buy,
                    total_sell_volume=total_sell,
                    current_kline_volume=self.current_kline_volume,
                    history_count=len(self.buy_volume_history)
                )
                # 检查推送结果
                if result and isinstance(result, dict) and result.get('errcode') == 0:
                    print(f"✅ 【Delta Volume推送】✅✅✅ 推送成功！✅✅✅ (errcode=0)")
                elif result is None:
                    print(f"⚠️  【Delta Volume推送】❌ 推送返回None，可能失败")
                else:
                    errcode = result.get('errcode', 'unknown') if isinstance(result, dict) else 'unknown'
                    errmsg = result.get('errmsg', '未知错误') if isinstance(result, dict) else '未知错误'
                    print(f"⚠️  【Delta Volume推送】❌ 推送可能失败: errcode={errcode}, errmsg={errmsg}")
            except Exception as e:
                print(f"❌ 【Delta Volume推送】❌❌❌ 推送异常: {e}")
                import traceback
                traceback.print_exc()
        elif timestamp is None:
            print(f"⚠️  【Delta Volume推送】❌ 跳过推送: timestamp为None")
        elif not self.dingtalk_notifier:
            print(f"⚠️  【Delta Volume推送】❌ 跳过推送: 钉钉推送器未初始化")
        
        # 只在正式交易模式打印结束分隔线
        if not self.is_warmup_mode:
            print(f"{'='*60}\n")
        
    def update(self, timestamp, open_price, high_price, low_price, close_price, volume=0, silent=False):
        """处理1分钟K线数据 - 单周期模式"""
        # 🔴 调试：打印第一条数据的接收情况
        if not hasattr(self, '_first_update_logged'):
            self._first_update_logged = True
            print(f"\n🔔 【策略更新】收到第一条数据:")
            print(f"    时间: {timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else 'None'}")
            print(f"    价格: ${close_price:.2f}")
            print(f"    成交量: {volume:,.0f}")
            print(f"    钉钉推送器状态: {'✅ 已初始化' if self.dingtalk_notifier else '❌ 未初始化'}")
        
        signal_info = {
            'timestamp': timestamp,
            'timeframe': self.timeframe,
            'new_kline': False,
            'signals': [],
            'position': self.position,
            'sar_value': None
        }
        
        # 1. 更新波动率计算器（每个1分钟数据都更新，因为它是6小时周期）
        self.volatility_calculator.update(timestamp, close_price)
        
        # 1.5. 更新EMA计算器（每个1分钟数据都更新，因为它是1小时周期）
        self.ema_calculator.update(timestamp, close_price)
        
        # 1.6. 更新ATR计算器累积数据（每分钟数据都记录，但不计算）
        self.atr_calculator.update_accumulate(close_price, high_price, low_price)
        
        # 🔴 1.7. 每1分钟根据涨跌实时分类成交量（用于固定周期Delta Volume）
        # 逻辑：当前周期未完成时，按每分钟的1分钟K线涨跌实时分类
        #       - 上涨（收盘>开盘）：成交量计入买入量
        #       - 下跌（收盘<开盘）：成交量计入卖出量
        #       - 十字星（收盘=开盘）：不计入买卖量
        if volume > 0:
            self.current_kline_volume += volume
            # 当前周期未完成时，按1分钟K线涨跌实时分类
            if close_price > open_price:
                # 上涨：计入买入量
                self.current_period_buy_volume += volume
            elif close_price < open_price:
                # 下跌：计入卖出量
                self.current_period_sell_volume += volume
            # 如果收盘=开盘（十字星），不计入买卖量（保持原值）
        
        # 2. 更新单时间周期聚合数据（SAR的4小时周期）
        # 🔴 注意：先更新K线数据，如果生成新K线，会保存上一周期到历史
        # 这样计算Delta Volume时可以使用最新的历史数据
        new_kline = self.timeframe_manager.update_kline_data(
            timestamp, open_price, high_price, low_price, close_price, volume
        )
        
        # 更新signal_info
        signal_info['new_kline'] = new_kline is not None
        
        sar_result = None
        
        # 🔴 1.8. 每1分钟计算固定周期Delta Volume（并推送钉钉消息）
        # 注意：在新K线生成之后计算，这样可以使用最新的历史数据
        # 时间戳加1分钟显示当前实际时间（例如14:58:00的数据显示为14:59:00）
        display_timestamp = timestamp + timedelta(minutes=1) if timestamp else None
        print(f"\n🔄 【策略Update】正在调用 Delta Volume 计算... (显示时间: {display_timestamp.strftime('%H:%M:%S') if display_timestamp else 'N/A'})")
        self._update_fixed_delta_volume(timestamp=display_timestamp, current_price=close_price)
        
        # 3. 更新SAR指标（当新K线生成时）
        if new_kline is not None:
            
            timeframe_minutes = self.timeframe_manager.get_timeframe_minutes()
            kline_end_time = new_kline['timestamp'] + timedelta(minutes=timeframe_minutes-1, seconds=59)
            indicator_available_time = new_kline['timestamp'] + timedelta(minutes=timeframe_minutes)
            
            print(f"[{self.timeframe}] 新K线生成: {new_kline['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"      📅 周期: {new_kline['timestamp'].strftime('%H:%M')} - {kline_end_time.strftime('%H:%M')}")
            print(f"      📊 开:${new_kline['open']:.2f} 高:${new_kline['high']:.2f} "
                  f"低:${new_kline['low']:.2f} 收:${new_kline['close']:.2f} 量:{new_kline.get('volume', 0):.2f}")
            
            # 🔴 3.0. 在新K线生成时，保存上一根完整周期K线的成交量（按整个周期K线涨跌分类）
            # 逻辑：已完成的周期K线，按整个周期K线的涨跌判断（收盘>开盘=买入，收盘<开盘=卖出）
            # 注意：在update_kline_data返回new_kline时，current_kline_volume还没有被重置（重置在下一行）
            prev_volume = self.current_kline_volume if self.current_kline_volume > 0 else new_kline.get('volume', 0)
            if prev_volume > 0:
                # 从new_kline中获取上一根完整周期K线的数据（new_kline就是刚保存的上一根K线）
                prev_open = new_kline['open']
                prev_close = new_kline['close']
                
                # 按整个周期K线的涨跌判断（不是按分钟分类）
                if prev_close > prev_open:
                    # 阳线：整个周期K线的总成交量归为买入量
                    self.buy_volume_history.append(prev_volume)
                    self.sell_volume_history.append(0)
                    kline_type = "阳线(买入)"
                elif prev_close < prev_open:
                    # 阴线：整个周期K线的总成交量归为卖出量
                    self.buy_volume_history.append(0)
                    self.sell_volume_history.append(prev_volume)
                    kline_type = "阴线(卖出)"
                else:
                    # 十字星：不计入买卖量
                    self.buy_volume_history.append(0)
                    self.sell_volume_history.append(0)
                    kline_type = "十字星(不计)"
                
                # 只保留最近N个周期
                if len(self.buy_volume_history) > self.delta_volume_period:
                    self.buy_volume_history = self.buy_volume_history[-self.delta_volume_period:]
                    self.sell_volume_history = self.sell_volume_history[-self.delta_volume_period:]
                
                print(f"    📊 【Delta Volume】周期K线完成，保存: {kline_type} Open={prev_open:.2f}, Close={prev_close:.2f}, Vol={prev_volume:,.0f} | 历史长度={len(self.buy_volume_history)}")
            
            # 重置当前周期K线累积和分类（开始新的聚合周期）
            self.current_kline_volume = 0
            self.current_period_buy_volume = 0   # 重置当前周期的买入量
            self.current_period_sell_volume = 0  # 重置当前周期的卖出量
            
            # 3.1. 在新K线生成时计算ATR（整个周期结束时）
            self.atr_calculator.update_kline_end(
                new_kline['close'], 
                new_kline['high'], 
                new_kline['low']
            )
            
            sar_result = self.sar_indicator.update(
                new_kline['close'], 
                new_kline['high'], 
                new_kline['low']
            )
            signal_info['sar_value'] = sar_result['sar_value']
            
            print(f"  📊 {self.timeframe} SAR: {sar_result['sar_value']:.2f} | 方向: {'上升' if sar_result['sar_rising'] else '下降'}")
            print(f"  📊 {self.timeframe} RSI: {sar_result['rsi']:.2f} (周期{self.sar_indicator.rsi_period})")
            print(f"  📊 {self.timeframe} Delta Volume: {self.delta_volume_percent_fixed:+.2f}% (周期{self.delta_volume_period}, 止损阈值{self.delta_volume_stop_loss_threshold*100:.0f}%)")
            print(f"  🎯 {self.timeframe}指标可用时间: {indicator_available_time.strftime('%H:%M')} (K线完成后)")
            
            # 3. 检查SAR方向改变（开仓信号或平仓反转信号）
            self._check_trend_change(sar_result, open_price, signal_info)
            
            # print(f"  🔍 new_kline: {new_kline}")

            # 4. 更新动态SAR止损（如果有持仓且没有触发方向转换平仓）
            if self.position is not None:
                self._update_sar_stop_loss(sar_result, signal_info)
            
            # 🔴 5. 推送周期结束时的指标信息（包含持仓情况）
            print(f"  🔍 推送周期结束时的指标信息（包含持仓情况）")
            print(f"  🔍 dingtalk_notifier对象: {self.dingtalk_notifier}")
            if self.dingtalk_notifier:
                # 🔴 传递策略逻辑层面的持仓信息（已添加说明区分真实持仓）
                position_info = None
                if self.position is not None:
                    position_info = {
                        'position': self.position,
                        'entry_price': self.entry_price,
                        'current_price': open_price,  # 使用当前K线的开盘价作为当前价格
                        'stop_loss_level': self.stop_loss_level,
                        'take_profit_level': self.take_profit_level
                    }
                
                # 🔴 获取ATR波动率信息
                atr_info = self.atr_calculator.get_atr_volatility_ratio()
                
                # 🔴 在sar_result中添加当前价格信息（用于风险收益比计算）
                sar_result_with_price = sar_result.copy()
                sar_result_with_price['current_price'] = close_price  # 使用收盘价作为当前价格
                
                print(f"  🔍 准备发送指标更新消息...")
                result = self.dingtalk_notifier.send_indicator_update(
                    timestamp=new_kline['timestamp'],
                    timeframe=self.timeframe,
                    sar_result=sar_result_with_price,
                    position_info=position_info,
                    atr_info=atr_info
                )
                print(f"  🔍 指标更新消息发送结果: {result}")
            else:
                print(f"  ❌ dingtalk_notifier为None，跳过推送")
        
        # 5. 基于1分钟K线检查平仓触发
        self._check_stop_position_trigger_1min(timestamp, open_price, high_price, low_price, close_price, signal_info)
        
        # 🔴 将sar_result和kline_timestamp添加到signal_info中，供数据库保存使用
        if sar_result is not None:
            signal_info['sar_result'] = sar_result
        
        # 🔴 添加周期K线的时间戳（用于数据库保存）
        if new_kline is not None:
            signal_info['kline_timestamp'] = new_kline['timestamp']
        
        return signal_info
    
    def _calculate_optimal_stop_loss(self, sar_stop_loss, entry_price, position):
        """
        计算最优止损价格（对比SAR止损和最大止损，选择距离开仓价更近的）
        
        Args:
            sar_stop_loss: float SAR止损价格
            entry_price: float 开仓价格
            position: str 'long' 或 'short'
            
        Returns:
            tuple: (最优止损价格, 使用的止损类型描述)
        """
        if sar_stop_loss is None:
            return None, None
        
        # 如果没有配置最大止损，直接使用SAR止损
        if self.max_stop_loss_pct <= 0:
            return sar_stop_loss, 'SAR止损'
        
        # 计算最大止损价格
        if position == 'long':
            # 多单：最大止损在开仓价下方
            max_stop_loss = entry_price * (1 - self.max_stop_loss_pct / 100)
            # 选择更高的止损（更接近开仓价，更宽松）
            if max_stop_loss > sar_stop_loss:
                return max_stop_loss, f'最大止损({self.max_stop_loss_pct}%)'
            else:
                return sar_stop_loss, 'SAR止损'
        else:  # short
            # 空单：最大止损在开仓价上方
            max_stop_loss = entry_price * (1 + self.max_stop_loss_pct / 100)
            # 选择更低的止损（更接近开仓价，更宽松）
            if max_stop_loss < sar_stop_loss:
                return max_stop_loss, f'最大止损({self.max_stop_loss_pct}%)'
            else:
                return sar_stop_loss, 'SAR止损'
    
    def _check_trend_change(self, sar_result, open_price, signal_info):
        """检查SAR方向改变，触发平仓反转信号"""
        # 🔴 预热期间跳过交易，只更新指标
        if self.is_warmup_mode:
            # 更新趋势方向（但不进行交易）
            self.previous_trend_direction = self.current_trend_direction
            if sar_result['sar_rising']:
                self.current_trend_direction = 'long'
            elif sar_result['sar_falling']:
                self.current_trend_direction = 'short'
            else:
                self.current_trend_direction = None
            return
        
        # 更新趋势方向
        self.previous_trend_direction = self.current_trend_direction
        
        # 获取当前方向
        if sar_result['sar_rising']:
            current_direction = 'long'
        elif sar_result['sar_falling']:
            current_direction = 'short'
        else:
            current_direction = None
        
        print(f"  🔍 SAR趋势: {self.previous_trend_direction} → {current_direction}")
        
        # 检查是否发生方向改变
        direction_changed = (self.previous_trend_direction != current_direction)
        
        print(f"  🔍 方向是否改变: {direction_changed}")
        print(f"  🔍 当前持仓: {self.position}")
        print(f"  🔍 current_direction is not None: {current_direction is not None}")
        
        # 更新当前方向
        self.current_trend_direction = current_direction
        
        if current_direction is not None:
            print(f"  🔍 进入current_direction分支")
            if direction_changed:
                print(f"  🔍 进入direction_changed分支")
                if self.position is not None:
                    # 🔄 有持仓且方向改变：使用K线收盘价立即平仓并标记反向开仓
                    print(f"  🔄 【SAR方向转换】持仓{self.position} → 收盘价${open_price:.2f}平仓并准备反向开仓{current_direction}")
                
                    # 使用K线收盘价立即平仓
                    close_reason = f"SAR方向转换平仓 | 条件：{self.previous_trend_direction}→{current_direction} | 价格来源：{self.timeframe}K线开盘价${open_price:.2f}"
                    self._close_position(open_price, signal_info, signal_info['timestamp'], True, close_reason)
                
                    # 方向改变,平仓后，立即开仓
                    self._execute_entry(current_direction, open_price, signal_info)
                
                else:
                    # 🎯 无持仓且方向改变：使用K线收盘价直接开仓
                    print(f"  🔍 进入无持仓分支")
                    print(f"  🔍 开仓条件检查:")
                    print(f"       📊 SAR方向改变: {direction_changed}")
                    print(f"       💼 无持仓状态: True")
                
                    self._execute_entry(current_direction, open_price, signal_info)
            else: # 这里注释掉后，就是一个方向只开一个仓位（回测不开仓效果还好一些）
                print(f"  🔍 进入else分支（方向未改变）")
                print(f"  🔍 self.position is None: {self.position is None}")
                
                # 🔴 修复：如果已有持仓且方向相同，不生成重复的开仓信号
                if self.position is not None and self.position == current_direction:
                    print(f"  ✅ 已有{current_direction}持仓，跳过重复开仓信号")
                    return
                
                # 🔴 修改：不依赖本地持仓状态，让实盘交易脚本处理持仓检查
                # 策略只负责生成信号，实盘脚本负责检查OKX实际持仓
                print(f"  🔍 生成开仓信号（由实盘脚本检查OKX实际持仓）")
                print(f"  🔍 开仓条件检查:")
                print(f"       📊 SAR方向未改变但符合开仓条件: {not direction_changed}")
                print(f"       💼 持仓检查: 由实盘脚本处理")
                
                self._execute_entry(current_direction, open_price, signal_info)

    def _execute_entry(self, direction, entry_price, signal_info):
        """执行开仓"""
        # 检查是否已预热完成
        if not self.sar_indicator.is_warmed_up:
            print(f"  ⚠️  【预热未完成】指标预热中，跳过开仓")
            return
            
        potential_invested_amount = self._get_invested_capital()
        # if potential_invested_amount <= 0:
        #     print(f"  ⚠️  【资金不足】无法开仓：现金余额=${self.cash_balance:,.2f} <= 0")
        #     return
        
        # 获取波动率相关值
        current_ratio = self.volatility_calculator.get_volatility_ratio_vs_ema()
        current_volatility_ratio = self.volatility_calculator.get_volatility_ratio()
        
        # 检查波动率过滤（使用缓存值，避免重复计算）
        # if not self.volatility_calculator.is_volatility_sufficient(self.volatility_threshold) and not current_volatility_ratio:
        #     isOpen = False

        #     # 检查是否大于volatility_threshold
        #     if current_ratio > self.volatility_threshold:
        #         isOpen = True
            
        #     # 检查是否大于0.05
        #     if current_volatility_ratio > 0.05:
        #         isOpen = True
            
        #     # 检查是否开仓
        #     if not isOpen:
        #         print(f"  ❌ 【波动率过滤】波动率不足: {current_ratio:.2f}倍 < {self.volatility_threshold}倍，{current_volatility_ratio:.4f}倍 < 0.05倍")
        #         return
        
        # 检查中轨变化率过滤
        # if not self.volatility_calculator.is_basis_change_sufficient(self.basis_change_threshold):
        #     current_basis_change = self.volatility_calculator.get_basis_change_rate()
        #     if current_basis_change < self.basis_change_threshold:
        #         print(f"  ❌ 【中轨变化率过滤】变化率不足: {current_basis_change:.2f} < {self.basis_change_threshold}")
        #         return
        
        # 检查RSI过滤
        current_rsi = self.sar_indicator.current_rsi
        print(f"  🔍 当前RSI: {current_rsi:.2f}")
        if direction == 'long' and current_rsi > 75: 
            print(f"  ❌ 【RSI过滤】多单RSI过高: {current_rsi:.2f} > 75")
            return
        elif direction == 'short' and current_rsi < 25:
            print(f"  ❌ 【RSI过滤】空单RSI过低: {current_rsi:.2f} < 25")
            return
        
        # 检查EMA过滤
        ema_info = self.ema_calculator.get_ema_info()
        print(f"  🔍 EMA值: 24={ema_info['ema24']:.2f}, 50={ema_info['ema50']:.2f}, 100={ema_info['ema100']:.2f}")
        print(f"  🔍 EMA前值: 24={ema_info['previous_ema24']:.2f}")
        
        # if direction == 'long':
        #     if not ema_info['is_long_signal']:
        #         print(f"  ❌ 【EMA过滤】多单条件不满足: 24EMA({ema_info['ema24']:.2f}) > 50EMA({ema_info['ema50']:.2f}) > 100EMA({ema_info['ema100']:.2f}) 且 24EMA上升")
        #         return
        # elif direction == 'short':
        #     if not ema_info['is_short_signal']:
        #         print(f"  ❌ 【EMA过滤】空单条件不满足: 24EMA({ema_info['ema24']:.2f}) < 50EMA({ema_info['ema50']:.2f}) < 100EMA({ema_info['ema100']:.2f}) 且 24EMA下降")
        #         return
        
        # 检查ATR波动率过滤
        atr_result = self.atr_calculator.get_atr_volatility_ratio()
        if not atr_result['is_atr_filter_passed']:
            print(f"  ❌ 【ATR过滤】{atr_result['reason']}")
            print(f"        ATR3: {atr_result['atr_3']:.6f} | ATR14: {atr_result['atr_14']:.6f} | 比率: {atr_result['atr_ratio']:.2f}")
            return
        
        # 展示ATR信息
        print(f"  ✅ 【ATR过滤】{atr_result['reason']}")
        print(f"        ATR3: {atr_result['atr_3']:.6f} | ATR14: {atr_result['atr_14']:.6f} | 比率: {atr_result['atr_ratio']:.2f}")
        
        current_basis_change = self.volatility_calculator.get_basis_change_rate()
        volatility_info_str = f" | 波动率过滤：{current_ratio:.2f}倍≥{self.volatility_threshold}倍"
        volatility_ratio_info_str = f" | 波动率比值过滤：{current_volatility_ratio:.4f}倍>0.05倍"
        basis_change_info_str = f" | 中轨变化率过滤：{current_basis_change:.2f}≥{self.basis_change_threshold}"
        ema_info_str = f" | EMA过滤：24({ema_info['ema24']:.2f})>{ema_info['ema50']:.2f}>{ema_info['ema100']:.2f}" if direction == 'long' else f" | EMA过滤：24({ema_info['ema24']:.2f})<{ema_info['ema50']:.2f}<{ema_info['ema100']:.2f}"
        rsi_info_str = f" | RSI过滤：{current_rsi:.2f}{'≤70' if direction == 'long' else '≥30'}"
        
        if direction == 'long':
            reason = f"{self.timeframe}SAR转多开仓 | 条件：SAR方向{self.previous_trend_direction}→{direction}{volatility_info_str}{volatility_ratio_info_str}{basis_change_info_str}{ema_info_str}{rsi_info_str} | 价格来源：{self.timeframe}K线收盘价${entry_price:.2f}"
            self._open_long_position(entry_price, signal_info, reason, potential_invested_amount)
        elif direction == 'short':
            reason = f"{self.timeframe}SAR转空开仓 | 条件：SAR方向{self.previous_trend_direction}→{direction}{volatility_info_str}{volatility_ratio_info_str}{basis_change_info_str}{ema_info_str}{rsi_info_str} | 价格来源：{self.timeframe}K线收盘价${entry_price:.2f}"
            self._open_short_position(entry_price, signal_info, reason, potential_invested_amount)
    
    def _open_long_position(self, entry_price, signal_info, reason, invested_amount):
        """开多单"""
        print(f"\n🔵 ========== 开多单 ==========")
        print(f"🔵 开仓前持仓状态: {self.position}")
        print(f"🔵 开仓价格: ${entry_price:.2f}")
        print(f"🔵 开仓原因: {reason}")
        
        self.position = 'long'
        print(f"🔵 开仓后持仓状态: {self.position}")
        
        # 计算手续费
        transactionFee = invested_amount * 0.02 / 100
        # 实际投入金额（扣除手续费后）
        actual_invested_amount = invested_amount - transactionFee
        
        # 更新现金余额（扣除实际投入金额，不包含手续费）
        self.cash_balance -= actual_invested_amount
        
        # 开仓价格
        self.entry_price = entry_price

        self.current_invested_amount = actual_invested_amount
        
        # 🔴 合约交易：计算合约张数
        # OKX合约张数计算：可用保证金 ÷ 合约面值
        # ETH-USDT-SWAP的合约面值通常是10 USDT（每张合约代表0.01 ETH）
        # 使用杠杆后的实际买入数量 = 投入金额 * 杠杆 / 合约面值
        try:
            from okx_config import TRADING_CONFIG
            leverage = TRADING_CONFIG.get('leverage', 2)
        except:
            leverage = 2  # 默认2倍杠杆
        
        # ETH-USDT-SWAP合约面值：每张合约10 USDT
        contract_face_value = 10  # USDT per contract
        
        # 计算可开合约张数：可用保证金 × 杠杆 ÷ 合约面值
        self.position_shares = round((actual_invested_amount * leverage) / contract_face_value, 1)
        
        print(f"        💰 合约仓位计算: 投入${actual_invested_amount:.2f} × {leverage}倍杠杆 ÷ ${contract_face_value}合约面值 = {self.position_shares:.1f}张合约")
        
        # 🔴 双重止损机制：对比SAR止损和最大止损，选择距离开仓价更近的
        sar_stop_loss = self.sar_indicator.get_stop_loss_level()
        self.stop_loss_level, stop_loss_type = self._calculate_optimal_stop_loss(
            sar_stop_loss, entry_price, 'long'
        )
        
        # 打印止损对比信息
        if self.max_stop_loss_pct > 0:
            max_stop_loss_price = entry_price * (1 - self.max_stop_loss_pct / 100)
            print(f"        🛡️  SAR止损: ${sar_stop_loss:.2f} | 最大止损: ${max_stop_loss_price:.2f} ({self.max_stop_loss_pct}%)")
            print(f"        ✅ 选择止损: ${self.stop_loss_level:.2f} ({stop_loss_type})")
        else:
            print(f"        🛡️  止损: ${self.stop_loss_level:.2f} (SAR止损)")
        
        # 计算固定止盈位
        if self.fixed_take_profit_pct > 0:
            self.take_profit_level = self.entry_price * (1 + self.fixed_take_profit_pct / 100)
        else:
            self.take_profit_level = None
        
        signal_info['signals'].append({
            'type': 'OPEN_LONG',
            'price': self.entry_price,
            'stop_loss': self.stop_loss_level,
            'take_profit': self.take_profit_level,
            'invested_amount': self.current_invested_amount,
            'position_shares': self.position_shares,
            'cash_balance': self.cash_balance,
            'transaction_fee': transactionFee,
            'reason': f"{reason} | 投入${self.current_invested_amount:,.2f} | 止损${self.stop_loss_level:.2f}({stop_loss_type}) | 止盈{f'${self.take_profit_level:.2f}' if self.take_profit_level is not None else '无'}(固定{self.fixed_take_profit_pct}%)"
        })
        
        print(f"  🟢 【开多】{reason} | 价格: ${entry_price:.2f} | 投入: ${actual_invested_amount:,.2f} | 份额: {self.position_shares:.4f}")
        print(f"       止损: ${self.stop_loss_level:.2f} ({stop_loss_type}) | 止盈: {f'${self.take_profit_level:.2f}' if self.take_profit_level else '无'}")
        print(f"        现金更新: 余额=${self.cash_balance:,.2f}")
        
        # 🔴 推送开仓消息
        print(f"  🔍 准备发送开多仓消息，dingtalk_notifier: {self.dingtalk_notifier}")
        if self.dingtalk_notifier:
            position_info = {
                'invested_amount': self.current_invested_amount,
                'position_shares': self.position_shares,
                'stop_loss': self.stop_loss_level,
                'take_profit': self.take_profit_level
            }
            result = self.dingtalk_notifier.send_open_position(
                timestamp=signal_info.get('timestamp'),
                direction='long',
                entry_price=entry_price,
                reason=reason,
                position_info=position_info
            )
            print(f"  🔍 开多仓消息发送结果: {result}")
        else:
            print(f"  ❌ dingtalk_notifier为None，跳过开多仓推送")
    
    def _open_short_position(self, entry_price, signal_info, reason, invested_amount):
        """开空单"""
        print(f"\n🔴 ========== 开空单 ==========")
        print(f"🔴 开仓前持仓状态: {self.position}")
        print(f"🔴 开仓价格: ${entry_price:.2f}")
        print(f"🔴 开仓原因: {reason}")
        
        self.position = 'short'
        print(f"🔴 开仓后持仓状态: {self.position}")
        
        # 计算手续费
        transactionFee = invested_amount * 0.02 / 100
        # 实际投入金额（扣除手续费后）
        actual_invested_amount = invested_amount - transactionFee
        
        # 更新现金余额（扣除实际投入金额，不包含手续费）
        self.cash_balance -= actual_invested_amount
        
        # 开仓价格
        self.entry_price = entry_price

        self.current_invested_amount = actual_invested_amount
        
        # 🔴 合约交易：计算合约张数
        # OKX合约张数计算：可用保证金 ÷ 合约面值
        # ETH-USDT-SWAP的合约面值通常是10 USDT（每张合约代表0.01 ETH）
        # 使用杠杆后的实际买入数量 = 投入金额 * 杠杆 / 合约面值
        try:
            from okx_config import TRADING_CONFIG
            leverage = TRADING_CONFIG.get('leverage', 1)
        except:
            leverage = 1  # 默认2倍杠杆
        
        # ETH-USDT-SWAP合约面值：每张合约10 USDT
        contract_face_value = 10  # USDT per contract
        
        # 计算可开合约张数：可用保证金 × 杠杆 ÷ 合约面值
        self.position_shares = round((actual_invested_amount * leverage) / contract_face_value, 1)
        
        print(f"        💰 合约仓位计算: 投入${actual_invested_amount:.2f} × {leverage}倍杠杆 ÷ ${contract_face_value}合约面值 = {self.position_shares:.1f}张合约")
        
        # 🔴 双重止损机制：对比SAR止损和最大止损，选择距离开仓价更近的
        sar_stop_loss = self.sar_indicator.get_stop_loss_level()
        self.stop_loss_level, stop_loss_type = self._calculate_optimal_stop_loss(
            sar_stop_loss, entry_price, 'short'
        )
        
        # 打印止损对比信息
        if self.max_stop_loss_pct > 0:
            max_stop_loss_price = entry_price * (1 + self.max_stop_loss_pct / 100)
            print(f"        🛡️  SAR止损: ${sar_stop_loss:.2f} | 最大止损: ${max_stop_loss_price:.2f} ({self.max_stop_loss_pct}%)")
            print(f"        ✅ 选择止损: ${self.stop_loss_level:.2f} ({stop_loss_type})")
        else:
            print(f"        🛡️  止损: ${self.stop_loss_level:.2f} (SAR止损)")
        
        # 计算固定止盈位
        if self.fixed_take_profit_pct > 0:
            self.take_profit_level = self.entry_price * (1 - self.fixed_take_profit_pct / 100)
        else:
            self.take_profit_level = None
        
        signal_info['signals'].append({
            'type': 'OPEN_SHORT',
            'price': self.entry_price,
            'stop_loss': self.stop_loss_level,
            'take_profit': self.take_profit_level,
            'invested_amount': self.current_invested_amount,
            'position_shares': self.position_shares,
            'cash_balance': self.cash_balance,
            'transaction_fee': transactionFee,
            'reason': f"{reason} | 投入${self.current_invested_amount:,.2f} | 止损${self.stop_loss_level:.2f}({stop_loss_type}) | 止盈{f'${self.take_profit_level:.2f}' if self.take_profit_level is not None else '无'}(固定{self.fixed_take_profit_pct}%)"
        })
        
        print(f"  🔴 【开空】{reason} | 价格: ${entry_price:.2f} | 投入: ${actual_invested_amount:,.2f} | 份额: {self.position_shares:.4f}")
        print(f"       止损: ${self.stop_loss_level:.2f} ({stop_loss_type}) | 止盈: {f'${self.take_profit_level:.2f}' if self.take_profit_level else '无'}")
        print(f"        现金更新: 余额=${self.cash_balance:,.2f}")
        
        # 🔴 推送开仓消息
        print(f"  🔍 准备发送开空仓消息，dingtalk_notifier: {self.dingtalk_notifier}")
        if self.dingtalk_notifier:
            position_info = {
                'invested_amount': self.current_invested_amount,
                'position_shares': self.position_shares,
                'stop_loss': self.stop_loss_level,
                'take_profit': self.take_profit_level
            }
            result = self.dingtalk_notifier.send_open_position(
                timestamp=signal_info.get('timestamp'),
                direction='short',
                entry_price=entry_price,
                reason=reason,
                position_info=position_info
            )
            print(f"  🔍 开空仓消息发送结果: {result}")
        else:
            print(f"  ❌ dingtalk_notifier为None，跳过开空仓推送")
    
    def _update_sar_stop_loss(self, sar_result, signal_info):
        """更新动态SAR止损（双重止损机制：对比SAR止损和最大止损，选择距离开仓价更近的）"""
        if self.position is None or self.entry_price is None:
            return
        
        new_sar_value = sar_result['sar_value']
        old_stop_loss = self.stop_loss_level
        
        # 🔴 使用双重止损机制：对比SAR止损和最大止损，选择更近的
        optimal_stop_loss, stop_loss_type = self._calculate_optimal_stop_loss(
            new_sar_value, self.entry_price, self.position
        )
        
        # 检查止损是否需要更新（只允许向有利方向移动）
        if self.position == 'long':
            # 多单：止损只能向上移动（更有利，更接近开仓价）
            if optimal_stop_loss > old_stop_loss:
                self.stop_loss_level = optimal_stop_loss
                print(f"    🔄 【动态止损更新】多单止损: ${old_stop_loss:.2f} → ${optimal_stop_loss:.2f} ({stop_loss_type})")
                
                # 🔴 打印止损对比信息
                if self.max_stop_loss_pct > 0:
                    max_stop_loss_price = self.entry_price * (1 - self.max_stop_loss_pct / 100)
                    print(f"         🛡️  SAR止损: ${new_sar_value:.2f} | 最大止损: ${max_stop_loss_price:.2f} ({self.max_stop_loss_pct}%) | 选择: ${optimal_stop_loss:.2f}")
                
                # 🔴 生成止损更新信号，通知实盘交易脚本调用OKX接口
                signal_info['signals'].append({
                    'type': 'UPDATE_STOP_LOSS',
                    'new_stop_loss': optimal_stop_loss,
                    'old_stop_loss': old_stop_loss,
                    'position': self.position,
                    'reason': f"多单双重止损更新 | 旧止损${old_stop_loss:.2f} → 新止损${optimal_stop_loss:.2f} ({stop_loss_type})"
                })
                
        elif self.position == 'short':
            # 空单：止损只能向下移动（更有利，更接近开仓价）
            if optimal_stop_loss < old_stop_loss:
                self.stop_loss_level = optimal_stop_loss
                print(f"    🔄 【动态止损更新】空单止损: ${old_stop_loss:.2f} → ${optimal_stop_loss:.2f} ({stop_loss_type})")
                
                # 🔴 打印止损对比信息
                if self.max_stop_loss_pct > 0:
                    max_stop_loss_price = self.entry_price * (1 + self.max_stop_loss_pct / 100)
                    print(f"         🛡️  SAR止损: ${new_sar_value:.2f} | 最大止损: ${max_stop_loss_price:.2f} ({self.max_stop_loss_pct}%) | 选择: ${optimal_stop_loss:.2f}")
                
                # 🔴 生成止损更新信号，通知实盘交易脚本调用OKX接口
                signal_info['signals'].append({
                    'type': 'UPDATE_STOP_LOSS',
                    'new_stop_loss': optimal_stop_loss,
                    'old_stop_loss': old_stop_loss,
                    'position': self.position,
                    'reason': f"空单双重止损更新 | 旧止损${old_stop_loss:.2f} → 新止损${optimal_stop_loss:.2f} ({stop_loss_type})"
                })
    
    def _check_stop_position_trigger_1min(self, timestamp, open_price, high_price, low_price, close_price, signal_info):
        """基于1分钟K线检查平仓触发"""
        if self.position is None or self.stop_loss_level is None:
            return
            
        stop_loss_triggered = False
        
        # 🔴 优先检查Delta Volume止损（市场情绪强烈反转）
        current_dv_percent = self.delta_volume_percent_fixed / 100.0  # 转换为小数（例如60% = 0.6）
        
        if self.position == 'long':
            # 持有多单：如果Delta% < -threshold（卖出压力过大），立即止损
            if current_dv_percent < -self.delta_volume_stop_loss_threshold:
                stop_loss_triggered = True
                exit_price = close_price
                reason = f"多单Delta Volume止损 | Delta%={current_dv_percent*100:.2f}% < -{self.delta_volume_stop_loss_threshold*100:.0f}%（卖出压力过大）"
                print(f"  ❌ 【Delta Volume止损】多单：卖出压力{abs(current_dv_percent)*100:.2f}% > {self.delta_volume_stop_loss_threshold*100:.0f}%，触发止损")
                self._close_position(exit_price, signal_info, timestamp, False, reason)
                return  # 已触发止损，直接返回
        
        elif self.position == 'short':
            # 持有空单：如果Delta% > +threshold（买入压力过大），立即止损
            if current_dv_percent > self.delta_volume_stop_loss_threshold:
                stop_loss_triggered = True
                exit_price = close_price
                reason = f"空单Delta Volume止损 | Delta%={current_dv_percent*100:.2f}% > +{self.delta_volume_stop_loss_threshold*100:.0f}%（买入压力过大）"
                print(f"  ❌ 【Delta Volume止损】空单：买入压力{abs(current_dv_percent)*100:.2f}% > {self.delta_volume_stop_loss_threshold*100:.0f}%，触发止损")
                self._close_position(exit_price, signal_info, timestamp, False, reason)
                return  # 已触发止损，直接返回
        
        # 计算硬性保护位（如果设置了max_stop_loss_pct）
        max_stop_loss_hard_level = None
        if self.max_stop_loss_pct > 0 and self.entry_price is not None:
            if self.position == 'long':
                max_stop_loss_hard_level = self.entry_price * (1 - self.max_stop_loss_pct / 100)
            elif self.position == 'short':
                max_stop_loss_hard_level = self.entry_price * (1 + self.max_stop_loss_pct / 100)
        
        # 检查其他平仓触发
        if self.position == 'long':
            # 优先检查固定止盈
            if self.take_profit_level is not None and high_price >= self.take_profit_level:
                stop_loss_triggered = True
                exit_price = self.take_profit_level
                reason = f"多单固定止盈 | 条件：价格${high_price:.2f}≥止盈位${self.take_profit_level:.2f} | 价格来源：1分钟最高价触及固定止盈位"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 检查硬性保护位（最大止损）
            elif max_stop_loss_hard_level is not None and low_price <= max_stop_loss_hard_level:
                stop_loss_triggered = True
                exit_price = max_stop_loss_hard_level
                reason = f"多单硬性保护位触发 | 条件：价格${low_price:.2f}≤硬性保护位${max_stop_loss_hard_level:.2f}({self.max_stop_loss_pct}%) | 价格来源：1分钟最低价触及硬性保护位"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 检查止损（已包含双重止损机制的选择）
            elif low_price <= self.stop_loss_level:
                stop_loss_triggered = True
                exit_price = self.stop_loss_level
                profit_loss = self.position_shares * (exit_price - self.entry_price)
                result_type = "盈利平仓" if profit_loss > 0 else "亏损平仓"
                reason = f"多单止损{result_type} | 条件：价格${low_price:.2f}≤止损位${self.stop_loss_level:.2f} | 价格来源：1分钟最低价触及止损线"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
        
        elif self.position == 'short':
            # 优先检查固定止盈
            if self.take_profit_level is not None and low_price <= self.take_profit_level:
                stop_loss_triggered = True
                exit_price = self.take_profit_level
                reason = f"空单固定止盈 | 条件：价格${low_price:.2f}≤止盈位${self.take_profit_level:.2f} | 价格来源：1分钟最低价触及固定止盈位"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 检查硬性保护位（最大止损）
            elif max_stop_loss_hard_level is not None and high_price >= max_stop_loss_hard_level:
                stop_loss_triggered = True
                exit_price = max_stop_loss_hard_level
                reason = f"空单硬性保护位触发 | 条件：价格${high_price:.2f}≥硬性保护位${max_stop_loss_hard_level:.2f}({self.max_stop_loss_pct}%) | 价格来源：1分钟最高价触及硬性保护位"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 检查止损（已包含双重止损机制的选择）
            elif high_price >= self.stop_loss_level:
                stop_loss_triggered = True
                exit_price = self.stop_loss_level
                profit_loss = self.position_shares * (self.entry_price - exit_price)
                result_type = "盈利平仓" if profit_loss > 0 else "亏损平仓"
                reason = f"空单止损{result_type} | 条件：价格${high_price:.2f}≥止损位${self.stop_loss_level:.2f} | 价格来源：1分钟最高价触及止损线"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
    
    def _close_position(self, exit_price, signal_info, exit_timestamp,isEatOrder, reason):
        """平仓处理"""
        if self.position is None:
            return
            
        # 计算盈亏（使用临时变量计算滑点，不修改原始entry_price）
        if self.position == 'long':
            # 开仓价格加上滑点
            # self.entry_price = self.entry_price * (1 + 0.0002)
            self.entry_price = self.entry_price
            profit_loss = self.position_shares * (exit_price - self.entry_price)
        else:  # short
            # 开仓价格减去滑点
            # self.entry_price = self.entry_price * (1 - 0.0002)
            self.entry_price = self.entry_price
            profit_loss = self.position_shares * (self.entry_price - exit_price)

        # 计算平仓总金额
        transactionAmount = self.current_invested_amount + profit_loss;
        # 手续费
        transactionFee = 0.0
        # 如果平仓是吃单，需要扣除手续费
        if isEatOrder:
            # 吃单手续费为0.02%
            transactionFee = transactionAmount * 0.02 / 100
            # 平仓总金额扣除手续费
            transactionAmount = transactionAmount - transactionFee
        
        # 更新现金余额
        old_balance = self.cash_balance
        self.cash_balance += transactionAmount
        
        # 记录信号
        signal_type = 'STOP_LOSS_LONG' if self.position == 'long' else 'STOP_LOSS_SHORT'
        if '止盈' in reason:
            signal_type = 'TAKE_PROFIT_LONG' if self.position == 'long' else 'TAKE_PROFIT_SHORT'
        
        signal_info['signals'].append({
            'type': signal_type,
            'price': exit_price,
            'profit_loss': profit_loss,
            'invested_amount': transactionAmount,
            'position_shares': self.position_shares,
            'old_balance': old_balance,
            'new_balance': self.cash_balance,
            'transaction_fee': transactionFee,
            'exit_timestamp': exit_timestamp,
            'reason': f"{reason}：价格${exit_price:.2f} | 盈亏${profit_loss:+.2f}"
        })
        
        return_rate = (profit_loss / self.current_invested_amount * 100) if self.current_invested_amount > 0 else 0
        result_type = "盈利" if profit_loss > 0 else "亏损"
        print(f"  {'✅' if profit_loss > 0 else '❌'} 【{reason}】平仓价: ${exit_price:.2f} | {result_type}: ${profit_loss:.2f} | 收益率: {return_rate:+.2f}%")
        
        # 🔴 推送平仓消息
        print(f"  🔍 准备发送平仓消息，dingtalk_notifier: {self.dingtalk_notifier}")
        if self.dingtalk_notifier:
            result = self.dingtalk_notifier.send_close_position(
                timestamp=exit_timestamp,
                position_type=self.position,
                entry_price=self.entry_price,
                exit_price=exit_price,
                profit_loss=profit_loss,
                return_rate=return_rate,
                reason=reason
            )
            print(f"  🔍 平仓消息发送结果: {result}")
        else:
            print(f"  ❌ dingtalk_notifier为None，跳过平仓推送")
        
        # 重置交易状态
        self.position = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None
        self.current_invested_amount = None
        self.position_shares = None
    
    def _get_invested_capital(self):
        """获取投入的资金量"""
        position_size = self.position_size_percentage / 100
        available_capital = max(0, self.cash_balance)
        
        # 如果是全仓，返回所有可用资金
        if position_size >= 1.0:
            print(f"        💰 全仓计算: 现金余额=${self.cash_balance:,.2f} → 投入金额=${available_capital:,.2f}")
            return available_capital
        
        invested = available_capital * position_size
        print(f"        💰 部分仓位计算: 现金余额=${self.cash_balance:,.2f} × {position_size*100}% → 投入金额=${invested:,.2f}")
        return invested
    
    def sync_real_trade_data(self, trade_data):
        """同步真实交易数据到策略内部状态
        
        Args:
            trade_data: dict 包含以下字段：
                - position: 'long' 或 'short' 或 None
                - entry_price: float 开仓价格
                - position_shares: float 持仓数量
                - stop_loss_price: float 止损价格
                - take_profit_price: float 止盈价格
                - invested_amount: float 投入金额
                - timestamp: str 交易时间
        """
        print(f"\n🔄 同步真实交易数据到策略...")
        print(f"   持仓方向: {trade_data.get('position', 'None')}")
        print(f"   开仓价格: ${trade_data.get('entry_price', 0):.2f}")
        print(f"   持仓数量: {trade_data.get('position_shares', 0):.4f}")
        print(f"   止损价格: ${trade_data.get('stop_loss_price', 0):.2f}")
        print(f"   止盈价格: ${trade_data.get('take_profit_price', 0):.2f}")
        print(f"   投入金额: ${trade_data.get('invested_amount', 0):.2f}")
        
        # 同步持仓状态
        self.position = trade_data.get('position')
        self.entry_price = trade_data.get('entry_price', 0)
        self.position_shares = trade_data.get('position_shares', 0)
        self.current_invested_amount = trade_data.get('invested_amount', 0)
        
        # 同步止损止盈价格
        if trade_data.get('stop_loss_price'):
            self.stop_loss_level = trade_data['stop_loss_price']
        
        if trade_data.get('take_profit_price'):
            self.take_profit_level = trade_data['take_profit_price']
        
        # 更新现金余额（扣除投入金额）
        if self.position and trade_data.get('invested_amount'):
            self.cash_balance -= trade_data['invested_amount']
        
        # 更新交易统计
        if self.position:
            self.total_trades += 1
        
        print(f"✅ 策略状态同步完成")
        print(f"   策略持仓: {self.position}")
        print(f"   策略开仓价: ${self.entry_price:.2f}")
        print(f"   策略止损位: ${self.stop_loss_level:.2f}")
        print(f"   策略止盈位: ${self.take_profit_level:.2f}")
    
    def sync_stop_loss_update(self, new_stop_loss_price):
        """同步止损价格更新
        
        Args:
            new_stop_loss_price: float 新的止损价格
        """
        print(f"\n🔄 同步止损价格更新: ${self.stop_loss_level:.2f} → ${new_stop_loss_price:.2f}")
        
        old_stop_loss = self.stop_loss_level
        self.stop_loss_level = new_stop_loss_price
        
        print(f"✅ 止损价格已更新: ${old_stop_loss:.2f} → ${new_stop_loss_price:.2f}")
    
    def sync_position_close(self, close_reason="手动平仓"):
        """同步持仓平仓
        
        Args:
            close_reason: str 平仓原因
        """
        print(f"\n🔄 同步持仓平仓: {close_reason}")
        
        # 清空持仓状态
        self.position = None
        self.entry_price = 0
        self.position_shares = 0
        self.stop_loss_level = None
        self.take_profit_level = None
        self.current_invested_amount = 0
        
        print(f"✅ 持仓状态已清空")

    def get_current_status(self):
        """获取当前单周期策略状态"""
        return {
            'position': self.position,
            'entry_price': self.entry_price if self.entry_price is not None else 0,
            'stop_loss_level': self.stop_loss_level if self.stop_loss_level is not None else 0,
            'take_profit_level': self.take_profit_level if self.take_profit_level is not None else 0,
            'sar_value': self.sar_indicator.get_stop_loss_level(),
            'timeframe': self.timeframe,
            'current_trend_direction': self.current_trend_direction,
            'previous_trend_direction': self.previous_trend_direction,
            'position_shares': self.position_shares if self.position_shares is not None else 0,
            'current_invested_amount': self.current_invested_amount if self.current_invested_amount is not None else 0,
            'max_stop_loss_pct': self.max_stop_loss_pct,
            'volatility_info': self.volatility_calculator.get_volatility_info()
        }