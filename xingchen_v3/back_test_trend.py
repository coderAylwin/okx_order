#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import pandas as pd
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from trend_volumatic_dynamic_average_strategy import TrendVolumaticDynamicAverageStrategy
from database_config import LOCAL_DATABASE_CONFIG
from database_service import DatabaseService
from strategy_configs import get_strategy_config, print_config_info
from performance_analysis import PerformanceAnalyzer

def create_output_directory(config, annual_return):
    """
    创建统一的输出目录结构
    /back_test_data/{币种}/{时间戳}-{年化收益率}/
    
    Args:
        config: 策略配置
        annual_return: 年化收益率（用于文件夹命名）
    
    Returns:
        str: 输出目录路径
    """
    # 获取币种
    long_coin = config['long_coin']
    
    # 生成时间戳
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 格式化年化收益率（保留2位小数）
    annual_return_str = f"{annual_return:+.2f}%"
    
    # 创建目录结构
    base_dir = "back_test_data"
    coin_dir = os.path.join(base_dir, long_coin)
    result_dir = os.path.join(coin_dir, f"{timestamp}-{annual_return_str}")
    
    # 确保目录存在
    os.makedirs(result_dir, exist_ok=True)
    
    print(f"📁 创建输出目录: {result_dir}")
    return result_dir

def export_trades_to_excel(trades, config, output_dir):
    """
    导出交易记录到Excel文件
    
    Args:
        trades: 交易记录列表
        config: 策略配置
        output_dir: 输出目录
    """
    if not trades:
        print("❌ 没有交易记录，跳过Excel导出")
        return None
    
    # 生成文件名（添加时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(output_dir, f"交易记录_{timestamp}.xlsx")
    
    # 合并开仓和平仓记录，按时间顺序
    trade_data = []
    current_entry = None  # 记录当前开仓信息
    
    for i, trade in enumerate(trades):
        if trade['signal_type'] in ['OPEN_LONG', 'OPEN_SHORT']:
            # 开仓记录（满仓模式）
            if 'LONG' in trade['signal_type']:
                direction = "做多"
            else:
                direction = "做空"
            
            operation_type = "开仓"
            stop_loss = trade.get('stop_loss', 'N/A')
            take_profit = trade.get('take_profit', 'N/A')
            
            # 🔄 获取实际投入金额（来自策略传递的复投信息）
            trade_amount = trade.get('invested_amount', 0)
            
            # 调试信息：检查开仓信号是否包含投入金额
            if trade_amount == 0:
                print(f"⚠️  警告：开仓信号 {trade['signal_type']} 缺少 invested_amount 信息")
                print(f"    信号内容: {trade}")
                # 🔄 使用当前现金余额计算（复投逻辑）
                position_size = config.get('position_size_percentage', 100) / 100
                # 单账户模式：使用统一现金余额
                current_balance = trade.get('cash_balance', config['initial_capital'])
                trade_amount = current_balance * position_size
                print(f"    🔄 复投计算: 当前余额${current_balance:,.2f} × {position_size*100}% = ${trade_amount:,.2f}")
            
            # 单账户模式：获取统一现金余额信息
            cash_balance = trade.get('cash_balance', 0)
            
            # 保存当前开仓信息，用于平仓时引用
            current_entry = {
                'direction': direction,
                'price': trade['price'],
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'amount': trade_amount,
                'cash_balance': cash_balance
            }
            
            # 获取份额信息（满仓模式）
            current_shares = trade.get('position_shares', 0)
            
            trade_data.append({
                '序号': len(trade_data) + 1,
                '操作类型': operation_type,
                '交易方向': direction,
                '时间': trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if trade.get('timestamp') else 'N/A',
                '价格': f"{trade['price']:.2f}",
                '交易金额': f"{trade_amount:,.2f}",
                '交易份额': f"{current_shares:.4f}",
                '止损位': f"{stop_loss:.2f}" if isinstance(stop_loss, (int, float)) else stop_loss,
                '止盈位': f"{take_profit:.2f}" if isinstance(take_profit, (int, float)) else take_profit,
                '盈亏金额': '-',
                '手续费': f"{trade.get('transaction_fee', 0):.2f}",
                '收益率': '-',
                '交易结果': '-',
                '现金余额': f"{cash_balance:,.2f}",
                '原因': trade['reason']
            })
            
        elif trade['signal_type'] in ['STOP_LOSS_LONG', 'STOP_LOSS_SHORT', 'TAKE_PROFIT_LONG', 'TAKE_PROFIT_SHORT', 
                                       'MA_PROFIT_LONG', 'MA_LOSS_LONG', 'MA_PROFIT_SHORT', 'MA_LOSS_SHORT',
                                       'MAX_STOP_LOSS_LONG', 'MAX_STOP_LOSS_SHORT']:
            # 平仓记录
            direction = "做多" if 'LONG' in trade['signal_type'] else "做空"
            profit_loss = trade.get('profit_loss', 0)
            
            # 判断平仓类型和结果 - 更精确地描述平仓原因
            if 'TAKE_PROFIT' in trade['signal_type']:
                close_type = "固定止盈"
                # 🔴 根据实际盈亏判断结果
                result = "盈利" if profit_loss > 0 else "亏损"
                print(f"    🎯 平仓分类: {trade['signal_type']} + {'盈利' if profit_loss > 0 else '亏损'}${profit_loss:.2f} -> {close_type} ({result})")
            elif 'MA_PROFIT' in trade['signal_type'] or 'MA_LOSS' in trade['signal_type']:
                # 回归MA卖出信号
                if profit_loss > 0:
                    close_type = "回归MA盈利"
                    result = "盈利"
                    print(f"    📊 平仓分类: {trade['signal_type']} + 盈利${profit_loss:.2f} -> {close_type} ({result})")
                else:
                    close_type = "回归MA亏损"
                    result = "亏损"
                    print(f"    📊 平仓分类: {trade['signal_type']} + 亏损${profit_loss:.2f} -> {close_type} ({result})")
            elif 'MAX_STOP_LOSS' in trade['signal_type']:
                # 最大固定止损
                close_type = "最大固定止损"
                result = "亏损"
                print(f"    🔒 平仓分类: {trade['signal_type']} + 亏损${profit_loss:.2f} -> {close_type} ({result})")
            else:  # STOP_LOSS - 基于固定比例或布林带宽度的止损
                if profit_loss > 0:
                    close_type = "动态止盈"  # 其他原因导致的盈利平仓
                    result = "盈利"
                    print(f"    📈 平仓分类: {trade['signal_type']} + 盈利${profit_loss:.2f} -> {close_type} ({result})")
                else:
                    close_type = "动态止损"  # 固定比例或布林带止损
                    result = "亏损"
                    print(f"    📉 平仓分类: {trade['signal_type']} + 亏损${profit_loss:.2f} -> {close_type} ({result})")
            
            # 计算收益率（基于投入本金）
            if profit_loss != 0 and current_entry and current_entry.get('amount', 0) > 0:
                # 使用投入的资金作为基准计算收益率
                invested_capital = current_entry['amount']
                return_rate = (profit_loss / invested_capital) * 100
            else:
                return_rate = 0
            
            # 使用开仓时的止损止盈位和最新现金余额
            if current_entry:
                entry_stop_loss = current_entry['stop_loss']
                entry_take_profit = current_entry['take_profit']
                entry_amount = current_entry['amount']
            else:
                # 如果没有开仓记录，使用默认值
                print(f"⚠️  警告：平仓记录 {trade['signal_type']} 没有对应的开仓记录")
                entry_stop_loss = 'N/A'
                entry_take_profit = 'N/A'
                entry_amount = trade.get('invested_amount', 0)
                
            # 确保 entry_amount 不为0，避免除零错误
            if entry_amount == 0:
                print(f"⚠️  警告：交易金额为0，设置为默认值1000")
                entry_amount = 1000  # 设置一个默认值避免除零错误
            
            # 🔄 获取平仓后的现金余额（单账户模式）
            new_cash_balance = trade.get('new_balance', 0)
            
            # 🔄 平仓交易金额 = 本金 + 盈亏
            close_trade_amount = entry_amount + profit_loss
            print(f"    💰 平仓金额计算: 本金${entry_amount:,.2f} + 盈亏${profit_loss:+.2f} = ${close_trade_amount:,.2f}")
            
            trade_data.append({
                '序号': len(trade_data) + 1,
                '操作类型': f'平仓({close_type})',
                '交易方向': direction,
                '时间': trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if trade.get('timestamp') else 'N/A',
                '价格': f"{trade['price']:.2f}",
                '交易金额': f"{close_trade_amount:,.2f}",
                '交易份额': f"{trade.get('position_shares', 0):.4f}",
                '止损位': f"{entry_stop_loss:.2f}" if isinstance(entry_stop_loss, (int, float)) else entry_stop_loss,
                '止盈位': f"{entry_take_profit:.2f}" if isinstance(entry_take_profit, (int, float)) else entry_take_profit,
                '盈亏金额': f"{profit_loss:.2f}",
                '手续费': f"{trade.get('transaction_fee', 0):.2f}",
                '收益率': f"{return_rate:+.2f}%",
                '交易结果': result,
                '现金余额': f"{new_cash_balance:,.2f}",
                '原因': trade['reason']
            })
            
            # 清除当前开仓信息
            current_entry = None
    
    # 创建DataFrame
    df = pd.DataFrame(trade_data)
    
    # 写入Excel
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # 交易明细表
        df.to_excel(writer, sheet_name='交易明细', index=False)
        
        # 获取工作簿和工作表
        workbook = writer.book
        worksheet = writer.sheets['交易明细']
        
        # 设置样式
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        center_alignment = Alignment(horizontal="center", vertical="center")
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'), 
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # 设置表头样式
        for cell in worksheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_alignment
            cell.border = border
        
        # 设置数据行样式
        for row in worksheet.iter_rows(min_row=2, max_row=len(df)+1):
            for cell in row:
                cell.alignment = center_alignment
                cell.border = border
                
                # 根据操作类型和交易结果设置颜色
                if cell.column == 2:  # 操作类型列
                    if cell.value == "开仓":
                        cell.fill = PatternFill(start_color="E6F3FF", end_color="E6F3FF", fill_type="solid")
                        cell.font = Font(color="0066CC")
                    elif "平仓" in str(cell.value):
                        if "止盈" in str(cell.value):
                            cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                            cell.font = Font(color="006100")
                        elif "止损" in str(cell.value):
                            cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                            cell.font = Font(color="9C0006")
                elif cell.column == 6:  # 交易金额列
                    cell.font = Font(bold=True)
                    if "开仓" in worksheet.cell(row=cell.row, column=2).value:
                        cell.font = Font(color="0066CC", bold=True)
                elif cell.column == 11:  # 交易结果列（位置变了，因为加了现金余额列）
                    if cell.value == "盈利":
                        cell.font = Font(color="006100", bold=True)
                    elif cell.value == "亏损":
                        cell.font = Font(color="9C0006", bold=True)
                elif cell.column == 12:  # 现金余额列
                    cell.font = Font(bold=True, color="FF6600")  # 橙色加粗显示现金余额
        
        # 自动调整列宽
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 20)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # 添加统计信息表
        stats_data = []
        if trade_data:
            # 分离开仓和平仓操作进行统计
            open_trades = [t for t in trade_data if t['操作类型'] == '开仓']
            close_trades = [t for t in trade_data if '平仓' in t['操作类型']]
            
            total_complete_trades = len(close_trades)  # 完整交易次数
            profit_trades = len([t for t in close_trades if t['交易结果'] == '盈利'])
            loss_trades = len([t for t in close_trades if t['交易结果'] == '亏损'])
            win_rate = (profit_trades / total_complete_trades) * 100 if total_complete_trades > 0 else 0
            
            # 计算总盈亏（只计算平仓记录）
            total_pnl = sum([float(t['盈亏金额'].replace('$', '')) for t in close_trades if t['盈亏金额'] != '-'])
            
            # 统计开仓类型（满仓模式，无加仓）
            long_opens = len([t for t in open_trades if t['交易方向'] == '做多'])
            short_opens = len([t for t in open_trades if t['交易方向'] == '做空'])
            
            # 统计平仓类型
            take_profit_closes = len([t for t in close_trades if '止盈' in t['操作类型']])
            stop_loss_closes = len([t for t in close_trades if '止损' in t['操作类型']])
            ma_closes = len([t for t in close_trades if '回归MA' in t['操作类型']])
            
            stats_data = [
                ['交易统计', ''],
                ['总开仓次数', len(open_trades)],
                ['总平仓次数', len(close_trades)],
                ['完整交易次数', total_complete_trades],
                ['做多开仓', long_opens],
                ['做空开仓', short_opens],
                ['止盈平仓', take_profit_closes],
                ['止损平仓', stop_loss_closes],
                ['回归MA平仓', ma_closes],
                ['盈利次数', profit_trades],
                ['亏损次数', loss_trades],
                ['胜率', f"{win_rate:.2f}%"],
                ['总盈亏', f"${total_pnl:.2f}"],
                ['', ''],
                ['策略参数', ''],
                ['单周期模式', config['timeframe']],
                ['VIDYA长度', config.get('vidya_length', 20)],
                ['VIDYA动量', config.get('vidya_momentum', 9)],
                ['VIDYA平滑', config.get('vidya_smooth', 15)],
                ['ATR距离', config.get('vidya_band_distance', 2.0)],
                ['ATR周期', config.get('vidya_atr_period', 200)],
                ['固定止盈', f"{config['fixed_take_profit_pct']}%"],
                ['止损策略', 'VIDYA动态止损跟随'],
                ['开仓机制', 'VIDYA趋势改变时开仓']
            ]
        
        stats_df = pd.DataFrame(stats_data, columns=['项目', '数值'])
        stats_df.to_excel(writer, sheet_name='统计汇总', index=False)
        
        # 设置统计表样式
        stats_sheet = writer.sheets['统计汇总']
        for cell in stats_sheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_alignment
        
        for column in stats_sheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 25)
            stats_sheet.column_dimensions[column_letter].width = adjusted_width
    
    print(f"✅ 交易记录已导出到: {filename}")
    open_count = len([t for t in trade_data if t['操作类型'] == '开仓'])
    close_count = len([t for t in trade_data if '平仓' in t['操作类型']])
    print(f"📊 共导出 {len(trade_data)} 条记录 (开仓: {open_count}, 平仓: {close_count})")
    
    return filename

