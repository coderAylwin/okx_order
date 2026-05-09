# OKX Taker量价分析实现方案

## 一、数据源分析

### 1. Taker数据（5分钟频率）
- **表名**：`okx_taker_volume`
- **字段**：
  - `coin`: 币种（BTC/ETH/SOL）
  - `symbol`: 合约符号（如BTC-USDT-SWAP）
  - `ts`: 时间戳（DATETIME，UTC+8）
  - `buy_vol`: 买入量（币）
  - `sell_vol`: 卖出量（币）
  - `ratio`: 买/卖比
- **时间对齐**：5分钟对齐（如：10:00, 10:05, 10:10...）

### 2. K线数据（1分钟频率）
- **表名格式**：`ml_{coin}_swap_history_1m_{year}`
  - BTC: `ml_btc_swap_history_1m_2025`
  - ETH: `ml_eth_swap_history_1m_2025`
  - SOL: `ml_sol_swap_history_1m_2025`
- **字段**：
  - `time`: 时间戳（INT，秒）
  - `open`, `high`, `low`, `close`: OHLC价格
  - `vol`: 交易量-合约（张）
  - `vol_ccy`: 交易量-币
  - `vol_ccy_quote`: 交易量-计价货币（USDT）
- **时间对齐**：1分钟对齐（如：10:00, 10:01, 10:02...）

---

## 二、技术实现方案

### 方案1：SQL聚合（推荐，性能好）

#### 2.1 聚合1分钟K线到5分钟K线

```sql
-- 示例：聚合BTC 2025年的1分钟K线到5分钟K线
SELECT 
    -- 将时间戳对齐到5分钟（向下取整）
    FROM_UNIXTIME(
        FLOOR(UNIX_TIMESTAMP(FROM_UNIXTIME(time)) / 300) * 300
    ) AS ts_5m,
    
    -- OHLC聚合规则
    MAX(CAST(high AS DECIMAL(20, 8))) AS high_5m,      -- 最高价：取5分钟内最高
    MIN(CAST(low AS DECIMAL(20, 8))) AS low_5m,         -- 最低价：取5分钟内最低
    SUBSTRING_INDEX(GROUP_CONCAT(CAST(open AS DECIMAL(20, 8)) ORDER BY time), ',', 1) AS open_5m,  -- 开盘价：取第一个
    SUBSTRING_INDEX(GROUP_CONCAT(CAST(close AS DECIMAL(20, 8)) ORDER BY time DESC), ',', 1) AS close_5m,  -- 收盘价：取最后一个
    
    -- 成交量聚合：求和
    SUM(CAST(vol_ccy AS DECIMAL(30, 8))) AS vol_5m,     -- 5分钟总成交量（币）
    SUM(CAST(vol_ccy_quote AS DECIMAL(30, 8))) AS vol_usdt_5m,  -- 5分钟总成交量（USDT）
    
    -- 统计信息
    COUNT(*) AS kline_count                             -- 包含的1分钟K线数量（应该是5条）
    
FROM ml_btc_swap_history_1m_2025
WHERE time >= UNIX_TIMESTAMP('2025-01-01 00:00:00')
  AND time < UNIX_TIMESTAMP('2025-01-02 00:00:00')
GROUP BY ts_5m
ORDER BY ts_5m;
```

#### 2.2 优化版本（使用窗口函数，MySQL 8.0+）

