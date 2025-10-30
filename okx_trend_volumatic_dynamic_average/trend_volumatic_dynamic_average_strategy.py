#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import numpy as np
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
    """时间周期管理器 - 处理1分钟数据聚合到指定时间周期（支持成交量）"""
    
    def __init__(self, timeframe='30m'):
        self.timeframe = timeframe
        self.kline_data = []
        self.current_period = None
        self.current_open = None
        self.current_high = None  
        self.current_low = None
        self.current_close = None
        self.current_volume = 0  # 🔴 新增：聚合成交量
        
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
        """更新K线数据（处理1分钟数据聚合，包含成交量）"""
        minutes = self.get_timeframe_minutes()
        period_start = self._calculate_period_start(timestamp, minutes)
        
        if self.current_period is None or period_start != self.current_period:
            # 保存上一个周期的K线数据
            if (self.current_period is not None and self.current_open is not None):
                kline_data = {
                    'timestamp': self.current_period,
                    'open': self.current_open,
                    'high': self.current_high,
                    'low': self.current_low,
                    'close': self.current_close,
                    'volume': self.current_volume  # 🔴 保存聚合成交量
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
            self.current_volume = volume  # 🔴 初始化成交量
            
            return new_kline
        else:
            # 更新当前周期的数据
            if self.current_high is not None:
                self.current_high = max(self.current_high, high_price)
            if self.current_low is not None:
                self.current_low = min(self.current_low, low_price)
            self.current_close = close_price
            self.current_volume += volume  # 🔴 累加成交量
            
            return None

class BollingerMidlineAngleCalculator:
    """
    布林带中轨角度计算器（基于EMA中轨的线性回归角度分析）
    
    用于判断趋势的强度和方向：
    - angle_degrees: 倾斜角度（度）
    - slope_percent: 斜率（每根K线的百分比变化）
    - r_squared: 回归R²（拟合优度，判断趋势质量）
    """
    
    def __init__(self, bb_period=20, window_size=20, 
                 angle_threshold=0.3, r_squared_threshold=0.6,
                 lock_periods=5):
        """
        初始化布林带中轨角度计算器（基于30分钟K线）
        
        Args:
            bb_period: EMA中轨周期（第一层平滑）
                      - 作用：对原始价格进行平滑处理，生成中轨序列
                      - 值越小：中轨对价格变化越敏感（如EMA10更灵活）
                      - 值越大：中轨越平滑，过滤更多噪音（如EMA50更稳定）
                      - 建议范围：10-50
                      
            window_size: 滑动窗口大小（第二层分析，用于角度线性回归）
                        - 作用：取最近N个中轨值计算趋势角度
                        - 值越小：角度反映短期趋势变化（如15根K线 = 7.5小时@30m周期）
                        - 值越大：角度反映长期趋势方向（如50根K线 = 25小时@30m周期）
                        - 建议范围：15-50
                        - 注意：window_size可以与bb_period不同（解耦合设计）
                        
            angle_threshold: 角度阈值（度），超过此值判定为明确趋势
                           - 0.2°: 敏感，捕捉小趋势
                           - 0.3°: 中等（默认）
                           - 0.5°: 严格，只捕捉强趋势
                           
            r_squared_threshold: R²阈值，超过此值判定为趋势而非震荡
                               - 0.5: 宽松，允许一定波动
                               - 0.6: 中等（默认）
                               - 0.75: 严格，只要明确的单边趋势
                               
            lock_periods: 止损后锁定周期数（包含当前周期）
                         - 默认5个周期 = 当前周期 + 4个完整周期
        """
        self.bb_period = bb_period
        self.window_size = window_size
        self.angle_threshold = angle_threshold
        self.r_squared_threshold = r_squared_threshold
        self.lock_period_count = lock_periods
        
        # 存储收盘价历史（用于计算EMA中轨）
        self.close_history = []
        
        # 存储EMA中轨历史
        self.midline_history = []
        self.current_ema_midline = None
        
        # 存储角度计算结果
        self.current_angle = None
        self.current_slope = None
        self.current_r_squared = None
        self.current_trend = None  # '上升', '下降', '震荡'
        
        # 🆕 锁定状态管理（止损后锁定）
        self.is_locked = False  # 是否处于锁定状态
        self.lock_end_time = None  # 锁定结束时间
        self.last_close_reason = None  # 上次平仓原因：'profit' 或 'loss'
        self.can_open_anytime = False  # 是否可以随时开仓（止盈后为True，止损后为False）
        
    def _calculate_ema(self, price, prev_ema, period):
        """计算EMA"""
        if prev_ema is None:
            return price
        alpha = 2.0 / (period + 1)
        return alpha * price + (1 - alpha) * prev_ema
    
    def _calculate_angle_from_midline(self, midline_prices):
        """
        从中轨序列计算角度（基于标准化百分比变化的线性回归）
        
        Args:
            midline_prices: 中轨价格序列（np.ndarray）
            
        Returns:
            angle_degrees, slope_percent, r_squared
        """
        if len(midline_prices) < 2:
            return 0.0, 0.0, 0.0
        
        n = len(midline_prices)
        base_price = float(midline_prices[0])
        
        # 避免除零
        if base_price == 0:
            return 0.0, 0.0, 0.0
        
        # 标准化为百分比变化
        relative_changes = ((midline_prices - base_price) / base_price) * 100.0
        
        # 线性回归
        time_index = np.arange(n)
        A = np.vstack([time_index, np.ones(n)]).T
        
        try:
            slope, intercept = np.linalg.lstsq(A, relative_changes, rcond=None)[0]
        except:
            return 0.0, 0.0, 0.0
        
        # 计算R²（拟合优度）
        y_pred = slope * time_index + intercept
        ss_res = np.sum((relative_changes - y_pred) ** 2)
        ss_tot = np.sum((relative_changes - np.mean(relative_changes)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0
        
        # 转换为角度
        slope_decimal = slope / 100.0
        angle_rad = np.arctan(slope_decimal)
        angle_degrees = np.degrees(angle_rad)
        
        return float(angle_degrees), float(slope), float(r_squared)
    
    def update(self, close_price, high_price=None, low_price=None, is_new_kline=False):
        """
        更新布林带中轨角度计算（只在30分钟K线结束时计算）
        
        Args:
            close_price: 当前收盘价
            high_price: 最高价（保留用于扩展）
            low_price: 最低价（保留用于扩展）
            is_new_kline: 是否是新的30分钟K线生成
            
        Returns:
            dict: 包含angle, slope, r_squared, trend的字典
        """
        # 🔴 只在新K线生成时更新
        if not is_new_kline:
            # 非新K线，返回当前状态
            return {
                'angle': self.current_angle if self.current_angle is not None else 0.0,
                'slope': self.current_slope if self.current_slope is not None else 0.0,
                'r_squared': self.current_r_squared if self.current_r_squared is not None else 0.0,
                'trend': self.current_trend if self.current_trend is not None else '震荡',
                'ema_midline': self.current_ema_midline,
                'is_ready': len(self.midline_history) >= self.window_size,
                'is_locked': self.is_locked
            }
        
        # 🔴 新K线生成，执行计算
        # 添加收盘价到历史
        self.close_history.append(close_price)
        
        # 保持历史长度（需要足够的数据计算滑动窗口）
        max_history = max(self.bb_period * 3, self.window_size * 2)
        if len(self.close_history) > max_history:
            self.close_history = self.close_history[-max_history:]
        
        # 计算EMA中轨
        self.current_ema_midline = self._calculate_ema(
            close_price, self.current_ema_midline, self.bb_period
        )
        self.midline_history.append(self.current_ema_midline)
        
        # 保持中轨历史长度
        if len(self.midline_history) > max_history:
            self.midline_history = self.midline_history[-max_history:]
        
        # 如果中轨历史不足window_size，返回默认值
        if len(self.midline_history) < self.window_size:
            return {
                'angle': 0.0,
                'slope': 0.0,
                'r_squared': 0.0,
                'trend': '震荡',
                'ema_midline': self.current_ema_midline,
                'is_ready': False,
                'is_locked': self.is_locked
            }
        
        # 取最近window_size个中轨值计算角度
        recent_midline = np.array(self.midline_history[-self.window_size:])
        angle, slope, r_squared = self._calculate_angle_from_midline(recent_midline)
        
        # 保存结果
        self.current_angle = angle
        self.current_slope = slope
        self.current_r_squared = r_squared
        
        # 判断趋势
        if r_squared < self.r_squared_threshold:
            self.current_trend = '震荡'  # R²太低，数据分散，判定为震荡
        else:
            if angle > self.angle_threshold:
                self.current_trend = '上升'
            elif angle < -self.angle_threshold:
                self.current_trend = '下降'
            else:
                self.current_trend = '震荡'
        
        return {
            'angle': self.current_angle,
            'slope': self.current_slope,
            'r_squared': self.current_r_squared,
            'trend': self.current_trend,
            'ema_midline': self.current_ema_midline,
            'is_ready': True,
            'is_locked': self.is_locked
        }
    
    def get_entry_signal(self, current_position=None, current_time=None, is_kline_end=False):
        """
        获取独立的开仓信号（满足条件即开仓）
        
        Args:
            current_position: 当前持仓状态（'long', 'short', None）
            current_time: 当前时间（用于检查锁定状态）
            is_kline_end: 是否是K线结束时（整点）
            
        Returns:
            dict: {
                'can_open_long': bool,
                'can_open_short': bool,
                'reason': str,
                'can_check_now': bool  # 🆕 当前是否可以检查开仓
            }
        """
        # 🔴 调试打印：开始计算
        print(f"\n  📐 ========== BB中轨角度信号计算 ==========")
        print(f"  📊 数据状态:")
        print(f"     ├─ 中轨历史长度: {len(self.midline_history)} (需要{self.window_size})")
        print(f"     ├─ 当前持仓: {current_position}")
        print(f"     ├─ 锁定状态: {'🔒 已锁定' if self.is_locked else '🔓 未锁定'}")
        print(f"     ├─ 整点检查: {'是' if is_kline_end else '否'}")
        print(f"     ├─ 随时开仓: {'是' if self.can_open_anytime else '否'}（止盈后=是）")
        midline_str = f"{self.current_ema_midline:.2f}" if self.current_ema_midline is not None else "N/A"
        print(f"     └─ EMA中轨值: {midline_str}")
        
        # 🆕 检查锁定状态（止损后）
        if self.is_locked:
            if current_time is not None and self.lock_end_time is not None:
                if current_time < self.lock_end_time:
                    remaining_minutes = (self.lock_end_time - current_time).total_seconds() / 60
                    print(f"  🔒 【锁定中】解锁时间: {self.lock_end_time.strftime('%H:%M')}")
                    print(f"     剩余时间: {remaining_minutes:.0f}分钟")
                    return {
                        'can_open_long': False,
                        'can_open_short': False,
                        'reason': f'止损锁定中，解锁时间: {self.lock_end_time.strftime("%H:%M")}',
                        'can_check_now': False
                    }
                else:
                    # 解锁（止损锁定期结束）
                    self.is_locked = False
                    self.lock_end_time = None
                    self.can_open_anytime = False  # 止损锁定期结束后，只能整点开仓
                    print(f"  🔓 【解锁】止损锁定期结束，恢复整点开仓检查")
        
        # 🆕 检查是否可以在当前时刻检查开仓
        # 规则1：整点时（is_kline_end=True）永远可以检查
        # 规则2：非整点时，只有止盈后（can_open_anytime=True）才能检查
        if not is_kline_end and not self.can_open_anytime:
            print(f"  ⏰ 【非整点】当前非整点且非止盈后，不检查开仓（等待整点）")
            return {
                'can_open_long': False,
                'can_open_short': False,
                'reason': '非整点且非止盈后，等待整点开仓',
                'can_check_now': False
            }
        
        # 如果指标未就绪，不开仓
        if len(self.midline_history) < self.window_size:
            print(f"  ❌ 指标未就绪：中轨历史不足")
            return {
                'can_open_long': False,
                'can_open_short': False,
                'reason': f'中轨角度指标未就绪（需要{self.window_size}根K线）',
                'can_check_now': True  # 已经通过时机检查，但指标未就绪
            }
        
        # 🔴 打印当前计算结果
        print(f"  📈 计算结果:")
        print(f"     ├─ 角度 (angle): {self.current_angle:.4f}°")
        print(f"     ├─ 斜率 (slope): {self.current_slope:.4f}%/bar")
        print(f"     ├─ R² (拟合度): {self.current_r_squared:.4f}")
        print(f"     └─ 趋势判断: {self.current_trend}")
        
        print(f"  🎯 阈值条件:")
        print(f"     ├─ 角度阈值: {self.angle_threshold}°")
        print(f"     └─ R²阈值: {self.r_squared_threshold}")
        
        # 检查R²是否满足阈值（必须是明确趋势，非震荡）
        if self.current_r_squared < self.r_squared_threshold:
            print(f"  ❌ R²不满足: {self.current_r_squared:.4f} < {self.r_squared_threshold} (震荡市场)")
            return {
                'can_open_long': False,
                'can_open_short': False,
                'reason': f'R²={self.current_r_squared:.3f} < {self.r_squared_threshold}（震荡市场）',
                'can_check_now': True
            }
        
        # 判断开多信号
        can_open_long = (
            self.current_angle > self.angle_threshold and
            self.current_r_squared >= self.r_squared_threshold and
            current_position != 'long'  # 没有持多仓
        )
        
        # 判断开空信号
        can_open_short = (
            self.current_angle < -self.angle_threshold and
            self.current_r_squared >= self.r_squared_threshold and
            current_position != 'short'  # 没有持空仓
        )
        
        # 🔴 详细的条件检查打印
        print(f"  🔍 开多条件检查:")
        print(f"     ├─ 角度 > {self.angle_threshold}°: {self.current_angle:.4f}° > {self.angle_threshold}° = {self.current_angle > self.angle_threshold}")
        print(f"     ├─ R² ≥ {self.r_squared_threshold}: {self.current_r_squared:.4f} ≥ {self.r_squared_threshold} = {self.current_r_squared >= self.r_squared_threshold}")
        print(f"     ├─ 无持多仓: {current_position} != 'long' = {current_position != 'long'}")
        print(f"     └─ 最终结果: {'✅ 可开多' if can_open_long else '❌ 不可开多'}")
        
        print(f"  🔍 开空条件检查:")
        print(f"     ├─ 角度 < -{self.angle_threshold}°: {self.current_angle:.4f}° < -{self.angle_threshold}° = {self.current_angle < -self.angle_threshold}")
        print(f"     ├─ R² ≥ {self.r_squared_threshold}: {self.current_r_squared:.4f} ≥ {self.r_squared_threshold} = {self.current_r_squared >= self.r_squared_threshold}")
        print(f"     ├─ 无持空仓: {current_position} != 'short' = {current_position != 'short'}")
        print(f"     └─ 最终结果: {'✅ 可开空' if can_open_short else '❌ 不可开空'}")
        
        reason = ''
        if can_open_long:
            reason = f'上升趋势：角度={self.current_angle:.2f}° > {self.angle_threshold}°，R²={self.current_r_squared:.3f}'
            print(f"  🟢 【开多信号】{reason}")
        elif can_open_short:
            reason = f'下降趋势：角度={self.current_angle:.2f}° < -{self.angle_threshold}°，R²={self.current_r_squared:.3f}'
            print(f"  🔴 【开空信号】{reason}")
        else:
            reason = f'无信号：角度={self.current_angle:.2f}°，R²={self.current_r_squared:.3f}'
            print(f"  ⚪ 【无信号】{reason}")
        
        print(f"  ==========================================\n")
        
        # 🆕 开仓后清除"随时开仓"标记（只允许一次快速开仓）
        if can_open_long or can_open_short:
            self.can_open_anytime = False  # 开仓后恢复只能整点开仓
        
        return {
            'can_open_long': can_open_long,
            'can_open_short': can_open_short,
            'reason': reason,
            'can_check_now': True
        }
    
    def set_lock_after_stop_loss(self, current_time, timeframe_minutes=30):
        """
        止损后锁定5个周期（包含当前周期，实际等待4个完整周期）
        
        Args:
            current_time: 当前时间（止损发生时间）
            timeframe_minutes: 时间周期（分钟）
            
        示例：
            止损时间：10:25
            当前周期：10:00-10:30（周期1，包含在5个周期内）
            锁定周期：10:30-11:00（周期2），11:00-11:30（周期3），
                     11:30-12:00（周期4），12:00-12:30（周期5）
            解锁时间：12:30
        """
        self.is_locked = True
        self.last_close_reason = 'loss'
        
        # 步骤1：计算当前周期的结束时间（下一个整点）
        current_period_end = self._calculate_next_period_start(current_time, timeframe_minutes)
        
        # 步骤2：从下一个整点开始，再等待4个完整周期
        # 5个周期 - 1个当前周期 = 4个完整周期
        remaining_periods = self.lock_period_count - 1
        self.lock_end_time = current_period_end + timedelta(
            minutes=remaining_periods * timeframe_minutes
        )
        
        # 计算总等待时间（用于显示）
        total_wait_minutes = (self.lock_end_time - current_time).total_seconds() / 60
        
        print(f"  🔒 【止损锁定】锁定{self.lock_period_count}个周期（包含当前周期）")
        print(f"     止损时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"     当前周期结束: {current_period_end.strftime('%H:%M')}")
        print(f"     再等待: {remaining_periods}个完整周期")
        print(f"     解锁时间: {self.lock_end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"     总等待时长: {total_wait_minutes:.0f}分钟")
    
    def unlock_after_take_profit(self):
        """止盈后解锁（下一分钟立即可以开仓）"""
        self.is_locked = False
        self.lock_end_time = None
        self.last_close_reason = 'profit'
        self.can_open_anytime = True  # 🆕 止盈后可以随时开仓（每1分钟检查）
        print(f"  🔓 【止盈解锁】下一分钟立即检查开仓（不等整点）")
    
    def _calculate_next_period_start(self, timestamp, timeframe_minutes):
        """
        计算下一个周期的开始时间（当前周期的结束时间）
        
        Args:
            timestamp: 当前时间
            timeframe_minutes: 时间周期（分钟）
            
        Returns:
            datetime: 下一个周期的开始时间
        """
        if timeframe_minutes == 30:
            # 30分钟：整点和半点
            minute = timestamp.minute
            if minute < 30:
                return timestamp.replace(minute=30, second=0, microsecond=0)
            else:
                # 下一个小时的整点
                return (timestamp + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        elif timeframe_minutes == 60:
            # 1小时：整点
            return (timestamp + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        elif timeframe_minutes == 15:
            # 15分钟：00, 15, 30, 45
            minute = timestamp.minute
            if minute < 15:
                return timestamp.replace(minute=15, second=0, microsecond=0)
            elif minute < 30:
                return timestamp.replace(minute=30, second=0, microsecond=0)
            elif minute < 45:
                return timestamp.replace(minute=45, second=0, microsecond=0)
            else:
                return (timestamp + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        else:
            # 通用计算（向上取整到下一个周期）
            total_minutes = timestamp.hour * 60 + timestamp.minute
            periods_passed = total_minutes // timeframe_minutes
            next_period_start_minutes = (periods_passed + 1) * timeframe_minutes
            next_hour = next_period_start_minutes // 60
            next_minute = next_period_start_minutes % 60
            
            next_time = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            next_time += timedelta(hours=next_hour, minutes=next_minute)
            
            return next_time


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
                    if atr_ratio <= 1.3:
                        print(f"        ✅ ATR波动率: 通过过滤 ({atr_ratio:.4f} ≤ 1.3)")
                    else:
                        print(f"        ❌ ATR波动率: 过高 ({atr_ratio:.4f} > 1.3)")
    
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
    
class VIDYAIndicator:
    """
    VIDYA (Variable Index Dynamic Average) 指标实现
    基于Chande Momentum Oscillator (CMO) 的动态移动平均线
    """
    
    def __init__(self, vidya_length=20, vidya_momentum=9, smooth_length=15, 
                 band_distance=2.0, atr_period=200, pivot_left=3, pivot_right=3,
                 delta_volume_period=14):
        """
        初始化标准VIDYA指标
        
        Args:
            vidya_length: VIDYA基础周期（类似EMA周期）
            vidya_momentum: CMO计算的动量周期
            smooth_length: 最终SMA平滑周期
            band_distance: ATR带宽距离因子
            atr_period: ATR计算周期
            pivot_left: 枢轴点左侧K线数量
            pivot_right: 枢轴点右侧K线数量
            delta_volume_period: 固定周期Delta Volume长度
        """
        self.vidya_length = vidya_length
        self.vidya_momentum = vidya_momentum
        self.smooth_length = smooth_length
        self.band_distance = band_distance
        self.atr_period = atr_period
        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.delta_volume_period = delta_volume_period
        
        # 价格历史数据
        self.close_history = []
        self.high_history = []
        self.low_history = []
        
        # VIDYA值历史
        self.vidya_values = []
        self.current_vidya = None
        
        # 平滑后的VIDYA历史
        self.smoothed_vidya_values = []
        
        # 🔴 VIDYA斜率分析
        self.vidya_slope = 0  # VIDYA斜率（正=向上，负=向下）
        self.vidya_is_rising = False  # VIDYA是否上升
        self.vidya_is_falling = False  # VIDYA是否下降
        
        # 🔴 EMA指标
        self.ema_50_values = []  # EMA50历史值（不平滑）
        self.ema_120_values = []  # EMA120原始历史值
        self.ema_120_smoothed_values = []  # EMA120平滑后的历史值（SMA50平滑）
        self.current_ema_50 = None  # 当前EMA50值（不平滑）
        self.current_ema_120 = None  # 当前EMA120原始值
        self.current_ema_120_smoothed = None  # 当前EMA120平滑值（SMA50平滑）
        
        # 🔴 EMA120斜率分析
        self.ema_120_slope = 0  # EMA120斜率（T1 - T7）
        self.ema_120_is_rising = False  # EMA120是否上升
        self.ema_120_is_falling = False  # EMA120是否下降
        
        # ATR and带宽数据
        self.atr_values = []
        self.current_atr = None
        self.upper_band_values = []
        self.lower_band_values = []
        
        # 成交量相关数据
        self.volume_history = []
        self.buy_volume = 0  # 当前趋势的买入成交量（旧逻辑，保留）
        self.sell_volume = 0  # 当前趋势的卖出成交量（旧逻辑，保留）
        self.delta_volume = 0  # Delta Volume（旧逻辑，保留）
        
        # 🔴 固定周期Delta Volume（新逻辑）
        # delta_volume_period 从参数传入，不再硬编码
        self.buy_volume_history = []   # 每根K线的买入量历史（阳线的成交量）
        self.sell_volume_history = []  # 每根K线的卖出量历史（阴线的成交量）
        self.current_kline_volume = 0        # 当前K线累积的总成交量（每30分钟重置）
        self.delta_volume_fixed = 0          # 固定周期Delta Volume值
        self.delta_volume_percent_fixed = 0  # 固定周期Delta Volume百分比
        
        # 趋势方向
        self.current_trend = None  # 'up', 'down', 'neutral'
        self.previous_trend = None
        
        # 🔴 穿越信号（用于重置成交量）
        self.trend_cross_up = False  # 当前K线是否发生向上穿越
        self.trend_cross_down = False  # 当前K线是否发生向下穿越
        self.prev_trend_cross_up = False  # 上一个K线的向上穿越状态
        self.prev_trend_cross_down = False  # 上一个K线的向下穿越状态
        
        # 枢轴点分析
        self.pivot_highs = []
        self.pivot_lows = []
        self.support_levels = []  # 支撑线
        self.resistance_levels = []  # 阻力线
        
        # 预热状态
        self.is_warmed_up = False
        self.warmup_data_count = 0
        self.required_warmup = max(200, vidya_length * 3, atr_period)
        
    def _calculate_cmo(self, prices, period):
        """
        计算Chande Momentum Oscillator (CMO)
        
        Args:
            prices: 价格序列
            period: 计算周期
            
        Returns:
            float: CMO绝对值 (0-100)
        """
        if len(prices) < period + 1:
            return 0.0
        
        # 计算最近period个周期的价格变化
        changes = []
        for i in range(len(prices) - period, len(prices)):
            if i > 0:
                change = prices[i] - prices[i-1]
                changes.append(change)
        
        if not changes:
            return 0.0
        
        # 分离正向和负向动量
        sum_pos_momentum = sum(max(c, 0) for c in changes)
        sum_neg_momentum = sum(max(-c, 0) for c in changes)
        
        # 避免除零
        total = sum_pos_momentum + sum_neg_momentum
        if total == 0:
            return 0.0
        
        # 计算CMO绝对值
        cmo = abs(100 * (sum_pos_momentum - sum_neg_momentum) / total)
        
        return cmo
    
    def _calculate_vidya(self, price, prev_vidya):
        """
        计算VIDYA值
        
        Args:
            price: 当前价格
            prev_vidya: 前一个VIDYA值
            
        Returns:
            float: 新的VIDYA值
        """
        # 计算CMO
        abs_cmo = self._calculate_cmo(self.close_history, self.vidya_momentum)
        
        # 计算标准EMA的alpha
        alpha = 2.0 / (self.vidya_length + 1)
        
        # 根据CMO调整alpha（核心创新！）
        adjusted_alpha = alpha * (abs_cmo / 100.0)
        
        # 计算VIDYA（类似EMA，但alpha是动态的）
        if prev_vidya is None:
            # 第一次计算，使用当前价格
            vidya = price
        else:
            vidya = adjusted_alpha * price + (1 - adjusted_alpha) * prev_vidya
        
        return vidya, abs_cmo, adjusted_alpha
    
    def _calculate_sma(self, values, period):
        """计算简单移动平均"""
        if len(values) < period:
            return sum(values) / len(values) if values else 0
        return sum(values[-period:]) / period
    
    def _calculate_ema(self, price, prev_ema, period):
        """
        计算EMA（指数移动平均）
        
        Args:
            price: 当前价格
            prev_ema: 前一个EMA值
            period: EMA周期
            
        Returns:
            float: 新的EMA值
        """
        if prev_ema is None:
            # 第一次计算，使用当前价格作为初始值
            return price
        
        # EMA = (Price - Previous EMA) * (2 / (period + 1)) + Previous EMA
        alpha = 2.0 / (period + 1)
        ema = alpha * price + (1 - alpha) * prev_ema
        
        return ema
    
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
        
        # 计算真实波幅TR
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
        
        # 计算ATR
        if len(tr_values) >= period:
            return sum(tr_values[-period:]) / period
        elif len(tr_values) > 0:
            return sum(tr_values) / len(tr_values)
        else:
            return 0.0
    
    def _detect_pivot_points(self, high_prices, low_prices):
        """
        检测枢轴点
        
        Args:
            high_prices: 最高价序列
            low_prices: 最低价序列
            
        Returns:
            tuple: (pivot_high, pivot_low)
        """
        pivot_high = None
        pivot_low = None
        
        if len(high_prices) < self.pivot_left + self.pivot_right + 1:
            return pivot_high, pivot_low
        
        # 检测枢轴高点
        current_idx = len(high_prices) - self.pivot_right - 1
        if current_idx >= self.pivot_left:
            current_high = high_prices[current_idx]
            is_pivot_high = True
            
            # 检查左侧
            for i in range(current_idx - self.pivot_left, current_idx):
                if high_prices[i] >= current_high:
                    is_pivot_high = False
                    break
            
            # 检查右侧
            if is_pivot_high:
                for i in range(current_idx + 1, current_idx + self.pivot_right + 1):
                    if high_prices[i] >= current_high:
                        is_pivot_high = False
                        break
            
            if is_pivot_high:
                pivot_high = current_high
        
        # 检测枢轴低点
        current_low = low_prices[current_idx]
        is_pivot_low = True
        
        # 检查左侧
        for i in range(current_idx - self.pivot_left, current_idx):
            if low_prices[i] <= current_low:
                is_pivot_low = False
                break
        
        # 检查右侧
        if is_pivot_low:
            for i in range(current_idx + 1, current_idx + self.pivot_right + 1):
                if low_prices[i] <= current_low:
                    is_pivot_low = False
                    break
        
        if is_pivot_low:
            pivot_low = current_low
        
        return pivot_high, pivot_low
    
    def _update_support_resistance(self, pivot_high, pivot_low, support_level=None, resistance_level=None):
        """更新支撑阻力线（按照Pine Script逻辑）"""
        # 🔴 存储有效的支撑位（只保留最近3个）
        if support_level is not None:
            self.support_levels.append(support_level)
            if len(self.support_levels) > 3:
                self.support_levels = self.support_levels[-3:]
        
        # 🔴 存储有效的阻力位（只保留最近3个）
        if resistance_level is not None:
            self.resistance_levels.append(resistance_level)
            if len(self.resistance_levels) > 3:
                self.resistance_levels = self.resistance_levels[-3:]
        
        # 保留原有的枢轴点存储（用于其他分析）
        if pivot_high is not None:
            self.pivot_highs.append(pivot_high)
            if len(self.pivot_highs) > 20:
                self.pivot_highs = self.pivot_highs[-20:]
        
        if pivot_low is not None:
            self.pivot_lows.append(pivot_low)
            if len(self.pivot_lows) > 20:
                self.pivot_lows = self.pivot_lows[-20:]
    
    def update(self, close_price, high_price=None, low_price=None, volume=0, is_new_kline=False, open_price=None):
        """
        更新标准VIDYA指标
        
        Args:
            close_price: 收盘价
            high_price: 最高价（必需，用于ATR和枢轴点计算）
            low_price: 最低价（必需，用于ATR和枢轴点计算）
            volume: 成交量（可选，用于成交量压力分析）
            is_new_kline: 是否是新K线（用于固定周期Delta Volume）
            open_price: 开盘价（可选，用于固定周期Delta Volume的开盘价记录）
        """
        self.warmup_data_count += 1
        
        # 🔴 固定周期Delta Volume：当新K线生成时，保存上一根K线的成交量
        if is_new_kline:
            # 保存刚完成的K线（使用传入的open_price和close_price）
            if self.current_kline_volume > 0 and open_price is not None:
                # 🔴 使用传入的聚合K线的开盘价和收盘价判断涨跌
                if close_price > open_price:
                    # 阳线：总成交量归为买入量
                    self.buy_volume_history.append(self.current_kline_volume)
                    self.sell_volume_history.append(0)
                    kline_type = "阳线(买入)"
                elif close_price < open_price:
                    # 阴线：总成交量归为卖出量
                    self.buy_volume_history.append(0)
                    self.sell_volume_history.append(self.current_kline_volume)
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
                
                print(f"    📊 【固定周期DV】K线完成，保存: {kline_type} Open={open_price:.2f}, Close={close_price:.2f}, Vol={self.current_kline_volume:,.0f} | 历史长度={len(self.buy_volume_history)}")
            
            # 重置当前K线累积（开始新的聚合周期）
            self.current_kline_volume = 0
        
        # 存储历史数据
        self.close_history.append(close_price)
        if high_price is not None:
            self.high_history.append(high_price)
        if low_price is not None:
            self.low_history.append(low_price)
        
        # 保持历史长度
        max_history = max(self.vidya_length * 3, self.atr_period)
        if len(self.close_history) > max_history:
            self.close_history = self.close_history[-max_history:]
            self.high_history = self.high_history[-max_history:]
            self.low_history = self.low_history[-max_history:]
        
        # 存储成交量
        if volume > 0:
            self.volume_history.append(volume)
            if len(self.volume_history) > 100:
                self.volume_history = self.volume_history[-100:]
        
        # 计算VIDYA（需要足够的数据）
        if len(self.close_history) >= self.vidya_momentum + 1:
            prev_vidya = self.current_vidya
            self.current_vidya, abs_cmo, adjusted_alpha = self._calculate_vidya(
                close_price, prev_vidya
            )
            self.vidya_values.append(self.current_vidya)
            
            # 保持历史长度
            if len(self.vidya_values) > self.smooth_length * 2:
                self.vidya_values = self.vidya_values[-self.smooth_length * 2:]
            
            # 计算平滑后的VIDYA（二次平滑）
            if len(self.vidya_values) >= self.smooth_length:
                smoothed_vidya = self._calculate_sma(self.vidya_values, self.smooth_length)
                self.smoothed_vidya_values.append(smoothed_vidya)
                
                if len(self.smoothed_vidya_values) > 100:
                    self.smoothed_vidya_values = self.smoothed_vidya_values[-100:]
                
                # 🔴 计算VIDYA斜率（使用最近3-5根K线的变化）
                if len(self.smoothed_vidya_values) >= 5:
                    # 计算线性斜率：(最新值 - 5根K线前的值) / 5
                    self.vidya_slope = (self.smoothed_vidya_values[-1] - self.smoothed_vidya_values[-5]) / 5
                    
                    # 判断趋势倾斜（使用CMO强度作为阈值）
                    slope_threshold = smoothed_vidya * 0.0005  # 0.05%的价格变化
                    self.vidya_is_rising = (self.vidya_slope > slope_threshold and abs_cmo > 20)
                    self.vidya_is_falling = (self.vidya_slope < -slope_threshold and abs_cmo > 20)
            else:
                smoothed_vidya = self.current_vidya
            
            # 计算ATR和带宽（需要足够的高低价数据）
            upper_band = None
            lower_band = None
            current_atr = None
            
            if (len(self.high_history) >= self.atr_period and 
                len(self.low_history) >= self.atr_period):
                
                current_atr = self._calculate_atr(
                    self.high_history, self.low_history, self.close_history, self.atr_period
                )
                self.atr_values.append(current_atr)
                self.current_atr = current_atr
                
                if len(self.atr_values) > 100:
                    self.atr_values = self.atr_values[-100:]
                
                # 计算带宽
                upper_band = smoothed_vidya + (current_atr * self.band_distance)
                lower_band = smoothed_vidya - (current_atr * self.band_distance)
                
                self.upper_band_values.append(upper_band)
                self.lower_band_values.append(lower_band)
                
                if len(self.upper_band_values) > 100:
                    self.upper_band_values = self.upper_band_values[-100:]
                    self.lower_band_values = self.lower_band_values[-100:]
            
            # 🔴 检测枢轴点并应用交易逻辑（基于当前价格）
            pivot_high, pivot_low = None, None
            support_level = None
            resistance_level = None
            
            if (len(self.high_history) >= self.pivot_left + self.pivot_right + 1 and
                len(self.low_history) >= self.pivot_left + self.pivot_right + 1):
                pivot_high, pivot_low = self._detect_pivot_points(
                    self.high_history, self.low_history
                )
                
                # 🔴 新逻辑：基于当前价格判断支撑阻力位
                # 支撑位：当前价格下方的枢轴低点（做多回调时买入）
                # 阻力位：当前价格上方的枢轴高点（做空反弹时卖出）
                
                if pivot_low is not None:
                    # 支撑位：枢轴低点在当前价格下方
                    if pivot_low < close_price:
                        support_level = pivot_low
                        print(f"    📈 检测到支撑位: {support_level:.2f} (枢轴低点 < 当前价格{close_price:.2f})")
                
                if pivot_high is not None:
                    # 阻力位：枢轴高点在当前价格上方
                    if pivot_high > close_price:
                        resistance_level = pivot_high
                        print(f"    📉 检测到阻力位: {resistance_level:.2f} (枢轴高点 > 当前价格{close_price:.2f})")
                
                # 更新支撑阻力历史
                self._update_support_resistance(pivot_high, pivot_low, support_level, resistance_level)
            
            # 🔴 修正：基于穿越逻辑判断趋势方向（符合Pine Script逻辑）
            self.previous_trend = self.current_trend
            
            if upper_band is not None and lower_band is not None:
                # 检查穿越上轨（做多信号）
                if (len(self.close_history) >= 2 and 
                    self.close_history[-2] <= upper_band and 
                    close_price > upper_band):
                    self.current_trend = 'up'
                # 检查穿越下轨（做空信号）
                elif (len(self.close_history) >= 2 and 
                      self.close_history[-2] >= lower_band and 
                      close_price < lower_band):
                    self.current_trend = 'down'
                # 如果没有穿越，保持当前趋势
                elif self.current_trend is not None:
                    # 保持当前趋势不变
                    pass
                else:
                    # 初始状态，基于价格位置判断
                    if close_price > upper_band:
                        self.current_trend = 'up'
                    elif close_price < lower_band:
                        self.current_trend = 'down'
                    else:
                        self.current_trend = 'neutral'
            else:
                # 备用逻辑：基于价格与VIDYA的关系
                if close_price > smoothed_vidya:
                    self.current_trend = 'up'
                elif close_price < smoothed_vidya:
                    self.current_trend = 'down'
                else:
                    self.current_trend = 'neutral'
            
            # 🔴 检测趋势穿越信号（按照Pine Script逻辑）
            # 保存上一个穿越状态
            self.prev_trend_cross_up = self.trend_cross_up
            self.prev_trend_cross_down = self.trend_cross_down
            
            # 计算当前穿越信号
            trend_changed = (self.previous_trend is not None and 
                           self.previous_trend != self.current_trend)
            
            if trend_changed:
                if self.current_trend == 'up':
                    self.trend_cross_up = True
                    self.trend_cross_down = False
                elif self.current_trend == 'down':
                    self.trend_cross_up = False
                    self.trend_cross_down = True
            else:
                # 趋势未改变，穿越信号重置为False
                self.trend_cross_up = False
                self.trend_cross_down = False
            
            # 🔴 检测穿越信号的变化（ta.change逻辑）
            cross_up_changed = (self.trend_cross_up != self.prev_trend_cross_up)
            cross_down_changed = (self.trend_cross_down != self.prev_trend_cross_down)
            
            # 🔴 当穿越信号变化时重置成交量（Pine Script逻辑）
            if cross_up_changed or cross_down_changed:
                print(f"    🔄 穿越信号变化，重置成交量: cross_up({self.prev_trend_cross_up}→{self.trend_cross_up}), cross_down({self.prev_trend_cross_down}→{self.trend_cross_down})")
                self.buy_volume = 0
                self.sell_volume = 0
                # 🔴 不再清空支撑阻力位，保留历史数据用于交易决策
                # self.support_levels = []
                # self.resistance_levels = []
                # print(f"        🗑️ 已清空旧的支撑阻力位（趋势转换）")
            
            # 🔴 当穿越信号未变化时累积成交量（旧逻辑：动态周期）
            if not (cross_up_changed or cross_down_changed):
                if volume > 0 and len(self.close_history) >= 2:
                    # 判断当前K线是阳线还是阴线（Pine Script: close > open）
                    # 这里用close vs 上一个close，更接近open的概念
                    prev_close = self.close_history[-2]
                    if close_price > prev_close:  # 阳线
                        self.buy_volume += volume
                    elif close_price < prev_close:  # 阴线
                        self.sell_volume += volume
            
            self.delta_volume = self.buy_volume - self.sell_volume
            
            # 🔴 固定周期Delta Volume的累积和计算已移到策略主类，每1分钟执行
            
            # 🔴 计算EMA50（不平滑）
            self.current_ema_50 = self._calculate_ema(close_price, self.current_ema_50, 50)
            self.ema_50_values.append(self.current_ema_50)
            
            # 🔴 计算EMA120（需要SMA50平滑）
            # 第一步：计算原始EMA120
            self.current_ema_120 = self._calculate_ema(close_price, self.current_ema_120, 120)
            self.ema_120_values.append(self.current_ema_120)
            
            # 第二步：对EMA120进行SMA50平滑
            if len(self.ema_120_values) >= 50:
                # 有足够数据，使用SMA50平滑
                self.current_ema_120_smoothed = self._calculate_sma(self.ema_120_values, 50)
            else:
                # 数据不足，使用当前EMA120值
                self.current_ema_120_smoothed = self.current_ema_120
            
            self.ema_120_smoothed_values.append(self.current_ema_120_smoothed)
            
            # 🔴 计算EMA120平滑的斜率（T1 - T7）
            if len(self.ema_120_smoothed_values) >= 7:
                # 获取当前值（T1）和7个周期前的值（T7）
                t1 = self.ema_120_smoothed_values[-1]  # 最新值
                t7 = self.ema_120_smoothed_values[-7]  # 7个周期前
                
                # 计算斜率
                self.ema_120_slope = t1 - t7
                
                # 判断斜率方向（使用阈值避免噪音）
                slope_threshold = t1 * 0.0001  # 0.01%的价格变化作为阈值
                self.ema_120_is_rising = self.ema_120_slope > slope_threshold
                self.ema_120_is_falling = self.ema_120_slope < -slope_threshold
            else:
                # 数据不足，默认无方向
                self.ema_120_slope = 0
                self.ema_120_is_rising = False
                self.ema_120_is_falling = False
            
            # 保持历史长度
            if len(self.ema_50_values) > 200:
                self.ema_50_values = self.ema_50_values[-200:]
            if len(self.ema_120_values) > 200:
                self.ema_120_values = self.ema_120_values[-200:]
            if len(self.ema_120_smoothed_values) > 200:
                self.ema_120_smoothed_values = self.ema_120_smoothed_values[-200:]
            
            # 检查预热状态
            if not self.is_warmed_up and self.warmup_data_count >= self.required_warmup:
                self.is_warmed_up = True
                print(f"    ✅ 标准VIDYA指标预热完成！")
        
            # 调试信息
            if self.is_warmed_up:
                print(f"    📊 VIDYA: {self.current_vidya:.2f} | 平滑VIDYA: {smoothed_vidya:.2f}")
                print(f"    💫 CMO: {abs_cmo:.2f} | Alpha: {adjusted_alpha:.4f}")
                
                # 🔴 显示VIDYA斜率信息
                slope_direction = "📈上升" if self.vidya_is_rising else "📉下降" if self.vidya_is_falling else "➡️平缓"
                print(f"    🎯 VIDYA斜率: {self.vidya_slope:.4f} ({slope_direction})")
                if current_atr is not None:
                    print(f"    📏 ATR: {current_atr:.2f} | 上轨: {upper_band:.2f} | 下轨: {lower_band:.2f}")
                print(f"    🎯 趋势: {self.current_trend} | 价格: {close_price:.2f}")
                
                # 🔴 显示EMA指标
                ema_slope_direction = "📈上升" if self.ema_120_is_rising else "📉下降" if self.ema_120_is_falling else "➡️平缓"
                print(f"    📈 EMA50: {self.current_ema_50:.2f} | EMA120(原始): {self.current_ema_120:.2f} | EMA120(SMA50平滑): {self.current_ema_120_smoothed:.2f}")
                print(f"    📊 EMA120斜率: {self.ema_120_slope:.2f} ({ema_slope_direction})")
                print(f"    📊 成交量压力(动态): 买入={self.buy_volume:,.0f} | 卖出={self.sell_volume:,.0f} | Delta={self.delta_volume:+,.0f}")
                print(f"    📊 固定周期DV({self.delta_volume_period}): Delta%={self.delta_volume_percent_fixed:+.2f}% | Delta={self.delta_volume_fixed:+,.0f} | 当前K线量={self.current_kline_volume:,.0f}")
                if pivot_high is not None:
                    print(f"    🔺 枢轴高点: {pivot_high:.2f}")
                if pivot_low is not None:
                    print(f"    🔻 枢轴低点: {pivot_low:.2f}")
                if self.support_levels:
                    print(f"    📈 支撑线: {self.support_levels[-1]:.2f}")
                if self.resistance_levels:
                    print(f"    📉 阻力线: {self.resistance_levels[-1]:.2f}")
                
                if trend_changed:
                    print(f"    🔄 【VIDYA趋势转换】{self.previous_trend} → {self.current_trend}")
            else:
                print(f"    🔥 VIDYA预热中 {self.warmup_data_count}/{self.required_warmup} | VIDYA: {self.current_vidya:.2f}")
            
            return {
                'vidya': self.current_vidya,
                'smoothed_vidya': smoothed_vidya,
                'cmo': abs_cmo,
                'alpha': adjusted_alpha,
                'atr': current_atr,
                'upper_band': upper_band,
                'lower_band': lower_band,
                'trend': self.current_trend,
                'trend_changed': trend_changed,
                'buy_volume': self.buy_volume,
                'sell_volume': self.sell_volume,
                'delta_volume': self.delta_volume,
                # 🔴 固定周期Delta Volume
                'delta_volume_fixed': self.delta_volume_fixed,
                'delta_volume_percent_fixed': self.delta_volume_percent_fixed,
                'pivot_high': pivot_high,
                'pivot_low': pivot_low,
                'support_level': self.support_levels[-1] if self.support_levels else None,
                'resistance_level': self.resistance_levels[-1] if self.resistance_levels else None,
                'is_warmed_up': self.is_warmed_up,
                # 🔴 新增斜率信息
                'vidya_slope': self.vidya_slope,
                'vidya_is_rising': self.vidya_is_rising,
                'vidya_is_falling': self.vidya_is_falling,
                # 🔴 新增EMA指标
                'ema_50': self.current_ema_50,
                'ema_120': self.current_ema_120_smoothed,  # 返回平滑后的EMA120（主要使用）
                'ema_120_raw': self.current_ema_120,  # 返回原始EMA120（供参考）
                # 🔴 EMA120斜率信息
                'ema_120_slope': self.ema_120_slope,
                'ema_120_is_rising': self.ema_120_is_rising,
                'ema_120_is_falling': self.ema_120_is_falling
            }
        else:
            # 数据不足
            print(f"    🔥 VIDYA预热中 {self.warmup_data_count}/{self.required_warmup} | 数据累积: {len(self.close_history)}/{self.vidya_momentum + 1}")
            return {
                'vidya': None,
                'smoothed_vidya': None,
                'cmo': 0,
                'alpha': 0,
                'atr': None,
                'upper_band': None,
                'lower_band': None,
                'trend': None,
                'trend_changed': False,
                'buy_volume': 0,
                'sell_volume': 0,
                'delta_volume': 0,
                'pivot_high': None,
                'pivot_low': None,
                'support_level': None,
                'resistance_level': None,
                'is_warmed_up': False,
                'ema_50': None,
                'ema_120': None,
                'ema_120_raw': None,
                'ema_120_slope': 0,
                'ema_120_is_rising': False,
                'ema_120_is_falling': False
            }


class TrendVolumaticDynamicAverageStrategy:
    """纯VIDYA策略管理器"""
    
    def __init__(self, timeframe='30m', initial_capital=100000, position_size_percentage=100, 
                 fixed_take_profit_pct=2.0, max_loss_pct=4.0, 
                 volatility_timeframe='6h', volatility_length=14, volatility_mult=2.0, 
                 volatility_ema_period=90, volatility_threshold=0.8, 
                 vidya_length=20, vidya_momentum=9, vidya_smooth=15, 
                 vidya_band_distance=2.0, vidya_atr_period=200, 
                 vidya_pivot_left=3, vidya_pivot_right=3,
                 delta_volume_period=14,
                 entry_condition_trend_breakthrough=True,
                 entry_condition_arrow_signal=False,
                 entry_condition_vidya_slope=False,
                 entry_condition_delta_volume=True,
                 entry_condition_ema_120_slope=False,
                 bb_midline_period=20,
                 bb_angle_window_size=20,
                 bb_angle_threshold=0.3,
                 bb_r_squared_threshold=0.6,
                 bb_stop_loss_lock_periods=5,
                 enable_bb_angle_entry=False, **kwargs):
        """
        初始化纯VIDYA策略
        
        布林带中轨角度参数说明（独立开仓信号）：
        --------------------------------------------
        bb_midline_period: EMA中轨周期（第一层平滑，建议10-50）
            - 控制中轨对价格的敏感度
            - 小值(10-15): 快速响应，适合短期波动
            - 中值(20-30): 平衡，默认推荐
            - 大值(40-50): 平滑稳定，过滤噪音
            
        bb_angle_window_size: 角度计算窗口（第二层分析，建议15-50）
            - 控制角度看多长的趋势
            - 小值(15-20): 捕捉短期趋势（7.5-10小时@30m周期）
            - 中值(20-30): 中期趋势（10-15小时@30m周期）
            - 大值(40-50): 长期趋势（20-25小时@30m周期）
            
        配置示例：
        ----------
        1. 快速中轨 + 长期趋势（推荐震荡市）
           bb_midline_period=10, bb_angle_window_size=30
           
        2. 平滑中轨 + 短期趋势（推荐单边市）
           bb_midline_period=30, bb_angle_window_size=15
           
        3. 统一配置（默认，适用大多数情况）
           bb_midline_period=20, bb_angle_window_size=20
        """
        self.timeframe = timeframe
        
        # 初始化单时间周期管理器和指标
        self.timeframe_manager = TrendFilterTimeframeManager(timeframe)
        
        # 🔴 初始化标准VIDYA指标
        self.vidya_indicator = VIDYAIndicator(
            vidya_length=vidya_length,
            vidya_momentum=vidya_momentum,
            smooth_length=vidya_smooth,
            band_distance=vidya_band_distance,
            atr_period=vidya_atr_period,
            pivot_left=vidya_pivot_left,
            pivot_right=vidya_pivot_right,
            delta_volume_period=delta_volume_period  # 🔴 传入固定周期Delta Volume参数
        )
        print(f"📊 标准VIDYA指标已初始化: length={vidya_length}, momentum={vidya_momentum}, smooth={vidya_smooth}")
        print(f"📏 ATR带宽: distance={vidya_band_distance}, period={vidya_atr_period}")
        print(f"🔍 枢轴点: left={vidya_pivot_left}, right={vidya_pivot_right}")
        
        # 🔴 初始化布林带中轨角度计算器（基于30分钟K线）
        self.bb_angle_calculator = BollingerMidlineAngleCalculator(
            bb_period=bb_midline_period,
            window_size=bb_angle_window_size,
            angle_threshold=bb_angle_threshold,
            r_squared_threshold=bb_r_squared_threshold,
            lock_periods=bb_stop_loss_lock_periods
        )
        self.enable_bb_angle_entry = enable_bb_angle_entry
        self.bb_stop_loss_lock_periods = bb_stop_loss_lock_periods
        
        # 计算时间周期（用于说明）
        timeframe_minutes = timeframe_to_minutes(timeframe)
        midline_time_hours = (bb_midline_period * timeframe_minutes) / 60
        window_time_hours = (bb_angle_window_size * timeframe_minutes) / 60
        
        print(f"📐 布林带中轨角度计算器已初始化（基于{timeframe}周期，整点开仓）:")
        print(f"   ├─ EMA中轨周期: {bb_midline_period}根K线 (≈{midline_time_hours:.1f}小时) - 第一层平滑")
        print(f"   ├─ 角度计算窗口: {bb_angle_window_size}根K线 (≈{window_time_hours:.1f}小时) - 第二层分析")
        print(f"   ├─ 角度阈值: {bb_angle_threshold}° (趋势判断)")
        print(f"   ├─ R²阈值: {bb_r_squared_threshold} (趋势质量过滤)")
        print(f"   ├─ 止损锁定: {bb_stop_loss_lock_periods}个周期 (包含当前周期，实际等待{bb_stop_loss_lock_periods-1}个完整周期)")
        print(f"   └─ 独立开仓: {'✅ 启用' if enable_bb_angle_entry else '❌ 禁用'}")
        
        if enable_bb_angle_entry:
            lock_time_hours = (bb_stop_loss_lock_periods - 1) * timeframe_minutes / 60
            print(f"   💡 提示: ")
            print(f"      • 整点开仓：只在{timeframe}周期结束时检查开仓（初始状态）")
            print(f"      • 止盈后：下一分钟立即可开仓（不等整点）✨")
            print(f"      • 止损后：锁定约{lock_time_hours:.1f}小时，然后整点才可开仓")
        
        # 🔴 开仓条件配置（独立开关）
        self.entry_condition_trend_breakthrough = entry_condition_trend_breakthrough
        self.entry_condition_arrow_signal = entry_condition_arrow_signal
        self.entry_condition_vidya_slope = entry_condition_vidya_slope
        self.entry_condition_delta_volume = entry_condition_delta_volume
        self.entry_condition_ema_120_slope = entry_condition_ema_120_slope
        
        print(f"🎯 开仓条件配置（开启的条件必须全部满足）:")
        print(f"   1️⃣ 趋势突破: {'✅' if entry_condition_trend_breakthrough else '❌'}")
        print(f"   2️⃣ 箭头信号: {'✅' if entry_condition_arrow_signal else '❌'}")
        print(f"   3️⃣ VIDYA斜率: {'✅' if entry_condition_vidya_slope else '❌'}")
        print(f"   4️⃣ Delta Volume: {'✅' if entry_condition_delta_volume else '❌'}")
        print(f"   5️⃣ EMA120斜率: {'✅' if entry_condition_ema_120_slope else '❌'}")
        
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
        
        print(f"📊 纯VIDYA策略模式: 主周期({timeframe})")
        
        # 资金配置
        self.initial_capital = initial_capital
        self.position_size_percentage = position_size_percentage
        self.cash_balance = initial_capital
        
        # 止盈止损配置
        self.fixed_take_profit_pct = fixed_take_profit_pct
        self.max_loss_pct = max_loss_pct
        
        # 单周期交易状态
        self.position = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None
        self.max_loss_level = None
        self.current_invested_amount = None
        self.position_shares = None
        
        # 🔴 仓位记录
        self.position_entries = []  # 存储开仓记录（满仓模式，只记录不加仓）
        
        # 🔴 目标开仓价格（每分钟检查是否触及）
        self.target_entry_price = None  # 目标开仓价格（支撑位或阻力位）
        self.target_entry_direction = None  # 目标开仓方向（'long' 或 'short'）
        self.target_entry_vidya_result = None  # 记录开仓时的VIDYA结果
        
        # 🔴 支撑阻力线止损控制（趋势转变后只能使用一次）
        self.can_use_support_resistance_stop = False  # 是否可以使用支撑/阻力线作为止损
        
        # 🔴 保存当前的VIDYA上下轨（用于1分钟平仓检查）
        self.current_upper_band = None
        self.current_lower_band = None
        
        # 🔴 保存当前的EMA120平滑值（用于1分钟平仓检查）
        self.current_ema_120_smoothed = None
        
        # 🔴 Delta Volume止盈优化
        self.waiting_for_dv_target = False  # 是否正在等待Delta Volume达到目标
        self.target_dv_percent = None  # 目标Delta Volume百分比
        self.dv_trigger_threshold = 0.3  # 触发阈值（30%）
        self.dv_target_threshold = 1.01  # 目标阈值（120%）
        
        # 单周期趋势方向跟踪
        self.current_trend_direction = None
        self.previous_trend_direction = None
        
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
        
    def warmup_filter(self, historical_data):
        """使用历史数据预热VIDYA指标"""
        if not historical_data:
            print("⚠️  没有历史数据可用于预热")
            return
            
        print(f"🔥 开始使用 {len(historical_data)} 条历史数据预热指标...")
        print(f"   📊 VIDYA指标、波动率计算器、EMA计算器")
        
        kline_count = 0
        
        for i, data in enumerate(historical_data):
            timestamp = data.get('timestamp')
            open_price = data.get('open', 0)
            high_price = data.get('high', 0)
            low_price = data.get('low', 0)
            close_price = data.get('close', 0)
            volume = data.get('volume', 0)  # 🔴 获取成交量数据
            
            # 预热波动率计算器（使用1分钟数据）
            self.volatility_calculator.update(timestamp, close_price)
            
            # 预热EMA计算器（使用1分钟数据）
            self.ema_calculator.update(timestamp, close_price)
            
            # 预热主周期（包含成交量）
            new_kline = self.timeframe_manager.update_kline_data(
                timestamp, open_price, high_price, low_price, close_price, volume
            )
            
            if new_kline is not None:
                kline_count += 1
                
                # 🔴 预热布林带中轨角度计算器（基于30分钟K线）
                self.bb_angle_calculator.update(
                    new_kline['close'],
                    new_kline['high'],
                    new_kline['low'],
                    is_new_kline=True
                )
                
                # 🔴 预热VIDYA指标（包含成交量，标记为新K线）
                vidya_result = self.vidya_indicator.update(
                    new_kline['close'], 
                    new_kline['high'], 
                    new_kline['low'],
                    new_kline.get('volume', 0),
                    is_new_kline=True,  # 🔴 标记为新K线生成
                    open_price=new_kline['open']  # 🔴 传入聚合K线的开盘价
                )
                
                if kline_count <= 5:
                    vidya_value = vidya_result.get('vidya')
                    vidya_str = f"{vidya_value:.2f}" if vidya_value is not None else 'N/A'
                    print(f"    🟢 {self.timeframe} K线 #{kline_count}: {new_kline['timestamp'].strftime('%H:%M')} | "
                          f"VIDYA: {vidya_str}")
            
            if (i + 1) % 100 == 0:
                print(f"    预热进度: {i+1}/{len(historical_data)} | {self.timeframe} K线: {kline_count}个")
        
        print(f"✅ 指标预热完成！")
        print(f"  📊 {self.timeframe}周期: {kline_count}个K线")
        print(f"  🎯 VIDYA预热状态: {'完成' if self.vidya_indicator.is_warmed_up else '未完成'}")
        
        # 预热后重置方向，确保第一次运行能检测到方向改变
        self.current_trend_direction = None
        self.previous_trend_direction = None
        
        print(f"📊 策略已准备好，等待{self.timeframe}VIDYA趋势改变触发开仓！")
        
    def _update_fixed_delta_volume(self):
        """每1分钟更新固定周期Delta Volume计算"""
        # 计算历史K线的买卖量
        if len(self.vidya_indicator.buy_volume_history) > 0:
            # 取前N-1个完整K线（如果不足，则取全部）
            history_count = min(self.vidya_indicator.delta_volume_period - 1, 
                              len(self.vidya_indicator.buy_volume_history))
            total_buy_history = sum(self.vidya_indicator.buy_volume_history[-history_count:])
            total_sell_history = sum(self.vidya_indicator.sell_volume_history[-history_count:])
        else:
            total_buy_history = 0
            total_sell_history = 0
        
        # 当前未完成K线无法判断涨跌，按历史比例分配
        total_buy = total_buy_history
        total_sell = total_sell_history
        current_kline_total = self.vidya_indicator.current_kline_volume
        
        # 将当前未完成K线的成交量按历史比例分配（粗略估算）
        if current_kline_total > 0 and (total_buy_history + total_sell_history) > 0:
            buy_ratio = total_buy_history / (total_buy_history + total_sell_history)
            total_buy += current_kline_total * buy_ratio
            total_sell += current_kline_total * (1 - buy_ratio)
        
        # 计算Delta Volume
        avg_volume = (total_buy + total_sell) / 2
        if avg_volume > 0:
            self.vidya_indicator.delta_volume_fixed = total_buy - total_sell
            self.vidya_indicator.delta_volume_percent_fixed = (total_buy - total_sell) / avg_volume * 100
        else:
            self.vidya_indicator.delta_volume_fixed = 0
            self.vidya_indicator.delta_volume_percent_fixed = 0
    
    def update(self, timestamp, open_price, high_price, low_price, close_price, volume=0):
        """处理1分钟K线数据 - 单周期模式（集成VIDYA）"""
        signal_info = {
            'timestamp': timestamp,
            'timeframe': self.timeframe,
            'new_kline': False,
            'signals': [],
            'position': self.position,
            'sar_value': None,
            'vidya_value': None,  # 🔴 新增VIDYA值
            'vidya_result': None  # 🔴 新增VIDYA完整结果
        }
        
        # 1. 更新波动率计算器（每个1分钟数据都更新，因为它是6小时周期）
        self.volatility_calculator.update(timestamp, close_price)
        
        # 1.5. 更新EMA计算器（每个1分钟数据都更新，因为它是1小时周期）
        self.ema_calculator.update(timestamp, close_price)
        
        # 1.6. 更新ATR计算器累积数据（每分钟数据都记录，但不计算）
        self.atr_calculator.update_accumulate(close_price, high_price, low_price)
        
        # 🔴 1.7. 每1分钟累积成交量（用于固定周期Delta Volume）
        if volume > 0:
            self.vidya_indicator.current_kline_volume += volume
        
        # 🔴 1.8. 每1分钟计算固定周期Delta Volume
        self._update_fixed_delta_volume()
        
        # 2. 更新单时间周期聚合数据（包含成交量）
        new_kline = self.timeframe_manager.update_kline_data(
            timestamp, open_price, high_price, low_price, close_price, volume
        )
        
        # 更新signal_info
        signal_info['new_kline'] = new_kline is not None
        
        # 3. 更新指标（当新K线生成时）
        if new_kline is not None:
            
            timeframe_minutes = self.timeframe_manager.get_timeframe_minutes()
            print(f"[{self.timeframe}] 新K线生成: {new_kline['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | "
                  f"OHLC: {new_kline['open']:.2f}/{new_kline['high']:.2f}/{new_kline['low']:.2f}/{new_kline['close']:.2f}")
            
            kline_end_time = new_kline['timestamp'] + timedelta(minutes=timeframe_minutes-1, seconds=59)
            indicator_available_time = new_kline['timestamp'] + timedelta(minutes=timeframe_minutes)
            
            print(f"      📅 K线数据时间范围: {new_kline['timestamp'].strftime('%H:%M')} - {kline_end_time.strftime('%H:%M')}")
            
            # 3.1. 在新K线生成时计算ATR（整个周期结束时）
            self.atr_calculator.update_kline_end(
                new_kline['close'], 
                new_kline['high'], 
                new_kline['low']
            )
            
            # 🆕 3.2. 更新布林带中轨角度计算器（基于30分钟K线）
            bb_angle_result = self.bb_angle_calculator.update(
                new_kline['close'],
                new_kline['high'],
                new_kline['low'],
                is_new_kline=True
            )
            signal_info['bb_angle_result'] = bb_angle_result
            
            # 🔴 3.3. 更新VIDYA指标（包含成交量，标记为新K线）
            vidya_result = self.vidya_indicator.update(
                new_kline['close'], 
                new_kline['high'], 
                new_kline['low'],
                new_kline.get('volume', 0),
                is_new_kline=True,  # 🔴 标记为新K线生成
                open_price=new_kline['open']  # 🔴 传入聚合K线的开盘价
            )
            signal_info['vidya_value'] = vidya_result.get('smoothed_vidya')
            signal_info['vidya_result'] = vidya_result
            
            # 🔴 保存当前的上下轨（用于1分钟平仓检查）
            self.current_upper_band = vidya_result.get('upper_band')
            self.current_lower_band = vidya_result.get('lower_band')
            
            # 🔴 保存当前的EMA120平滑值（用于1分钟平仓检查）
            self.current_ema_120_smoothed = vidya_result.get('ema_120')
            
            # 🔴 显示VIDYA信息
            if vidya_result.get('vidya') is not None:
                print(f"  🎯 {self.timeframe} VIDYA: {vidya_result['vidya']:.2f} | "
                      f"平滑VIDYA: {vidya_result['smoothed_vidya']:.2f} | "
                      f"趋势: {vidya_result['trend']}")
                print(f"  💫 {self.timeframe} CMO: {vidya_result['cmo']:.2f} | "
                      f"Alpha: {vidya_result['alpha']:.4f}")
                if vidya_result.get('delta_volume', 0) != 0:
                    print(f"  📊 {self.timeframe} 成交量压力: "
                          f"买入={vidya_result['buy_volume']:,.0f} | "
                          f"卖出={vidya_result['sell_volume']:,.0f} | "
                          f"Delta={vidya_result['delta_volume']:+,.0f}")
            
            print(f"  🎯 {self.timeframe}指标可用时间: {indicator_available_time.strftime('%H:%M')} (K线完成后)")
            
            # 🆕 3.4. 检查布林带角度整点开仓（优先级最高）
            self._check_bb_angle_entry_at_kline_end(
                new_kline['open'],  # 🔴 使用下一根K线的开盘价（即当前K线的收盘价）
                timestamp,
                signal_info,
                bb_angle_result
            )
            
            # 3.5. 使用VIDYA交易逻辑（只在没有被布林带角度开仓时执行）
            if self.position is None:
                self._check_vidya_trend_change(vidya_result, open_price, signal_info)
            
            print(f"  🔍 new_kline: {new_kline}")

            # 4. 🔴 不再使用VIDYA动态止损（已取消）
            # if self.position is not None:
            #     # 🔴 VIDYA追踪止损（跟随带宽）
            #     self._update_vidya_trailing_stop(vidya_result, signal_info)
        
        # 5. 基于1分钟K线检查平仓触发（每个1分钟数据都检查）
        self._check_stop_position_trigger_1min(timestamp, open_price, high_price, low_price, close_price, signal_info)
        
        return signal_info
    

    def _check_bb_angle_entry_at_kline_end(self, entry_price, timestamp, signal_info, bb_angle_result):
        """
        在30分钟K线结束时检查布林带角度开仓（整点执行）
        
        Args:
            entry_price: 下一根K线的开盘价（即当前K线的收盘价）
            timestamp: 当前时间
            signal_info: 信号信息
            bb_angle_result: 布林带角度计算结果
        """
        # 🔴 只在无持仓且开关启用时检查
        if self.position is not None or not self.enable_bb_angle_entry:
            return
        
        # 🔴 检查是否锁定（止损后5个周期）
        bb_angle_signal = self.bb_angle_calculator.get_entry_signal(
            current_position=self.position,
            current_time=timestamp,  # 🆕 传入当前时间
            is_kline_end=True  # 🆕 标记为整点检查
        )
        
        print(f"\n  📐 ========== 整点布林带角度开仓检查 ==========")
        print(f"  🕐 时间: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  📊 锁定状态: {'🔒 已锁定' if self.bb_angle_calculator.is_locked else '🔓 未锁定'}")
        
        if self.bb_angle_calculator.is_locked:
            print(f"  ⏳ 解锁时间: {self.bb_angle_calculator.lock_end_time.strftime('%H:%M')}")
            print(f"  =============================================\n")
            return
        
        # 🔴 判断开仓信号
        if bb_angle_signal['can_open_long']:
            reason = f"布林带角度整点开多 | {bb_angle_signal['reason']}"
            print(f"  🟢 【布林带角度开多】{bb_angle_signal['reason']}")
            self._execute_bb_angle_entry('long', entry_price, signal_info, reason)
            
        elif bb_angle_signal['can_open_short']:
            reason = f"布林带角度整点开空 | {bb_angle_signal['reason']}"
            print(f"  🔴 【布林带角度开空】{bb_angle_signal['reason']}")
            self._execute_bb_angle_entry('short', entry_price, signal_info, reason)
        
        print(f"  =============================================\n")

    def _check_vidya_trend_change(self, vidya_result, open_price, signal_info):
        """检查VIDYA方向改变，触发标准VIDYA交易信号（新逻辑：支撑阻力位开仓）"""
        # 检查VIDYA是否预热完成且有有效数据
        if not vidya_result.get('is_warmed_up', False) or vidya_result.get('smoothed_vidya') is None:
            return
        
        # 获取VIDYA趋势信息
        current_vidya_trend = vidya_result.get('trend')
        trend_changed = vidya_result.get('trend_changed', False)
        smoothed_vidya = vidya_result.get('smoothed_vidya')
        upper_band = vidya_result.get('upper_band')
        lower_band = vidya_result.get('lower_band')
        delta_volume = vidya_result.get('delta_volume', 0)
        
        # 🔴 获取所有支撑阻力位（不是单个，而是列表）
        all_support_levels = self.vidya_indicator.support_levels if self.vidya_indicator.support_levels else []
        all_resistance_levels = self.vidya_indicator.resistance_levels if self.vidya_indicator.resistance_levels else []
        
        # 🔴 筛选有效的支撑阻力位（基于当前价格，不过滤距离）
        # 支撑位：在当前价格下方，选择最接近的（价格最高的）
        valid_supports = [s for s in all_support_levels if s < open_price]
        support_level = max(valid_supports) if valid_supports else None  # 价格下方最高的
        
        # 阻力位：在当前价格上方，选择最接近的（价格最低的）
        valid_resistances = [r for r in all_resistance_levels if r > open_price]
        resistance_level = min(valid_resistances) if valid_resistances else None  # 价格上方最低的
        
        # 🔴 获取VIDYA斜率信息
        vidya_slope = vidya_result.get('vidya_slope', 0)
        vidya_is_rising = vidya_result.get('vidya_is_rising', False)
        vidya_is_falling = vidya_result.get('vidya_is_falling', False)
        
        # 🔴 获取EMA120斜率信息
        ema_120_slope = vidya_result.get('ema_120_slope', 0)
        ema_120_is_rising = vidya_result.get('ema_120_is_rising', False)
        ema_120_is_falling = vidya_result.get('ema_120_is_falling', False)
        
        print(f"  🔍 标准VIDYA交易检查:")
        print(f"       📊 VIDYA趋势: {current_vidya_trend}")
        print(f"       🔄 趋势改变: {trend_changed}")
        print(f"       💫 平滑VIDYA: {smoothed_vidya:.2f}")
        print(f"       💰 当前价格: {open_price:.2f}")
        print(f"       🎯 VIDYA斜率: {vidya_slope:.4f} (上升:{vidya_is_rising}, 下降:{vidya_is_falling})")
        if upper_band is not None and lower_band is not None:
            print(f"       📏 上轨: {upper_band:.2f} | 下轨: {lower_band:.2f}")
        print(f"       📊 Delta Volume: {delta_volume:+,.0f}")
        
        # 支撑位信息
        if all_support_levels:
            print(f"       📈 全部支撑位({len(all_support_levels)}个): {[f'{s:.2f}' for s in all_support_levels]}")
            if valid_supports:
                print(f"       ✅ 价格下方支撑位({len(valid_supports)}个): {[f'{s:.2f}' for s in valid_supports]}")
                if support_level is not None:
                    distance = open_price - support_level
                    distance_pct = (distance / open_price) * 100
                    print(f"       🎯 目标支撑位: {support_level:.2f} (距离: {distance:.2f}, {distance_pct:.2f}%)")
            else:
                print(f"       ❌ 无有效支撑位（价格下方无支撑）")
        else:
            print(f"       📈 全部支撑位: 无")
        
        # 阻力位信息
        if all_resistance_levels:
            print(f"       📉 全部阻力位({len(all_resistance_levels)}个): {[f'{r:.2f}' for r in all_resistance_levels]}")
            if valid_resistances:
                print(f"       ✅ 价格上方阻力位({len(valid_resistances)}个): {[f'{r:.2f}' for r in valid_resistances]}")
                if resistance_level is not None:
                    distance = resistance_level - open_price
                    distance_pct = (distance / open_price) * 100
                    print(f"       🎯 目标阻力位: {resistance_level:.2f} (距离: {distance:.2f}, {distance_pct:.2f}%)")
            else:
                print(f"       ❌ 无有效阻力位（价格上方无阻力）")
        else:
            print(f"       📉 全部阻力位: 无")
        
        # 🔴 新逻辑：设置目标开仓价格（不立即开仓，等待每分钟触发）
        if current_vidya_trend == 'up':
            # 🟢 上升趋势：使用支撑位作为目标开仓价格（做多）
            if self.position is None:
                if support_level is not None:
                    # 检查开启的条件
                    can_open = self._check_entry_conditions(
                        'long', trend_changed, vidya_is_rising, vidya_is_falling,
                        delta_volume, ema_120_is_rising, ema_120_is_falling,
                        vidya_slope, ema_120_slope
                    )
                    
                    if can_open:
                        # 🔴 设置目标开仓价格，不立即开仓
                        self.target_entry_price = support_level
                        self.target_entry_direction = 'long'
                        # 🔴 确保vidya_result不为None
                        self.target_entry_vidya_result = vidya_result if vidya_result else None
                        # 🔴 允许使用支撑/阻力线作为止损（趋势转变）
                        self.can_use_support_resistance_stop = True
                        print(f"  🎯 【设置目标开仓】上升趋势，目标价格=${support_level:.2f}（支撑位），等待触发")
                    else:
                        # 条件不满足，清除目标
                        self.target_entry_price = None
                        self.target_entry_direction = None
                        self.target_entry_vidya_result = None
                else:
                    print(f"  ⏳ 【等待支撑位】当前无支撑位数据，等待检测")
                    self.target_entry_price = None
                    self.target_entry_direction = None
                    self.target_entry_vidya_result = None
            elif self.position == 'short':
                # 🔄 持空单，趋势转多，设置开多目标价格（不立即平仓）
                if support_level is not None:
                    self.target_entry_price = support_level
                    self.target_entry_direction = 'long'
                    # 🔴 确保vidya_result不为None
                    self.target_entry_vidya_result = vidya_result if vidya_result else None
                    # 🔴 允许使用支撑/阻力线作为止损（趋势转变）
                    self.can_use_support_resistance_stop = True
                    print(f"  🔄 【趋势转多】持有空单，等待价格回调至支撑位${support_level:.2f}开多（使用上轨平空）")
                else:
                    print(f"  🔄 【趋势转多】持有空单，但无支撑位数据")
                    self.target_entry_price = None
                    self.target_entry_direction = None
                    self.target_entry_vidya_result = None
        
        elif current_vidya_trend == 'down':
            # 🔴 下降趋势：使用阻力位作为目标开仓价格（做空）
            if self.position is None:
                if resistance_level is not None:
                    # 检查开启的条件
                    can_open = self._check_entry_conditions(
                        'short', trend_changed, vidya_is_rising, vidya_is_falling,
                        delta_volume, ema_120_is_rising, ema_120_is_falling,
                        vidya_slope, ema_120_slope
                    )
                    
                    if can_open:
                        # 🔴 设置目标开仓价格，不立即开仓
                        self.target_entry_price = resistance_level
                        self.target_entry_direction = 'short'
                        # 🔴 确保vidya_result不为None
                        self.target_entry_vidya_result = vidya_result if vidya_result else None
                        # 🔴 允许使用支撑/阻力线作为止损（趋势转变）
                        self.can_use_support_resistance_stop = True
                        print(f"  🎯 【设置目标开仓】下降趋势，目标价格=${resistance_level:.2f}（阻力位），等待触发")
                    else:
                        # 条件不满足，清除目标
                        self.target_entry_price = None
                        self.target_entry_direction = None
                        self.target_entry_vidya_result = None
                else:
                    print(f"  ⏳ 【等待阻力位】当前无阻力位数据，等待检测")
                    self.target_entry_price = None
                    self.target_entry_direction = None
                    self.target_entry_vidya_result = None
            elif self.position == 'long':
                # 🔄 持多单，趋势转空，设置开空目标价格（不立即平仓）
                if resistance_level is not None:
                    self.target_entry_price = resistance_level
                    self.target_entry_direction = 'short'
                    # 🔴 确保vidya_result不为None
                    self.target_entry_vidya_result = vidya_result if vidya_result else None
                    # 🔴 允许使用支撑/阻力线作为止损（趋势转变）
                    self.can_use_support_resistance_stop = True
                    print(f"  🔄 【趋势转空】持有多单，等待价格反弹至阻力位${resistance_level:.2f}开空（使用下轨平多）")
                else:
                    print(f"  🔄 【趋势转空】持有多单，但无阻力位数据")
                    self.target_entry_price = None
                    self.target_entry_direction = None
                    self.target_entry_vidya_result = None
        
        elif current_vidya_trend == 'neutral':
            # 价格在带宽内，中性状态，清除目标
            print(f"  ⚪ 【VIDYA中性】价格{open_price:.2f}在带宽内，等待突破")
            if self.position is None:
                self.target_entry_price = None
                self.target_entry_direction = None
                self.target_entry_vidya_result = None
    
    def _check_entry_conditions(self, direction, trend_changed, vidya_is_rising, vidya_is_falling,
                                delta_volume, ema_120_is_rising, ema_120_is_falling,
                                vidya_slope, ema_120_slope):
        """检查开仓条件（提取为独立方法）"""
        can_open = True
        failed_conditions = []
        
        # 1. 趋势突破（如果开启）
        if self.entry_condition_trend_breakthrough:
            print(f"  ✅ 趋势突破: 已确认")
        
        # 2. 箭头信号（如果开启）
        if self.entry_condition_arrow_signal:
            if trend_changed:
                print(f"  ✅ 箭头信号: 趋势转换确认")
            else:
                can_open = False
                failed_conditions.append("箭头信号")
                print(f"  ❌ 箭头信号: 无趋势转换")
        
        # 3. VIDYA斜率（如果开启）
        if self.entry_condition_vidya_slope:
            if direction == 'long' and vidya_is_rising:
                print(f"  ✅ VIDYA斜率: 向上倾斜 (斜率{vidya_slope:.4f})")
            elif direction == 'short' and vidya_is_falling:
                print(f"  ✅ VIDYA斜率: 向下倾斜 (斜率{vidya_slope:.4f})")
            else:
                can_open = False
                failed_conditions.append("VIDYA斜率")
                print(f"  ❌ VIDYA斜率: 不支持{direction} (斜率{vidya_slope:.4f})")
        
        # 4. Delta Volume（如果开启）
        if self.entry_condition_delta_volume:
            if (direction == 'long' and delta_volume >= 0) or (direction == 'short' and delta_volume <= 0):
                print(f"  ✅ Delta Volume: 支持{direction} ({delta_volume:+,.0f})")
            else:
                can_open = False
                failed_conditions.append("Delta Volume")
                print(f"  ❌ Delta Volume: 不支持{direction} ({delta_volume:+,.0f})")
        
        # 5. EMA120斜率（如果开启）
        if self.entry_condition_ema_120_slope:
            if (direction == 'long' and ema_120_is_rising) or (direction == 'short' and ema_120_is_falling):
                print(f"  ✅ EMA120斜率: 支持{direction} (斜率{ema_120_slope:.2f})")
            else:
                can_open = False
                failed_conditions.append("EMA120斜率")
                print(f"  ❌ EMA120斜率: 不支持{direction} (斜率{ema_120_slope:.2f})")
        
        if not can_open:
            print(f"  ❌ 开仓条件不满足，缺少: {', '.join(failed_conditions)}")
        
        return can_open

    def _execute_vidya_entry(self, direction, entry_price, signal_info, vidya_result):
        """执行标准VIDYA开仓（基于支撑阻力线和ATR带宽）"""
        # 🔴 防御性检查：entry_price不能为None
        if entry_price is None:
            print(f"  ⚠️  【开仓价格为空】无法开仓：entry_price=None")
            return
            
        # 检查是否已预热完成
        if not self.vidya_indicator.is_warmed_up:
            print(f"  ⚠️  【VIDYA预热未完成】指标预热中，跳过开仓")
            return
        
        # 🔴 检查固定周期Delta Volume过滤条件
        # current_dv_percent_fixed = self.vidya_indicator.delta_volume_percent_fixed / 100.0  # 转换为小数
        
        # if direction == 'long':
        #     # 🔴 开多仓：如果固定DV < -0.4（-40%），不开仓
        #     if current_dv_percent_fixed < -0.4:
        #         print(f"  ❌ 【Delta Volume过滤】开多仓被拒绝：固定DV={current_dv_percent_fixed*100:.2f}% < -50%，市场卖压过大")
        #         return
        # elif direction == 'short':
        #     # 🔴 开空仓：如果固定DV > 0.4（40%），不开仓
        #     if current_dv_percent_fixed > 0.4:
        #         print(f"  ❌ 【Delta Volume过滤】开空仓被拒绝：固定DV={current_dv_percent_fixed*100:.2f}% > 50%，市场买压过大")
        #         return
            
        potential_invested_amount = self._get_invested_capital()
        if potential_invested_amount <= 0:
            print(f"  ⚠️  【资金不足】无法开仓：现金余额=${self.cash_balance:,.2f} <= 0")
            return
        
        # 🔴 防御性检查：如果vidya_result为None，使用当前VIDYA指标状态
        if vidya_result is None or not isinstance(vidya_result, dict):
            print(f"  ⚠️  【vidya_result为空】使用当前VIDYA指标状态")
            all_support_levels = self.vidya_indicator.support_levels if self.vidya_indicator.support_levels else []
            all_resistance_levels = self.vidya_indicator.resistance_levels if self.vidya_indicator.resistance_levels else []
            
            vidya_result = {
                'support_level': all_support_levels[-1] if all_support_levels else None,
                'resistance_level': all_resistance_levels[-1] if all_resistance_levels else None,
                'upper_band': self.vidya_indicator.upper_band_values[-1] if self.vidya_indicator.upper_band_values else None,
                'lower_band': self.vidya_indicator.lower_band_values[-1] if self.vidya_indicator.lower_band_values else None,
                'atr': self.vidya_indicator.current_atr,
                'smoothed_vidya': self.vidya_indicator.smoothed_vidya_values[-1] if self.vidya_indicator.smoothed_vidya_values else 0,
                'delta_volume': self.vidya_indicator.delta_volume,
                'cmo': 0
            }
        
        # 🔴 基于支撑阻力线和ATR带宽计算止盈止损
        support_level = vidya_result.get('support_level')
        resistance_level = vidya_result.get('resistance_level')
        upper_band = vidya_result.get('upper_band')
        lower_band = vidya_result.get('lower_band')
        atr = vidya_result.get('atr')
        smoothed_vidya = vidya_result.get('smoothed_vidya', 0)
        delta_volume = vidya_result.get('delta_volume', 0)
        cmo = vidya_result.get('cmo', 0)
        
        # 计算止损价格（基于支撑阻力线或ATR）
        if direction == 'long':
            # 做多止损：支撑线下方或下轨下方
            if lower_band is not None and lower_band < entry_price:
                stop_loss_price = lower_band * 0.99  # 下轨下方1%
                stop_reason = f"下轨{lower_band:.2f}下方"
            else:
                # 🔴 备用：基于开仓价格的固定百分比止损
                stop_loss_price = entry_price * (1 - self.max_loss_pct / 100)
                stop_reason = f"固定{self.max_loss_pct}%止损"
        else:
            # 做空止损：阻力线上方或上轨上方
            if upper_band is not None and upper_band > entry_price:
                stop_loss_price = upper_band * 1.01  # 上轨上方1%
                stop_reason = f"上轨{upper_band:.2f}上方"
            else:
                # 🔴 备用：基于开仓价格的固定百分比止损
                stop_loss_price = entry_price * (1 + self.max_loss_pct / 100)
                stop_reason = f"固定{self.max_loss_pct}%止损"
        
        # 🔴 强制使用固定止盈（避免VIDYA带宽导致的错误止盈）
        if direction == 'long':
            if self.fixed_take_profit_pct > 0:
                take_profit_price = entry_price * (1 + self.fixed_take_profit_pct / 100)
                profit_reason = f"固定{self.fixed_take_profit_pct}%止盈"
            else:
                take_profit_price = None
                profit_reason = "无固定止盈"
        else:
            if self.fixed_take_profit_pct > 0:
                take_profit_price = entry_price * (1 - self.fixed_take_profit_pct / 100)
                profit_reason = f"固定{self.fixed_take_profit_pct}%止盈"
            else:
                take_profit_price = None
                profit_reason = "无固定止盈"
        
        # 计算风险回报比
        if direction == 'long':
            risk = entry_price - stop_loss_price
            reward = take_profit_price - entry_price
        else:
            risk = stop_loss_price - entry_price
            reward = entry_price - take_profit_price
        
        risk_reward_ratio = reward / risk if risk > 0 else 0
        
        # 构建开仓原因
        if direction == 'long':
            reason = f"标准VIDYA上升趋势开多 | 价格${entry_price:.2f} > 上轨${upper_band:.2f} | VIDYA:${smoothed_vidya:.2f} | CMO:{cmo:.1f} | Delta:{delta_volume:+,.0f}"
        else:
            reason = f"标准VIDYA下降趋势开空 | 价格${entry_price:.2f} < 下轨${lower_band:.2f} | VIDYA:${smoothed_vidya:.2f} | CMO:{cmo:.1f} | Delta:{delta_volume:+,.0f}"
        
        print(f"  🎯 【标准VIDYA开仓】{direction.upper()} | 价格: ${entry_price:.2f}")
        print(f"  📊 VIDYA: ${smoothed_vidya:.2f} | Delta Volume: {delta_volume:+,.0f}")
        print(f"  🛡️ 止损: ${stop_loss_price:.2f} ({stop_reason})")
        print(f"  🎯 止盈: ${take_profit_price:.2f} ({profit_reason})")
        print(f"  📈 风险回报比: 1:{risk_reward_ratio:.2f}")
        
        if direction == 'long':
            self._open_long_position(entry_price, signal_info, reason, potential_invested_amount, 
                                    stop_loss_price, take_profit_price)
        elif direction == 'short':
            self._open_short_position(entry_price, signal_info, reason, potential_invested_amount,
                                     stop_loss_price, take_profit_price)
    
    def _open_long_position(self, entry_price, signal_info, reason, invested_amount, stop_loss_price=None, take_profit_price=None):
        """开多单"""
        self.position = 'long'
        # 计算手续费
        transactionFee = invested_amount * 0.02 / 100
        # 实际投入金额（扣除手续费后）
        actual_invested_amount = invested_amount - transactionFee
        
        # 更新现金余额（扣除实际投入金额，不包含手续费）
        self.cash_balance -= actual_invested_amount
        
        # 开仓价格
        self.entry_price = entry_price

        self.current_invested_amount = actual_invested_amount
        self.position_shares = round(self.current_invested_amount / self.entry_price, 4)
        
        # 🔴 使用传入的止损止盈，如果没有则使用VIDYA带宽计算
        self.stop_loss_level = stop_loss_price if stop_loss_price is not None else entry_price * 0.98
        self.take_profit_level = take_profit_price if take_profit_price is not None else entry_price * 1.015
        
        # 计算最大亏损位
        if self.max_loss_pct > 0:
            self.max_loss_level = self.entry_price * (1 - self.max_loss_pct / 100)
        else:
            self.max_loss_level = None
        
        signal_info['signals'].append({
            'type': 'OPEN_LONG',
            'price': self.entry_price,
            'stop_loss': self.stop_loss_level,
            'take_profit': self.take_profit_level,
            'max_loss': self.max_loss_level,
            'invested_amount': self.current_invested_amount,
            'position_shares': self.position_shares,
            'cash_balance': self.cash_balance,
            'transaction_fee': transactionFee,
            'entry_timestamp': signal_info.get('timestamp'),  # 🔴 添加开仓时间戳
            'reason': f"{reason} | 投入${self.current_invested_amount:,.2f} | 止损${self.stop_loss_level:.2f}(VIDYA) | 止盈{f'${self.take_profit_level:.2f}' if self.take_profit_level is not None else '无'}(VIDYA) | 最大亏损{f'${self.max_loss_level:.2f}' if self.max_loss_level is not None else '无'}({self.max_loss_pct}%)"
        })
        
        # 🔴 记录开仓信息（满仓模式）
        self.position_entries = [{
            'price': entry_price,
            'amount': actual_invested_amount,
            'shares': self.position_shares,
            'timestamp': signal_info.get('timestamp')
        }]
        
        print(f"  🟢 【开多】{reason} | 价格: ${entry_price:.2f} | 投入: ${actual_invested_amount:,.2f} | 份额: {self.position_shares:.4f}")
        print(f"       止损: ${self.stop_loss_level:.2f} (VIDYA) | 止盈: {f'${self.take_profit_level:.2f}' if self.take_profit_level else '无'} | 最大亏损: {f'${self.max_loss_level:.2f}' if self.max_loss_level else '无'}")
        print(f"        现金更新: 余额=${self.cash_balance:,.2f}")
    
    def _open_short_position(self, entry_price, signal_info, reason, invested_amount, stop_loss_price=None, take_profit_price=None):
        """开空单"""
        # 计算手续费
        transactionFee = invested_amount * 0.02 / 100
        # 实际投入金额（扣除手续费后）
        actual_invested_amount = invested_amount - transactionFee
        
        # 更新现金余额（扣除实际投入金额，不包含手续费）
        self.cash_balance -= actual_invested_amount
        self.position = 'short'
        
        # 开仓价格
        self.entry_price = entry_price

        self.current_invested_amount = actual_invested_amount
        self.position_shares = round(self.current_invested_amount / self.entry_price, 4)
        
        # 🔴 使用传入的止损止盈，如果没有则使用VIDYA带宽计算
        self.stop_loss_level = stop_loss_price if stop_loss_price is not None else entry_price * 1.02
        self.take_profit_level = take_profit_price if take_profit_price is not None else entry_price * 0.985
        
        # 计算最大亏损位
        if self.max_loss_pct > 0:
            self.max_loss_level = self.entry_price * (1 + self.max_loss_pct / 100)
        else:
            self.max_loss_level = None
        
        signal_info['signals'].append({
            'type': 'OPEN_SHORT',
            'price': self.entry_price,
            'stop_loss': self.stop_loss_level,
            'take_profit': self.take_profit_level,
            'max_loss': self.max_loss_level,
            'invested_amount': self.current_invested_amount,
            'position_shares': self.position_shares,
            'cash_balance': self.cash_balance,
            'transaction_fee': transactionFee,
            'reason': f"{reason} | 投入${self.current_invested_amount:,.2f} | 止损${self.stop_loss_level:.2f}(VIDYA) | 止盈{f'${self.take_profit_level:.2f}' if self.take_profit_level is not None else '无'}(VIDYA) | 最大亏损{f'${self.max_loss_level:.2f}' if self.max_loss_level is not None else '无'}({self.max_loss_pct}%)"
        })
        
        # 🔴 记录开仓信息（满仓模式）
        self.position_entries = [{
            'price': entry_price,
            'amount': actual_invested_amount,
            'shares': self.position_shares,
            'timestamp': signal_info.get('timestamp')
        }]
        
        print(f"  🔴 【开空】{reason} | 价格: ${entry_price:.2f} | 投入: ${actual_invested_amount:,.2f} | 份额: {self.position_shares:.4f}")
        print(f"       止损: ${self.stop_loss_level:.2f} (VIDYA) | 止盈: {f'${self.take_profit_level:.2f}' if self.take_profit_level else '无'}")
        print(f"        现金更新: 余额=${self.cash_balance:,.2f}")
    
    def _update_vidya_trailing_stop(self, vidya_result, signal_info):
        """🔴 VIDYA追踪止损（随带宽动态调整）"""
        if self.position is None:
            return
        
        lower_band = vidya_result.get('lower_band')
        upper_band = vidya_result.get('upper_band')
        support_level = vidya_result.get('support_level')
        resistance_level = vidya_result.get('resistance_level')
        
        old_stop_loss = self.stop_loss_level
        new_stop_loss = old_stop_loss
        
        if self.position == 'long':
            # 🔴 多单追踪止损：优先使用下轨，其次使用支撑线（仅趋势转变后第一次）
            if lower_band is not None:
                # 使用下轨作为止损
                new_stop_loss = lower_band
            elif self.can_use_support_resistance_stop and support_level is not None and support_level < self.entry_price:
                # 只有当允许使用支撑线 且 支撑线低于开仓价格时才使用
                new_stop_loss = support_level * 0.995
                # 🔴 使用后立即禁用，后续不再使用支撑/阻力线
                self.can_use_support_resistance_stop = False
                print(f"    ⚠️  【首次使用支撑线止损】后续将只使用VIDYA带宽")
            
            # 止损只能向上移动（锁定利润）
            if new_stop_loss > old_stop_loss:
                self.stop_loss_level = new_stop_loss
                move_pct = ((new_stop_loss - old_stop_loss) / old_stop_loss) * 100
                print(f"    🔄 【VIDYA追踪止损】多单止损: ${old_stop_loss:.2f} → ${new_stop_loss:.2f} (+{move_pct:.2f}%)")
                
                if lower_band is not None:
                    print(f"        📏 基于下轨{lower_band:.2f}")
                elif support_level is not None:
                    print(f"        📈 基于支撑线{support_level:.2f}下方0.5%")
        
        elif self.position == 'short':
            # 🔴 空单追踪止损：优先使用上轨，其次使用阻力线（仅趋势转变后第一次）
            if upper_band is not None:
                # 使用上轨作为止损
                new_stop_loss = upper_band
            elif self.can_use_support_resistance_stop and resistance_level is not None and resistance_level > self.entry_price:
                # 只有当允许使用阻力线 且 阻力线高于开仓价格时才使用
                new_stop_loss = resistance_level * 1.005
                # 🔴 使用后立即禁用，后续不再使用支撑/阻力线
                self.can_use_support_resistance_stop = False
                print(f"    ⚠️  【首次使用阻力线止损】后续将只使用VIDYA带宽")
            
            # 止损只能向下移动（锁定利润）
            if new_stop_loss < old_stop_loss:
                self.stop_loss_level = new_stop_loss
                move_pct = ((old_stop_loss - new_stop_loss) / old_stop_loss) * 100
                print(f"    🔄 【VIDYA追踪止损】空单止损: ${old_stop_loss:.2f} → ${new_stop_loss:.2f} (-{move_pct:.2f}%)")
                
                if upper_band is not None:
                    print(f"        📏 基于上轨{upper_band:.2f}")
                elif resistance_level is not None:
                    print(f"        📉 基于阻力线{resistance_level:.2f}上方0.5%")
    
    
    def _check_stop_position_trigger_1min(self, timestamp, open_price, high_price, low_price, close_price, signal_info):
        """基于1分钟K线检查平仓触发和开仓触发（新增：布林带角度每1分钟检查 + 目标价格开仓）"""
                
        # 🔴 优先检查持仓的平仓触发（必须先平仓才能开新仓）
        if self.position is not None and self.stop_loss_level is not None:
            # 检查平仓逻辑（下面的代码）
            self._check_close_position_trigger(timestamp, open_price, high_price, low_price, close_price, signal_info)
            # 如果平仓后，position会变成None，下面的开仓逻辑会被执行
        
        # 🆕 检查布林带角度开仓（每1分钟检查，但只有止盈后才会真正执行）
        if self.position is None and self.enable_bb_angle_entry:
            bb_angle_signal = self.bb_angle_calculator.get_entry_signal(
                current_position=self.position,
                current_time=timestamp,
                is_kline_end=False  # 🆕 标记为非整点检查（每1分钟）
            )
            
            # 只有通过时机检查（止盈后或整点）才会进入开仓逻辑
            if bb_angle_signal.get('can_check_now', False):
                if bb_angle_signal['can_open_long']:
                    reason = f"布林带角度开多（止盈后快速开仓） | {bb_angle_signal['reason']}"
                    print(f"  🟢 【布林带角度开多】{bb_angle_signal['reason']}")
                    self._execute_bb_angle_entry('long', close_price, signal_info, reason)
                    return  # 开仓后直接返回
                elif bb_angle_signal['can_open_short']:
                    reason = f"布林带角度开空（止盈后快速开仓） | {bb_angle_signal['reason']}"
                    print(f"  🔴 【布林带角度开空】{bb_angle_signal['reason']}")
                    self._execute_bb_angle_entry('short', close_price, signal_info, reason)
                    return  # 开仓后直接返回
        
        # 🔴 检查目标开仓价格触发（VIDYA支撑阻力位开仓，只在无持仓时执行）
        # 做多：价格 ≤ 支撑位；做空：价格 ≥ 阻力位
        if self.position is None and self.target_entry_price is not None and self.target_entry_direction is not None:
            price_hit_target = False
            
            # 判断触发条件
            if self.target_entry_direction == 'long':
                # 做多：价格回调到支撑位或以下
                price_hit_target = low_price <= self.target_entry_price
            elif self.target_entry_direction == 'short':
                # 做空：价格反弹到阻力位或以上
                price_hit_target = high_price >= self.target_entry_price
            else:
                # 无效的方向，不触发
                price_hit_target = False
            
            if price_hit_target:
                if self.target_entry_direction == 'long':
                    print(f"  ✅ 【触发开仓】最低价格${low_price:.2f} ≤ 目标支撑位${self.target_entry_price:.2f}")
                    print(f"  🟢 【开多】价格回调至支撑位${self.target_entry_price:.2f}")
                    self._execute_vidya_entry('long', self.target_entry_price, signal_info, self.target_entry_vidya_result)
                    # 清除目标
                    self.target_entry_price = None
                    self.target_entry_direction = None
                    self.target_entry_vidya_result = None
                    return
                
                elif self.target_entry_direction == 'short':
                    print(f"  ✅ 【触发开仓】最高价格${high_price:.2f} ≥ 目标阻力位${self.target_entry_price:.2f}")
                    print(f"  🔴 【开空】价格反弹至阻力位${self.target_entry_price:.2f}")
                    self._execute_vidya_entry('short', self.target_entry_price, signal_info, self.target_entry_vidya_result)
                    # 清除目标
                    self.target_entry_price = None
                    self.target_entry_direction = None
                    self.target_entry_vidya_result = None
                    return
    
    def _execute_bb_angle_entry(self, direction, entry_price, signal_info, reason):
        """
        执行布林带中轨角度独立开仓
        
        Args:
            direction: 'long' 或 'short'
            entry_price: 开仓价格（使用当前收盘价）
            signal_info: 信号信息字典
            reason: 开仓原因
        """
        if entry_price is None or entry_price <= 0:
            print(f"  ⚠️  【开仓价格无效】无法开仓：entry_price={entry_price}")
            return
        
        potential_invested_amount = self._get_invested_capital()
        if potential_invested_amount <= 0:
            print(f"  ⚠️  【资金不足】无法开仓：现金余额=${self.cash_balance:,.2f} <= 0")
            return
        
        # 计算止盈止损（使用固定百分比）
        if direction == 'long':
            # 做多止损：固定百分比
            stop_loss_price = entry_price * (1 - self.max_loss_pct / 100)
            
            # 做多止盈：固定百分比
            if self.fixed_take_profit_pct > 0:
                take_profit_price = entry_price * (1 + self.fixed_take_profit_pct / 100)
            else:
                take_profit_price = None
        else:
            # 做空止损：固定百分比
            stop_loss_price = entry_price * (1 + self.max_loss_pct / 100)
            
            # 做空止盈：固定百分比
            if self.fixed_take_profit_pct > 0:
                take_profit_price = entry_price * (1 - self.fixed_take_profit_pct / 100)
            else:
                take_profit_price = None
        
        print(f"  🎯 【布林带角度开仓】{direction.upper()} | 价格: ${entry_price:.2f}")
        print(f"  🛡️ 止损: ${stop_loss_price:.2f} (固定{self.max_loss_pct}%)")
        print(f"  🎯 止盈: ${take_profit_price:.2f} (固定{self.fixed_take_profit_pct}%)")
        
        if direction == 'long':
            self._open_long_position(entry_price, signal_info, reason, potential_invested_amount, 
                                    stop_loss_price, take_profit_price)
        elif direction == 'short':
            self._open_short_position(entry_price, signal_info, reason, potential_invested_amount,
                                     stop_loss_price, take_profit_price)
    
    def _check_close_position_trigger(self, timestamp, open_price, high_price, low_price, close_price, signal_info):
        """检查平仓触发条件（从 _check_stop_position_trigger_1min 中提取）"""
        if self.position is None or self.stop_loss_level is None:
            return
        
        stop_loss_triggered = False
        
        # 🔴 检查平仓触发（固定止盈、最大亏损、VIDYA上下轨、EMA120平滑值）
        if self.position == 'long':
            # 1. 检查固定止盈（增强：Delta Volume优化）
            if self.take_profit_level is not None and high_price >= self.take_profit_level:
                # 获取当前固定周期Delta Volume百分比
                current_dv_percent = self.vidya_indicator.delta_volume_percent_fixed / 100.0  # 转换为小数
                
                # 🔴 如果正在等待DV目标
                if self.waiting_for_dv_target:
                    # 检查是否达到目标DV且价格仍然≥止盈位
                    if current_dv_percent >= self.target_dv_percent and close_price >= self.take_profit_level:
                        stop_loss_triggered = True
                        exit_price = close_price
                        reason = f"多单DV优化止盈 | 价格${close_price:.2f}≥止盈位${self.take_profit_level:.2f} | DV={current_dv_percent*100:.2f}%≥目标{self.target_dv_percent*100:.2f}%"
                        print(f"  ✅ 【DV目标达成】多单止盈：DV={current_dv_percent*100:.2f}% ≥ {self.target_dv_percent*100:.2f}%")
                        self.waiting_for_dv_target = False
                        self.target_dv_percent = None
                        self._close_position(exit_price, signal_info, timestamp, False, reason)
                    else:
                        print(f"  ⏳ 【等待DV目标】多单：当前DV={current_dv_percent*100:.2f}%，目标={self.target_dv_percent*100:.2f}%，价格=${high_price:.2f}")
                # 🔴 首次触及止盈位，检查DV是否满足条件
                elif current_dv_percent > self.dv_trigger_threshold:
                    # DV > 30%，设置目标DV = 120%，等待
                    self.waiting_for_dv_target = True
                    self.target_dv_percent = self.dv_target_threshold
                    print(f"  🎯 【设置DV目标】多单触及止盈位，DV={current_dv_percent*100:.2f}% > {self.dv_trigger_threshold*100:.0f}%，等待DV≥{self.dv_target_threshold*100:.0f}%")
                else:
                    # DV ≤ 30%，直接止盈
                    stop_loss_triggered = True
                    exit_price = self.take_profit_level
                    reason = f"多单固定止盈 | 价格${high_price:.2f}≥止盈位${self.take_profit_level:.2f} | DV={current_dv_percent*100:.2f}%≤{self.dv_trigger_threshold*100:.0f}%"
                    print(f"  ✅ 【直接止盈】多单：DV={current_dv_percent*100:.2f}% ≤ {self.dv_trigger_threshold*100:.0f}%")
                    self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 2. 检查下轨平仓（多单使用下轨）
            elif self.current_lower_band is not None and low_price <= self.current_lower_band:
                stop_loss_triggered = True
                exit_price = self.current_lower_band
                profit_loss = self.position_shares * (exit_price - self.entry_price) if self.position_shares else 0
                result_type = "盈利平仓" if profit_loss > 0 else "亏损平仓"
                reason = f"多单VIDYA下轨{result_type} | 条件：价格${low_price:.2f}≤下轨${self.current_lower_band:.2f} | 价格来源：1分钟最低价触及下轨"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 3. 检查最大亏损保护
            elif self.max_loss_level is not None and low_price <= self.max_loss_level:
                stop_loss_triggered = True
                exit_price = self.max_loss_level
                reason = f"多单最大亏损保护 | 条件：价格${low_price:.2f}≤最大亏损位${self.max_loss_level:.2f} | 价格来源：1分钟最低价触及最大亏损位"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 4. 🆕 检查EMA120平滑值止损（仅亏损且超过fixed_take_profit_pct时平仓）
            elif self.current_ema_120_smoothed is not None and low_price <= self.current_ema_120_smoothed:
                exit_price = self.current_ema_120_smoothed
                profit_loss = self.position_shares * (exit_price - self.entry_price) if self.position_shares else 0
                loss_pct = (profit_loss / self.current_invested_amount * 100) if self.current_invested_amount else 0
                # 🔴 只在亏损且亏损超过fixed_take_profit_pct时平仓
                if profit_loss < 0:
                    stop_loss_triggered = True
                    reason = f"多单EMA120平滑值止损 | 条件：价格${low_price:.2f}≤EMA120=${self.current_ema_120_smoothed:.2f} | 亏损${profit_loss:.2f}({loss_pct:.2f}%) > {self.fixed_take_profit_pct}%"
                    print(f"  ❌ 【EMA120止损】多单亏损{loss_pct:.2f}% > {self.fixed_take_profit_pct}%，触发止损")
                    self._close_position(exit_price, signal_info, timestamp, False, reason)
                elif profit_loss < 0:
                    print(f"  ⏳ 【EMA120触及】多单亏损{loss_pct:.2f}% ≤ {self.fixed_take_profit_pct}%，未达到止损阈值，继续持仓")
                else:
                    print(f"  ⏭️  【EMA120触及】多单盈利${profit_loss:.2f}，不触发止损，继续持仓")
        
        elif self.position == 'short':
            # 1. 检查固定止盈（增强：Delta Volume优化）
            if self.take_profit_level is not None and low_price <= self.take_profit_level:
                # 获取当前固定周期Delta Volume百分比
                current_dv_percent = self.vidya_indicator.delta_volume_percent_fixed / 100.0  # 转换为小数
                
                # 🔴 如果正在等待DV目标
                if self.waiting_for_dv_target:
                    # 检查是否达到目标DV且价格仍然≤止盈位
                    if current_dv_percent <= self.target_dv_percent and close_price <= self.take_profit_level:
                        stop_loss_triggered = True
                        exit_price = close_price
                        reason = f"空单DV优化止盈 | 价格${close_price:.2f}≤止盈位${self.take_profit_level:.2f} | DV={current_dv_percent*100:.2f}%≤目标{self.target_dv_percent*100:.2f}%"
                        print(f"  ✅ 【DV目标达成】空单止盈：DV={current_dv_percent*100:.2f}% ≤ {self.target_dv_percent*100:.2f}%")
                        self.waiting_for_dv_target = False
                        self.target_dv_percent = None
                        self._close_position(exit_price, signal_info, timestamp, False, reason)
                    else:
                        print(f"  ⏳ 【等待DV目标】空单：当前DV={current_dv_percent*100:.2f}%，目标={self.target_dv_percent*100:.2f}%，价格=${low_price:.2f}")
                # 🔴 首次触及止盈位，检查DV是否满足条件
                elif current_dv_percent < -self.dv_trigger_threshold:
                    # DV < -30%，设置目标DV = -120%，等待
                    self.waiting_for_dv_target = True
                    self.target_dv_percent = -self.dv_target_threshold
                    print(f"  🎯 【设置DV目标】空单触及止盈位，DV={current_dv_percent*100:.2f}% < -{self.dv_trigger_threshold*100:.0f}%，等待DV≤-{self.dv_target_threshold*100:.0f}%")
                else:
                    # DV ≥ -30%，直接止盈
                    stop_loss_triggered = True
                    exit_price = self.take_profit_level
                    reason = f"空单固定止盈 | 价格${low_price:.2f}≤止盈位${self.take_profit_level:.2f} | DV={current_dv_percent*100:.2f}%≥-{self.dv_trigger_threshold*100:.0f}%"
                    print(f"  ✅ 【直接止盈】空单：DV={current_dv_percent*100:.2f}% ≥ -{self.dv_trigger_threshold*100:.0f}%")
                    self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 2. 检查上轨平仓（空单使用上轨）
            elif self.current_upper_band is not None and high_price >= self.current_upper_band:
                stop_loss_triggered = True
                exit_price = self.current_upper_band
                profit_loss = self.position_shares * (self.entry_price - exit_price) if self.position_shares else 0
                result_type = "盈利平仓" if profit_loss > 0 else "亏损平仓"
                reason = f"空单VIDYA上轨{result_type} | 条件：价格${high_price:.2f}≥上轨${self.current_upper_band:.2f} | 价格来源：1分钟最高价触及上轨"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 3. 检查最大亏损保护
            elif self.max_loss_level is not None and high_price >= self.max_loss_level:
                stop_loss_triggered = True
                exit_price = self.max_loss_level
                reason = f"空单最大亏损保护 | 条件：价格${high_price:.2f}≥最大亏损位${self.max_loss_level:.2f} | 价格来源：1分钟最高价触及最大亏损位"
                self._close_position(exit_price, signal_info, timestamp, False, reason)
            # 4. 🆕 检查EMA120平滑值止损（仅亏损且超过fixed_take_profit_pct时平仓）
            elif self.current_ema_120_smoothed is not None and high_price >= self.current_ema_120_smoothed:
                exit_price = self.current_ema_120_smoothed
                profit_loss = self.position_shares * (self.entry_price - exit_price) if self.position_shares else 0
                loss_pct = (profit_loss / self.current_invested_amount * 100) if self.current_invested_amount else 0
                # 🔴 只在亏损且亏损超过fixed_take_profit_pct时平仓
                if profit_loss < 0:
                    stop_loss_triggered = True
                    reason = f"空单EMA120平滑值止损 | 条件：价格${high_price:.2f}≥EMA120=${self.current_ema_120_smoothed:.2f} | 亏损${profit_loss:.2f}({loss_pct:.2f}%) > {self.fixed_take_profit_pct}%"
                    print(f"  ❌ 【EMA120止损】空单亏损{loss_pct:.2f}% > {self.fixed_take_profit_pct}%，触发止损")
                    self._close_position(exit_price, signal_info, timestamp, False, reason)
                elif profit_loss < 0:
                    print(f"  ⏳ 【EMA120触及】空单亏损{loss_pct:.2f}% ≤ {self.fixed_take_profit_pct}%，未达到止损阈值，继续持仓")
                else:
                    print(f"  ⏭️  【EMA120触及】空单盈利${profit_loss:.2f}，不触发止损，继续持仓")
    
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
        elif '最大亏损' in reason:
            signal_type = 'MAX_STOP_LOSS_LONG' if self.position == 'long' else 'MAX_STOP_LOSS_SHORT'
        
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
        
        # 🆕 判断平仓类型，设置布林带角度锁定状态
        is_profit = profit_loss > 0
        
        if is_profit:
            # 🔓 止盈：解锁，下一个整点立即可开仓
            self.bb_angle_calculator.unlock_after_take_profit()
        else:
            # 🔒 止损：锁定5个周期（包含当前周期，实际等待4个完整周期）
            timeframe_minutes = timeframe_to_minutes(self.timeframe)
            self.bb_angle_calculator.set_lock_after_stop_loss(
                exit_timestamp, 
                timeframe_minutes
            )
        
        # 重置交易状态
        self.position = None
        self.entry_price = None
        self.stop_loss_level = None
        self.take_profit_level = None
        self.max_loss_level = None
        self.current_invested_amount = None
        self.position_shares = None
        self.position_entries = []  # 🔴 清空加仓记录
        
        # 🔴 清除目标开仓价格（平仓后可能需要重新设置）
        self.target_entry_price = None
        self.target_entry_direction = None
        self.target_entry_vidya_result = None
        
        # 🔴 清除Delta Volume等待状态
        self.waiting_for_dv_target = False
        self.target_dv_percent = None
    
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
    
    def get_current_status(self):
        """获取当前纯VIDYA策略状态"""
        return {
            'position': self.position,
            'entry_price': self.entry_price,
            'stop_loss_level': self.stop_loss_level,
            'take_profit_level': self.take_profit_level,
            'max_loss_level': self.max_loss_level,
            'timeframe': self.timeframe,
            'position_shares': self.position_shares,
            'volatility_info': self.volatility_calculator.get_volatility_info(),
            # 🔴 VIDYA信息
            'vidya_value': self.vidya_indicator.current_vidya,
            'vidya_trend': self.vidya_indicator.current_trend,
            'vidya_cmo': self._calculate_cmo(self.vidya_indicator.close_history, self.vidya_indicator.vidya_momentum) if len(self.vidya_indicator.close_history) > 0 else 0,
            'vidya_delta_volume': self.vidya_indicator.delta_volume
        }
    
    def _calculate_cmo(self, prices, period):
        """辅助方法：计算CMO"""
        if len(prices) < period + 1:
            return 0.0
        changes = []
        for i in range(len(prices) - period, len(prices)):
            if i > 0:
                changes.append(prices[i] - prices[i-1])
        if not changes:
            return 0.0
        sum_pos = sum(max(c, 0) for c in changes)
        sum_neg = sum(max(-c, 0) for c in changes)
        total = sum_pos + sum_neg
        if total == 0:
            return 0.0
        return abs(100 * (sum_pos - sum_neg) / total)
    
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
            self.max_loss_level = trade_data['stop_loss_price']  # 同步到最大亏损位
        
        if trade_data.get('take_profit_price'):
            self.take_profit_level = trade_data['take_profit_price']
        
        # 更新现金余额（扣除投入金额）
        if self.position and trade_data.get('invested_amount'):
            self.cash_balance -= trade_data['invested_amount']
        
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
        self.max_loss_level = new_stop_loss_price  # 同步到最大亏损位
        
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
        self.max_loss_level = None
        self.current_invested_amount = 0
        
        print(f"✅ 持仓平仓完成")
    
    def get_current_status(self):
        """获取当前VIDYA策略状态"""
        return {
            'position': self.position,
            'entry_price': self.entry_price,
            'stop_loss_level': self.stop_loss_level,
            'take_profit_level': self.take_profit_level,
            'max_loss_level': self.max_loss_level,
            'sar_value': None,  # VIDYA策略没有SAR，返回None
            'timeframe': self.timeframe,
            'current_trend_direction': self.current_trend_direction,
            'previous_trend_direction': self.previous_trend_direction,
            'position_shares': self.position_shares,
            'current_invested_amount': self.current_invested_amount,
            'volatility_info': self.volatility_calculator.get_volatility_info() if hasattr(self, 'volatility_calculator') else {}
        }