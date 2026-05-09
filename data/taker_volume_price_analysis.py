#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Taker量价分析工具
将1分钟K线聚合为5分钟，并与Taker数据合并进行量价分析
"""

import pandas as pd
import pymysql
from datetime import datetime
from zoneinfo import ZoneInfo
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

# 数据库配置
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'port': 3306,
    'user': 'quantify_read_write',
    'password': '02Ya6fPDo@w67UI%sEaDvPXfT',
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


def aggregate_1m_to_5m_kline(coin, start_date, end_date, db_config):
    """
    将1分钟K线聚合为5分钟K线
    
    Args:
        coin: 币种（'BTC', 'ETH', 'SOL'）
        start_date: 开始日期（datetime，UTC+8）
        end_date: 结束日期（datetime，UTC+8）
        db_config: 数据库配置字典
    
    Returns:
        DataFrame: 5分钟K线数据
    """
    connection = pymysql.connect(**db_config)
    
    try:
        # 获取所有相关年份的表
        years = set(range(start_date.year, end_date.year + 1))
        all_data = []
        
        for year in years:
            table_name = get_kline_table_name(coin, year)
            
            # 检查表是否存在
            check_table_query = f"""
            SELECT COUNT(*) as cnt
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = '{table_name}'
            """
            
            check_df = pd.read_sql(check_table_query, connection)
            if check_df.iloc[0]['cnt'] == 0:
                print(f"⚠️  表 {table_name} 不存在，跳过")
                continue
            
            # 查询该年份的1分钟K线数据
            query = f"""
            SELECT 
                time,
                CAST(open AS DECIMAL(20, 8)) AS open,
                CAST(high AS DECIMAL(20, 8)) AS high,
                CAST(low AS DECIMAL(20, 8)) AS low,
                CAST(close AS DECIMAL(20, 8)) AS close,
                CAST(vol_ccy AS DECIMAL(30, 8)) AS vol_ccy,
                CAST(vol_ccy_quote AS DECIMAL(30, 8)) AS vol_ccy_quote
            FROM `{table_name}`
            WHERE time >= %s AND time < %s
            ORDER BY time
            """
            
            start_ts = int(start_date.timestamp())
            end_ts = int(end_date.timestamp())
            
            print(f"📊 查询 {table_name}: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
            
            df = pd.read_sql(query, connection, params=(start_ts, end_ts))
            
            if not df.empty:
                print(f"   ✅ 获取到 {len(df)} 条1分钟K线数据")
                # 转换为datetime（兼容不同pandas版本）
                try:
                    # 尝试使用utc=True（pandas >= 1.2.0）
                    df['ts'] = pd.to_datetime(df['time'], unit='s', utc=True).dt.tz_convert('Asia/Shanghai')
                except TypeError:
                    # 兼容旧版本：先转换为datetime，再设置时区
                    df['ts'] = pd.to_datetime(df['time'], unit='s')
                    df['ts'] = df['ts'].dt.tz_localize('UTC').dt.tz_convert('Asia/Shanghai')
                all_data.append(df)
            else:
                print(f"   ⚠️  该时间段无数据")
        
        if not all_data:
            print("❌ 没有获取到任何K线数据")
            return pd.DataFrame()
        
        # 合并所有年份的数据
        df_all = pd.concat(all_data, ignore_index=True)
        df_all = df_all.sort_values('ts').reset_index(drop=True)
        
        print(f"📈 总共 {len(df_all)} 条1分钟K线，开始聚合为5分钟K线...")
        
        # 将时间对齐到5分钟（向下取整）
        df_all['ts_5m'] = df_all['ts'].dt.floor('5T')
        
        # 聚合为5分钟K线
        agg_dict = {
            'open': 'first',      # 开盘价：第一个
            'high': 'max',         # 最高价：最大值
            'low': 'min',          # 最低价：最小值
            'close': 'last',       # 收盘价：最后一个
            'vol_ccy': 'sum',      # 成交量：求和
            'vol_ccy_quote': 'sum' # 成交量（USDT）：求和
        }
        
        df_5m = df_all.groupby('ts_5m').agg(agg_dict).reset_index()
        df_5m = df_5m.rename(columns={
            'ts_5m': 'ts',
            'vol_ccy': 'vol_5m',
            'vol_ccy_quote': 'vol_usdt_5m'
        })
        
        # 移除时区信息（便于后续处理）
        df_5m['ts'] = df_5m['ts'].dt.tz_localize(None)
        
        print(f"✅ 聚合完成，共 {len(df_5m)} 条5分钟K线")
        print(f"   时间范围: {df_5m['ts'].min()} 至 {df_5m['ts'].max()}")
        
        return df_5m
        
    except Exception as e:
        print(f"❌ 聚合K线数据失败: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        connection.close()


def get_taker_volume_data(coin, start_date, end_date, db_config):
    """
    获取Taker数据
    
    Args:
        coin: 币种（'BTC', 'ETH', 'SOL'）
        start_date: 开始日期（datetime，UTC+8）
        end_date: 结束日期（datetime，UTC+8）
        db_config: 数据库配置字典
    
    Returns:
        DataFrame: Taker数据
    """
    connection = pymysql.connect(**db_config)
    
    try:
        config = COIN_CONFIG.get(coin.upper())
        if not config:
            raise ValueError(f"不支持的币种: {coin}")
        
        symbol = config['symbol']
        
        query = """
        SELECT 
            ts,
            buy_vol,
            sell_vol,
            ratio
        FROM okx_taker_volume
        WHERE coin = %s
          AND symbol = %s
          AND ts >= %s
          AND ts < %s
        ORDER BY ts
        """
        
        print(f"📊 查询Taker数据: {coin} {symbol}")
        print(f"   时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        df = pd.read_sql(query, connection, params=(coin.upper(), symbol, start_date, end_date))
        
        if not df.empty:
            df['ts'] = pd.to_datetime(df['ts'])
            print(f"   ✅ 获取到 {len(df)} 条Taker数据")
            print(f"   时间范围: {df['ts'].min()} 至 {df['ts'].max()}")
        else:
            print(f"   ⚠️  该时间段无Taker数据")
        
        return df
        
    except Exception as e:
        print(f"❌ 获取Taker数据失败: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        connection.close()


def merge_kline_taker_data(coin, start_date, end_date, db_config):
    """
    合并5分钟K线和Taker数据
    
    Args:
        coin: 币种（'BTC', 'ETH', 'SOL'）
        start_date: 开始日期（datetime，UTC+8）
        end_date: 结束日期（datetime，UTC+8）
        db_config: 数据库配置字典
    
    Returns:
        DataFrame: 合并后的量价分析数据
    """
    print(f"\n{'='*60}")
    print(f"🚀 开始分析 {coin} 量价数据")
    print(f"{'='*60}\n")
    
    # 获取5分钟K线
    df_kline = aggregate_1m_to_5m_kline(coin, start_date, end_date, db_config)
    
    if df_kline.empty:
        print("❌ K线数据为空，无法继续分析")
        return pd.DataFrame()
    
    # 获取Taker数据
    df_taker = get_taker_volume_data(coin, start_date, end_date, db_config)
    
    if df_taker.empty:
        print("⚠️  Taker数据为空，仅显示K线数据")
        # 即使没有Taker数据，也返回K线数据
        df_merged = df_kline.copy()
        df_merged['buy_vol'] = None
        df_merged['sell_vol'] = None
        df_merged['ratio'] = None
    else:
        # 合并数据（左连接，以K线时间为准）
        print(f"\n🔗 合并K线和Taker数据...")
        df_merged = pd.merge(
            df_kline,
            df_taker,
            on='ts',
            how='left',
            suffixes=('_kline', '_taker')
        )
        
        # 统计合并结果
        matched_count = df_merged['buy_vol'].notna().sum()
        total_count = len(df_merged)
        print(f"   ✅ 合并完成: {matched_count}/{total_count} 条数据有Taker匹配")
        
        # 调试信息：检查时间对齐情况
        if matched_count == 0:
            print(f"   ⚠️  警告：没有匹配到Taker数据！")
            print(f"   K线时间范围: {df_kline['ts'].min()} 至 {df_kline['ts'].max()}")
            print(f"   Taker时间范围: {df_taker['ts'].min()} 至 {df_taker['ts'].max()}")
            print(f"   K线时间示例（前5个）: {df_kline['ts'].head().tolist()}")
            print(f"   Taker时间示例（前5个）: {df_taker['ts'].head().tolist()}")
    
    # 计算量价指标
    print(f"\n📊 计算量价指标...")
    
    # 价格变化
    df_merged['price_change'] = df_merged['close'] - df_merged['open']
    df_merged['price_change_pct'] = (df_merged['price_change'] / df_merged['open'] * 100).round(4)
    
    # Taker指标（如果有数据）
    if df_merged['buy_vol'].notna().any():
        df_merged['net_taker'] = df_merged['buy_vol'] - df_merged['sell_vol']
        df_merged['total_taker'] = df_merged['buy_vol'] + df_merged['sell_vol']
        df_merged['buy_sell_ratio'] = (df_merged['buy_vol'] / df_merged['sell_vol']).round(4)
        
        # K线成交量与Taker量对比
        df_merged['vol_taker_ratio'] = (df_merged['vol_5m'] / df_merged['total_taker']).round(4)
        
        # Taker主导度
        df_merged['taker_dominance'] = (df_merged['total_taker'] / df_merged['vol_5m']).round(4)
        
        # 买卖失衡度
        df_merged['buy_sell_imbalance'] = (df_merged['net_taker'] / df_merged['total_taker']).round(4)
    else:
        # 如果没有Taker数据，填充NaN
        df_merged['net_taker'] = None
        df_merged['total_taker'] = None
        df_merged['buy_sell_ratio'] = None
        df_merged['vol_taker_ratio'] = None
        df_merged['taker_dominance'] = None
        df_merged['buy_sell_imbalance'] = None
    
    print(f"   ✅ 指标计算完成")
    
    # 显示统计摘要
    print(f"\n📈 数据统计摘要:")
    print(f"   总数据点: {len(df_merged)}")
    print(f"   价格范围: {df_merged['low'].min():.2f} - {df_merged['high'].max():.2f} USDT")
    print(f"   平均成交量: {df_merged['vol_5m'].mean():.2f} {coin}")
    
    if df_merged['total_taker'].notna().any():
        print(f"   平均Taker总量: {df_merged['total_taker'].mean():.2f} {coin}")
        print(f"   平均Taker主导度: {df_merged['taker_dominance'].mean():.4f}")
    
    return df_merged


def plot_volume_price_analysis(df, coin, title_suffix=""):
    """
    绘制量价分析图表
    
    Args:
        df: 合并后的量价分析数据（DataFrame）
        coin: 币种
        title_suffix: 标题后缀
    """
    if df.empty:
        print("❌ 数据为空，无法绘制图表")
        return None
    
    print(f"\n🎨 开始绘制图表...")
    
    # 检查是否有Taker数据
    has_taker_data = df['buy_vol'].notna().any()
    
    # 创建子图：4行1列（如果有Taker数据）或3行1列（如果只有K线数据）
    if has_taker_data:
        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=(
                f'{coin} 价格走势（5分钟K线）',
                '成交量 vs Taker量',
                'Taker买卖量',
                '价格变化 vs 净Taker量'
            ),
            row_heights=[0.35, 0.2, 0.2, 0.25]  # 增加价格变化的高度
        )
    else:
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=(
                f'{coin} 价格走势（5分钟K线）',
                '成交量',
                '价格变化'
            ),
            row_heights=[0.4, 0.3, 0.3]  # 增加价格变化的高度
        )
    
    # 1. 价格K线图（蜡烛图）
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
    
    # 2. 成交量对比（双Y轴）
    # 只显示有数据的部分
    df_vol = df[df['vol_5m'].notna()].copy()
    if not df_vol.empty:
        fig.add_trace(
            go.Bar(
                x=df_vol['ts'],
                y=df_vol['vol_5m'],
                name='K线成交量',
                marker_color='rgba(55, 128, 191, 0.7)'
            ),
            row=2, col=1
        )
    
    if has_taker_data:
        # 只显示有Taker数据的部分
        df_taker_vol = df[df['total_taker'].notna()].copy()
        if not df_taker_vol.empty:
            fig.add_trace(
                go.Bar(
                    x=df_taker_vol['ts'],
                    y=df_taker_vol['total_taker'],
                    name='Taker总量',
                    marker_color='rgba(219, 64, 82, 0.7)'
                ),
                row=2, col=1
            )
    
    # 3. Taker买卖量（如果有数据）
    if has_taker_data:
        # 只显示有Taker数据的部分
        df_taker_buy_sell = df[(df['buy_vol'].notna()) & (df['sell_vol'].notna())].copy()
        if not df_taker_buy_sell.empty:
            fig.add_trace(
                go.Bar(
                    x=df_taker_buy_sell['ts'],
                    y=df_taker_buy_sell['buy_vol'],
                    name='Taker买入',
                    marker_color='#26a69a'
                ),
                row=3, col=1
            )
            
            fig.add_trace(
                go.Bar(
                    x=df_taker_buy_sell['ts'],
                    y=-df_taker_buy_sell['sell_vol'],  # 负数显示在下方
                    name='Taker卖出',
                    marker_color='#ef5350'
                ),
                row=3, col=1
            )
    
    # 4. 价格变化 vs 净Taker量（如果有数据）
    if has_taker_data:
        # 只显示有数据的部分
        df_price_change = df[df['price_change_pct'].notna()].copy()
        if not df_price_change.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_price_change['ts'],
                    y=df_price_change['price_change_pct'],
                    mode='lines+markers',
                    name='价格变化%',
                    line=dict(color='#ff9800', width=2),
                    marker=dict(size=4)
                ),
                row=4, col=1
            )
        
        # 净Taker量（使用独立Y轴，不归一化，显示实际值）
        df_net_taker = df[df['net_taker'].notna()].copy()
        if not df_net_taker.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_net_taker['ts'],
                    y=df_net_taker['net_taker'],
                    mode='lines',
                    name='净Taker量（买入-卖出）',
                    line=dict(color='#9c27b0', width=2, dash='dash'),
                    yaxis='y5'
                ),
                row=4, col=1
            )
    else:
        # 只有价格变化
        df_price_change = df[df['price_change_pct'].notna()].copy()
        if not df_price_change.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_price_change['ts'],
                    y=df_price_change['price_change_pct'],
                    mode='lines+markers',
                    name='价格变化%',
                    line=dict(color='#ff9800', width=2),
                    marker=dict(size=4)
                ),
                row=3, col=1
            )
    
    # 更新布局
    title = f'{coin} 量价分析 {title_suffix}'
    if not has_taker_data:
        title += ' (仅K线数据，无Taker数据)'
    
    fig.update_layout(
        title=title,
        height=1400,  # 增加总高度
        showlegend=True,
        hovermode='x unified',
        xaxis_rangeslider_visible=True  # 启用底部滑动条
    )
    
    # 更新Y轴标签
    fig.update_yaxes(title_text="价格 (USDT)", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    
    if has_taker_data:
        fig.update_yaxes(title_text="Taker量", row=3, col=1)
        fig.update_yaxes(title_text="价格变化 (%)", row=4, col=1)
        
        # 添加第二个Y轴（第4个子图）- 显示净Taker量的实际值
        fig.update_layout(
            yaxis5=dict(
                title=dict(text="净Taker量（ETH）", font=dict(color='#9c27b0')),
                overlaying="y4",
                side="right",
                tickfont=dict(color='#9c27b0')
            )
        )
    else:
        fig.update_yaxes(title_text="价格变化 (%)", row=3, col=1)
    
    print(f"   ✅ 图表绘制完成")
    
    return fig


def main():
    """主函数"""
    # 配置参数
    coin = 'ETH'
    start_date = datetime(2026, 1, 6, 0, 0, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    end_date = datetime(2026, 1, 22, 23, 59, 59, tzinfo=ZoneInfo('Asia/Shanghai'))
    
    print(f"\n{'='*60}")
    print(f"📊 OKX Taker量价分析工具")
    print(f"{'='*60}")
    print(f"币种: {coin}")
    print(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # 合并数据
    df = merge_kline_taker_data(coin, start_date, end_date, DB_CONFIG)
    
    if df.empty:
        print("❌ 没有数据，退出")
        return
    
    # 保存数据到CSV（可选）
    csv_filename = f'{coin}_volume_price_analysis_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.csv'
    df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
    print(f"\n💾 数据已保存到: {csv_filename}")
    
    # 绘制图表
    fig = plot_volume_price_analysis(df, coin, f"{start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    
    if fig:
        # 保存为HTML
        html_filename = f'{coin}_volume_price_analysis_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.html'
        fig.write_html(html_filename)
        print(f"💾 图表已保存到: {html_filename}")
        
        # 显示图表（如果在Jupyter或支持的环境中）
        try:
            fig.show()
        except:
            print("💡 提示: 在浏览器中打开HTML文件查看交互式图表")
    
    print(f"\n✅ 分析完成！")


if __name__ == "__main__":
    main()