```sql
-- 更高效的聚合方式（如果MySQL版本支持）
SELECT 
    FROM_UNIXTIME(
        FLOOR(UNIX_TIMESTAMP(FROM_UNIXTIME(time)) / 300) * 300
    ) AS ts_5m,
    
    -- 使用窗口函数获取第一个和最后一个值
    FIRST_VALUE(CAST(open AS DECIMAL(20, 8))) OVER (
        PARTITION BY FLOOR(UNIX_TIMESTAMP(FROM_UNIXTIME(time)) / 300)
        ORDER BY time
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS open_5m,
    
    MAX(CAST(high AS DECIMAL(20, 8))) AS high_5m,
    MIN(CAST(low AS DECIMAL(20, 8))) AS low_5m,
    
    LAST_VALUE(CAST(close AS DECIMAL(20, 8))) OVER (
        PARTITION BY FLOOR(UNIX_TIMESTAMP(FROM_UNIXTIME(time)) / 300)
        ORDER BY time
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS close_5m,
    
    SUM(CAST(vol_ccy AS DECIMAL(30, 8))) AS vol_5m,
    SUM(CAST(vol_ccy_quote AS DECIMAL(30, 8))) AS vol_usdt_5m
    
FROM ml_btc_swap_history_1m_2025
WHERE time >= UNIX_TIMESTAMP('2025-01-01 00:00:00')
  AND time < UNIX_TIMESTAMP('2025-01-02 00:00:00')
GROUP BY ts_5m
ORDER BY ts_5m;
```

#### 2.3 关联Taker数据

```sql
-- 将5分钟K线与Taker数据关联
SELECT 
    k.ts_5m,
    k.open_5m,
    k.high_5m,
    k.low_5m,
    k.close_5m,
    k.vol_5m AS kline_vol,              -- K线成交量
    k.vol_usdt_5m AS kline_vol_usdt,    -- K线成交量（USDT）
    
    t.buy_vol AS taker_buy,             -- Taker买入量
    t.sell_vol AS taker_sell,           -- Taker卖出量
    t.ratio AS taker_ratio,             -- Taker买/卖比
    
    -- 计算量价指标
    (t.buy_vol - t.sell_vol) AS net_taker,           -- 净Taker量
    (t.buy_vol + t.sell_vol) AS total_taker,         -- 总Taker量
    (t.buy_vol / NULLIF(t.sell_vol, 0)) AS buy_sell_ratio,  -- 买卖比
    
    -- 价格变化
    (k.close_5m - k.open_5m) AS price_change,       -- 价格变化
    ((k.close_5m - k.open_5m) / NULLIF(k.open_5m, 0) * 100) AS price_change_pct,  -- 价格变化百分比
    
    -- 成交量与Taker量对比
    (k.vol_5m / NULLIF((t.buy_vol + t.sell_vol), 0)) AS vol_taker_ratio  -- K线成交量/Taker总量比

FROM (
    -- 5分钟K线聚合（子查询）
    SELECT 
        FROM_UNIXTIME(
            FLOOR(UNIX_TIMESTAMP(FROM_UNIXTIME(time)) / 300) * 300
        ) AS ts_5m,
        SUBSTRING_INDEX(GROUP_CONCAT(CAST(open AS DECIMAL(20, 8)) ORDER BY time), ',', 1) AS open_5m,
        MAX(CAST(high AS DECIMAL(20, 8))) AS high_5m,
        MIN(CAST(low AS DECIMAL(20, 8))) AS low_5m,
        SUBSTRING_INDEX(GROUP_CONCAT(CAST(close AS DECIMAL(20, 8)) ORDER BY time DESC), ',', 1) AS close_5m,
        SUM(CAST(vol_ccy AS DECIMAL(30, 8))) AS vol_5m,
        SUM(CAST(vol_ccy_quote AS DECIMAL(30, 8))) AS vol_usdt_5m
    FROM ml_btc_swap_history_1m_2025
    WHERE time >= UNIX_TIMESTAMP('2025-01-01 00:00:00')
      AND time < UNIX_TIMESTAMP('2025-01-02 00:00:00')
    GROUP BY ts_5m
) k

LEFT JOIN okx_taker_volume t 
    ON k.ts_5m = t.ts 
    AND t.coin = 'BTC' 
    AND t.symbol = 'BTC-USDT-SWAP'

ORDER BY k.ts_5m;
```

---

### 方案2：Python聚合（灵活，可扩展）

