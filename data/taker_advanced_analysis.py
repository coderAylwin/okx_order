#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Taker高级量价分析工具
整合Delta、Ratio、Cumulative Delta、背离检测等功能
基于数据库数据，直接分析
"""

import pandas as pd
import pymysql
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

# 数据库配置
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'port': 3306,
    'user': 'payment_pro',
    'password': 'nS4kO7tG1jH7cI6oR4b',
    'database': 'quantify',
    'charset': 'utf8mb4'
}

# 币种配置
COIN_CONFIG = {
    'BTC': {
        'symbol': 'BTC-USDT-SWAP',
        'table_prefix': 'ml_btc_swap_history_1m'
    },
    'ETH': {
        'symbol': 'ETH-USDT-SWAP',
        'table_prefix': 'ml_eth_swap_history_1m'
    },
    'SOL': {
        'symbol': 'SOL-USDT-SWAP',
        'table_prefix': 'ml_sol_swap_history_1m'
    }
}


def get_kline_table_name(coin, year):
    """获取K线表名"""
    config = COIN_CONFIG.get(coin.upper())
    if not config:
        raise ValueError(f"不支持的币种: {coin}")
    return f"{config['table_prefix']}_{year}"


def load_data_from_db(coin, start_date, end_date, db_config, delay_minutes=0):
    """
    从数据库加载数据并聚合为5分钟
    
    Args:
        coin: 币种
        start_date: 开始日期
        end_date: 结束日期
        db_config: 数据库配置
        delay_minutes: Taker数据延迟补偿（分钟）
    
    Returns:
        DataFrame: 包含K线和Taker数据的合并数据
    """
    connection = pymysql.connect(**db_config)
    
    try:
        config = COIN_CONFIG.get(coin.upper())
        symbol = config['symbol']
        
        # 1. 获取1分钟K线数据
        table_name = get_kline_table_name(coin, start_date.year)
        
        kline_query = f"""
        SELECT 
            time,
            CAST(open AS DECIMAL(20, 8)) AS open,
            CAST(high AS DECIMAL(20, 8)) AS high,
            CAST(low AS DECIMAL(20, 8)) AS low,
            CAST(close AS DECIMAL(20, 8)) AS close,
            CAST(vol_ccy AS DECIMAL(30, 8)) AS volume
        FROM `{table_name}`
        WHERE time >= %s AND time < %s
        ORDER BY time
        """
        
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())
        
        print(f"📊 加载{coin} 1分钟K线数据...")
        df_1m = pd.read_sql(kline_query, connection, params=(start_ts, end_ts))
        
        if df_1m.empty:
            print(f"   ⚠️  无K线数据")
            return pd.DataFrame()
        
        # 转换为datetime
        try:
            df_1m['ts'] = pd.to_datetime(df_1m['time'], unit='s', utc=True).dt.tz_convert('Asia/Shanghai')
        except TypeError:
            df_1m['ts'] = pd.to_datetime(df_1m['time'], unit='s')
            df_1m['ts'] = df_1m['ts'].dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai')
        
        df_1m['ts'] = df_1m['ts'].dt.tz_localize(None)
        df_1m.set_index('ts', inplace=True)
        
        print(f"   ✅ 获取到 {len(df_1m)} 条1分钟K线")
        
        # 2. 聚合为5分钟K线
        df_5m_kline = df_1m.resample('5T').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        # 3. 获取5分钟Taker数据
        taker_query = """
        SELECT 
            ts,
            buy_vol AS taker_buy_volume,
            sell_vol AS taker_sell_volume
        FROM okx_taker_volume
        WHERE coin = %s
          AND symbol = %s
          AND ts >= %s
          AND ts < %s
        ORDER BY ts
        """
        
        print(f"📊 加载{coin} 5分钟Taker数据...")
        df_5m_taker = pd.read_sql(taker_query, connection, params=(coin.upper(), symbol, start_date, end_date))
        
        if not df_5m_taker.empty:
            df_5m_taker['ts'] = pd.to_datetime(df_5m_taker['ts'])
            # 补偿延迟（如果需要）
            if delay_minutes > 0:
                df_5m_taker['ts'] = df_5m_taker['ts'] + timedelta(minutes=delay_minutes)
            df_5m_taker.set_index('ts', inplace=True)
            print(f"   ✅ 获取到 {len(df_5m_taker)} 条Taker数据")
        else:
            print(f"   ⚠️  无Taker数据")
            df_5m_taker = pd.DataFrame()
        
        # 4. 合并数据（left join，以K线时间为准）
        df_5m = df_5m_kline.join(df_5m_taker, how='left')
        
        # 填充缺失值
        df_5m[['taker_buy_volume', 'taker_sell_volume']] = df_5m[['taker_buy_volume', 'taker_sell_volume']].fillna(0)
        
        print(f"   ✅ 合并完成，共 {len(df_5m)} 条5分钟数据")
        
        return df_5m
        
    except Exception as e:
        print(f"❌ 加载数据失败: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        connection.close()


def calculate_indicators(df):
    """
    计算核心指标
    
    Args:
        df: 5分钟数据DataFrame
    
    Returns:
        DataFrame: 添加了指标列的数据
    """
    df = df.copy()
    
    # 基础指标
    df['delta'] = df['taker_buy_volume'] - df['taker_sell_volume']
    df['ratio'] = df['taker_buy_volume'] / df['taker_sell_volume'].replace(0, 1e-10)  # 避免除0
    df['cum_delta'] = df['delta'].cumsum()
    df['taker_total'] = df['taker_buy_volume'] + df['taker_sell_volume']
    df['taker_ratio_to_volume'] = df['taker_total'] / df['volume'].replace(0, 1e-10)
    
    # 价格变化
    df['close_pct_change'] = df['close'].pct_change() * 100
    df['price_change'] = df['close'] - df['open']
    
    # 滚动统计（用于背离检测）
    window = 10
    df['price_rolling_max'] = df['close'].rolling(window).max()
    df['price_rolling_min'] = df['close'].rolling(window).min()
    df['delta_rolling_max'] = df['delta'].rolling(window).max()
    df['delta_rolling_min'] = df['delta'].rolling(window).min()
    
    return df


def detect_signals(df, lookback=5):
    """
    检测交易信号
    
    Args:
        df: 数据DataFrame
        lookback: 回看周期
    
    Returns:
        list: 信号列表 [(timestamp, signal_type, description)]
    """
    signals = []
    df = df.reset_index()
    
    for i in range(lookback, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        # 1. 看多背离：价格创新低，但Delta变正/越来越大
        if (i >= 2 and 
            current['close'] < df.iloc[i-1]['close'] and 
            current['close'] < df.iloc[i-2]['close'] and 
            current['delta'] > 0 and 
            current['delta'] > prev['delta']):
            signals.append((
                current['ts'],
                'bullish_divergence',
                f"潜在底部 - Delta正向背离 (价格: {current['close']:.2f}, Delta: {current['delta']:.2f})"
            ))
        
        # 2. 看空背离：价格创新高，但Delta变负/越来越小
        if (i >= 2 and 
            current['close'] > df.iloc[i-1]['close'] and 
            current['close'] > df.iloc[i-2]['close'] and 
            current['delta'] < 0 and 
            current['delta'] < prev['delta']):
            signals.append((
                current['ts'],
                'bearish_divergence',
                f"潜在顶部 - Delta负向背离 (价格: {current['close']:.2f}, Delta: {current['delta']:.2f})"
            ))
        
        # 3. 极端买入情绪（Ratio > 2.0 且 Delta > 0）
        if current['ratio'] > 2.0 and current['delta'] > 0:
            signals.append((
                current['ts'],
                'extreme_buy',
                f"极端买入情绪 (Ratio: {current['ratio']:.2f}, Delta: {current['delta']:.2f})"
            ))
        
        # 4. 极端卖出情绪（Ratio < 0.5 且 Delta < 0）
        if current['ratio'] < 0.5 and current['delta'] < 0:
            signals.append((
                current['ts'],
                'extreme_sell',
                f"极端卖出情绪 (Ratio: {current['ratio']:.2f}, Delta: {current['delta']:.2f})"
            ))
        
        # 5. Cumulative Delta 反转
        if i >= 3:
            cum_delta_trend = current['cum_delta'] - df.iloc[i-3]['cum_delta']
            if abs(cum_delta_trend) > df['delta'].abs().quantile(0.8) * 3:
                signal_type = 'cum_delta_reversal_bullish' if cum_delta_trend > 0 else 'cum_delta_reversal_bearish'
                signals.append((
                    current['ts'],
                    signal_type,
                    f"Cumulative Delta反转 (变化: {cum_delta_trend:.2f})"
                ))
    
    return signals


def plot_advanced_analysis(df, coin, signals=None, title_suffix=""):
    """
    绘制高级分析图表
    
    Args:
        df: 数据DataFrame
        coin: 币种
        signals: 信号列表
        title_suffix: 标题后缀
    """
    if df.empty:
        print("❌ 数据为空，无法绘制图表")
        return None
    
    print(f"\n🎨 开始绘制高级分析图表...")
    
    df = df.reset_index()
    
    # 创建子图：5行1列
    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=(
            f'{coin} 价格走势（5分钟K线）',
            'Taker Buy vs Sell',
            'Delta',
            'Cumulative Delta',
            'Ratio & Taker占比'
        ),
        row_heights=[0.35, 0.15, 0.15, 0.15, 0.2]
    )
    
    # 1. 价格K线图
    fig.add_trace(
        go.Candlestick(
            x=df['ts'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='价格',
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350'
        ),
        row=1, col=1
    )
    
    # 标注信号
    if signals:
        for ts, signal_type, description in signals:
            price_at_signal = df[df['ts'] == ts]['close'].values
            if len(price_at_signal) > 0:
                color = '#ffeb3b' if 'bullish' in signal_type or 'buy' in signal_type else '#ff9800'
                fig.add_annotation(
                    x=ts,
                    y=price_at_signal[0],
                    text=description[:30] + '...' if len(description) > 30 else description,
                    showarrow=True,
                    arrowhead=2,
                    arrowcolor=color,
                    bgcolor=color,
                    bordercolor=color,
                    font=dict(size=9, color='black'),
                    row=1, col=1
                )
    
    # 2. Taker Buy vs Sell（堆叠柱状图）
    df_buy = df[df['taker_buy_volume'] > 0].copy()
    df_sell = df[df['taker_sell_volume'] > 0].copy()
    
    if not df_buy.empty:
        fig.add_trace(
            go.Bar(
                x=df_buy['ts'],
                y=df_buy['taker_buy_volume'],
                name='Taker Buy',
                marker_color='#26a69a'
            ),
            row=2, col=1
        )
    
    if not df_sell.empty:
        fig.add_trace(
            go.Bar(
                x=df_sell['ts'],
                y=-df_sell['taker_sell_volume'],
                name='Taker Sell',
                marker_color='#ef5350'
            ),
            row=2, col=1
        )
    
    # 3. Delta柱状图
    colors = ['#26a69a' if x >= 0 else '#ef5350' for x in df['delta']]
    fig.add_trace(
        go.Bar(
            x=df['ts'],
            y=df['delta'],
            name='Delta',
            marker_color=colors
        ),
        row=3, col=1
    )
    
    # 4. Cumulative Delta
    fig.add_trace(
        go.Scatter(
            x=df['ts'],
            y=df['cum_delta'],
            mode='lines',
            name='Cumulative Delta',
            line=dict(color='#00bcd4', width=2)
        ),
        row=4, col=1
    )
    
    # 5. Ratio & Taker占比（双Y轴）
    fig.add_trace(
        go.Scatter(
            x=df['ts'],
            y=df['ratio'],
            mode='lines',
            name='Buy/Sell Ratio',
            line=dict(color='#ff9800', width=2),
            yaxis='y6'
        ),
        row=5, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=df['ts'],
            y=df['taker_ratio_to_volume'] * 100,
            mode='lines',
            name='Taker占比 (%)',
            line=dict(color='#9c27b0', width=2, dash='dash')
        ),
        row=5, col=1
    )
    
    # 更新布局
    title = f'{coin} Taker高级量价分析 {title_suffix}'
    fig.update_layout(
        title=title,
        height=1600,
        showlegend=True,
        hovermode='x unified',
        xaxis_rangeslider_visible=True
    )
    
    # 更新Y轴标签
    fig.update_yaxes(title_text="价格 (USDT)", row=1, col=1)
    fig.update_yaxes(title_text="Taker量", row=2, col=1)
    fig.update_yaxes(title_text="Delta", row=3, col=1)
    fig.update_yaxes(title_text="Cumulative Delta", row=4, col=1)
    fig.update_yaxes(title_text="Taker占比 (%)", row=5, col=1)
    
    # 添加Ratio的Y轴（右侧）
    fig.update_layout(
        yaxis6=dict(
            title="Buy/Sell Ratio",
            overlaying="y5",
            side="right",
            titlefont=dict(color='#ff9800'),
            tickfont=dict(color='#ff9800')
        )
    )
    
    print(f"   ✅ 图表绘制完成")
    
    return fig


def main():
    """主函数"""
    # 配置参数
    coin = 'ETH'
    start_date = datetime(2026, 1, 6, 0, 0, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    end_date = datetime(2026, 1, 22, 23, 59, 59, tzinfo=ZoneInfo('Asia/Shanghai'))
    delay_minutes = 0  # Taker数据延迟补偿（分钟），可根据实际情况调整
    
    print(f"\n{'='*60}")
    print(f"📊 OKX Taker高级量价分析工具")
    print(f"{'='*60}")
    print(f"币种: {coin}")
    print(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Taker延迟补偿: {delay_minutes} 分钟")
    print(f"{'='*60}\n")
    
    # 加载数据
    df = load_data_from_db(coin, start_date, end_date, DB_CONFIG, delay_minutes)
    
    if df.empty:
        print("❌ 没有数据，退出")
        return
    
    # 计算指标
    print("\n📊 计算核心指标...")
    df = calculate_indicators(df)
    print(f"   ✅ 指标计算完成")
    
    # 检测信号
    print("\n🔍 检测交易信号...")
    signals = detect_signals(df)
    print(f"   ✅ 检测到 {len(signals)} 个信号")
    
    if signals:
        print("\n📋 信号详情:")
        for ts, signal_type, description in signals[:10]:  # 只显示前10个
            print(f"   {ts}: {description}")
        if len(signals) > 10:
            print(f"   ... 还有 {len(signals) - 10} 个信号")
    
    # 保存数据
    csv_filename = f'{coin}_advanced_analysis_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.csv'
    df.reset_index().to_csv(csv_filename, index=False, encoding='utf-8-sig')
    print(f"\n💾 数据已保存到: {csv_filename}")
    
    # 绘制图表
    fig = plot_advanced_analysis(
        df, coin, signals,
        f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}"
    )
    
    if fig:
        # 保存为HTML
        html_filename = f'{coin}_advanced_analysis_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.html'
        fig.write_html(html_filename)
        print(f"💾 图表已保存到: {html_filename}")
        
        try:
            fig.show()
        except:
            print("💡 提示: 在浏览器中打开HTML文件查看交互式图表")
    
    print(f"\n✅ 分析完成！")


if __name__ == "__main__":
    main()

