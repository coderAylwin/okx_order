#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
趋势滤波策略 - 绩效分析模块
功能：净值曲线、回撤分析、收益率折现图
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.axis import DateAxis
import os
import base64
from io import BytesIO

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class PerformanceAnalyzer:
    """绩效分析器"""
    
    def __init__(self, config):
        """
        初始化分析器
        :param config: 策略配置
        """
        self.config = config
        self.initial_capital = config['initial_capital']
        self.total_initial_capital = self.initial_capital
        
        # 净值数据
        self.daily_nav = []
        self.daily_returns = []
        self.max_drawdown_info = {}
        
    def calculate_daily_nav(self, trades_data, price_data):
        """
        计算每日净值
        :param trades_data: 交易记录列表
        :param price_data: 价格数据 [(timestamp, open, high, low, close), ...]
        :return: 每日净值DataFrame
        """
        print("📊 开始计算每日净值...")
        
        # 转换价格数据为DataFrame
        price_df = pd.DataFrame(price_data, columns=['timestamp', 'open', 'high', 'low', 'close'])
        price_df['timestamp'] = pd.to_datetime(price_df['timestamp'])
        price_df['date'] = price_df['timestamp'].dt.date
        
        # 获取每日收盘价（00:00的价格作为当日收盘价）
        daily_prices = price_df.groupby('date').agg({
            'close': 'last',  # 取当日最后一个价格
            'timestamp': 'max'
        }).reset_index()
        
        # 转换交易数据为DataFrame
        trades_df = pd.DataFrame(trades_data)
        if not trades_df.empty:
            trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
            trades_df['date'] = trades_df['timestamp'].dt.date
        
        # 初始化账户状态
        cash_balance = self.initial_capital
        current_position = None
        position_entry_price = 0
        position_amount = 0
        position_shares = 0  # 💎 添加份额跟踪
        
        nav_records = []
        
        for _, day_data in daily_prices.iterrows():
            current_date = day_data['date']
            current_price = day_data['close']
            
            # 处理当日的交易
            day_trades = trades_df[trades_df['date'] == current_date] if not trades_df.empty else pd.DataFrame()
            
            for _, trade in day_trades.iterrows():
                if trade['signal_type'] in ['OPEN_LONG', 'OPEN_SHORT']:
                    # 开仓
                    direction = 'long' if 'LONG' in trade['signal_type'] else 'short'
                    current_position = direction
                    position_entry_price = trade['price']
                    position_amount = trade.get('invested_amount', 0)
                    position_shares = trade.get('position_shares', 0)  # 💎 记录份额
                    
                    # 开仓时：现金减少，持仓增加（单账户模式）
                    cash_balance -= position_amount
                    
                    print(f"    🔓 开仓: {direction} | 价格: ${position_entry_price:.2f} | 投入: ${position_amount:,.2f} | 份额: {position_shares:.4f}")
                    print(f"        现金更新: 余额=${cash_balance:,.2f}")
                        
                elif trade['signal_type'] in ['STOP_LOSS_LONG', 'STOP_LOSS_SHORT', 'TAKE_PROFIT_LONG', 'TAKE_PROFIT_SHORT',
                                             'MA_PROFIT_LONG', 'MA_LOSS_LONG', 'MA_PROFIT_SHORT', 'MA_LOSS_SHORT',
                                             'MAX_STOP_LOSS_LONG', 'MAX_STOP_LOSS_SHORT']:
                    # 平仓时：持仓清零，现金增加（本金+盈亏）
                    exit_price = trade['price']
                    profit_loss = trade.get('profit_loss', 0)
                    position_amount = trade.get('invested_amount', 0)
                    # 💰 平仓回收：使用实际市值计算
                    # 实际回收金额 = 份额 × 平仓价格
                    actual_return = position_shares * exit_price
                    
                    # 单账户模式：平仓资金回到统一账户
                    cash_balance += position_amount
                    
                    print(f"    🔒 平仓: {current_position} | 价格: ${exit_price:.2f} | 份额: {position_shares:.4f} | 盈亏: ${profit_loss:+.2f}")
                    print(f"        💎 市值计算: {position_shares:.4f} × ${exit_price:.2f} = ${actual_return:,.2f}")
                    print(f"        💰 资金回收: 实际市值${actual_return:,.2f}")
                    print(f"        现金更新: 余额=${cash_balance:,.2f}")
                    
                    # 清空持仓
                    current_position = None
                    position_entry_price = 0
                    position_amount = 0
                    position_shares = 0
            
            # 计算持仓价值
            position_value = 0
            if current_position and position_shares > 0:
                # 💎 使用份额计算持仓价值：份额 × 当前价格
                position_value = position_shares * current_price
                total_nav = cash_balance + position_value
                print(f"  📊 持仓价值: {position_shares:.4f} × ${current_price:.2f} = ${position_value:,.2f}")
            else:
                # 无持仓（单账户模式）
                position_value = 0
                total_nav = cash_balance
            
            # 记录净值
            nav_record = {
                'date': current_date,
                'timestamp': day_data['timestamp'],
                'price': current_price,
                'cash_balance': cash_balance,
                'position': current_position,
                'position_entry_price': position_entry_price,
                'position_amount': position_amount,
                'position_value': position_value,
                'total_nav': total_nav,
                'daily_return': 0  # 将在后面计算
            }
            nav_records.append(nav_record)
            
            # 调试信息
            if current_position:
                print(f"📅 {current_date} | 价格: ${current_price:.2f} | 💎{current_position}持仓: {position_shares:.4f}份额 × ${current_price:.2f} = ${position_value:,.2f} | 净值: ${total_nav:,.2f}")
            else:
                print(f"📅 {current_date} | 价格: ${current_price:.2f} | ⚪空仓 | 净值: ${total_nav:,.2f}")
        
        # 转换为DataFrame并计算日收益率
        nav_df = pd.DataFrame(nav_records)
        if len(nav_df) > 1:
            nav_df['daily_return'] = nav_df['total_nav'].pct_change().fillna(0)
            nav_df['cumulative_return'] = (nav_df['total_nav'] / self.total_initial_capital - 1) * 100
        
        self.daily_nav = nav_df
        return nav_df
    
    def calculate_drawdown(self, nav_df):
        """
        计算回撤
        :param nav_df: 净值DataFrame
        :return: 包含回撤信息的DataFrame
        """
        print("📉 开始计算回撤...")
        
        if nav_df.empty:
            return nav_df
        
        # 计算累计最高净值
        nav_df['peak_nav'] = nav_df['total_nav'].expanding().max()
        
        # 计算回撤
        nav_df['drawdown'] = (nav_df['total_nav'] - nav_df['peak_nav']) / nav_df['peak_nav'] * 100
        
        # 找出最大回撤
        max_dd_idx = nav_df['drawdown'].idxmin()
        max_drawdown = nav_df.loc[max_dd_idx, 'drawdown']
        max_dd_date = nav_df.loc[max_dd_idx, 'date']
        
        # 找出最大回撤的峰值日期
        peak_nav_before_max_dd = nav_df.loc[:max_dd_idx, 'peak_nav'].iloc[-1]
        peak_date_idx = nav_df[nav_df['total_nav'] == peak_nav_before_max_dd].index[0]
        peak_date = nav_df.loc[peak_date_idx, 'date']
        
        self.max_drawdown_info = {
            'max_drawdown': max_drawdown,
            'max_dd_date': max_dd_date,
            'peak_date': peak_date,
            'peak_nav': peak_nav_before_max_dd,
            'valley_nav': nav_df.loc[max_dd_idx, 'total_nav']
        }
        
        print(f"📉 最大回撤: {max_drawdown:.2f}% ({peak_date} -> {max_dd_date})")
        print(f"    峰值净值: ${peak_nav_before_max_dd:,.2f} -> 谷值净值: ${nav_df.loc[max_dd_idx, 'total_nav']:,.2f}")
        
        return nav_df
    
    def generate_performance_charts(self, nav_df, output_dir="trend_filter/performance_charts"):
        """
        生成绩效图表
        :param nav_df: 净值DataFrame
        :param output_dir: 输出目录
        """
        print("📈 开始生成绩效图表...")
        
        if nav_df.empty:
            print("⚠️  没有净值数据，无法生成图表")
            return
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. 净值曲线图
        plt.figure(figsize=(15, 10))
        
        # 子图1：净值曲线
        plt.subplot(3, 1, 1)
        plt.plot(nav_df['date'], nav_df['total_nav'], 'b-', linewidth=2, label='净值曲线')
        plt.axhline(y=self.total_initial_capital, color='gray', linestyle='--', alpha=0.7, label='初始资金')
        plt.title(f'📈 净值曲线 (初始资金: ${self.total_initial_capital:,.0f})', fontsize=14, fontweight='bold')
        plt.ylabel('净值 ($)', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # 子图2：累计收益率
        plt.subplot(3, 1, 2)
        plt.plot(nav_df['date'], nav_df['cumulative_return'], 'g-', linewidth=2, label='累计收益率')
        plt.axhline(y=0, color='gray', linestyle='--', alpha=0.7)
        plt.title('📊 累计收益率', fontsize=14, fontweight='bold')
        plt.ylabel('收益率 (%)', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # 子图3：回撤曲线
        plt.subplot(3, 1, 3)
        plt.fill_between(nav_df['date'], nav_df['drawdown'], 0, color='red', alpha=0.3, label='回撤区域')
        plt.plot(nav_df['date'], nav_df['drawdown'], 'r-', linewidth=2, label='回撤曲线')
        
        # 标记最大回撤点
        if self.max_drawdown_info:
            max_dd_date = self.max_drawdown_info['max_dd_date']
            max_dd_value = self.max_drawdown_info['max_drawdown']
            plt.scatter([max_dd_date], [max_dd_value], color='red', s=100, zorder=5)
            plt.annotate(f'最大回撤: {max_dd_value:.2f}%', 
                        xy=(max_dd_date, max_dd_value), 
                        xytext=(10, 10), textcoords='offset points',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7),
                        arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
        
        plt.title('📉 回撤分析', fontsize=14, fontweight='bold')
        plt.ylabel('回撤 (%)', fontsize=12)
        plt.xlabel('日期', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # 调整布局并保存
        plt.tight_layout()
        chart_file = os.path.join(output_dir, '绩效分析图表.png')
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"📈 绩效图表已保存: {chart_file}")
        
        # 2. 资金分布饼图
        plt.figure(figsize=(10, 8))
        
        final_nav = nav_df.iloc[-1]
        labels = ['现金余额']
        sizes = [final_nav['cash_balance']]
        colors = ['lightblue']
        
        if final_nav['position_value'] > 0:
            if final_nav['position'] == 'long':
                labels.append('做多持仓')
                colors.append('darkgreen')
            else:
                labels.append('做空持仓')
                colors.append('darkred')
            sizes.append(final_nav['position_value'])
        
        plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        plt.title(f'💰 最终资金分布 (总净值: ${final_nav["total_nav"]:,.2f})', fontsize=14, fontweight='bold')
        
        pie_file = os.path.join(output_dir, '资金分布图.png')
        plt.savefig(pie_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"💰 资金分布图已保存: {pie_file}")
        
        return chart_file, pie_file
    
    def generate_performance_excel(self, nav_df, output_dir="trend_filter/performance_charts"):
        """
        生成绩效Excel报告
        :param nav_df: 净值DataFrame
        :param output_dir: 输出目录
        """
        print("📋 开始生成绩效Excel报告...")
        
        if nav_df.empty:
            print("⚠️  没有净值数据，无法生成Excel报告")
            return None
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 创建Excel文件（去掉时间戳）
        excel_file = os.path.join(output_dir, '绩效报告.xlsx')
        
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            # 1. 每日净值明细
            nav_export = nav_df.copy()
            nav_export['date'] = nav_export['date'].astype(str)
            nav_export['timestamp'] = nav_export['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # 格式化数值列
            for col in ['price', 'cash_balance', 'position_entry_price', 'position_amount', 'position_value', 'total_nav']:
                if col in nav_export.columns:
                    nav_export[col] = nav_export[col].round(2)
            
            nav_export['daily_return'] = (nav_export['daily_return'] * 100).round(4)
            nav_export['cumulative_return'] = nav_export['cumulative_return'].round(2)
            nav_export['drawdown'] = nav_export['drawdown'].round(2)
            
            # 重命名列
            nav_export = nav_export.rename(columns={
                'date': '日期',
                'timestamp': '时间戳',
                'price': '当日价格',
                'cash_balance': '现金余额',
                'position': '持仓方向',
                'position_entry_price': '持仓开仓价',
                'position_amount': '持仓金额',
                'position_value': '持仓价值',
                'total_nav': '总净值',
                'daily_return': '日收益率(%)',
                'cumulative_return': '累计收益率(%)',
                'peak_nav': '历史最高净值',
                'drawdown': '回撤(%)'
            })
            
            nav_export.to_excel(writer, sheet_name='每日净值明细', index=False)
            
            # 2. 绩效统计汇总
            stats_data = []
            
            # 基础统计 - 修复：使用配置的初始资金
            actual_initial_nav = self.initial_capital
            final_nav = nav_df.iloc[-1]['total_nav']
            total_return = (final_nav / actual_initial_nav - 1) * 100
            
            # 计算实际时间跨度
            start_date = nav_df.iloc[0]['date']
            end_date = nav_df.iloc[-1]['date']
            if hasattr(start_date, 'date'):
                start_date = start_date.date()
            if hasattr(end_date, 'date'):  
                end_date = end_date.date()
            actual_days = (end_date - start_date).days + 1
            
            stats_data.extend([
                ['策略名称', 'Trend SAR 趋势策略'],
                ['回测期间', f"{nav_df.iloc[0]['date']} 至 {nav_df.iloc[-1]['date']}"],
                ['数据点数量', len(nav_df)],
                ['实际天数', f"{actual_days} 天"],
                ['年化基准', '365天/年'],
                ['', ''],
                ['💰 资金统计', ''],
                ['初始资金', f"${actual_initial_nav:,.2f}"],
                ['最终净值', f"${final_nav:,.2f}"],
                ['总收益', f"${final_nav - actual_initial_nav:,.2f}"],
                ['总收益率', f"{total_return:+.2f}%"],
                ['', ''],
                ['📊 收益统计', ''],
                ['最高净值', f"${nav_df['total_nav'].max():,.2f}"],
                ['最低净值', f"${nav_df['total_nav'].min():,.2f}"],
                ['平均日收益率', f"{nav_df['daily_return'].mean() * 100:.4f}%"],
                ['收益率标准差', f"{nav_df['daily_return'].std() * 100:.4f}%"],
                ['', ''],
                ['📉 风险统计', ''],
                ['最大回撤', f"{self.max_drawdown_info.get('max_drawdown', 0):.2f}%"],
                ['最大回撤开始日期', str(self.max_drawdown_info.get('peak_date', ''))],
                ['最大回撤结束日期', str(self.max_drawdown_info.get('max_dd_date', ''))],
                ['回撤天数', ''], # TODO: 计算回撤恢复天数
                ['', ''],
                ['📈 策略参数', ''],
                ['交易币种', self.config.get('long_coin', '')],
                ['时间周期', self.config.get('trend_filter_timeframe', '')],
                ['滤波器长度', str(self.config.get('trend_filter_length', ''))],
                ['阻尼系数', str(self.config.get('trend_filter_damping', ''))],
                ['连续阈值', str(self.config.get('trend_filter_rising_falling', ''))],
                ['止盈比例', f"{self.config.get('fixed_take_profit_pct', 0)}%"],
            ])
            
            stats_df = pd.DataFrame(stats_data, columns=['指标', '数值'])
            stats_df.to_excel(writer, sheet_name='绩效统计汇总', index=False)
        
        print(f"📋 绩效Excel报告已保存: {excel_file}")
        return excel_file
    
    def calculate_performance_metrics(self, nav_df, trades_data=None):
        """
        计算详细的绩效指标
        :param nav_df: 净值DataFrame
        :param trades_data: 交易记录列表，用于计算胜率
        :return: 绩效指标字典
        """
        if nav_df.empty:
            return {}
        
        # 基础收益指标 - 修复：使用配置的初始资金作为基准
        actual_initial_nav = self.initial_capital  # 使用配置的初始资金
        final_nav = nav_df.iloc[-1]['total_nav']
        total_return = (final_nav / actual_initial_nav - 1) * 100
        
        # 简化调试信息
        print(f"🔍 净值计算结果:")
        print(f"   📅 回测期间: {nav_df.iloc[0]['date']} 至 {nav_df.iloc[-1]['date']}")
        print(f"   💰 初始资金: ${actual_initial_nav:,.2f}")
        print(f"   💎 最终净值: ${final_nav:,.2f}")
        print(f"   📊 总收益: ${final_nav - actual_initial_nav:,.2f}")
        print(f"   📈 总收益率: {total_return:.2f}%")
        
        # 年化收益率计算
        trading_days = len(nav_df)
        
        # 计算实际的时间跨度（自然日）
        start_date = nav_df.iloc[0]['date'] if hasattr(nav_df.iloc[0]['date'], 'date') else nav_df.iloc[0]['date']
        end_date = nav_df.iloc[-1]['date'] if hasattr(nav_df.iloc[-1]['date'], 'date') else nav_df.iloc[-1]['date']
        
        if hasattr(start_date, 'date'):
            start_date = start_date.date()
        if hasattr(end_date, 'date'):
            end_date = end_date.date()
            
        actual_days = (end_date - start_date).days + 1  # +1 包含结束日
        
        # 使用实际自然日计算年化收益率
        annualized_return = ((final_nav / actual_initial_nav) ** (365 / actual_days) - 1) * 100 if actual_days > 0 else 0
        
        # 风险指标
        daily_returns = nav_df['daily_return'].dropna()
        volatility = daily_returns.std() * np.sqrt(252) * 100  # 年化波动率
        
        # 夏普比率 (假设无风险利率为3%)
        risk_free_rate = 0.03
        if volatility > 0:
            sharpe_ratio = (annualized_return / 100 - risk_free_rate) / (volatility / 100)
        else:
            sharpe_ratio = 0
        
        # 最大回撤
        max_drawdown = self.max_drawdown_info.get('max_drawdown', 0)
        
        # 计算胜率相关指标
        win_rate = 0
        profit_loss_ratio = 0
        total_trades = 0
        winning_trades = 0
        losing_trades = 0
        total_profit = 0
        total_loss = 0
        
        if trades_data:
            # 筛选出平仓交易
            exit_trades = [trade for trade in trades_data if trade.get('signal_type') in [
                'STOP_LOSS_LONG', 'STOP_LOSS_SHORT', 'TAKE_PROFIT_LONG', 'TAKE_PROFIT_SHORT',
                'MA_PROFIT_LONG', 'MA_LOSS_LONG', 'MA_PROFIT_SHORT', 'MA_LOSS_SHORT',
                'MAX_STOP_LOSS_LONG', 'MAX_STOP_LOSS_SHORT'
            ]]
            
            total_trades = len(exit_trades)
            
            if total_trades > 0:
                for trade in exit_trades:
                    profit_loss = trade.get('profit_loss', 0)
                    if profit_loss > 0:
                        winning_trades += 1
                        total_profit += profit_loss
                    elif profit_loss < 0:
                        losing_trades += 1
                        total_loss += abs(profit_loss)
                
                # 计算胜率
                win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
                
                # 计算盈亏比
                if total_loss > 0:
                    profit_loss_ratio = total_profit / total_loss
                else:
                    profit_loss_ratio = float('inf') if total_profit > 0 else 0
        
        metrics = {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_loss_ratio': profit_loss_ratio,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'trading_days': trading_days,
            'actual_days': actual_days,
            'initial_nav': actual_initial_nav,
            'final_nav': final_nav
        }
        
        return metrics
    
    def generate_html_report(self, nav_df, long_coin="BTC", trades_data=None, config=None, output_dir="trend_filter/performance_charts"):
        """
        生成HTML绩效报告
        :param nav_df: 净值DataFrame
        :param long_coin: 币种名称，如 'BTC', 'ETH', 'SOL' 等
        :param trades_data: 交易记录列表，用于计算胜率
        :param config: 策略配置字典
        :param output_dir: 输出目录
        """
        print("🌐 开始生成HTML绩效报告...")
        
        if nav_df.empty:
            print("⚠️  没有净值数据，无法生成HTML报告")
            return None
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成图表数据JSON
        chart_data_json = self._generate_chart_data_json(nav_df)
        
        # 计算绩效指标
        metrics = self.calculate_performance_metrics(nav_df, trades_data)
        
        # 准备净值数据表格
        nav_table_html = self._generate_nav_table_html(nav_df)
        
        # HTML模板
        html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{long_coin} - SAR Single Period Trend Filter 策略绩效报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
    <style>
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        .header {{
            text-align: center;
            border-bottom: 3px solid #007bff;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #007bff;
            margin: 0;
            font-size: 2.5rem;
        }}
        .header p {{
            color: #666;
            margin: 10px 0 0 0;
            font-size: 1.1rem;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-card.positive {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }}
        .metric-card.negative {{
            background: linear-gradient(135deg, #fc466b 0%, #3f5efb 100%);
        }}
        .metric-value {{
            font-size: 2rem;
            font-weight: bold;
            margin: 10px 0;
        }}
        .metric-label {{
            font-size: 0.9rem;
            opacity: 0.9;
        }}
        .chart-container {{
            margin: 40px 0;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            padding: 20px;
        }}
        .chart-wrapper {{
            position: relative;
            height: 400px;
            margin: 20px 0;
        }}
        .chart-title {{
            text-align: center;
            color: #007bff;
            margin-bottom: 20px;
            font-size: 1.3rem;
            font-weight: bold;
        }}
        .section {{
            margin: 40px 0;
        }}
        .section h2 {{
            color: #007bff;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .nav-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            font-size: 0.9rem;
        }}
        .nav-table th, .nav-table td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: center;
        }}
        .nav-table th {{
            background-color: #007bff;
            color: white;
            font-weight: bold;
        }}
        .nav-table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        .nav-table tr:hover {{
            background-color: #f5f5f5;
        }}
        .summary-box {{
            background: #f8f9fa;
            border-left: 4px solid #007bff;
            padding: 20px;
            margin: 20px 0;
            border-radius: 5px;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 {long_coin} - SAR Single Period Trend Filter 策略绩效报告</h1>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>回测期间: {nav_df.iloc[0]['date']} 至 {nav_df.iloc[-1]['date']} ({metrics.get('actual_days', len(nav_df))} 天)</p>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card {'positive' if metrics.get('total_return', 0) > 0 else 'negative'}">
                <div class="metric-label">💰 总收益率</div>
                <div class="metric-value">{metrics.get('total_return', 0):+.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">📈 年化收益率</div>
                <div class="metric-value">{metrics.get('annualized_return', 0):+.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">⚠️ 最大回撤</div>
                <div class="metric-value">{metrics.get('max_drawdown', 0):.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🎯 夏普比率</div>
                <div class="metric-value">{metrics.get('sharpe_ratio', 0):.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">📉 年化波动率</div>
                <div class="metric-value">{metrics.get('volatility', 0):.2f}%</div>
            </div>
            <div class="metric-card {'positive' if metrics.get('win_rate', 0) > 50 else 'negative'}">
                <div class="metric-label">🎯 胜率</div>
                <div class="metric-value">{metrics.get('win_rate', 0):.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">📊 盈亏比</div>
                <div class="metric-value">{metrics.get('profit_loss_ratio', 0):.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">🔄 总交易次数</div>
                <div class="metric-value">{metrics.get('total_trades', 0)}</div>
            </div>
        </div>
        
        <div class="summary-box">
            <h3>📊 资金概览</h3>
            <p><strong>初始资金:</strong> ${self.total_initial_capital:,.2f}</p>
            <p><strong>最终净值:</strong> ${metrics.get('final_nav', 0):,.2f}</p>
            <p><strong>净盈亏:</strong> ${metrics.get('final_nav', 0) - self.total_initial_capital:,.2f}</p>
        </div>
        
        <div class="summary-box">
            <h3>📈 交易统计</h3>
            <p><strong>总交易次数:</strong> {metrics.get('total_trades', 0)} 次</p>
            <p><strong>盈利交易:</strong> {metrics.get('winning_trades', 0)} 次</p>
            <p><strong>亏损交易:</strong> {metrics.get('losing_trades', 0)} 次</p>
            <p><strong>胜率:</strong> {metrics.get('win_rate', 0):.1f}%</p>
            <p><strong>盈亏比:</strong> {metrics.get('profit_loss_ratio', 0):.2f}</p>
        </div>
        
        <div class="summary-box">
            <h3>⚙️ 策略配置</h3>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <h4>📊 单周期SAR策略参数</h4>
                    <p><strong>时间周期:</strong> {config.get('timeframe', 'N/A') if config else 'N/A'}</p>
                    <p><strong>指标周期:</strong> {config.get('length', 'N/A') if config else 'N/A'}</p>
                </div>
                <div>
                    <h4>🎯 SAR参数</h4>
                    <p><strong>起始值:</strong> {config.get('sar_start', 'N/A') if config else 'N/A'}</p>
                    <p><strong>递增值:</strong> {config.get('sar_increment', 'N/A') if config else 'N/A'}</p>
                    <p><strong>最大值:</strong> {config.get('sar_maximum', 'N/A') if config else 'N/A'}</p>
                </div>
            </div>
            <div style="margin-top: 15px;">
                <h4>💰 止盈止损配置</h4>
                <p><strong>固定止盈:</strong> {config.get('fixed_take_profit_pct', 'N/A') if config else 'N/A'}%</p>
                <p><strong>最大亏损:</strong> {config.get('max_loss_pct', 'N/A') if config else 'N/A'}%</p>
            </div>
        </div>
        
        <div class="chart-container">
            <h2>📈 绩效图表</h2>
            
            <div class="chart-title">💰 净值曲线</div>
            <div class="chart-wrapper">
                <canvas id="navChart"></canvas>
            </div>
            
            <div class="chart-title">📊 累计收益率</div>
            <div class="chart-wrapper">
                <canvas id="returnChart"></canvas>
            </div>
            
            <div class="chart-title">📉 回撤分析</div>
            <div class="chart-wrapper">
                <canvas id="drawdownChart"></canvas>
            </div>
        </div>
        
        <div class="section">
            <h2>📋 每日净值明细</h2>
            {nav_table_html}
        </div>
        
        <div class="footer">
            <p>🤖 由 SAR Single Period Trend Filter 策略自动生成</p>
        </div>
    </div>

    <script>
        // 图表数据
        const chartData = {chart_data_json};
        
        // 通用图表配置
        const commonOptions = {{
            responsive: true,
            maintainAspectRatio: false,
            interaction: {{
                intersect: false,
                mode: 'index'
            }},
            plugins: {{
                tooltip: {{
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: 'white',
                    bodyColor: 'white',
                    borderColor: '#007bff',
                    borderWidth: 1,
                    cornerRadius: 5,
                    displayColors: false,
                    callbacks: {{
                        title: function(context) {{
                            return '日期: ' + context[0].label;
                        }}
                    }}
                }},
                legend: {{
                    display: true,
                    position: 'top'
                }}
            }},
            scales: {{
                x: {{
                    type: 'category',
                    display: true,
                    title: {{
                        display: true,
                        text: '日期'
                    }},
                    grid: {{
                        display: true,
                        color: 'rgba(0,0,0,0.1)'
                    }}
                }},
                y: {{
                    display: true,
                    grid: {{
                        display: true,
                        color: 'rgba(0,0,0,0.1)'
                    }}
                }}
            }}
        }};

        // 1. 净值曲线图
        const navCtx = document.getElementById('navChart').getContext('2d');
        new Chart(navCtx, {{
            type: 'line',
            data: {{
                labels: chartData.dates,
                datasets: [
                    {{
                        label: '净值曲线',
                        data: chartData.nav_values,
                        borderColor: '#007bff',
                        backgroundColor: 'rgba(0, 123, 255, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 1,
                        pointHoverRadius: 5
                    }},
                    {{
                        label: '初始资金线',
                        data: Array(chartData.dates.length).fill(chartData.initial_capital),
                        borderColor: '#6c757d',
                        backgroundColor: 'transparent',
                        borderWidth: 1,
                        borderDash: [5, 5],
                        fill: false,
                        pointRadius: 0,
                        pointHoverRadius: 0
                    }}
                ]
            }},
            options: {{
                ...commonOptions,
                scales: {{
                    ...commonOptions.scales,
                    y: {{
                        ...commonOptions.scales.y,
                        title: {{
                            display: true,
                            text: '净值 ($)'
                        }},
                        ticks: {{
                            callback: function(value) {{
                                return '$' + value.toLocaleString();
                            }}
                        }}
                    }}
                }},
                plugins: {{
                    ...commonOptions.plugins,
                    tooltip: {{
                        ...commonOptions.plugins.tooltip,
                        callbacks: {{
                            ...commonOptions.plugins.tooltip.callbacks,
                            label: function(context) {{
                                if (context.datasetIndex === 0) {{
                                    return '净值: $' + context.parsed.y.toLocaleString();
                                }} else {{
                                    return '初始资金: $' + context.parsed.y.toLocaleString();
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        }});

        // 2. 累计收益率图
        const returnCtx = document.getElementById('returnChart').getContext('2d');
        new Chart(returnCtx, {{
            type: 'line',
            data: {{
                labels: chartData.dates,
                datasets: [
                    {{
                        label: '累计收益率',
                        data: chartData.cumulative_returns,
                        borderColor: '#28a745',
                        backgroundColor: 'rgba(40, 167, 69, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 1,
                        pointHoverRadius: 5
                    }},
                    {{
                        label: '零基准线',
                        data: Array(chartData.dates.length).fill(0),
                        borderColor: '#6c757d',
                        backgroundColor: 'transparent',
                        borderWidth: 1,
                        borderDash: [5, 5],
                        fill: false,
                        pointRadius: 0,
                        pointHoverRadius: 0
                    }}
                ]
            }},
            options: {{
                ...commonOptions,
                scales: {{
                    ...commonOptions.scales,
                    y: {{
                        ...commonOptions.scales.y,
                        title: {{
                            display: true,
                            text: '收益率 (%)'
                        }},
                        ticks: {{
                            callback: function(value) {{
                                return value.toFixed(1) + '%';
                            }}
                        }}
                    }}
                }},
                plugins: {{
                    ...commonOptions.plugins,
                    tooltip: {{
                        ...commonOptions.plugins.tooltip,
                        callbacks: {{
                            ...commonOptions.plugins.tooltip.callbacks,
                            label: function(context) {{
                                if (context.datasetIndex === 0) {{
                                    return '累计收益率: ' + context.parsed.y.toFixed(2) + '%';
                                }} else {{
                                    return '零基准线: 0%';
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        }});

        // 3. 回撤分析图
        const drawdownCtx = document.getElementById('drawdownChart').getContext('2d');
        const drawdownChart = new Chart(drawdownCtx, {{
            type: 'line',
            data: {{
                labels: chartData.dates,
                datasets: [
                    {{
                        label: '回撤曲线',
                        data: chartData.drawdowns,
                        borderColor: '#dc3545',
                        backgroundColor: 'rgba(220, 53, 69, 0.2)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 1,
                        pointHoverRadius: 5
                    }}
                ]
            }},
            options: {{
                ...commonOptions,
                scales: {{
                    ...commonOptions.scales,
                    y: {{
                        ...commonOptions.scales.y,
                        title: {{
                            display: true,
                            text: '回撤 (%)'
                        }},
                        max: 0,
                        ticks: {{
                            callback: function(value) {{
                                return value.toFixed(1) + '%';
                            }}
                        }}
                    }}
                }},
                plugins: {{
                    ...commonOptions.plugins,
                    tooltip: {{
                        ...commonOptions.plugins.tooltip,
                        callbacks: {{
                            ...commonOptions.plugins.tooltip.callbacks,
                            label: function(context) {{
                                return '回撤: ' + context.parsed.y.toFixed(2) + '%';
                            }}
                        }}
                    }}
                }}
            }}
        }});

        // 标记最大回撤点
        if (chartData.max_drawdown_point) {{
            const maxDDIndex = chartData.dates.indexOf(chartData.max_drawdown_point.date);
            if (maxDDIndex !== -1) {{
                // 添加最大回撤点标记
                drawdownChart.data.datasets.push({{
                    label: '最大回撤点',
                    data: chartData.dates.map((date, index) => 
                        index === maxDDIndex ? chartData.max_drawdown_point.value : null
                    ),
                    borderColor: '#ff6b6b',
                    backgroundColor: '#ff6b6b',
                    borderWidth: 3,
                    pointRadius: 6,
                    pointHoverRadius: 8,
                    showLine: false,
                    fill: false
                }});
                drawdownChart.update();
            }}
        }}
    </script>
</body>
</html>
        """
        
        # 生成HTML文件（去掉时间戳）
        html_file = os.path.join(output_dir, '绩效报告.html')
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_template)
        
        print(f"🌐 HTML绩效报告已保存: {html_file}")
        return html_file
    
    def _generate_chart_data_json(self, nav_df):
        """生成图表数据的JSON格式，用于JavaScript交互式图表"""
        import json
        
        # 准备数据
        dates = nav_df['date'].astype(str).tolist()
        nav_values = nav_df['total_nav'].round(2).tolist()
        cumulative_returns = nav_df['cumulative_return'].round(2).tolist()
        drawdowns = nav_df['drawdown'].round(2).tolist()
        
        # 最大回撤点数据
        max_dd_point = None
        if self.max_drawdown_info:
            max_dd_date = str(self.max_drawdown_info['max_dd_date'])
            max_dd_value = round(self.max_drawdown_info['max_drawdown'], 2)
            max_dd_point = {
                'date': max_dd_date,
                'value': max_dd_value
            }
        
        chart_data = {
            'dates': dates,
            'nav_values': nav_values,
            'cumulative_returns': cumulative_returns,
            'drawdowns': drawdowns,
            'initial_capital': self.total_initial_capital,
            'max_drawdown_point': max_dd_point
        }
        
        return json.dumps(chart_data)
    
    def _generate_nav_table_html(self, nav_df):
        """生成净值表格HTML"""
        # 只显示最近30天的数据，避免表格过长
        display_df = nav_df.tail(30).copy()
        
        html = '<table class="nav-table">'
        html += '''
        <thead>
            <tr>
                <th>日期</th>
                <th>价格</th>
                <th>持仓</th>
                <th>持仓价值</th>
                <th>现金余额</th>
                <th>总净值</th>
                <th>日收益率</th>
                <th>累计收益率</th>
                <th>回撤</th>
            </tr>
        </thead>
        <tbody>
        '''
        
        for _, row in display_df.iterrows():
            html += f'''
            <tr>
                <td>{row['date']}</td>
                <td>${row['price']:,.2f}</td>
                <td>{row['position'] or '空仓'}</td>
                <td>${row['position_value']:,.2f}</td>
                <td>${row['cash_balance']:,.2f}</td>
                <td>${row['total_nav']:,.2f}</td>
                <td>{row['daily_return']*100:+.2f}%</td>
                <td>{row['cumulative_return']:+.2f}%</td>
                <td>{row['drawdown']:.2f}%</td>
            </tr>
            '''
        
        html += '</tbody></table>'
        
        if len(nav_df) > 30:
            html += f'<p style="text-align: center; color: #666; margin-top: 10px;">* 仅显示最近30天数据，完整数据共{len(nav_df)}天</p>'
        
        return html