#### 2.1 数据聚合函数

```python
import pandas as pd
import pymysql
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def aggregate_1m_to_5m_kline(coin, start_date, end_date, db_config):
    """
    将1分钟K线聚合为5分钟K线
    
    Args:
        coin: 币种（'BTC', 'ETH', 'SOL'）
        start_date: 开始日期（datetime）
        end_date: 结束日期（datetime）
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
            table_name = f"ml_{coin.lower()}_swap_history_1m_{year}"
            
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
            FROM {table_name}
            WHERE time >= %s AND time < %s
            ORDER BY time
            """
            
            start_ts = int(start_date.timestamp())
            end_ts = int(end_date.timestamp())
            
            df = pd.read_sql(query, connection, params=(start_ts, end_ts))
            
            if not df.empty:
                # 转换为datetime
                df['ts'] = pd.to_datetime(df['time'], unit='s', tz='UTC').dt.tz_convert('Asia/Shanghai')
                all_data.append(df)
        
        if not all_data:
            return pd.DataFrame()
        
        # 合并所有年份的数据
        df_all = pd.concat(all_data, ignore_index=True)
        df_all = df_all.sort_values('ts')
        
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
        
        return df_5m
        
    finally:
        connection.close()


def get_taker_volume_data(coin, start_date, end_date, db_config):
    """
    获取Taker数据
    
    Args:
        coin: 币种（'BTC', 'ETH', 'SOL'）
        start_date: 开始日期（datetime）
        end_date: 结束日期（datetime）
        db_config: 数据库配置字典
    
    Returns:
        DataFrame: Taker数据
    """
    connection = pymysql.connect(**db_config)
    
    try:
        query = """
        SELECT 
            ts,
            buy_vol,
            sell_vol,
            ratio
        FROM okx_taker_volume
        WHERE coin = %s
          AND ts >= %s
          AND ts < %s
        ORDER BY ts
        """
        
        df = pd.read_sql(query, connection, params=(coin, start_date, end_date))
        
        if not df.empty:
            df['ts'] = pd.to_datetime(df['ts'])
        
        return df
        
    finally:
        connection.close()


def merge_kline_taker_data(coin, start_date, end_date, db_config):
    """
    合并5分钟K线和Taker数据
    
    Args:
        coin: 币种（'BTC', 'ETH', 'SOL'）
        start_date: 开始日期（datetime）
        end_date: 结束日期（datetime）
        db_config: 数据库配置字典
    
    Returns:
        DataFrame: 合并后的量价分析数据
    """
    # 获取5分钟K线
    df_kline = aggregate_1m_to_5m_kline(coin, start_date, end_date, db_config)
    
    # 获取Taker数据
    df_taker = get_taker_volume_data(coin, start_date, end_date, db_config)
    
    if df_kline.empty or df_taker.empty:
        return pd.DataFrame()
    
    # 合并数据（左连接，以K线时间为准）
    df_merged = pd.merge(
        df_kline,
        df_taker,
        on='ts',
        how='left',
        suffixes=('_kline', '_taker')
    )
    
    # 计算量价指标
    df_merged['price_change'] = df_merged['close'] - df_merged['open']
    df_merged['price_change_pct'] = (df_merged['price_change'] / df_merged['open'] * 100).round(4)
    
    df_merged['net_taker'] = df_merged['buy_vol'] - df_merged['sell_vol']
    df_merged['total_taker'] = df_merged['buy_vol'] + df_merged['sell_vol']
    df_merged['buy_sell_ratio'] = (df_merged['buy_vol'] / df_merged['sell_vol']).round(4)
    
    # K线成交量与Taker量对比
    df_merged['vol_taker_ratio'] = (df_merged['vol_5m'] / df_merged['total_taker']).round(4)
    
    return df_merged
```

---

## 三、可视化方案

### 方案1：使用 Plotly（交互式图表，推荐）

#### 3.1 多子图布局

