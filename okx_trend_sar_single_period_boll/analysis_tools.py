#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
马丁格尔网格策略分析工具
包含净值计算、回撤分析、数据导出、图表生成等功能
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime
from openpyxl.utils import get_column_letter
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.offline as pyo

class StrategyAnalyzer:
    """策略分析器类"""
    
    def __init__(self, initial_capital):
        """
        初始化分析器
        :param initial_capital: 初始资金
        """
        self.initial_capital = initial_capital
        self.daily_nav_list = []
        self.last_nav_date = None
        
        # 创建输出文件夹
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.base_folder = "back_test_data"  # 基础文件夹
        self.output_folder = os.path.join(self.base_folder, f"BTC_{self.timestamp}")  # 默认使用BTC，可以在后续设置中修改
        
        # 确保基础文件夹存在
        if not os.path.exists(self.base_folder):
            os.makedirs(self.base_folder)
            print(f"📁 创建基础文件夹: {self.base_folder}")
        
        # 确保输出文件夹存在
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
            print(f"📁 创建输出文件夹: {self.output_folder}")
    
    def set_output_folder(self, coin_name):
        """
        设置输出文件夹名称
        :param coin_name: 币种名称，如 'BTC', 'ETH' 等
        """
        # 如果文件夹已经创建，先删除
        if os.path.exists(self.output_folder):
            import shutil
            shutil.rmtree(self.output_folder)
        
        # 重新创建文件夹
        self.output_folder = os.path.join(self.base_folder, f"{coin_name}_{self.timestamp}")
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
            print(f"📁 重新创建输出文件夹: {self.output_folder}")
    
    def add_daily_nav(self, date, nav):
        """
        添加每日净值数据
        :param date: 日期
        :param nav: 净值
        """
        if date != self.last_nav_date:
            self.daily_nav_list.append({'date': date, 'nav': nav})
            self.last_nav_date = date
    
    def calculate_nav_from_strategy(self, strategy, current_price, date):
        """
        从策略对象计算当前净值
        :param strategy: 策略对象
        :param current_price: 当前价格
        :param date: 日期
        """
        cash = strategy.btc_cash
        holdings = strategy.btc_holdings
        price = current_price
        position_groups_value = 0
        # 当前方向
        current_direction = strategy.current_trading_direction
        
        # 计算多单持仓组价值
        if hasattr(strategy, 'long_position_groups') and strategy.long_position_groups:
            for group in strategy.long_position_groups:
                position_groups_value += group['quantity'] * price

        # 计算空单持仓组价值（空头价值计算：反向计算盈亏）
        if hasattr(strategy, 'short_position_groups') and strategy.short_position_groups:
            for group in strategy.short_position_groups:
                avg_price = group.get('avg_price', price)
                quantity = group.get('quantity', 0)
                # 空头价值 = 数量 × (开仓均价 × 2 - 当前价格)
                # 这样当价格上涨时，价值减少（亏损）；价格下跌时，价值增加（盈利）
                short_value = quantity * (avg_price * 2 - price)
                position_groups_value += short_value
        
        # 计算亏损持仓组价值
        if hasattr(strategy, 'loss_position_groups') and strategy.loss_position_groups:
            for group in strategy.loss_position_groups:
                position_groups_value += group['quantity'] * price

        # 检查持仓组是否存在
        long_groups_exist = hasattr(strategy, 'long_position_groups')
        short_groups_exist = hasattr(strategy, 'short_position_groups') 
        loss_groups_exist = hasattr(strategy, 'loss_position_groups')
        
        # 打印详细持仓信息
        print(f"剩余现金: {cash}")
        print(f"当前持仓: {holdings} (价值: {holdings * price:.2f})")
        if holdings < 0:
            current_direction = getattr(strategy, 'current_trading_direction', 'N/A')
            print(f"⚠️ 警告：持仓为负数！")
            print(f"   总成本: {getattr(strategy, 'btc_total_cost', 'N/A')}")
            print(f"   平均价格: {getattr(strategy, 'btc_avg_price', 'N/A')}")
            print(f"   当前交易方向: {current_direction}")
            if current_direction == 'short':
                print(f"💡 可能原因：空单逻辑中持仓计算有误")
                print(f"   建议：检查空单买入/卖出的持仓更新逻辑")
            else:
                print(f"💡 可能原因：多单逻辑中存在bug，持仓计算错误")
        print(f"当前价格: {price}")
        print(f"持仓组价值: {position_groups_value}")
        print(f"多单持仓组: {len(strategy.long_position_groups) if long_groups_exist else 0} 组")
        print(f"空单持仓组: {len(strategy.short_position_groups) if short_groups_exist else 0} 组") 
        print(f"止损持仓组: {len(strategy.loss_position_groups) if loss_groups_exist else 0} 组")
        
        # 详细显示空头持仓组的价值计算
        if short_groups_exist and strategy.short_position_groups:
            total_short_value = 0
            for i, group in enumerate(strategy.short_position_groups):
                avg_price = group.get('avg_price', price)
                quantity = group.get('quantity', 0)
                short_value = quantity * (avg_price * 2 - price)
                total_short_value += short_value
                print(f"   空头组{i+1}: {quantity:.6f} BTC @ ${avg_price:.2f}, 价值=${short_value:.2f}")
            print(f"   空头持仓组总价值: ${total_short_value:.2f}")
        
        # 如果有空单持仓组，显示详细信息
        if short_groups_exist and strategy.short_position_groups:
            # print(f"📊 空单持仓组详情:")
            for i, group in enumerate(strategy.short_position_groups):
                avg_price = group.get('avg_price', 0)
                initial_tp = group.get('initial_take_profit_price', 0)
                quantity = group.get('quantity', 0)
                timestamp = group.get('timestamp', 'N/A')
                period = group.get('period', 'N/A')
                
                # 计算当前盈亏状态
                current_profit = (avg_price - price) * quantity  # 空单盈利计算
                profit_pct = (avg_price - price) / avg_price * 100 if avg_price > 0 else 0
                
                print(f"   组{i+1} [{period}]: 开仓价{avg_price:.1f} 数量{quantity:.6f} 止盈价{initial_tp:.1f}")
                print(f"         当前盈亏: ${current_profit:.2f} ({profit_pct:+.2f}%) 时间:{timestamp}")
                
                # 分析为什么没有止盈
                reasons = []
                if hasattr(strategy, 'stop_profit_multiple') and strategy.stop_profit_multiple > 1:
                    target_price = avg_price * (1 - strategy.stop_profit_multiple * getattr(strategy, 'short_down_pct', 0.05))
                    if price > target_price:
                        reasons.append(f"翻倍止盈未达到(需跌至{target_price:.1f})")
                
                if price > initial_tp:
                    reasons.append(f"价格高于止盈价({initial_tp:.1f})")
                
                if reasons:
                    print(f"         未止盈原因: {'; '.join(reasons)}")
            print()
        
        # 检查最近交易记录（用于调试负持仓）
        if holdings < 0 and hasattr(strategy, 'trades') and strategy.trades:
            print(f"🔍 最近5笔交易记录（调试负持仓）:")
            for trade in strategy.trades[-5:]:
                action = trade.get('action', 'N/A')
                position = trade.get('position', 'N/A')
                quantity = trade.get('quantity', 'N/A')
                reason = trade.get('reason', 'N/A')[:30] + '...' if len(trade.get('reason', '')) > 30 else trade.get('reason', 'N/A')
                print(f"  {trade.get('time', 'N/A')} {action} 数量:{quantity} 持仓:{position} 原因:{reason}")
        
        # 解释持仓组为空的原因
        # if (long_groups_exist and len(strategy.long_position_groups) == 0 and 
        #     short_groups_exist and len(strategy.short_position_groups) == 0 and 
        #     loss_groups_exist and len(strategy.loss_position_groups) == 0 and 
        #     holdings >= 0):  # 只在持仓非负时显示正常提示
        #     print("💡 持仓组为空是正常的！持仓组只在以下情况创建：")
        #     print("   1. 部分止盈后的剩余持仓")
        #     print("   2. 止损后的剩余持仓") 
        #     print("   3. 方向切换时转移的持仓")
        #     print("   普通买入的持仓保留在 btc_holdings 中")
        
        # 根据当前交易方向计算当前持仓价值
        if current_direction == 'short' and holdings != 0:
            # 空头持仓：使用空头价值计算逻辑
            avg_price = getattr(strategy, 'btc_avg_price', price)
            current_holdings_value = holdings * (avg_price * 2 - price)
            print(f"💰 空头持仓价值计算: {holdings:.6f} × ({avg_price:.2f} × 2 - {price:.2f}) = ${current_holdings_value:.2f}")
        else:
            # 多头持仓或无持仓：正常计算
            current_holdings_value = holdings * price
            if holdings != 0:
                print(f"💰 多头持仓价值: {holdings:.6f} × {price:.2f} = ${current_holdings_value:.2f}")
        
        nav = cash + current_holdings_value + position_groups_value
        print(f"净值: {nav} (时间: {date})\n")
        self.add_daily_nav(date, nav)
        return nav
    
    def calculate_drawdown_stats(self):
        """
        计算回撤统计数据
        :return: 回撤统计字典
        """
        if not self.daily_nav_list:
            return None
        
        navs = [item['nav'] for item in self.daily_nav_list]
        dates = [item['date'] for item in self.daily_nav_list]
        
        if not navs:
            return None
            
        peak = navs[0]
        max_drawdown = 0
        max_drawdown_pct = 0
        current_drawdown = 0
        current_drawdown_pct = 0
        drawdown_pcts = []
        drawdown_dates = []
        
        for i, nav in enumerate(navs):
            if nav > peak:
                peak = nav
            drawdown = peak - nav
            drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0
            drawdown_pcts.append(drawdown_pct)
            drawdown_dates.append(dates[i])
            
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            if drawdown_pct > max_drawdown_pct:
                max_drawdown_pct = drawdown_pct
        
        current_drawdown = peak - navs[-1]
        current_drawdown_pct = (current_drawdown / peak * 100) if peak > 0 else 0
        
        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'current_drawdown': current_drawdown,
            'current_drawdown_pct': current_drawdown_pct,
            'drawdown_pcts': drawdown_pcts,
            'drawdown_dates': drawdown_dates,
            'navs': navs,
            'dates': dates,
            'peak_nav': max(navs),
            'final_nav': navs[-1],
            'total_return': (navs[-1] - self.initial_capital) / self.initial_capital * 100
        }
    
    def export_trades_to_excel(self, trades_data, config):
        """
        导出交易记录为Excel
        :param trades_data: 交易记录数据
        :param config: 策略配置
        """
        if not trades_data:
            print("没有交易记录，跳过Excel导出")
            return
        
        df_trades = pd.DataFrame(trades_data)
        
        # 英文列名到中文的映射
        en2zh = {
            "date": "日期",
            "time": "交易时间",
            "symbol": "币种",
            "action": "操作",
            "price": "交易价格",
            "quantity": "交易数量(BTC)",
            "revenue": "交易金额",
            "amount": "可用余额",
            "position": "当前持仓价值",
            "avg_price": "持仓均价",
            "grids": "持仓周期",
            "profit": "盈亏",
            "reason": "操作原因",
            "grid_level": "持仓时间(小时)",
            "current_strategy_type": "当前策略",
            "is_stop_loss": "是否止损",
            "direction": "做单方向",
            "current_position_detail": "当前持仓情况"
        }
        df_trades = df_trades.rename(columns=en2zh)
        
        excel_name = f"trades_record_{self.timestamp}.xlsx"
        
        # 将文件保存到输出文件夹
        excel_name = os.path.join(self.output_folder, excel_name)

        # 设置每列宽度（单位：字符数）
        col_widths = {
            "日期": 20,
            "交易时间": 20,
            "币种": 8,
            "操作": 12,
            "交易价格": 12,
            "交易数量(BTC)": 20,
            "交易金额": 12,
            "可用余额": 12,
            "当前持仓价值": 20,
            "持仓均价": 12,
            "持仓周期": 12,
            "盈亏": 12,
            "操作原因": 60,
            "持仓时间(小时)": 20,
            "当前策略": 20,
            "是否止损": 12,
            "做单方向": 12,
            "当前持仓情况": 60
        }

        with pd.ExcelWriter(excel_name, engine='openpyxl') as writer:
            df_trades.to_excel(writer, index=False)
            worksheet = writer.sheets['Sheet1']
            for i, col in enumerate(df_trades.columns, 1):
                width = col_widths.get(col, 15)  # 默认宽度15
                worksheet.column_dimensions[get_column_letter(i)].width = width

        print(f"\n交易记录已导出为: {excel_name}")
    
    def print_strategy_summary(self, strategy, current_price, config):
        """
        打印策略总结信息
        :param strategy: 策略对象
        :param current_price: 当前价格
        :param config: 策略配置
        """
        print(f"\n=== 回测结果 ===")
        print(f"总交易次数: {len(strategy.trades)}")

        # 计算回撤数据（基于每日净值）
        drawdown_stats = self.calculate_drawdown_stats()
        
        if strategy.long_coin:
            print(f"\n{strategy.long_coin} 策略统计:")
            print(f"当前价格: ${current_price:.2f}")
            print(f"总净收益: ${strategy.btc_total_profit:.2f}")
            print(f"当前使用网格数: {strategy.btc_grids_used}")
            
            # 计算收益率
            initial_capital = config['initial_capital']
            # 计算持仓组价值
            position_groups_value = 0

            # 计算多单持仓组价值
            if hasattr(strategy, 'long_position_groups') and strategy.long_position_groups:
                for group in strategy.long_position_groups:
                    position_groups_value += group['quantity'] * current_price

            # 计算空单持仓组价值（空头价值计算：反向计算盈亏）
            if hasattr(strategy, 'short_position_groups') and strategy.short_position_groups:
                for group in strategy.short_position_groups:
                    avg_price = group.get('avg_price', current_price)
                    quantity = group.get('quantity', 0)
                    # 空头价值 = 数量 × (开仓均价 × 2 - 当前价格)
                    short_value = quantity * (avg_price * 2 - current_price)
                    position_groups_value += short_value
            
            # 计算亏损持仓组价值
            if hasattr(strategy, 'loss_position_groups') and strategy.loss_position_groups:
                for group in strategy.loss_position_groups:
                    position_groups_value += group['quantity'] * current_price
            
            # 根据当前交易方向计算主仓位价值
            current_direction = getattr(strategy, 'current_trading_direction', 'long')
            if current_direction == 'short' and strategy.btc_holdings != 0:
                # 空头主仓位：使用空头价值计算逻辑
                avg_price = getattr(strategy, 'btc_avg_price', current_price)
                main_holdings_value = strategy.btc_holdings * (avg_price * 2 - current_price)
            else:
                # 多头主仓位或无持仓：正常计算
                main_holdings_value = strategy.btc_holdings * current_price
            
            final_value = strategy.btc_cash + main_holdings_value + position_groups_value
            total_return = (final_value - initial_capital) / initial_capital * 100
            print(f"账户价值详情:")
            print(f"  现金: ${strategy.btc_cash:.2f}")
            if current_direction == 'short' and strategy.btc_holdings != 0:
                avg_price = getattr(strategy, 'btc_avg_price', current_price)
                print(f"  主仓位价值: ${main_holdings_value:.2f} ({strategy.btc_holdings:.6f} BTC 空头@{avg_price:.2f})")
            else:
                print(f"  主仓位价值: ${main_holdings_value:.2f} ({strategy.btc_holdings:.6f} BTC)")
            print(f"  持仓组价值: ${position_groups_value:.2f}")
            print(f"  账户总价值: ${final_value:.2f}")
            print(f"总收益率: {total_return:.2f}%")
            
            # 显示回撤数据
            if drawdown_stats:
                print(f"\n=== 风险指标 (回撤分析) ===")
                print(f"最大回撤: ${drawdown_stats['max_drawdown']:.2f} ({drawdown_stats['max_drawdown_pct']:.2f}%)")
                print(f"当前回撤: ${drawdown_stats['current_drawdown']:.2f} ({drawdown_stats['current_drawdown_pct']:.2f}%)")
    
    def print_trade_samples(self, trades_data, sample_count=3):
        """
        打印交易样本
        :param trades_data: 交易记录数据
        :param sample_count: 样本数量
        """
        if not trades_data:
            return
        
        # 显示前几笔交易
        print(f"\n前{sample_count}笔交易记录:")
        for i, trade in enumerate(trades_data[:sample_count]):
            if isinstance(trade, dict):
                print(f"{i+1}. {trade['date']} {trade['time']} {trade['action']} "
                      f"{trade['symbol']} @ ${trade['price']:.2f} "
                      f"数量: {trade['quantity']:.6f} "
                      f"盈亏: ${trade['profit']:.2f} "
                      f"原因: {trade['reason']}")
            else:
                print(f"{i+1}. 非法交易数据: {trade}")

        # 显示后几笔交易
        if len(trades_data) > sample_count:
            print(f"\n后{sample_count}笔交易记录:")
            for i, trade in enumerate(trades_data[-sample_count:]):
                if isinstance(trade, dict):
                    print(f"{len(trades_data)-sample_count+1+i}. {trade['date']} {trade['time']} {trade['action']} "
                          f"{trade['symbol']} @ ${trade['price']:.2f} "
                          f"数量: {trade['quantity']:.6f} "
                          f"盈亏: ${trade['profit']:.2f} "
                          f"原因: {trade['reason']}")
                else:
                    print(f"{len(trades_data)-sample_count+1+i}. 非法交易数据: {trade}")
    
    def create_nav_chart(self, filename=None):
        """
        生成每日净值折线图
        :param filename: 保存的HTML文件名，如果为None则自动生成带时间戳的文件名
        """
        if not self.daily_nav_list:
            print("没有净值数据，无法生成图表")
            return
        
        # 如果没有指定文件名，则自动生成带时间戳的文件名
        if filename is None:
            filename = f'daily_nav_chart.html'
        
        # 将文件保存到输出文件夹
        output_path = os.path.join(self.output_folder, filename)
        
        print(f"\n正在生成每日净值折线图...")
        
        # 提取数据
        dates = [item['date'] for item in self.daily_nav_list]
        navs = [item['nav'] for item in self.daily_nav_list]
        
        # 计算收益率
        returns = [((nav - self.initial_capital) / self.initial_capital * 100) for nav in navs]
        
        # 计算回撤
        peaks = []
        peak = navs[0]
        drawdowns = []
        
        for nav in navs:
            if nav > peak:
                peak = nav
            peaks.append(peak)
            drawdown = (peak - nav) / peak * 100 if peak > 0 else 0
            drawdowns.append(drawdown)
        
        # 创建图表
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=('每日净值变化', '累计收益率 (%)', '回撤 (%)'),
            vertical_spacing=0.08,
            row_heights=[0.5, 0.25, 0.25]
        )
        
        # 添加净值曲线
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=navs,
                mode='lines',
                name='净值',
                line=dict(color='blue', width=2),
                hovertemplate='日期: %{x}<br>净值: $%{y:,.2f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # 添加初始资金基准线
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=[self.initial_capital] * len(dates),
                mode='lines',
                name='初始资金',
                line=dict(color='gray', width=1, dash='dash'),
                hovertemplate='基准线: $%{y:,.2f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # 添加收益率曲线
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=returns,
                mode='lines',
                name='收益率',
                line=dict(color='green', width=2),
                hovertemplate='日期: %{x}<br>收益率: %{y:.2f}%<extra></extra>',
                fill='tonexty' if any(r >= 0 for r in returns) else None,
                fillcolor='rgba(0,255,0,0.1)'
            ),
            row=2, col=1
        )
        
        # 添加0%基准线
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=[0] * len(dates),
                mode='lines',
                name='0%基准',
                line=dict(color='gray', width=1, dash='dash'),
                showlegend=False
            ),
            row=2, col=1
        )
        
        # 添加回撤曲线
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=[-d for d in drawdowns],  # 回撤显示为负值
                mode='lines',
                name='回撤',
                line=dict(color='red', width=2),
                fill='tonexty',
                fillcolor='rgba(255,0,0,0.1)',
                hovertemplate='日期: %{x}<br>回撤: %{y:.2f}%<extra></extra>'
            ),
            row=3, col=1
        )
        
        # 更新布局
        fig.update_layout(
            title=f'策略每日净值分析报告<br><sub>初始资金: ${self.initial_capital:,.2f} | 最终净值: ${navs[-1]:,.2f} | 总收益: {returns[-1]:.2f}%</sub>',
            height=800,
            width=1200,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        # 更新x轴
        fig.update_xaxes(title_text="日期", row=3, col=1)
        
        # 更新y轴
        fig.update_yaxes(title_text="净值 ($)", row=1, col=1)
        fig.update_yaxes(title_text="收益率 (%)", row=2, col=1)
        fig.update_yaxes(title_text="回撤 (%)", row=3, col=1)
        
        # 保存图表
        try:
            fig.write_html(output_path)
            print(f"✅ 每日净值图表已保存为: {output_path}")
            
            # 验证文件
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                print(f"文件大小: {file_size} 字节")
                
                # 打印统计信息
                self._print_nav_stats()
            else:
                print("❌ 文件保存失败")
                
        except Exception as e:
            print(f"❌ 生成净值图表时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _print_nav_stats(self):
        """打印净值统计信息"""
        if not self.daily_nav_list:
            return
        
        navs = [item['nav'] for item in self.daily_nav_list]
        returns = [((nav - self.initial_capital) / self.initial_capital * 100) for nav in navs]
        
        print(f"\n=== 净值统计 ===")
        print(f"统计天数: {len(self.daily_nav_list)} 天")
        print(f"初始净值: ${navs[0]:,.2f}")
        print(f"最终净值: ${navs[-1]:,.2f}")
        print(f"最高净值: ${max(navs):,.2f}")
        print(f"最低净值: ${min(navs):,.2f}")
        print(f"总收益: ${navs[-1] - self.initial_capital:,.2f}")
        print(f"总收益率: {returns[-1]:.2f}%")
        
        # 计算最大回撤
        drawdown_stats = self.calculate_drawdown_stats()
        if drawdown_stats:
            print(f"最大回撤: {drawdown_stats['max_drawdown_pct']:.2f}%")
    
    def create_kline_chart(self, df_minute, trades_data, timeframe='1H', coin_name='BTC'):
        """
        生成K线图并标记交易点
        :param df_minute: 分钟级K线数据
        :param trades_data: 交易记录数据
        :param timeframe: 时间周期 ('1H', '4H', '1D')
        :param coin_name: 币种名称
        """
        print(f"\n正在生成{timeframe}级别K线图...")
        
        # 转换时间周期
        if timeframe == '1H':
            freq = '1h'
            title_freq = '1小时'
        elif timeframe == '4H':
            freq = '4h'
            title_freq = '4小时'
        elif timeframe == '1D':
            freq = '1d'
            title_freq = '1天'
        else:
            freq = '1h'
            title_freq = '1小时'
        
        # 将分钟数据重采样为指定周期
        df_kline = df_minute.copy()
        df_kline['timestamp'] = pd.to_datetime(df_kline['timestamp'])
        df_kline.set_index('timestamp', inplace=True)
        
        # 重采样K线数据
        ohlcv = df_kline.resample(freq).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        # 创建交易数据DataFrame
        if trades_data:
            df_trades = pd.DataFrame(trades_data)
            df_trades['timestamp'] = pd.to_datetime(df_trades['time'], format='%Y-%m-%d_%H:%M:%S')
            
            # 分类交易数据
            buy_trades = df_trades[df_trades['action'] == 'BUY']
            sell_trades = df_trades[df_trades['action'].isin(['SELL', 'SELL-ALL'])]
            sell_part_trades = df_trades[df_trades['action'] == 'SELL-PART']
            
            # 进一步分类买入交易（正常买入 vs 低点加仓）
            normal_buy = buy_trades[~buy_trades['reason'].str.contains('低点形态|低点加仓', na=False)]
            trough_buy = buy_trades[buy_trades['reason'].str.contains('低点形态|低点加仓', na=False)]
            
            # 进一步分类卖出交易（正常止盈 vs 高点止盈）
            normal_sell = sell_trades[~sell_trades['reason'].str.contains('高点|翻倍', na=False)]
            peak_sell = sell_trades[sell_trades['reason'].str.contains('高点|翻倍', na=False)]
        
        # 创建plotly图表
        fig = make_subplots(
            rows=1, cols=1,
            subplot_titles=[f'{coin_name} {title_freq}K线图'],
        )
        
        # 添加K线图
        fig.add_trace(
            go.Candlestick(
                x=ohlcv.index,
                open=ohlcv['open'],
                high=ohlcv['high'],
                low=ohlcv['low'],
                close=ohlcv['close'],
                name='K线',
                increasing_line_color='red',
                decreasing_line_color='green'
            )
        )
        
        # 添加交易标记
        if trades_data and not df_trades.empty:
            # 正常买入点（绿色小圆点）
            if not normal_buy.empty:
                fig.add_trace(
                    go.Scatter(
                        x=normal_buy['timestamp'],
                        y=normal_buy['price'],
                        mode='markers',
                        marker=dict(
                            symbol='circle',
                            size=8,
                            color='green',
                            line=dict(width=1, color='darkgreen')
                        ),
                        name='买入',
                        text=normal_buy['reason'],
                        hovertemplate='<b>买入</b><br>时间: %{x}<br>价格: %{y}<br>原因: %{text}<extra></extra>'
                    )
                )
            
            # 低点加仓（深绿色向上三角）
            if not trough_buy.empty:
                fig.add_trace(
                    go.Scatter(
                        x=trough_buy['timestamp'],
                        y=trough_buy['price'],
                        mode='markers',
                        marker=dict(
                            symbol='triangle-up',
                            size=12,
                            color='darkgreen',
                            line=dict(width=2, color='black')
                        ),
                        name='低点加仓',
                        text=trough_buy['reason'],
                        hovertemplate='<b>低点加仓</b><br>时间: %{x}<br>价格: %{y}<br>原因: %{text}<extra></extra>'
                    )
                )
            
            # 正常卖出（红色向下三角）
            if not normal_sell.empty:
                fig.add_trace(
                    go.Scatter(
                        x=normal_sell['timestamp'],
                        y=normal_sell['price'],
                        mode='markers',
                        marker=dict(
                            symbol='triangle-down',
                            size=10,
                            color='red',
                            line=dict(width=1, color='darkred')
                        ),
                        name='卖出',
                        text=normal_sell['reason'],
                        hovertemplate='<b>卖出</b><br>时间: %{x}<br>价格: %{y}<br>盈亏: %{customdata}<br>原因: %{text}<extra></extra>',
                        customdata=normal_sell['profit']
                    )
                )
            
            # 高点止盈（橙色向下三角）
            if not peak_sell.empty:
                fig.add_trace(
                    go.Scatter(
                        x=peak_sell['timestamp'],
                        y=peak_sell['price'],
                        mode='markers',
                        marker=dict(
                            symbol='triangle-down',
                            size=12,
                            color='orange',
                            line=dict(width=2, color='darkorange')
                        ),
                        name='高点止盈',
                        text=peak_sell['reason'],
                        hovertemplate='<b>高点止盈</b><br>时间: %{x}<br>价格: %{y}<br>盈亏: %{customdata}<br>原因: %{text}<extra></extra>',
                        customdata=peak_sell['profit']
                    )
                )
            
            # 部分卖出（黄色圆点）
            if not sell_part_trades.empty:
                fig.add_trace(
                    go.Scatter(
                        x=sell_part_trades['timestamp'],
                        y=sell_part_trades['price'],
                        mode='markers',
                        marker=dict(
                            symbol='circle',
                            size=8,
                            color='yellow',
                            line=dict(width=1, color='orange')
                        ),
                        name='部分卖出',
                        text=sell_part_trades['reason'],
                        hovertemplate='<b>部分卖出</b><br>时间: %{x}<br>价格: %{y}<br>盈亏: %{customdata}<br>原因: %{text}<extra></extra>',
                        customdata=sell_part_trades['profit']
                    )
                )
        
        # 更新布局
        fig.update_layout(
            title=f'{coin_name} {title_freq}级别回测结果 - 交易标记图',
            xaxis_title='时间',
            yaxis_title='价格 (USDT)',
            height=1000,
            width=1400,
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="rgba(0,0,0,0.2)",
                borderwidth=1
            ),
            # 添加范围选择器
            xaxis=dict(
                rangeslider=dict(visible=True, thickness=0.1),
                rangeselector=dict(
                    buttons=list([
                        dict(count=1, label="1天", step="day", stepmode="backward"),
                        dict(count=3, label="3天", step="day", stepmode="backward"),
                        dict(count=7, label="7天", step="day", stepmode="backward"),
                        dict(count=30, label="30天", step="day", stepmode="backward"),
                        dict(step="all", label="全部")
                    ]),
                    bgcolor="rgba(255,255,255,0.8)",
                    bordercolor="rgba(0,0,0,0.2)",
                    borderwidth=1
                ),
                type="date"
            )
        )
        
        # 保存图表
        chart_filename = f"{coin_name}_{timeframe}_trade_chart.html"
        chart_filename = os.path.join(self.output_folder, chart_filename)
        fig.write_html(chart_filename)
        print(f"K线图已保存为: {chart_filename}")
        
        return fig
    
    def generate_all_charts(self, df, trades_data, config, timeframes=None):
        """
        生成所有图表
        :param df: K线数据
        :param trades_data: 交易记录数据
        :param config: 策略配置
        :param timeframes: 时间周期列表，默认为['1H']
        """
        if timeframes is None:
            timeframes = ['1H']  # 默认只生成1小时图
        
        # 生成净值图表
        if self.daily_nav_list:
            self.create_nav_chart()
        else:
            print("\n没有每日净值数据，跳过净值图表生成。")

        # 生成K线图
        if trades_data:
            for timeframe in timeframes:
                try:
                    self.create_kline_chart(df, trades_data, timeframe, config['long_coin'])
                except Exception as e:
                    print(f"生成{timeframe}K线图时出错: {e}")
            
            print(f"\n所有K线图生成完成！")
        else:
            print("\n没有交易记录，跳过K线图生成。")
    
    def print_output_summary(self):
        """打印输出文件总结"""
        if not os.path.exists(self.output_folder):
            print("❌ 输出文件夹不存在")
            return
        
        print(f"\n📁 输出文件夹: {self.output_folder}")
        print("📄 生成的文件:")
        
        files = os.listdir(self.output_folder)
        if not files:
            print("   没有生成任何文件")
            return
        
        for file in sorted(files):
            file_path = os.path.join(self.output_folder, file)
            file_size = os.path.getsize(file_path)
            print(f"   📄 {file} ({file_size:,} 字节)")
        
        print(f"\n✅ 所有文件已保存到: {self.output_folder}")
    
    def generate_result_report(self, strategy, current_price, config, drawdown_stats=None):
        """
        生成结果报告文本文件
        :param strategy: 策略对象
        :param current_price: 当前价格
        :param config: 策略配置
        :param drawdown_stats: 回撤统计数据
        """
        report_filename = os.path.join(self.output_folder, "backtest_report.txt")
        
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("马丁格尔网格策略回测报告\n")
            f.write("=" * 80 + "\n\n")
            
            # 写入配置信息
            f.write("📋 策略配置\n")
            f.write("-" * 40 + "\n")
            f.write(f"机器人ID: {config.get('robot_id', 'N/A')}\n")
            f.write(f"交易币种: {config.get('long_coin', 'N/A')}\n")
            f.write(f"交易模式: {config.get('trade_mode', 'N/A')}\n")
            f.write(f"初始资金: ${config.get('initial_capital', 0):,.2f}\n")
            f.write(f"最大网格数: {config.get('max_grid_size', 0)}\n")
            f.write(f"下跌触发阈值: {config.get('down_pct', 0)}%\n")
            f.write(f"上涨触发阈值: {config.get('up_pct', 0)}%\n")
            f.write(f"最大止损: {config.get('max_stop_loss_pct', 0)}% (双重止损机制)\n")
            f.write(f"止盈类型: {config.get('take_profit_type', 0)}\n")
            f.write(f"移动止盈倍数: {config.get('stop_profit_multiple', 0)}\n")
            f.write(f"首次止盈比例: {config.get('first_take_profit_ratio', 0)}\n")
            f.write(f"启用高点止盈: {'是' if config.get('enable_peak_pattern_take_profit', 0) else '否'}\n")
            f.write(f"高点周期: {config.get('peak_pattern_timeframe', 'N/A')}\n")
            f.write(f"启用低点加仓: {'是' if config.get('enable_trough_pattern_add', 0) else '否'}\n")
            f.write(f"低点周期: {config.get('trough_pattern_timeframe', 'N/A')}\n")
            f.write(f"低点加仓倍数: {config.get('trough_add_spread_multiples', 0)}\n")
            f.write(f"启用空仓买入: {'是' if config.get('enable_empty_buy', 0) else '否'}\n")
            f.write(f"启用60分钟K线止盈: {'是' if config.get('enable_60m_kline_take_profit', 0) else '否'}\n\n")
            
            # 写入回测结果
            f.write("📊 回测结果\n")
            f.write("-" * 40 + "\n")
            f.write(f"总交易次数: {len(strategy.trades)}\n")
            f.write(f"当前价格: ${current_price:.2f}\n\n")
            
            if strategy.long_coin:
                f.write(f"{strategy.long_coin} 策略统计:\n")
                f.write(f"多单账户最终持仓: {strategy.btc_holdings:.6f} (${strategy.btc_holdings * current_price:.2f})\n")
                f.write(f"多单账户最终现金: ${strategy.btc_cash:.2f}\n")
                f.write(f"多单账户最终总盈利: ${strategy.btc_total_profit:.2f}\n")
                f.write(f"总净收益: ${strategy.btc_total_profit:.2f}\n")
                f.write(f"当前使用网格数: {strategy.btc_grids_used}\n\n")
                
                # 计算收益率
                initial_capital = config['initial_capital']
                position_groups_value = 0
                
                # 计算多单持仓组价值
                if hasattr(strategy, 'long_position_groups') and strategy.long_position_groups:
                    for group in strategy.long_position_groups:
                        position_groups_value += group['quantity'] * current_price

                # 计算空单持仓组价值（空头价值计算：反向计算盈亏）
                if hasattr(strategy, 'short_position_groups') and strategy.short_position_groups:
                    for group in strategy.short_position_groups:
                        avg_price = group.get('avg_price', current_price)
                        quantity = group.get('quantity', 0)
                        # 空头价值 = 数量 × (开仓均价 × 2 - 当前价格)
                        short_value = quantity * (avg_price * 2 - current_price)
                        position_groups_value += short_value
                
                # 计算亏损持仓组价值
                if hasattr(strategy, 'loss_position_groups') and strategy.loss_position_groups:
                    for group in strategy.loss_position_groups:
                        position_groups_value += group['quantity'] * current_price
                
                # 根据当前交易方向计算主仓位价值
                current_direction = getattr(strategy, 'current_trading_direction', 'long')
                if current_direction == 'short' and strategy.btc_holdings != 0:
                    # 空头主仓位：使用空头价值计算逻辑
                    avg_price = getattr(strategy, 'btc_avg_price', current_price)
                    main_holdings_value = strategy.btc_holdings * (avg_price * 2 - current_price)
                else:
                    # 多头主仓位或无持仓：正常计算
                    main_holdings_value = strategy.btc_holdings * current_price
                
                final_value = strategy.btc_cash + main_holdings_value + position_groups_value
                total_return = (final_value - initial_capital) / initial_capital * 100
                
                f.write("账户价值详情:\n")
                f.write(f"  现金: ${strategy.btc_cash:.2f}\n")
                if current_direction == 'short' and strategy.btc_holdings != 0:
                    avg_price = getattr(strategy, 'btc_avg_price', current_price)
                    f.write(f"  主仓位价值: ${main_holdings_value:.2f} ({strategy.btc_holdings:.6f} {strategy.long_coin} 空头@{avg_price:.2f})\n")
                else:
                    f.write(f"  主仓位价值: ${main_holdings_value:.2f} ({strategy.btc_holdings:.6f} {strategy.long_coin})\n")
                f.write(f"  持仓组价值: ${position_groups_value:.2f}\n")
                f.write(f"  账户总价值: ${final_value:.2f}\n")
                f.write(f"总收益率: {total_return:.2f}%\n\n")
            
            # 写入回撤数据
            if drawdown_stats:
                f.write("📈 风险指标 (回撤分析)\n")
                f.write("-" * 40 + "\n")
                f.write(f"最大回撤: ${drawdown_stats['max_drawdown']:.2f} ({drawdown_stats['max_drawdown_pct']:.2f}%)\n")
                f.write(f"当前回撤: ${drawdown_stats['current_drawdown']:.2f} ({drawdown_stats['current_drawdown_pct']:.2f}%)\n")
                f.write(f"最高净值: ${drawdown_stats.get('peak_nav', 0):.2f}\n")
                f.write(f"最终净值: ${drawdown_stats.get('final_nav', 0):.2f}\n")
                f.write(f"总收益率: {drawdown_stats.get('total_return', 0):.2f}%\n\n")
            
            # 写入净值统计
            if self.daily_nav_list:
                f.write("📊 净值统计\n")
                f.write("-" * 40 + "\n")
                navs = [item['nav'] for item in self.daily_nav_list]
                f.write(f"统计天数: {len(self.daily_nav_list)} 天\n")
                f.write(f"初始净值: ${navs[0]:,.2f}\n")
                f.write(f"最终净值: ${navs[-1]:,.2f}\n")
                f.write(f"最高净值: ${max(navs):,.2f}\n")
                f.write(f"最低净值: ${min(navs):,.2f}\n")
                f.write(f"总收益: ${navs[-1] - self.initial_capital:,.2f}\n")
                f.write(f"总收益率: {((navs[-1] - self.initial_capital) / self.initial_capital * 100):.2f}%\n\n")
            
            # 写入交易样本
            if strategy.trades:
                f.write("📝 交易样本 (前5笔)\n")
                f.write("-" * 40 + "\n")
                for i, trade in enumerate(strategy.trades[:5]):
                    if isinstance(trade, dict):
                        f.write(f"{i+1}. {trade['date']} {trade['time']} {trade['action']} "
                               f"{trade['symbol']} @ ${trade['price']:.2f} "
                               f"数量: {trade['quantity']:.6f} "
                               f"盈亏: ${trade['profit']:.2f} "
                               f"原因: {trade['reason']}\n")
                
                if len(strategy.trades) > 5:
                    f.write(f"\n... (共 {len(strategy.trades)} 笔交易)\n\n")
            
            # 写入文件信息
            f.write("📁 生成的文件\n")
            f.write("-" * 40 + "\n")
            files = os.listdir(self.output_folder)
            for file in sorted(files):
                file_path = os.path.join(self.output_folder, file)
                file_size = os.path.getsize(file_path)
                f.write(f"📄 {file} ({file_size:,} 字节)\n")
            
            f.write(f"\n✅ 所有文件已保存到: {self.output_folder}\n")
            f.write("=" * 80 + "\n")
        
        print(f"📄 回测报告已保存为: {report_filename}") 