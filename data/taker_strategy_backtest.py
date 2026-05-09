#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Taker买卖比策略回测分析
策略规则：
1. 做空信号：ETH连续两个5分钟买卖比 < 0.8
2. 平仓信号：BTC和ETH同时买卖比 > 1.3
3. 计算胜率
"""

import pandas as pd
import pymysql
from datetime import datetime
from zoneinfo import ZoneInfo
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
    }
}


def get_taker_volume_data(coin, start_date, end_date, db_config):
    """
    获取Taker数据（包含买卖比）
    
    Args:
        coin: 币种（'BTC', 'ETH'）
        start_date: 开始日期（datetime，UTC+8）
        end_date: 结束日期（datetime，UTC+8）
        db_config: 数据库配置字典
    
    Returns:
        DataFrame: Taker数据，包含ts, buy_vol, sell_vol, ratio, buy_sell_ratio
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
            ratio,
            CASE 
                WHEN sell_vol > 0 THEN buy_vol / sell_vol
                ELSE NULL
            END AS buy_sell_ratio
        FROM okx_taker_volume
        WHERE coin = %s
          AND symbol = %s
          AND ts >= %s
          AND ts < %s
        ORDER BY ts
        """
        
        print(f"📊 查询{coin} Taker数据: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        df = pd.read_sql(query, connection, params=(coin.upper(), symbol, start_date, end_date))
        
        if not df.empty:
            df['ts'] = pd.to_datetime(df['ts'])
            print(f"   ✅ 获取到 {len(df)} 条{coin} Taker数据")
        else:
            print(f"   ⚠️  该时间段无{coin} Taker数据")
        
        return df
        
    except Exception as e:
        print(f"❌ 获取{coin} Taker数据失败: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        connection.close()


def get_price_data(coin, start_date, end_date, db_config):
    """
    获取价格数据（5分钟K线）
    
    Args:
        coin: 币种（'BTC', 'ETH'）
        start_date: 开始日期（datetime，UTC+8）
        end_date: 结束日期（datetime，UTC+8）
        db_config: 数据库配置字典
    
    Returns:
        DataFrame: 价格数据，包含ts, close（收盘价）
    """
    connection = pymysql.connect(**db_config)
    
    try:
        config = COIN_CONFIG.get(coin.upper())
        if not config:
            raise ValueError(f"不支持的币种: {coin}")
        
        table_name = f"{config['table_prefix']}_{start_date.year}"
        
        # 检查表是否存在
        check_table_query = f"""
        SELECT COUNT(*) as cnt
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
        AND table_name = '{table_name}'
        """
        
        check_df = pd.read_sql(check_table_query, connection)
        if check_df.iloc[0]['cnt'] == 0:
            print(f"⚠️  表 {table_name} 不存在")
            return pd.DataFrame()
        
        # 聚合1分钟K线为5分钟K线
        query = f"""
        SELECT 
            FROM_UNIXTIME(
                FLOOR(UNIX_TIMESTAMP(FROM_UNIXTIME(time)) / 300) * 300
            ) AS ts,
            SUBSTRING_INDEX(GROUP_CONCAT(CAST(close AS DECIMAL(20, 8)) ORDER BY time DESC), ',', 1) AS close
        FROM `{table_name}`
        WHERE time >= %s AND time < %s
        GROUP BY ts
        ORDER BY ts
        """
        
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())
        
        df = pd.read_sql(query, connection, params=(start_ts, end_ts))
        
        if not df.empty:
            df['ts'] = pd.to_datetime(df['ts'])
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            print(f"   ✅ 获取到 {len(df)} 条{coin}价格数据")
        else:
            print(f"   ⚠️  该时间段无{coin}价格数据")
        
        return df
        
    except Exception as e:
        print(f"❌ 获取{coin}价格数据失败: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        connection.close()


def identify_short_signals(eth_df):
    """
    识别做空信号：ETH连续两个5分钟买卖比 < 0.8
    
    Args:
        eth_df: ETH的Taker数据DataFrame
    
    Returns:
        DataFrame: 包含做空信号的DataFrame，添加short_signal列
    """
    df = eth_df.copy()
    df = df.sort_values('ts').reset_index(drop=True)
    
    # 计算买卖比
    df['buy_sell_ratio'] = df['buy_vol'] / df['sell_vol']
    
    # 识别连续两个5分钟买卖比 < 0.8
    df['ratio_below_0_8'] = df['buy_sell_ratio'] < 0.8
    df['prev_ratio_below_0_8'] = df['ratio_below_0_8'].shift(1)
    
    # 做空信号：当前和前一个都是 < 0.8
    df['short_signal'] = df['ratio_below_0_8'] & df['prev_ratio_below_0_8']
    
    return df


def identify_close_signals(btc_df, eth_df):
    """
    识别平仓信号：BTC和ETH同时买卖比 > 1.3
    
    Args:
        btc_df: BTC的Taker数据DataFrame
        eth_df: ETH的Taker数据DataFrame
    
    Returns:
        DataFrame: 包含平仓信号的DataFrame
    """
    # 合并BTC和ETH数据
    merged = pd.merge(
        btc_df[['ts', 'buy_sell_ratio']].rename(columns={'buy_sell_ratio': 'btc_ratio'}),
        eth_df[['ts', 'buy_sell_ratio']].rename(columns={'buy_sell_ratio': 'eth_ratio'}),
        on='ts',
        how='inner'
    )
    
    # 平仓信号：BTC和ETH同时 > 1.3
    merged['close_signal'] = (merged['btc_ratio'] > 1.3) & (merged['eth_ratio'] > 1.3)
    
    return merged


def backtest_strategy(start_date, end_date, db_config):
    """
    回测策略
    
    Args:
        start_date: 开始日期（datetime，UTC+8）
        end_date: 结束日期（datetime，UTC+8）
        db_config: 数据库配置字典
    
    Returns:
        dict: 回测结果
    """
    print(f"\n{'='*60}")
    print(f"🚀 开始回测策略")
    print(f"{'='*60}\n")
    
    # 获取数据
    print("📊 获取数据...")
    btc_taker = get_taker_volume_data('BTC', start_date, end_date, db_config)
    eth_taker = get_taker_volume_data('ETH', start_date, end_date, db_config)
    btc_price = get_price_data('BTC', start_date, end_date, db_config)
    eth_price = get_price_data('ETH', start_date, end_date, db_config)
    
    if btc_taker.empty or eth_taker.empty:
        print("❌ Taker数据不足，无法回测")
        return None
    
    if eth_price.empty:
        print("❌ ETH价格数据不足，无法回测")
        return None
    
    # 计算买卖比
    btc_taker['buy_sell_ratio'] = btc_taker['buy_vol'] / btc_taker['sell_vol']
    eth_taker['buy_sell_ratio'] = eth_taker['buy_vol'] / eth_taker['sell_vol']
    
    # 合并价格数据（先合并价格，再识别信号）
    print("\n🔗 合并价格数据...")
    eth_taker = pd.merge(
        eth_taker,
        eth_price[['ts', 'close']].rename(columns={'close': 'eth_price'}),
        on='ts',
        how='left'
    )
    
    # 识别做空信号
    print("\n🔍 识别做空信号（ETH连续两个5分钟买卖比 < 0.8）...")
    eth_taker = identify_short_signals(eth_taker)
    short_signals = eth_taker[eth_taker['short_signal'] == True].copy()
    
    print(f"   ✅ 找到 {len(short_signals)} 个做空信号")
    
    if short_signals.empty:
        print("❌ 没有找到做空信号，无法回测")
        return None
    
    # 识别平仓信号
    print("\n🔍 识别平仓信号（BTC和ETH同时买卖比 > 1.3）...")
    close_signals_df = identify_close_signals(btc_taker, eth_taker)
    close_signals = close_signals_df[close_signals_df['close_signal'] == True].copy()
    
    print(f"   ✅ 找到 {len(close_signals)} 个平仓信号")
    
    # 回测逻辑
    print("\n📈 开始回测...")
    trades = []
    
    for idx, short_row in short_signals.iterrows():
        short_time = short_row['ts']
        short_price = short_row['eth_price']
        
        if pd.isna(short_price):
            continue
        
        # 找到该做空信号之后的第一个平仓信号
        future_close_signals = close_signals[close_signals['ts'] > short_time]
        
        if future_close_signals.empty:
            # 如果没有平仓信号，使用最后一个价格数据
            future_prices = eth_price[eth_price['ts'] > short_time]
            if future_prices.empty:
                continue
            close_time = future_prices.iloc[-1]['ts']
            close_price = future_prices.iloc[-1]['close']
            is_closed = False  # 未平仓
        else:
            # 使用第一个平仓信号
            close_row = future_close_signals.iloc[0]
            close_time = close_row['ts']
            # 获取平仓时的价格
            close_price_row = eth_price[eth_price['ts'] == close_time]
            if close_price_row.empty:
                # 如果精确时间没有，找最接近的
                close_price_row = eth_price[eth_price['ts'] > close_time].iloc[0:1]
                if close_price_row.empty:
                    continue
            close_price = close_price_row.iloc[0]['close']
            is_closed = True  # 已平仓
        
        # 计算盈亏（做空：价格下跌盈利）
        pnl = short_price - close_price  # 做空：开仓价 - 平仓价
        pnl_pct = (pnl / short_price) * 100
        
        # 判断胜负（做空：价格下跌为胜）
        is_win = pnl > 0
        
        trades.append({
            'short_time': short_time,
            'short_price': short_price,
            'close_time': close_time,
            'close_price': close_price,
            'is_closed': is_closed,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'is_win': is_win,
            'duration_minutes': (close_time - short_time).total_seconds() / 60
        })
    
    if not trades:
        print("❌ 没有生成任何交易记录")
        return None
    
    # 转换为DataFrame
    trades_df = pd.DataFrame(trades)
    
    # 统计结果
    total_trades = len(trades_df)
    win_trades = trades_df['is_win'].sum()
    lose_trades = total_trades - win_trades
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
    
    closed_trades = trades_df[trades_df['is_closed'] == True]
    closed_total = len(closed_trades)
    closed_win = closed_trades['is_win'].sum() if closed_total > 0 else 0
    closed_win_rate = (closed_win / closed_total * 100) if closed_total > 0 else 0
    
    total_pnl = trades_df['pnl'].sum()
    total_pnl_pct = trades_df['pnl_pct'].sum()
    avg_pnl = trades_df['pnl'].mean()
    avg_pnl_pct = trades_df['pnl_pct'].mean()
    avg_duration = trades_df['duration_minutes'].mean()
    
    # 打印结果
    print(f"\n{'='*60}")
    print(f"📊 回测结果")
    print(f"{'='*60}")
    print(f"总交易次数: {total_trades}")
    print(f"盈利次数: {win_trades}")
    print(f"亏损次数: {lose_trades}")
    print(f"胜率: {win_rate:.2f}%")
    print(f"\n已平仓交易:")
    print(f"  总次数: {closed_total}")
    print(f"  盈利次数: {closed_win}")
    print(f"  胜率: {closed_win_rate:.2f}%")
    print(f"\n盈亏统计:")
    print(f"  总盈亏: {total_pnl:.2f} USDT ({total_pnl_pct:.2f}%)")
    print(f"  平均盈亏: {avg_pnl:.2f} USDT ({avg_pnl_pct:.2f}%)")
    print(f"  平均持仓时长: {avg_duration:.1f} 分钟")
    print(f"{'='*60}\n")
    
    # 保存详细交易记录
    csv_filename = f'strategy_backtest_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.csv'
    trades_df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
    print(f"💾 详细交易记录已保存到: {csv_filename}")
    
    return {
        'total_trades': total_trades,
        'win_trades': win_trades,
        'lose_trades': lose_trades,
        'win_rate': win_rate,
        'closed_total': closed_total,
        'closed_win': closed_win,
        'closed_win_rate': closed_win_rate,
        'total_pnl': total_pnl,
        'total_pnl_pct': total_pnl_pct,
        'avg_pnl': avg_pnl,
        'avg_pnl_pct': avg_pnl_pct,
        'avg_duration': avg_duration,
        'trades_df': trades_df
    }


def main():
    """主函数"""
    # 配置参数
    start_date = datetime(2026, 1, 6, 0, 0, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    end_date = datetime(2026, 1, 22, 23, 59, 59, tzinfo=ZoneInfo('Asia/Shanghai'))
    
    print(f"\n{'='*60}")
    print(f"📊 Taker买卖比策略回测分析")
    print(f"{'='*60}")
    print(f"策略规则:")
    print(f"  1. 做空信号：ETH连续两个5分钟买卖比 < 0.8")
    print(f"  2. 平仓信号：BTC和ETH同时买卖比 > 1.3")
    print(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 至 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # 回测
    result = backtest_strategy(start_date, end_date, DB_CONFIG)
    
    if result:
        print(f"\n✅ 回测完成！")
    else:
        print(f"\n❌ 回测失败")


if __name__ == "__main__":
    main()