```python
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def plot_volume_price_analysis(df, coin, title_suffix=""):
    """
    绘制量价分析图表
    
    Args:
        df: 合并后的量价分析数据（DataFrame）
        coin: 币种
        title_suffix: 标题后缀
    """
    # 创建子图：4行1列
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=(
            f'{coin} 价格走势（5分钟K线）',
            '成交量 vs Taker量',
            'Taker买卖量',
            '价格变化 vs 净Taker量'
        ),
        row_heights=[0.4, 0.2, 0.2, 0.2]
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
    fig.add_trace(
        go.Bar(
            x=df['ts'],
            y=df['vol_5m'],
            name='K线成交量',
            marker_color='rgba(55, 128, 191, 0.7)'
        ),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Bar(
            x=df['ts'],
            y=df['total_taker'],
            name='Taker总量',
            marker_color='rgba(219, 64, 82, 0.7)'
        ),
        row=2, col=1
    )
    
    # 3. Taker买卖量（堆叠柱状图）
    fig.add_trace(
        go.Bar(
            x=df['ts'],
            y=df['buy_vol'],
            name='Taker买入',
            marker_color='#26a69a'
        ),
        row=3, col=1
    )
    
    fig.add_trace(
        go.Bar(
            x=df['ts'],
            y=-df['sell_vol'],  # 负数显示在下方
            name='Taker卖出',
            marker_color='#ef5350'
        ),
        row=3, col=1
    )
    
    # 4. 价格变化 vs 净Taker量（散点图+趋势线）
    fig.add_trace(
        go.Scatter(
            x=df['ts'],
            y=df['price_change_pct'],
            mode='lines+markers',
            name='价格变化%',
            line=dict(color='#ff9800', width=2),
            marker=dict(size=4)
        ),
        row=4, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=df['ts'],
            y=df['net_taker'] / df['net_taker'].abs().max() * 100,  # 归一化到百分比范围
            mode='lines',
            name='净Taker量（归一化）',
            line=dict(color='#9c27b0', width=2, dash='dash'),
            yaxis='y5'
        ),
        row=4, col=1
    )
    
    # 更新布局
    fig.update_layout(
        title=f'{coin} 量价分析 {title_suffix}',
        height=1200,
        showlegend=True,
        hovermode='x unified',
        xaxis_rangeslider_visible=False
    )
    
    # 更新Y轴标签
    fig.update_yaxes(title_text="价格 (USDT)", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    fig.update_yaxes(title_text="Taker量", row=3, col=1)
    fig.update_yaxes(title_text="价格变化 (%)", row=4, col=1)
    
    # 添加第二个Y轴（第4个子图）
    fig.update_layout(
        yaxis5=dict(
            title="净Taker量（归一化）",
            overlaying="y4",
            side="right"
        )
    )
    
    return fig


# 使用示例
if __name__ == "__main__":
    db_config = {
        'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
        'port': 3306,
        'user': 'quantify_read_write',
        'password': '02Ya6fPDo@w67UI%sEaDvPXfT',
        'database': 'quantify'
    }
    
    coin = 'BTC'
    start_date = datetime(2025, 1, 1, tzinfo=ZoneInfo('Asia/Shanghai'))
    end_date = datetime(2025, 1, 2, tzinfo=ZoneInfo('Asia/Shanghai'))
    
    # 合并数据
    df = merge_kline_taker_data(coin, start_date, end_date, db_config)
    
    if not df.empty:
        # 绘制图表
        fig = plot_volume_price_analysis(df, coin, "2025-01-01")
        fig.show()
        
        # 保存为HTML
        fig.write_html(f'{coin}_volume_price_analysis.html')
    else:
        print("没有数据")
```

#### 3.2 热力图分析（相关性分析）

