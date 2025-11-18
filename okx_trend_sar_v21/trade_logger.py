#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
交易日志记录系统
记录所有交易信号、执行结果和异常
"""

import os
import json
from datetime import datetime


class TradeLogger:
    """交易日志记录器"""
    
    def __init__(self, log_dir='live_trade_logs'):
        """初始化日志记录器
        
        Args:
            log_dir: 日志目录
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # 创建今日日志文件
        today = datetime.now().strftime('%Y%m%d')
        self.log_file = os.path.join(log_dir, f'trade_log_{today}.txt')
        self.json_log_file = os.path.join(log_dir, f'trade_log_{today}.json')
        
        # 日志记录列表
        self.logs = []
        
        print(f"📝 日志文件: {self.log_file}")
    
    def log(self, message, level='INFO'):
        """记录日志
        
        Args:
            message: 日志消息
            level: 日志级别（INFO, WARNING, ERROR）
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        # 打印到控制台
        print(log_entry)
        
        # 写入文件
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\n')
    
    def log_signal(self, signal):
        """记录交易信号
        
        Args:
            signal: 交易信号字典
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        log_entry = {
            'timestamp': timestamp,
            'type': 'signal',
            'data': signal
        }
        
        self.logs.append(log_entry)
        
        # 写入JSON文件
        with open(self.json_log_file, 'w', encoding='utf-8') as f:
            json.dump(self.logs, f, indent=2, ensure_ascii=False, default=str)
        
        # 写入文本日志
        price_info = f"价格: ${signal['price']:.2f} | " if 'price' in signal else ""
        self.log(f"交易信号: {signal['type']} | {price_info}{signal.get('reason', '')}", 'SIGNAL')
    
    def log_trade(self, trade_info):
        """记录交易执行结果
        
        Args:
            trade_info: 交易信息
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        log_entry = {
            'timestamp': timestamp,
            'type': 'trade',
            'data': trade_info
        }
        
        self.logs.append(log_entry)
        
        # 写入JSON文件
        with open(self.json_log_file, 'w', encoding='utf-8') as f:
            json.dump(self.logs, f, indent=2, ensure_ascii=False, default=str)
    
    def log_error(self, error_message):
        """记录错误
        
        Args:
            error_message: 错误消息
        """
        self.log(error_message, 'ERROR')
    
    def log_warning(self, warning_message):
        """记录警告
        
        Args:
            warning_message: 警告消息
        """
        self.log(warning_message, 'WARNING')
    
    def get_today_stats(self):
        """获取今日交易统计
        
        Returns:
            dict: 统计信息
        """
        signals = [log for log in self.logs if log['type'] == 'signal']
        trades = [log for log in self.logs if log['type'] == 'trade']
        
        return {
            'total_signals': len(signals),
            'total_trades': len(trades),
            'log_file': self.log_file,
            'json_file': self.json_log_file
        }