def create_chart_html(chart_data, output_dir):
    """创建交互式图表HTML"""
    import json
    config_info = chart_data.get('config_info', {})
    timeframe = config_info.get('timeframe', '30m')
    
    html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>纯VIDYA策略回测 - 真实数据交互图表</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            color: #ffffff;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1800px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            background: rgba(255, 255, 255, 0.08);
            padding: 25px;
            border-radius: 15px;
            backdrop-filter: blur(15px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .header h1 {{
            margin: 0 0 15px 0;
            color: #00d4ff;
            text-shadow: 0 0 30px rgba(0, 212, 255, 0.4);
            font-size: 2.2em;
        }}
        .config-info {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
            padding: 20px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 10px;
        }}
        .config-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 12px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            border-left: 3px solid #00d4ff;
        }}
        .chart-container {{
            width: 100%;
            height: 800px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(15px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .legend {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-bottom: 25px;
            flex-wrap: wrap;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 15px;
            background: rgba(255, 255, 255, 0.08);
            padding: 10px 15px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            box-shadow: 0 0 10px rgba(255, 255, 255, 0.3);
        }}
        .info-panel {{
            background: rgba(255, 255, 255, 0.08);
            padding: 25px;
            border-radius: 15px;
            margin-top: 30px;
            backdrop-filter: blur(15px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 12px 15px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            border-left: 4px solid #00d4ff;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 纯VIDYA策略回测 - {timeframe}K线图表</h1>
            <p style="color: #cccccc; font-size: 16px;">💫 VIDYA动态趋势 + 固定止盈 + VIDYA动态止损 | 🎯 真实回测数据 | 📊 交互式分析</p>
            
            <div class="config-info">
                <div class="config-item">
                    <span>📅 回测开始:</span>
                    <span style="color: #00d4ff; font-weight: bold;">{config_info.get('start_date', 'N/A')}</span>
                </div>
                <div class="config-item">
                    <span>📅 回测结束:</span>
                    <span style="color: #00d4ff; font-weight: bold;">{config_info.get('end_date', 'N/A')}</span>
                </div>
                <div class="config-item">
                    <span>🎯 时间周期:</span>
                    <span style="color: #00d4ff; font-weight: bold;">{config_info.get('timeframe', 'N/A')}</span>
                </div>
                <div class="config-item">
                    <span>⚡ VIDYA参数:</span>
                    <span style="color: #00d4ff; font-weight: bold;">{config_info.get('vidya_length', 20)}/{config_info.get('vidya_momentum', 9)}/{config_info.get('vidya_smooth', 15)}</span>
                </div>
                <div class="config-item">
                    <span>📏 ATR带宽:</span>
                    <span style="color: #00d4ff; font-weight: bold;">距离{config_info.get('vidya_band_distance', 2.0)} | 周期{config_info.get('vidya_atr_period', 200)}</span>
                </div>
                <div class="config-item">
                    <span>🔍 枢轴点:</span>
                    <span style="color: #00d4ff; font-weight: bold;">左{config_info.get('vidya_pivot_left', 3)}/右{config_info.get('vidya_pivot_right', 3)}</span>
                </div>
                <div class="config-item">
                    <span>💰 初始资金:</span>
                    <span style="color: #00d4ff; font-weight: bold;">${config_info.get('initial_capital', 0):,}</span>
                </div>
                <div class="config-item">
                    <span>📊 K线数量:</span>
                    <span style="color: #00d4ff; font-weight: bold;">{len(chart_data.get('klineData', []))}</span>
                </div>
                <div class="config-item">
                    <span>🎯 交易信号:</span>
                    <span style="color: #00d4ff; font-weight: bold;">{len(chart_data.get('tradeSignals', []))}</span>
                </div>
            </div>
        </div>

        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #00da3c, #00ff41);"></div>
                <span>📈 上涨K线</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #ec0000, #ff1744);"></div>
                <span>📉 下跌K线</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #ffaa00, #ffcc00);"></div>
                <span>📏 VIDYA上轨 (黄色细线)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #00aaff, #00ccff);"></div>
                <span>📏 VIDYA下轨 (蓝色细线)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #ff6600, #ff8800);"></div>
                <span>📈 做多趋势线 (橙色粗线)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #0066ff, #0088ff);"></div>
                <span>📉 做空趋势线 (蓝色粗线)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #17dfad, #00ff88);"></div>
                <span>📈 支撑位 (绿色细线)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #dd326b, #ff4081);"></div>
                <span>📉 阻力位 (红色细线)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #00ff00, #00dd00);"></div>
                <span>📊 EMA50 (绿色线)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #ffff00, #ffdd00);"></div>
                <span>📊 EMA120原始 (黄色虚线)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: linear-gradient(45deg, #ff00ff, #dd00dd);"></div>
                <span>📊 EMA120平滑 (紫色线)</span>
            </div>
        </div>

        <div class="chart-container">
            <div id="main-chart" style="width: 100%; height: 100%;"></div>
        </div>

        <div class="info-panel">
            <h3>📊 当前K线详情</h3>
            <div class="info-grid" id="currentInfo">
                <div class="info-row">
                    <span>🕐 时间:</span>
                    <span id="currentTime">点击K线查看详情</span>
                </div>
                <div class="info-row">
                    <span>📈 开盘:</span>
                    <span id="currentOpen">-</span>
                </div>
                <div class="info-row">
                    <span>⬆️ 最高:</span>
                    <span id="currentHigh">-</span>
                </div>
                <div class="info-row">
                    <span>⬇️ 最低:</span>
                    <span id="currentLow">-</span>
                </div>
                <div class="info-row">
                    <span>📉 收盘:</span>
                    <span id="currentClose">-</span>
                </div>
                <div class="info-row">
                    <span>🎯 VIDYA趋势:</span>
                    <span id="currentTrend">-</span>
                </div>
                <div class="info-row">
                    <span>📏 VIDYA上轨:</span>
                    <span id="currentUpperBand">-</span>
            </div>
                <div class="info-row">
                    <span>📏 VIDYA下轨:</span>
                    <span id="currentLowerBand">-</span>
                </div>
                <div class="info-row">
                    <span>💫 CMO动量:</span>
                    <span id="currentCMO">-</span>
                </div>
                <div class="info-row">
                    <span>📈 Buy交易量:</span>
                    <span id="currentBuyVolume">-</span>
                </div>
                <div class="info-row">
                    <span>📉 Sell交易量:</span>
                    <span id="currentSellVolume">-</span>
                </div>
                <div class="info-row">
                    <span>🎚️ Delta Volume(动态):</span>
                    <span id="currentDeltaVolume">-</span>
                </div>
                <div class="info-row" style="border-left: 4px solid #00ff00;">
                    <span>⚡ DV固定周期(14):</span>
                    <span id="currentDeltaVolumeFixed" style="font-weight: bold;">-</span>
                </div>
                <div class="info-row">
                    <span>📊 EMA50:</span>
                    <span id="currentEma50">-</span>
                </div>
                <div class="info-row">
                    <span>📊 EMA120原始:</span>
                    <span id="currentEma120Raw">-</span>
                </div>
                <div class="info-row">
                    <span>📊 EMA120平滑:</span>
                    <span id="currentEma120Smoothed">-</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        const backtestData = {json.dumps(chart_data, ensure_ascii=False, indent=8)};
        
        const chartDom = document.getElementById('main-chart');
        const myChart = echarts.init(chartDom, 'dark');
        
        function getChartOption(data) {{
            return {{
                animation: true,
                backgroundColor: 'transparent',
                legend: {{
                    show: true,
                    top: 10,
                    left: 'center',
                    textStyle: {{
                        color: '#ffffff',
                        fontSize: 13
                    }},
                    selectedMode: true,  // 🔴 启用图例点击控制
                    selected: {{
                        'K线': true,
                        'VIDYA上轨': true,
                        'VIDYA下轨': true,
                        '做多趋势线': true,
                        '做空趋势线': true,
                        '支撑位': true,
                        '阻力位': true,
                        'EMA50': true,
                        'EMA120原始': false,  // 默认隐藏原始EMA120
                        'EMA120平滑': true
                    }}
                }},
                tooltip: {{
                    trigger: 'axis',
                    axisPointer: {{
                        type: 'cross',
                        lineStyle: {{
                            color: '#00d4ff',
                            width: 1.5,
                            opacity: 0.8
                        }}
                    }},
                    backgroundColor: 'rgba(20, 20, 30, 0.95)',
                    borderColor: '#00d4ff',
                    borderWidth: 2,
                    textStyle: {{
                        color: '#fff',
                        fontSize: 14
                    }},
                    formatter: function (params) {{
                        const dataIndex = params[0].dataIndex;
                        const time = data.timeData[dataIndex];
                        const kline = data.klineData[dataIndex];
                        const volume = data.volumeData[dataIndex];
                        const deltaVolume = data.deltaVolumeData[dataIndex];
                        const trendDirection = data.trendDirection[dataIndex];
                        
                        // 🔴 从后端获取真实的累积Buy/Sell交易量（Pine Script逻辑）
                        // 后端在整个趋势期间累积：阳线归buy_volume，阴线归sell_volume
                        const buyVolume = data.buyVolumeData[dataIndex] || 0;
                        const sellVolume = data.sellVolumeData[dataIndex] || 0;
                        const avgVolume = (buyVolume + sellVolume) / 2;
                        const deltaVolumePercent = avgVolume > 0 ? ((buyVolume - sellVolume) / avgVolume * 100).toFixed(2) : '0.00';
                        
                        // 获取上下轨数据
                        const upperBand = data.upperBandData[dataIndex];
                        const lowerBand = data.lowerBandData[dataIndex];
                        
                        // 🔴 获取EMA数据
                        const ema50 = data.ema50Data[dataIndex];
                        const ema120Raw = data.ema120RawData[dataIndex];
                        const ema120Smoothed = data.ema120SmoothedData[dataIndex];
                        
                        // 🔴 获取CMO数据
                        const cmo = data.cmoData[dataIndex];
                        
                        // 🔴 获取固定周期Delta Volume百分比
                        const deltaVolumePercentFixed = data.deltaVolumePercentFixed[dataIndex];
                        
                        updateInfoPanel(time, kline, null, null, null, null, null, null, null);
                        
                        const change = kline[1] - kline[0];
                        const changePercent = (change / kline[0] * 100).toFixed(3);
                        const changeColor = change >= 0 ? '#00da3c' : '#ec0000';
                        // 🔴 修正趋势颜色：做多时红色，做空时绿色
                        const trendColor = trendDirection === 'up' ? '#dd326b' : trendDirection === 'down' ? '#17dfad' : '#888888';
                        
                        return `
                            <div style="padding: 15px; min-width: 320px;">
                                <div style="margin-bottom: 12px; font-weight: bold; color: #00d4ff; font-size: 16px;">🕐 ${{time}}</div>
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px;">
                                    <div>📈 开盘: <span style="color: #fff; font-weight: bold;">$${{kline[0].toFixed(2)}}</span></div>
                                    <div>📉 收盘: <span style="color: ${{changeColor}}; font-weight: bold;">$${{kline[1].toFixed(2)}}</span></div>
                                    <div>⬆️ 最高: <span style="color: #00da3c; font-weight: bold;">$${{kline[3].toFixed(2)}}</span></div>
                                    <div>⬇️ 最低: <span style="color: #ec0000; font-weight: bold;">$${{kline[2].toFixed(2)}}</span></div>
                                </div>
                                <div style="margin-bottom: 12px; padding: 8px; background: rgba(0, 212, 255, 0.15); border-radius: 6px; text-align: center;">
                                    📊 涨跌: <span style="color: ${{changeColor}}; font-weight: bold; font-size: 15px;">$${{change.toFixed(2)}} (${{changePercent}}%)</span>
                                </div>
                                <hr style="margin: 12px 0; border-color: #444;">
                                <div style="display: grid; grid-template-columns: 1fr; gap: 8px;">
                                    <div style="color: ${{trendColor}}; font-size: 14px;">🎯 VIDYA趋势: <span style="font-weight: bold;">${{trendDirection === 'up' ? '做多 ▲' : trendDirection === 'down' ? '做空 ▼' : '中性'}}</span></div>
                                    ${{upperBand !== null ? `<div style="color: #ffaa00; font-size: 13px;">📏 VIDYA上轨: <span style="font-weight: bold;">$${{upperBand.toFixed(2)}}</span></div>` : ''}}
                                    ${{lowerBand !== null ? `<div style="color: #00aaff; font-size: 13px;">📏 VIDYA下轨: <span style="font-weight: bold;">$${{lowerBand.toFixed(2)}}</span></div>` : ''}}
                                    ${{cmo !== null ? `<div style="color: #00d4ff; font-size: 13px;">💫 CMO动量: <span style="font-weight: bold;">${{cmo.toFixed(2)}}</span></div>` : ''}}
                                    <div style="color: #00da3c; font-size: 13px;">📈 Buy: <span style="font-weight: bold;">${{buyVolume.toLocaleString()}}</span></div>
                                    <div style="color: #ec0000; font-size: 13px;">📉 Sell: <span style="font-weight: bold;">${{sellVolume.toLocaleString()}}</span></div>
                                    <div style="color: ${{deltaVolumePercent >= 0 ? '#00da3c' : '#ec0000'}}; font-size: 13px;">🎚️ Delta Volume(动态): <span style="font-weight: bold;">${{deltaVolumePercent >= 0 ? '+' : ''}}${{deltaVolumePercent}}%</span></div>
                                    ${{deltaVolumePercentFixed !== null && deltaVolumePercentFixed !== undefined ? `<div style="color: ${{deltaVolumePercentFixed >= 0 ? '#00da3c' : '#ec0000'}}; font-size: 14px; font-weight: bold;">⚡ DV固定周期(14): <span>${{deltaVolumePercentFixed >= 0 ? '+' : ''}}${{deltaVolumePercentFixed}}%</span></div>` : ''}}
                                    <hr style="margin: 8px 0; border-color: #444;">
                                    ${{ema50 !== null ? `<div style="color: #00ff00; font-size: 13px;">📊 EMA50: <span style="font-weight: bold;">$${{ema50.toFixed(2)}}</span></div>` : ''}}
                                    ${{ema120Raw !== null ? `<div style="color: #ffff00; font-size: 13px;">📊 EMA120(原): <span style="font-weight: bold;">$${{ema120Raw.toFixed(2)}}</span></div>` : ''}}
                                    ${{ema120Smoothed !== null ? `<div style="color: #ff00ff; font-size: 13px;">📊 EMA120(平滑): <span style="font-weight: bold;">$${{ema120Smoothed.toFixed(2)}}</span></div>` : ''}}
                                </div>
                            </div>
                        `;
                    }}
                }},
                grid: {{
                    left: '6%',
                    right: '6%',
                    bottom: 120,
                    top: 60,
                    backgroundColor: 'transparent'
                }},
                xAxis: {{
                    type: 'category',
                    data: data.timeData,
                    scale: true,
                    boundaryGap: false,
                    axisLine: {{ 
                        onZero: false,
                        lineStyle: {{ color: '#555' }}
                    }},
                    splitLine: {{ 
                        show: true,
                        lineStyle: {{ color: '#333', opacity: 0.6 }}
                    }},
                    axisLabel: {{
                        formatter: function (value) {{
                            return value.slice(5, 16);
                        }},
                        color: '#cccccc',
                        fontSize: 12
                    }}
                }},
                yAxis: {{
                    scale: true,
                    splitArea: {{
                        show: true,
                        areaStyle: {{
                            color: [['rgba(0, 212, 255, 0.03)', 'rgba(0, 212, 255, 0.01)']]
                        }}
                    }},
                    splitLine: {{
                        lineStyle: {{ color: '#333', opacity: 0.6 }}
                    }},
                    axisLabel: {{
                        formatter: function (value) {{
                            return '$' + value.toFixed(0);
                        }},
                        color: '#cccccc',
                        fontSize: 12
                    }},
                    axisLine: {{
                        lineStyle: {{ color: '#555' }}
                    }}
                }},
                dataZoom: [
                    {{
                        type: 'inside',
                        start: 80,
                        end: 100
                    }},
                    {{
                        show: true,
                        type: 'slider',
                        top: '94%',
                        start: 80,
                        end: 100,
                        backgroundColor: 'rgba(45, 45, 45, 0.8)',
                        borderColor: '#00d4ff',
                        fillerColor: 'rgba(0, 212, 255, 0.25)',
                        handleStyle: {{
                            color: '#00d4ff',
                            borderColor: '#00d4ff'
                        }},
                        textStyle: {{
                            color: '#cccccc'
                        }}
                    }}
                ],
                series: [
                    {{
                        name: 'K线',
                        type: 'candlestick',
                        data: data.klineData,
                        itemStyle: {{
                            color: '#00da3c',
                            color0: '#ec0000',
                            borderColor: '#00da3c',
                            borderColor0: '#ec0000',
                            borderWidth: 1.5
                        }}
                    }},
                    {{
                        name: 'VIDYA上轨',
                        type: 'line',
                        data: data.upperBandData || [],
                        smooth: true,
                        lineStyle: {{
                            color: '#ffaa00',  // 🔴 黄色细线
                            width: 1,
                            type: 'solid'
                        }},
                        symbol: 'none',
                        z: 2
                    }},
                    {{
                        name: 'VIDYA下轨',
                        type: 'line',
                        data: data.lowerBandData || [],
                        smooth: true,
                        lineStyle: {{
                            color: '#00aaff',  // 🔴 蓝色细线
                            width: 1,
                            type: 'solid'
                        }},
                        symbol: 'none',
                        z: 2
                    }},
                    {{
                        name: '做多趋势线',
                        type: 'line',
                        data: (function() {{
                            // 🔴 做多时显示下轨粗线，做空时隐藏
                            const lowerBand = data.lowerBandData || [];
                            const trendDirection = data.trendDirection || [];
                            const result = [];
                            
                            for (let i = 0; i < trendDirection.length; i++) {{
                                if (trendDirection[i] === 'up') {{
                                    // 做多时显示下轨
                                    result.push(lowerBand[i]);
                                }} else {{
                                    // 做空时隐藏
                                    result.push(null);
                                }}
                            }}
                            return result;
                        }})(),
                        smooth: true,
                        lineStyle: {{
                            color: '#ff6600',  // 🔴 橙色粗线
                            width: 3,
                            type: 'solid'
                        }},
                        symbol: 'none',
                        connectNulls: false,
                        z: 3
                    }},
                    {{
                        name: '做空趋势线',
                        type: 'line',
                        data: (function() {{
                            // 🔴 做空时显示上轨粗线，做多时隐藏
                            const upperBand = data.upperBandData || [];
                            const trendDirection = data.trendDirection || [];
                            const result = [];
                            
                            for (let i = 0; i < trendDirection.length; i++) {{
                                if (trendDirection[i] === 'down') {{
                                    // 做空时显示上轨
                                    result.push(upperBand[i]);
                                }} else {{
                                    // 做多时隐藏
                                    result.push(null);
                                }}
                            }}
                            return result;
                        }})(),
                        smooth: true,
                        lineStyle: {{
                            color: '#0066ff',  // 🔴 蓝色粗线
                            width: 3,
                            type: 'solid'
                        }},
                        symbol: 'none',
                        connectNulls: false,
                        z: 3
                    }},
                    {{
                        name: '支撑位',
                        type: 'custom',
                        renderItem: function(params, api) {{
                            const supportData = data.supportLevels || [];
                            const dataIndex = params.dataIndex;
                            const supportList = supportData[dataIndex];  // 现在是数组
                            
                            // 如果没有支撑位数据，返回null
                            if (!supportList || !Array.isArray(supportList) || supportList.length === 0) {{
                                return null;
                            }}
                            
                            // 🔴 为每个支撑位画一条短线（2根K线宽度）
                            const lineLength = 2;
                            const lines = [];
                            
                            for (let i = 0; i < supportList.length; i++) {{
                                const supportValue = supportList[i];
                                
                                // 检查是否是新的支撑位（与前一个时间点的不同）
                                const prevSupportList = dataIndex > 0 ? supportData[dataIndex - 1] : [];
                                const isNewSupport = !prevSupportList || !prevSupportList.includes(supportValue);
                                
                                if (!isNewSupport) {{
                                    continue;  // 不是新支撑位，跳过
                                }}
                                
                                const startIndex = dataIndex;
                                const endIndex = Math.min(dataIndex + lineLength, supportData.length - 1);
                                
                                const startPoint = api.coord([startIndex, supportValue]);
                                const endPoint = api.coord([endIndex, supportValue]);
                                
                                lines.push({{
                                    type: 'line',
                                    shape: {{
                                        x1: startPoint[0],
                                        y1: startPoint[1],
                                        x2: endPoint[0],
                                        y2: endPoint[1]
                                    }},
                                    style: {{
                                        stroke: '#17dfad',  // 绿色
                                        lineWidth: 1,
                                        opacity: 0.8
                                    }}
                                }});
                            }}
                            
                            // 如果有多条线，返回group；否则返回单条线
                            if (lines.length === 0) {{
                                return null;
                            }} else if (lines.length === 1) {{
                                return lines[0];
                            }} else {{
                                return {{
                                    type: 'group',
                                    children: lines
                                }};
                            }}
                        }},
                        data: data.supportLevels.map((value, index) => [index, value]),
                        z: 5
                    }},
                    {{
                        name: '阻力位',
                        type: 'custom',
                        renderItem: function(params, api) {{
                            const resistanceData = data.resistanceLevels || [];
                            const dataIndex = params.dataIndex;
                            const resistanceList = resistanceData[dataIndex];  // 现在是数组
                            
                            // 如果没有阻力位数据，返回null
                            if (!resistanceList || !Array.isArray(resistanceList) || resistanceList.length === 0) {{
                                return null;
                            }}
                            
                            // 🔴 为每个阻力位画一条短线（2根K线宽度）
                            const lineLength = 2;
                            const lines = [];
                            
                            for (let i = 0; i < resistanceList.length; i++) {{
                                const resistanceValue = resistanceList[i];
                                
                                // 检查是否是新的阻力位（与前一个时间点的不同）
                                const prevResistanceList = dataIndex > 0 ? resistanceData[dataIndex - 1] : [];
                                const isNewResistance = !prevResistanceList || !prevResistanceList.includes(resistanceValue);
                                
                                if (!isNewResistance) {{
                                    continue;  // 不是新阻力位，跳过
                                }}
                                
                                const startIndex = dataIndex;
                                const endIndex = Math.min(dataIndex + lineLength, resistanceData.length - 1);
                                
                                const startPoint = api.coord([startIndex, resistanceValue]);
                                const endPoint = api.coord([endIndex, resistanceValue]);
                                
                                lines.push({{
                                    type: 'line',
                                    shape: {{
                                        x1: startPoint[0],
                                        y1: startPoint[1],
                                        x2: endPoint[0],
                                        y2: endPoint[1]
                                    }},
                                    style: {{
                                        stroke: '#dd326b',  // 红色
                                        lineWidth: 1,
                                        opacity: 0.8
                                    }}
                                }});
                            }}
                            
                            // 如果有多条线，返回group；否则返回单条线
                            if (lines.length === 0) {{
                                return null;
                            }} else if (lines.length === 1) {{
                                return lines[0];
                            }} else {{
                                return {{
                                    type: 'group',
                                    children: lines
                                }};
                            }}
                        }},
                        data: data.resistanceLevels.map((value, index) => [index, value]),
                        z: 5
                    }},
                    {{
                        name: 'EMA50',
                        type: 'line',
                        data: data.ema50Data || [],
                        smooth: true,
                        lineStyle: {{
                            color: '#00ff00',  // 🔴 绿色
                            width: 2,
                            type: 'solid'
                        }},
                        symbol: 'none',
                        z: 4
                    }},
                    {{
                        name: 'EMA120原始',
                        type: 'line',
                        data: data.ema120RawData || [],
                        smooth: true,
                        lineStyle: {{
                            color: '#ffff00',  // 🔴 黄色
                            width: 1,
                            type: 'dashed'  // 虚线
                        }},
                        symbol: 'none',
                        z: 3
                    }},
                    {{
                        name: 'EMA120平滑',
                        type: 'line',
                        data: data.ema120SmoothedData || [],
                        smooth: true,
                        lineStyle: {{
                            color: '#ff00ff',  // 🔴 紫色
                            width: 2,
                            type: 'solid'
                        }},
                        symbol: 'none',
                        z: 4
                    }}
                ]
            }};
        }}
        
        function updateInfoPanel(time, kline, vidya, smoothedVidya, upperBand, lowerBand, support, resistance) {{
            document.getElementById('currentTime').textContent = time;
            document.getElementById('currentOpen').textContent = `$${{kline[0].toFixed(2)}}`;
            document.getElementById('currentHigh').textContent = `$${{kline[3].toFixed(2)}}`;
            document.getElementById('currentLow').textContent = `$${{kline[2].toFixed(2)}}`;
            document.getElementById('currentClose').textContent = `$${{kline[1].toFixed(2)}}`;
            
            // 🔴 获取当前趋势和交易量信息
            const dataIndex = backtestData.timeData.indexOf(time);
            if (dataIndex >= 0) {{
                const trendDirection = backtestData.trendDirection[dataIndex];
                const volume = backtestData.volumeData[dataIndex];
                const deltaVolume = backtestData.deltaVolumeData[dataIndex];
                const upperBand = backtestData.upperBandData[dataIndex];
                const lowerBand = backtestData.lowerBandData[dataIndex];
                
                // 🔴 从后端获取真实的累积Buy/Sell交易量
                const buyVolume = backtestData.buyVolumeData[dataIndex] || 0;
                const sellVolume = backtestData.sellVolumeData[dataIndex] || 0;
                const avgVolume = (buyVolume + sellVolume) / 2;
                const deltaVolumePercent = avgVolume > 0 ? ((buyVolume - sellVolume) / avgVolume * 100).toFixed(2) : '0.00';
                
                document.getElementById('currentTrend').textContent = trendDirection === 'up' ? '做多 ▲' : trendDirection === 'down' ? '做空 ▼' : '中性';
                document.getElementById('currentUpperBand').textContent = upperBand !== null ? `$${{upperBand.toFixed(2)}}` : 'N/A';
                document.getElementById('currentLowerBand').textContent = lowerBand !== null ? `$${{lowerBand.toFixed(2)}}` : 'N/A';
                document.getElementById('currentBuyVolume').textContent = buyVolume.toLocaleString();
                document.getElementById('currentSellVolume').textContent = sellVolume.toLocaleString();
                document.getElementById('currentDeltaVolume').textContent = `${{deltaVolumePercent >= 0 ? '+' : ''}}${{deltaVolumePercent}}%`;
                
                // 🔴 获取CMO数据
                const cmo = backtestData.cmoData[dataIndex];
                document.getElementById('currentCMO').textContent = cmo !== null ? `${{cmo.toFixed(2)}}` : 'N/A';
                
                // 🔴 获取固定周期Delta Volume百分比
                const deltaVolumePercentFixed = backtestData.deltaVolumePercentFixed[dataIndex];
                const deltaVolumeFixedText = deltaVolumePercentFixed !== null && deltaVolumePercentFixed !== undefined 
                    ? `${{deltaVolumePercentFixed >= 0 ? '+' : ''}}${{deltaVolumePercentFixed}}%` 
                    : 'N/A';
                const deltaVolumeFixedColor = deltaVolumePercentFixed >= 0 ? '#00da3c' : '#ec0000';
                const deltaVolumeFixedElement = document.getElementById('currentDeltaVolumeFixed');
                deltaVolumeFixedElement.textContent = deltaVolumeFixedText;
                deltaVolumeFixedElement.style.color = deltaVolumePercentFixed !== null && deltaVolumePercentFixed !== undefined ? deltaVolumeFixedColor : '#fff';
                
                // 🔴 获取EMA数据
                const ema50 = backtestData.ema50Data[dataIndex];
                const ema120Raw = backtestData.ema120RawData[dataIndex];
                const ema120Smoothed = backtestData.ema120SmoothedData[dataIndex];
                
                document.getElementById('currentEma50').textContent = ema50 !== null ? `$${{ema50.toFixed(2)}}` : 'N/A';
                document.getElementById('currentEma120Raw').textContent = ema120Raw !== null ? `$${{ema120Raw.toFixed(2)}}` : 'N/A';
                document.getElementById('currentEma120Smoothed').textContent = ema120Smoothed !== null ? `$${{ema120Smoothed.toFixed(2)}}` : 'N/A';
            }} else {{
                document.getElementById('currentTrend').textContent = 'N/A';
                document.getElementById('currentUpperBand').textContent = 'N/A';
                document.getElementById('currentLowerBand').textContent = 'N/A';
                document.getElementById('currentCMO').textContent = 'N/A';
                document.getElementById('currentBuyVolume').textContent = 'N/A';
                document.getElementById('currentSellVolume').textContent = 'N/A';
                document.getElementById('currentDeltaVolume').textContent = 'N/A';
                document.getElementById('currentDeltaVolumeFixed').textContent = 'N/A';
                document.getElementById('currentEma50').textContent = 'N/A';
                document.getElementById('currentEma120Raw').textContent = 'N/A';
                document.getElementById('currentEma120Smoothed').textContent = 'N/A';
            }}
        }}
        
        myChart.setOption(getChartOption(backtestData));
        
        myChart.on('click', function (params) {{
            if (params.componentType === 'series') {{
                const dataIndex = params.dataIndex;
                const time = backtestData.timeData[dataIndex];
                const kline = backtestData.klineData[dataIndex];
                
                updateInfoPanel(time, kline, null, null, null, null, null, null, null);
            }}
        }});
        
        window.addEventListener('resize', function() {{
            myChart.resize();
        }});
        
        console.log('🚀 真实回测数据图表已加载');
    </script>
</body>
</html>'''
    
    # 保存HTML文件到指定目录
    html_file = os.path.join(output_dir, "交互式图表.html")
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"🌐 交互式图表已保存: {html_file}")
    return html_file

def main():
    print("开始测试纯VIDYA策略...")
    
    # 使用配置文件中的数据库参数初始化db_service
    db_service = DatabaseService(**LOCAL_DATABASE_CONFIG)

    # 获取策略配置
    config = get_strategy_config()

    # 显示配置信息
    print_config_info()
    
    # 创建纯VIDYA策略实例
    strategy = TrendVolumaticDynamicAverageStrategy(
        timeframe=config['timeframe'],
        initial_capital=config['initial_capital'],
        position_size_percentage=config['position_size_percentage'],
        fixed_take_profit_pct=config['fixed_take_profit_pct'],
        max_loss_pct=config['max_loss_pct'],
        volatility_timeframe=config['volatility_timeframe'],
        volatility_length=config['volatility_length'],
        volatility_mult=config['volatility_mult'],
        volatility_ema_period=config['volatility_ema_period'],
        volatility_threshold=config['volatility_threshold'],
        basis_change_threshold=config['basis_change_threshold'],
        # 🔴 标准VIDYA参数
        vidya_length=config.get('vidya_length', 20),
        vidya_momentum=config.get('vidya_momentum', 9),
        vidya_smooth=config.get('vidya_smooth', 15),
        vidya_band_distance=config.get('vidya_band_distance', 2.0),
        vidya_atr_period=config.get('vidya_atr_period', 200),
        vidya_pivot_left=config.get('vidya_pivot_left', 3),
        vidya_pivot_right=config.get('vidya_pivot_right', 3),
        delta_volume_period=config.get('delta_volume_period', 14),  # 🔴 固定周期Delta Volume
        # 🔴 开仓条件配置（独立开关）
        entry_condition_trend_breakthrough=config.get('entry_condition_trend_breakthrough', True),
        entry_condition_arrow_signal=config.get('entry_condition_arrow_signal', False),
        entry_condition_vidya_slope=config.get('entry_condition_vidya_slope', False),
        entry_condition_delta_volume=config.get('entry_condition_delta_volume', True),
        entry_condition_ema_120_slope=config.get('entry_condition_ema_120_slope', False),
        # 📐 布林带中轨角度计算器参数
        enable_bb_angle_entry=config.get('enable_bb_angle_entry', False),
        bb_midline_period=config.get('bb_midline_period', 14),
        bb_angle_window_size=config.get('bb_angle_window_size', 14),
        bb_angle_threshold=config.get('bb_angle_threshold', 0.3),
        bb_r_squared_threshold=config.get('bb_r_squared_threshold', 0.6),
        bb_stop_loss_lock_periods=config.get('bb_stop_loss_lock_periods', 3),
        bb_max_loss_pct=config.get('bb_max_loss_pct', 1.0),
    )

    print(f"\n纯VIDYA策略初始化完成")
    print(f"📊 时间周期: {config['timeframe']}")
    print(f"🎯 VIDYA参数: length={config.get('vidya_length', 20)}, momentum={config.get('vidya_momentum', 9)}, smooth={config.get('vidya_smooth', 15)}")
    print(f"📏 ATR带宽: distance={config.get('vidya_band_distance', 2.0)}, period={config.get('vidya_atr_period', 200)}")
    print(f"🎯 交易逻辑: VIDYA趋势改变开仓 → 固定止盈{config['fixed_take_profit_pct']}% + VIDYA动态止损")
    
    # 交易统计
    trades = []
    initial_capital = config['initial_capital']
    current_position = None

    df = db_service.get_kline_data(config['long_coin'], config['start_date'], config['end_date'])

    if df.empty:
        print("未获取到数据，请检查数据库连接和表结构")
        return

    print(f"\n📊 获取到 {len(df)} 个数据点")
    print(f"时间范围: {df['timestamp'].min()} 到 {df['timestamp'].max()}")
    print(f"价格范围: ${df['low'].min():.2f} - ${df['high'].max():.2f}")

    # 🔥 滤波器预热：获取回测开始前的历史数据
    start_timestamp = pd.to_datetime(config['start_date'])
    warmup_days = 60  # 🔥 数据预热（确保VIDYA指标完全稳定，接近TradingView效果）
    warmup_start = start_timestamp - pd.Timedelta(days=warmup_days)
    warmup_start_str = warmup_start.strftime('%Y-%m-%d %H:%M:%S')
    warmup_end_str = config['start_date']
    
    print(f"\n🔥 获取预热数据...")
    print(f"预热时间范围: {warmup_start_str} 到 {warmup_end_str}")
    
    warmup_df = db_service.get_kline_data(config['long_coin'], warmup_start_str, warmup_end_str)
    
    if not warmup_df.empty:
        print(f"📈 预热数据: {len(warmup_df)} 个数据点")
        
        # 准备预热数据（包含完整的OHLC、volume和时间戳）
        warmup_data = []
        for _, row in warmup_df.iterrows():
            warmup_data.append({
                'timestamp': row['timestamp'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row.get('volume', 0)  # 🔴 添加成交量
            })
        
        # 执行预热
        strategy.warmup_filter(warmup_data)
    else:
        print("⚠️  未获取到预热数据，将使用默认初始化")

    print(f"\n🚀 开始正式回测，共 {len(df)} 个数据点")

    # 🎨 初始化图表数据收集（纯VIDYA）
    chart_data = {
        'timeData': [],
        'klineData': [],
        'vidyaData': [],  # 🔴 VIDYA数据
        'vidyaSmoothedData': [],  # 🔴 平滑VIDYA数据
        'cmoData': [],  # 🔴 CMO数据
        'volumeData': [],  # 🔴 成交量数据
        'buyVolumeData': [],  # 🔴 Buy Volume数据（累积）
        'sellVolumeData': [],  # 🔴 Sell Volume数据（累积）
        'deltaVolumeData': [],  # 🔴 Delta Volume数据（动态累积）
        'deltaVolumePercentFixed': [],  # 🔴 固定周期Delta Volume百分比（每1分钟更新）
        'upperBandData': [],  # 🔴 ATR上轨数据
        'lowerBandData': [],  # 🔴 ATR下轨数据
        'atrData': [],  # 🔴 ATR数据
        'supportLevels': [],  # 🔴 支撑线数据
        'resistanceLevels': [],  # 🔴 阻力线数据
        'trendDirection': [],  # 🔴 趋势方向数据 ('up', 'down', 'neutral')
        'trendChangeSignals': [],  # 🔴 趋势改变信号（用于显示箭头）
        'ema50Data': [],  # 🔴 EMA50数据
        'ema120RawData': [],  # 🔴 EMA120原始数据
        'ema120SmoothedData': [],  # 🔴 EMA120平滑数据（SMA50）
        'tradeSignals': [],
        'config_info': {
            'start_date': config['start_date'],
            'end_date': config['end_date'],
            'timeframe': config['timeframe'],
            'initial_capital': config['initial_capital'],
            'vidya_length': config.get('vidya_length', 20),
            'vidya_momentum': config.get('vidya_momentum', 9),
            'vidya_smooth': config.get('vidya_smooth', 15),
            'vidya_band_distance': config.get('vidya_band_distance', 2.0),
            'vidya_atr_period': config.get('vidya_atr_period', 200),
            'vidya_pivot_left': config.get('vidya_pivot_left', 3),
            'vidya_pivot_right': config.get('vidya_pivot_right', 3),
            'use_vidya_trading': config.get('use_vidya_trading', True),
            'use_delta_volume_filter': config.get('use_delta_volume_filter', True)
        }
    }
    
    # K线聚合状态（动态根据配置调整）
    current_kline = None
    current_kline_start = None

    # 执行策略
    for index, row in df.iterrows():
        timestamp = row['timestamp']
        open_price = row['open']
        high_price = row['high']
        low_price = row['low']
        close_price = row['close']
        volume = row.get('volume', 0)  # 🔴 获取成交量

        # 🎨 收集K线数据（用于图表，根据配置动态调整）
        timeframe = config['timeframe']
        
        # 根据时间周期计算K线开始时间
        if timeframe == '15m':
            minute = timestamp.minute
            if minute < 15:
                period_minute = 0
            elif minute < 30:
                period_minute = 15
            elif minute < 45:
                period_minute = 30
            else:
                period_minute = 45
            kline_start = timestamp.replace(minute=period_minute, second=0, microsecond=0)
        elif timeframe == '20m':
            minute = timestamp.minute
            if minute < 20:
                period_minute = 0
            elif minute < 40:
                period_minute = 20
            else:
                period_minute = 40
            kline_start = timestamp.replace(minute=period_minute, second=0, microsecond=0)
        elif timeframe == '30m':
            minute = timestamp.minute
            if minute < 30:
                period_minute = 0
            else:
                period_minute = 30
            kline_start = timestamp.replace(minute=period_minute, second=0, microsecond=0)
        elif timeframe == '1h':
            kline_start = timestamp.replace(minute=0, second=0, microsecond=0)
        elif timeframe == '2h':
            hour = timestamp.hour
            period_hour = (hour // 2) * 2
            kline_start = timestamp.replace(hour=period_hour, minute=0, second=0, microsecond=0)
        elif timeframe == '4h':
            hour = timestamp.hour
            period_hour = (hour // 4) * 4
            kline_start = timestamp.replace(hour=period_hour, minute=0, second=0, microsecond=0)
        else:
            # 默认30分钟
            minute = timestamp.minute
            if minute < 30:
                period_minute = 0
            else:
                period_minute = 30
            kline_start = timestamp.replace(minute=period_minute, second=0, microsecond=0)
        
        # 检查是否是新的K线周期
        if current_kline_start is None or kline_start != current_kline_start:
            # 保存上一个K线和指标数据
            if current_kline is not None:
                chart_data['timeData'].append(current_kline_start.strftime('%Y-%m-%d %H:%M:%S'))
                chart_data['klineData'].append([
                    round(current_kline['open'], 2),
                    round(current_kline['close'], 2),
                    round(current_kline['low'], 2),
                    round(current_kline['high'], 2)
                ])
                
                # SAR相关数据已删除，不再收集
                
                # 🔴 收集VIDYA数据
                current_vidya = strategy.vidya_indicator.current_vidya
                if current_vidya is not None:
                    chart_data['vidyaData'].append(round(current_vidya, 2))
                else:
                    chart_data['vidyaData'].append(None)
                
                # 🔴 收集平滑VIDYA数据
                if len(strategy.vidya_indicator.smoothed_vidya_values) > 0:
                    current_smoothed_vidya = strategy.vidya_indicator.smoothed_vidya_values[-1]
                    chart_data['vidyaSmoothedData'].append(round(current_smoothed_vidya, 2))
                else:
                    chart_data['vidyaSmoothedData'].append(None)
                
                # 🔴 收集CMO数据
                if len(strategy.vidya_indicator.close_history) >= strategy.vidya_indicator.vidya_momentum + 1:
                    # 计算当前CMO值
                    current_cmo = strategy._calculate_cmo(
                        strategy.vidya_indicator.close_history, 
                        strategy.vidya_indicator.vidya_momentum
                    )
                    chart_data['cmoData'].append(round(current_cmo, 2))
                else:
                    chart_data['cmoData'].append(None)
                
                # 🔴 收集成交量数据
                chart_data['volumeData'].append(current_kline.get('volume', 0))
                
                # 🔴 收集Buy/Sell Volume（累积值）
                current_buy_volume = strategy.vidya_indicator.buy_volume
                current_sell_volume = strategy.vidya_indicator.sell_volume
                chart_data['buyVolumeData'].append(current_buy_volume)
                chart_data['sellVolumeData'].append(current_sell_volume)
                
                # 🔴 收集Delta Volume（动态累积）
                current_delta_volume = strategy.vidya_indicator.delta_volume
                chart_data['deltaVolumeData'].append(current_delta_volume)
                
                # 🔴 收集固定周期Delta Volume百分比（每1分钟更新）
                current_delta_volume_percent_fixed = strategy.vidya_indicator.delta_volume_percent_fixed
                chart_data['deltaVolumePercentFixed'].append(round(current_delta_volume_percent_fixed, 2))
                
                # 🔴 收集ATR带宽数据（使用策略保存的当前值，确保与平仓逻辑一致）
                current_upper_band = strategy.current_upper_band
                current_lower_band = strategy.current_lower_band
                
                if current_upper_band is not None:
                    chart_data['upperBandData'].append(round(current_upper_band, 2))
                else:
                    chart_data['upperBandData'].append(None)
                
                if current_lower_band is not None:
                    chart_data['lowerBandData'].append(round(current_lower_band, 2))
                else:
                    chart_data['lowerBandData'].append(None)
                
                # 🔴 收集ATR数据
                if len(strategy.vidya_indicator.atr_values) > 0:
                    current_atr = strategy.vidya_indicator.atr_values[-1]
                    chart_data['atrData'].append(round(current_atr, 2))
                else:
                    chart_data['atrData'].append(None)
                
                # 🔴 收集所有支撑阻力线数据（用于图表显示）
                # 获取当前所有的支撑阻力位（最多3个）
                all_support_levels = strategy.vidya_indicator.support_levels if strategy.vidya_indicator.support_levels else []
                all_resistance_levels = strategy.vidya_indicator.resistance_levels if strategy.vidya_indicator.resistance_levels else []
                
                # 将所有支撑阻力位存储为列表（图表会显示所有的线）
                support_list = [round(s, 2) for s in all_support_levels] if all_support_levels else []
                resistance_list = [round(r, 2) for r in all_resistance_levels] if all_resistance_levels else []
                
                chart_data['supportLevels'].append(support_list)
                chart_data['resistanceLevels'].append(resistance_list)
                
                # 🔴 收集EMA数据
                if strategy.vidya_indicator.current_ema_50 is not None:
                    chart_data['ema50Data'].append(round(strategy.vidya_indicator.current_ema_50, 2))
                else:
                    chart_data['ema50Data'].append(None)
                
                if strategy.vidya_indicator.current_ema_120 is not None:
                    chart_data['ema120RawData'].append(round(strategy.vidya_indicator.current_ema_120, 2))
                else:
                    chart_data['ema120RawData'].append(None)
                
                if strategy.vidya_indicator.current_ema_120_smoothed is not None:
                    chart_data['ema120SmoothedData'].append(round(strategy.vidya_indicator.current_ema_120_smoothed, 2))
                else:
                    chart_data['ema120SmoothedData'].append(None)
                
                # 🔴 收集趋势方向数据
                current_trend = strategy.vidya_indicator.current_trend
                previous_trend = strategy.vidya_indicator.previous_trend
                chart_data['trendDirection'].append(current_trend if current_trend else 'neutral')
                
                # 🔴 检测趋势改变并记录箭头信号
                if previous_trend is not None and current_trend != previous_trend and current_trend != 'neutral':
                    # 趋势改变了，添加箭头标记
                    signal_data = {
                        'time': current_kline_start.strftime('%Y-%m-%d %H:%M:%S'),
                        'price': round(current_kline['close'], 2),
                        'direction': current_trend,  # 'up' or 'down'
                        'from_trend': previous_trend,
                        'to_trend': current_trend
                    }
                    chart_data['trendChangeSignals'].append(signal_data)
                    print(f"    🔄 检测到VIDYA趋势改变: {previous_trend} → {current_trend} @ {current_kline_start.strftime('%H:%M')} 价格${current_kline['close']:.2f}")
            
            # 开始新的K线周期
            current_kline_start = kline_start
            current_kline = {
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume  # 🔴 初始化成交量
            }
        else:
            # 更新当前K线
            current_kline['high'] = max(current_kline['high'], high_price)
            current_kline['low'] = min(current_kline['low'], low_price)
            current_kline['close'] = close_price
            current_kline['volume'] = current_kline.get('volume', 0) + volume  # 🔴 累加成交量

        # 更新趋势滤波器策略（传递volume）
        result = strategy.update(timestamp, open_price, high_price, low_price, close_price, volume)
        
        # 处理交易信号
        for signal in result['signals']:
            # 🔧 使用更精确的时间戳：如果有exit_timestamp且不为None就用它，否则用当前时间戳
            signal_timestamp = signal.get('exit_timestamp') if signal.get('exit_timestamp') is not None else timestamp
            
            trade_info = {
                'timestamp': signal_timestamp,
                'signal_type': signal['type'],
                'price': signal['price'],
                'reason': signal['reason']
            }
            
            # 添加止损止盈信息（只有开仓信号才有）
            if 'stop_loss' in signal:
                trade_info['stop_loss'] = signal['stop_loss']
            if 'take_profit' in signal:
                trade_info['take_profit'] = signal['take_profit']
            
            # 🔄 添加复投相关信息
            if 'invested_amount' in signal:
                trade_info['invested_amount'] = signal['invested_amount']
            if 'position_shares' in signal:
                trade_info['position_shares'] = signal['position_shares']
            if 'exit_amount' in signal:
                trade_info['exit_amount'] = signal['exit_amount']
            if 'cash_balance' in signal:
                trade_info['cash_balance'] = signal['cash_balance']
            if 'old_balance' in signal:
                trade_info['old_balance'] = signal['old_balance']
            if 'new_balance' in signal:
                trade_info['new_balance'] = signal['new_balance']
            
            if 'profit_loss' in signal:
                trade_info['profit_loss'] = signal['profit_loss']

            if 'transaction_fee' in signal:
                trade_info['transaction_fee'] = signal['transaction_fee']
            
            trades.append(trade_info)
            
            # 🎨 收集交易信号（用于图表显示）
            chart_signal = {
                'time': signal_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'type': signal['type'],
                'price': round(signal['price'], 2),
                'reason': signal['reason']
            }
            chart_data['tradeSignals'].append(chart_signal)
            
            # 🔍 调试信息：验证复投数据传递
            if signal['type'] in ['OPEN_LONG', 'OPEN_SHORT']:
                invested = trade_info.get('invested_amount', 'N/A')
                balance = trade_info.get('cash_balance', 'N/A')
                print(f"    🔄 开仓数据验证: 投入金额={invested} | 现金余额={balance}")
            elif signal['type'] in ['TAKE_PROFIT_LONG', 'TAKE_PROFIT_SHORT', 'STOP_LOSS_LONG', 'STOP_LOSS_SHORT']:
                old_balance = trade_info.get('old_balance', 'N/A')
                new_balance = trade_info.get('new_balance', 'N/A')
                print(f"    🔄 平仓数据验证: 旧余额={old_balance} | 新余额={new_balance}")
            
            # 更新资金状态和详细信息
            if signal['type'] == 'OPEN_LONG':
                current_position = 'long'
                stop_loss = signal.get('stop_loss', 0)
                take_profit = signal.get('take_profit', None)
                risk = abs(signal['price'] - stop_loss) if stop_loss else 0
                
                if take_profit is not None:
                    reward = abs(take_profit - signal['price'])
                    risk_reward_ratio = reward / risk if risk > 0 else 0
                    print(f"    💰 资金: ${initial_capital:,.2f} | 风险: ${risk:.2f} | 预期收益: ${reward:.2f} | 风险收益比: 1:{risk_reward_ratio:.2f}")
                else:
                    print(f"    💰 资金: ${initial_capital:,.2f} | 风险: ${risk:.2f} | 双周期动态止损策略 (无固定止盈目标)")
                    
            elif signal['type'] == 'OPEN_SHORT':
                current_position = 'short'
                stop_loss = signal.get('stop_loss', 0)
                take_profit = signal.get('take_profit', None)
                risk = abs(stop_loss - signal['price']) if stop_loss else 0
                
                if take_profit is not None:
                    reward = abs(signal['price'] - take_profit)
                    risk_reward_ratio = reward / risk if risk > 0 else 0
                    print(f"    💰 资金: ${initial_capital:,.2f} | 风险: ${risk:.2f} | 预期收益: ${reward:.2f} | 风险收益比: 1:{risk_reward_ratio:.2f}")
                else:
                    print(f"    💰 资金: ${initial_capital:,.2f} | 风险: ${risk:.2f} | 双周期动态止损策略 (无固定止盈目标)")
            elif signal['type'] in ['STOP_LOSS_LONG', 'STOP_LOSS_SHORT', 'TAKE_PROFIT_LONG', 'TAKE_PROFIT_SHORT']:
                current_position = None

        # 每10000个数据点保存一次状态
        if index % 10000 == 0:
            print(f"已处理 {index + 1}/{len(df)} 个数据点")

    # 🎨 保存最后一个K线
    if current_kline is not None:
        chart_data['timeData'].append(current_kline_start.strftime('%Y-%m-%d %H:%M:%S'))
        chart_data['klineData'].append([
            round(current_kline['open'], 2),
            round(current_kline['close'], 2),
            round(current_kline['low'], 2),
            round(current_kline['high'], 2)
        ])
        
        # SAR相关数据已删除，不再收集

    # === 回测结果统计 ===
    print(f"\n" + "=" * 60)
    print("📊 纯VIDYA策略回测结果")
    print("=" * 60)
    
    total_trades = len(trades)
    if total_trades > 0:
        # 统计交易类型
        long_opens = len([t for t in trades if t['signal_type'] == 'OPEN_LONG'])
        short_opens = len([t for t in trades if t['signal_type'] == 'OPEN_SHORT'])
        long_stops = len([t for t in trades if t['signal_type'] == 'STOP_LOSS_LONG'])
        short_stops = len([t for t in trades if t['signal_type'] == 'STOP_LOSS_SHORT'])
        long_profits = len([t for t in trades if t['signal_type'] == 'TAKE_PROFIT_LONG'])
        short_profits = len([t for t in trades if t['signal_type'] == 'TAKE_PROFIT_SHORT'])
        
        # 计算盈亏
        total_pnl = sum([t.get('profit_loss', 0) for t in trades if 'profit_loss' in t])
        
        print(f"📈 总交易次数: {total_trades}")
        print(f"🟢 开多次数: {long_opens}")
        print(f"🔴 开空次数: {short_opens}")
        print(f"✅ 多头止盈: {long_profits}")
        print(f"✅ 空头止盈: {short_profits}")
        print(f"❌ 多头止损: {long_stops}")
        print(f"❌ 空头止损: {short_stops}")
        print(f"💰 总盈亏: ${total_pnl:,.2f}")
        
        # 止盈止损比例
        total_closes = long_stops + short_stops + long_profits + short_profits
        if total_closes > 0:
            profit_rate = (long_profits + short_profits) / total_closes * 100
            loss_rate = (long_stops + short_stops) / total_closes * 100
            print(f"📊 止盈率: {profit_rate:.1f}% | 止损率: {loss_rate:.1f}%")
        
        # 显示最近几笔交易
        print(f"\n📋 最近5笔交易:")
        for trade in trades[-5:]:
            timestamp_str = trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if trade.get('timestamp') else 'N/A'
            pnl_str = f", 盈亏: ${trade['profit_loss']:,.2f}" if 'profit_loss' in trade else ""
            print(f"  {timestamp_str} | {trade['signal_type']} | 价格: ${trade['price']:,.2f}{pnl_str}")
            print(f"    原因: {trade['reason']}")
    else:
        print("❌ 未产生任何交易信号")
    
    # 显示最终策略状态
    final_status = strategy.get_current_status()
    print(f"\n🎯 最终策略状态:")
    print(f"  持仓状态: {final_status['position'] or '空仓'}")
    if final_status['entry_price']:
        print(f"  入场价格: ${final_status['entry_price']:,.2f}")
    if final_status['stop_loss_level']:
        print(f"  止损位: ${final_status['stop_loss_level']:,.2f}")
    if final_status['take_profit_level']:
        print(f"  止盈位: ${final_status['take_profit_level']:,.2f}")
    # SAR值已删除
    
    print(f"\n💰 资金状态:")
    print(f"  初始资金: ${initial_capital:,.2f} (单账户模式)")
    print(f"  策略现金余额: ${strategy.cash_balance:,.2f}")
    
    # 🔍 检查持仓状态
    if strategy.position is not None:
        print(f"  ⚠️  警告：策略还持有 {strategy.position} 仓位！")
        print(f"      入场价: ${strategy.entry_price:,.2f}")
        print(f"      持仓份额: {strategy.position_shares:.4f}")
        print(f"      投入金额: ${strategy.current_invested_amount:,.2f}")
    else:
        print(f"  ✅ 策略已清仓")
    
    # === 绩效分析 ===
    print(f"\n" + "=" * 60)
    print("📈 绩效分析")
    print("=" * 60)
    
    # 创建绩效分析器
    analyzer = PerformanceAnalyzer(config)
    
    # 准备价格数据 (timestamp, open, high, low, close)
    price_data = []
    for _, row in df.iterrows():
        price_data.append((row['timestamp'], row['open'], row['high'], row['low'], row['close']))
    
    # 计算每日净值
    nav_df = analyzer.calculate_daily_nav(trades, price_data)
    
    if not nav_df.empty:
        # 计算回撤
        nav_df = analyzer.calculate_drawdown(nav_df)
        
        # 计算关键绩效指标
        metrics = analyzer.calculate_performance_metrics(nav_df, trades)
        
        if metrics:
            # 创建统一的输出目录
            output_dir = create_output_directory(config, metrics['annualized_return'])
            
            print(f"\n📊 关键绩效指标:")
            print(f"  💰 总收益率: {metrics['total_return']:+.2f}%")
            print(f"  📈 年化收益率: {metrics['annualized_return']:+.2f}%")
            print(f"  📉 年化波动率: {metrics['volatility']:.2f}%")
            print(f"  🎯 夏普比率: {metrics['sharpe_ratio']:.2f}")
            print(f"  ⚠️  最大回撤: {metrics['max_drawdown']:.2f}%")
            print(f"  🎯 胜率: {metrics['win_rate']:.1f}%")
            print(f"  📊 盈亏比: {metrics['profit_loss_ratio']:.2f}")
            print(f"  🔄 总交易次数: {metrics['total_trades']}")
            print(f"  📅 交易天数: {metrics['trading_days']}")
            print(f"  💎 最终净值: ${metrics['final_nav']:,.2f}")
            
            # === 生成所有结果文件到统一目录 ===
            print(f"\n" + "=" * 60)
            print("📁 生成结果文件")
            print("=" * 60)
            
            # 1. 导出交易记录到Excel
            try:
                excel_file = export_trades_to_excel(trades, config, output_dir)
                if excel_file:
                    print(f"📋 交易记录: {os.path.abspath(excel_file)}")
            except Exception as e:
                print(f"⚠️  交易记录导出失败: {e}")
            
            # 2. 生成绩效图表
            try:
                chart_files = analyzer.generate_performance_charts(nav_df, output_dir)
                print(f"📈 绩效图表已生成")
            except Exception as e:
                print(f"⚠️  绩效图表生成失败: {e}")
            
            # 3. 生成绩效Excel报告
            try:
                perf_excel = analyzer.generate_performance_excel(nav_df, output_dir)
                if perf_excel:
                    print(f"📋 绩效Excel报告: {os.path.abspath(perf_excel)}")
            except Exception as e:
                print(f"⚠️  绩效Excel报告生成失败: {e}")
            
            # 4. 生成HTML报告
            try:
                html_report = analyzer.generate_html_report(nav_df, config['long_coin'], trades, config, output_dir)
                if html_report:
                    print(f"🌐 HTML绩效报告: {os.path.abspath(html_report)}")
            except Exception as e:
                print(f"⚠️  HTML报告生成失败: {e}")
            
            # 5. 生成交互式图表
            try:
                chart_html = create_chart_html(chart_data, output_dir)
                if chart_html:
                    print(f"🎨 交互式图表: {os.path.abspath(chart_html)}")
            except Exception as e:
                print(f"⚠️  交互式图表生成失败: {e}")
            
            print(f"\n✅ 所有结果文件已保存到: {os.path.abspath(output_dir)}")
    else:
        print("⚠️  无法计算净值，跳过绩效分析")
    
    # 关闭数据库连接
    db_service.disconnect()
    
    print(f"\n🎉 回测完成！所有结果文件已按币种和年化收益率分类保存")

if __name__ == "__main__":
    main() 