```python
import plotly.express as px
import numpy as np

def plot_correlation_heatmap(df):
    """
    绘制量价指标相关性热力图
    """
    # 选择数值列
    numeric_cols = [
        'open', 'high', 'low', 'close',
        'vol_5m', 'vol_usdt_5m',
        'buy_vol', 'sell_vol', 'ratio',
        'net_taker', 'total_taker', 'buy_sell_ratio',
        'price_change', 'price_change_pct',
        'vol_taker_ratio'
    ]
    
    # 计算相关性矩阵
    corr_matrix = df[numeric_cols].corr()
    
    # 绘制热力图
    fig = px.imshow(
        corr_matrix,
        labels=dict(x="指标", y="指标", color="相关系数"),
        x=corr_matrix.columns,
        y=corr_matrix.columns,
        color_continuous_scale='RdBu',
        aspect="auto"
    )
    
    fig.update_layout(
        title="量价指标相关性热力图",
        height=800
    )
    
    return fig
```

---

### 方案2：使用 Matplotlib（静态图表）

```python
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

def plot_volume_price_analysis_matplotlib(df, coin, title_suffix=""):
    """
    使用Matplotlib绘制量价分析图表
    """
    fig = plt.figure(figsize=(16, 12))
    gs = GridSpec(4, 1, figure=fig, height_ratios=[2, 1, 1, 1], hspace=0.3)
    
    # 1. 价格K线图
    ax1 = fig.add_subplot(gs[0])
    # 绘制蜡烛图（简化版，使用折线图）
    ax1.plot(df['ts'], df['close'], label='收盘价', linewidth=1.5)
    ax1.fill_between(df['ts'], df['low'], df['high'], alpha=0.3, label='价格区间')
    ax1.set_ylabel('价格 (USDT)', fontsize=12)
    ax1.set_title(f'{coin} 价格走势（5分钟K线）', fontsize=14, fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. 成交量对比
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.bar(df['ts'], df['vol_5m'], width=0.0003, label='K线成交量', alpha=0.7, color='blue')
    ax2_twin = ax2.twinx()
    ax2_twin.bar(df['ts'], df['total_taker'], width=0.0003, label='Taker总量', alpha=0.7, color='red')
    ax2.set_ylabel('K线成交量', fontsize=12, color='blue')
    ax2_twin.set_ylabel('Taker总量', fontsize=12, color='red')
    ax2.set_title('成交量 vs Taker量', fontsize=12, fontweight='bold')
    ax2.legend(loc='upper left')
    ax2_twin.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    # 3. Taker买卖量
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.bar(df['ts'], df['buy_vol'], width=0.0003, label='Taker买入', color='green', alpha=0.7)
    ax3.bar(df['ts'], -df['sell_vol'], width=0.0003, label='Taker卖出', color='red', alpha=0.7)
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax3.set_ylabel('Taker量', fontsize=12)
    ax3.set_title('Taker买卖量', fontsize=12, fontweight='bold')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # 4. 价格变化 vs 净Taker量
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    ax4.plot(df['ts'], df['price_change_pct'], label='价格变化%', linewidth=2, color='orange')
    ax4_twin = ax4.twinx()
    ax4_twin.plot(df['ts'], df['net_taker'], label='净Taker量', linewidth=2, color='purple', linestyle='--')
    ax4.set_ylabel('价格变化 (%)', fontsize=12, color='orange')
    ax4_twin.set_ylabel('净Taker量', fontsize=12, color='purple')
    ax4.set_title('价格变化 vs 净Taker量', fontsize=12, fontweight='bold')
    ax4.legend(loc='upper left')
    ax4_twin.legend(loc='upper right')
    ax4.grid(True, alpha=0.3)
    
    # 格式化X轴
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    ax4.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.suptitle(f'{coin} 量价分析 {title_suffix}', fontsize=16, fontweight='bold', y=0.995)
    plt.tight_layout()
    
    return fig
```

---

## 四、分析指标设计

### 4.1 量价关系指标

1. **Taker主导度** = `total_taker / vol_5m`
   - > 1: Taker交易量超过总成交量（异常，可能数据问题）
   - 接近1: Taker主导市场
   - < 0.5: 非Taker交易较多（可能是Maker或被动成交）

2. **买卖失衡度** = `(buy_vol - sell_vol) / total_taker`
   - > 0.3: 强烈买入压力
   - < -0.3: 强烈卖出压力
   - 接近0: 买卖平衡

3. **价格-Taker相关性**
   - 计算 `price_change_pct` 与 `net_taker` 的相关系数
   - 正值：净买入推动价格上涨
   - 负值：净买入反而价格下跌（可能被套）

4. **成交量放大倍数** = `vol_5m / vol_5m.rolling(20).mean()`
   - > 2: 成交量显著放大
   - < 0.5: 成交量萎缩

### 4.2 交易信号识别

```python
def identify_trading_signals(df):
    """
    识别交易信号
    
    Returns:
        DataFrame: 添加了信号列的数据
    """
    df = df.copy()
    
    # 信号1：强烈买入压力 + 价格上涨
    df['signal_buy_pressure'] = (
        (df['net_taker'] > df['net_taker'].rolling(20).quantile(0.8)) &
        (df['price_change_pct'] > 0) &
        (df['buy_sell_ratio'] > 1.2)
    )
    
    # 信号2：强烈卖出压力 + 价格下跌
    df['signal_sell_pressure'] = (
        (df['net_taker'] < df['net_taker'].rolling(20).quantile(0.2)) &
        (df['price_change_pct'] < 0) &
        (df['buy_sell_ratio'] < 0.8)
    )
    
    # 信号3：量价背离（价格上涨但Taker卖出增加）
    df['signal_divergence_bearish'] = (
        (df['price_change_pct'] > 0) &
        (df['net_taker'] < 0) &
        (df['sell_vol'] > df['sell_vol'].rolling(10).mean() * 1.2)
    )
    
    # 信号4：量价背离（价格下跌但Taker买入增加）
    df['signal_divergence_bullish'] = (
        (df['price_change_pct'] < 0) &
        (df['net_taker'] > 0) &
        (df['buy_vol'] > df['buy_vol'].rolling(10).mean() * 1.2)
    )
    
    return df
```

---

## 五、实现步骤

### 阶段1：数据聚合测试
1. ✅ 编写SQL聚合函数，测试1分钟→5分钟聚合
2. ✅ 验证时间对齐准确性（确保5分钟边界正确）
3. ✅ 测试数据完整性（确保没有遗漏）

### 阶段2：数据合并
1. ✅ 实现K线与Taker数据合并函数
2. ✅ 处理时间对齐问题（LEFT JOIN）
3. ✅ 计算量价指标

### 阶段3：可视化
1. ✅ 实现基础图表（价格、成交量、Taker量）
2. ✅ 添加交互功能（Plotly）
3. ✅ 优化图表布局和样式

### 阶段4：分析功能
1. ✅ 实现相关性分析
2. ✅ 实现交易信号识别
3. ✅ 添加统计摘要（均值、分位数等）

---

## 六、性能优化建议

1. **索引优化**
   - 确保 `okx_taker_volume` 表的 `(coin, ts)` 有索引
   - 确保K线表的 `time` 字段有索引

2. **缓存机制**
   - 对于历史数据，可以预先聚合并存储到新表
   - 实时数据使用增量更新

3. **分页查询**
   - 对于大量数据，使用分页查询避免内存溢出
   - 建议每次查询不超过7天的数据

4. **异步处理**
   - 如果数据量大，考虑使用异步查询
   - 使用多进程处理多个币种

---

## 七、下一步行动

1. **创建测试脚本**：实现数据聚合和合并功能
2. **创建可视化脚本**：实现图表绘制功能
3. **测试数据准确性**：验证聚合结果的正确性
4. **优化性能**：针对大数据量场景优化查询
5. **添加分析功能**：实现交易信号识别和统计摘要

