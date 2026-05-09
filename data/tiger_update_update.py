import pandas as pd
import time
import os
import mysql.connector
from datetime import datetime, date, timedelta, time as dt_time
from tigeropen.common.consts import (Language, BarPeriod, Market)
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.common.util.signature_utils import read_private_key
from tigeropen.quote.quote_client import QuoteClient

# ==============================================================================
# 1. 配置信息
# ==============================================================================
db_config = {
    'user': 'quantify_read_write',
    'password': '02Ya6fPDo@w67UI%sEaDvPXfT',
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'database': 'quantify',
    'port': '3306',
}

STOCK_PAIRS = [
    {"symbol": "AAPL", "table_prefix": "ml_us_aapl_history_1m"}
]

PERIOD = BarPeriod.ONE_MINUTE
MARKET = Market.US
START_DATE = date(2015, 12, 1)
END_DATE = date(2025, 12, 5)  # 从 2025年12月5日开始向前
RETRY_INTERVAL = 30

# ==============================================================================
# 2. 数据库操作函数
# ==============================================================================
db_connection = None
cursor = None

def check_session_downloaded(table_prefix, target_date):
    """
    检查数据库中该交易日是否已下载。
    逻辑：检查北京时间 22:30:00 (Unix时间戳) 是否存在数据。
    """
    table_name = f"{table_prefix}_{target_date.year}"
    
    # 1. 检查表是否存在
    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
    if not cursor.fetchone():
        return False
        
    # 2. 计算目标日期北京时间 22:30 的 Unix 时间戳
    # 无论夏令时还是冬令时，22:30 都是美股开盘后的活跃时间
    check_dt = datetime.combine(target_date, dt_time(22, 30, 0))
    target_ts = int(check_dt.timestamp())
    
    # 3. 精确查询该时间点的记录
    query = f"SELECT 1 FROM `{table_name}` WHERE `time` = %s LIMIT 1"
    try:
        cursor.execute(query, (target_ts,))
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"⚠️ 检查断点失败 ({table_name}): {e}")
        return False

def create_table_if_not_exists(year, table_prefix):
    table_name = f"{table_prefix}_{year}"
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
      `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
      `open` varchar(50) NULL,
      `high` varchar(50) NULL,
      `low` varchar(50) NULL,
      `close` varchar(50) NULL,
      `factor` double DEFAULT 1.0,
      `vol` varchar(50) NULL,
      `vol_ccy` varchar(50) NULL,
      `vol_ccy_quote` varchar(50) NULL,
      `confirm` tinyint(1) NULL DEFAULT 1,
      `time` int NULL DEFAULT 0,
      `create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (`id`),
      UNIQUE INDEX `time`(`time` ASC)
    ) ENGINE = InnoDB;
    """
    try:
        cursor.execute(create_table_query)
        db_connection.commit()
    except Exception as e:
        print(f"❌ 创建表 {table_name} 失败: {e}")

def connect_db_with_retry(initial_attempt=True):
    global db_connection, cursor
    while True:
        try:
            if db_connection and db_connection.is_connected():
                cursor.close()
                db_connection.close()
            db_connection = mysql.connector.connect(**db_config)
            cursor = db_connection.cursor()
            if initial_attempt: print("✅ 数据库连接成功。")
            return True
        except Exception as err:
            if initial_attempt: return False
            print(f"❌ 数据库重连失败... {err}")
            time.sleep(RETRY_INTERVAL)

def get_client_config():
    client_config = TigerOpenClientConfig()
    # 使用当前文件所在目录的privatekey.pem
    current_dir = os.path.dirname(os.path.abspath(__file__))
    private_key_path = os.path.join(current_dir, 'privatekey.pem')
    client_config.private_key = read_private_key(private_key_path)
    client_config.tiger_id = '20156851'
    client_config.account = '21584733964654530'
    client_config.license = 'TBSG'
    client_config.language = Language.zh_CN
    return client_config

# ==============================================================================
# 3. 主程序逻辑
# ==============================================================================

def run_data_fetch():
    global db_connection, cursor
    if not connect_db_with_retry(initial_attempt=True): return

    client_config = get_client_config()
    quote_client = QuoteClient(client_config)
    
    try:
        for stock in STOCK_PAIRS:
            symbol = stock["symbol"]
            table_prefix = stock["table_prefix"]
            
            # 直接从设置的最晚日期开始向前扫描
            current_date = END_DATE
            
            print(f"\n--- 任务开始: {symbol} (从 {END_DATE} 向前追溯至 {START_DATE}) ---")
            empty_days_count = 0

            while current_date >= START_DATE:
                # 数据库重连检查
                try:
                    db_connection.ping(reconnect=False, attempts=1)
                except:
                    connect_db_with_retry(initial_attempt=False)
                    
                target_date_str = current_date.strftime('%Y-%m-%d')
                
                # --- 1. 查缺补漏检查 ---
                # 检查北京时间 22:30 是否有数据。如果有，说明这一天已经拉过了。
                if check_session_downloaded(table_prefix, current_date):
                    print(f"⏩ {target_date_str} 数据库 22:30 已有记录，判定为已下载，跳过。")
                    current_date -= timedelta(days=1)
                    empty_days_count = 0 # 重置连续无数据计数，因为这里是有数据的
                    continue

                # --- 2. 接口请求 ---
                try:
                    print(f"====> 正在请求 {symbol} @ {target_date_str} 的数据...")
                    df = quote_client.get_bars(
                        symbols=[symbol],
                        period=PERIOD,
                        date=current_date.strftime('%Y%m%d'), # 老虎接口通常使用 YYYYMMDD
                        limit=10000
                    )
                    
                    if df is None or df.empty:
                        empty_days_count += 1
                        print(f"====> {target_date_str} 接口返回无数据 ({empty_days_count}/30)")
                        if empty_days_count >= 30:
                            print(f"🛑 连续30天无数据，判定 {symbol} 在此之前无更多历史。")
                            break
                    else:
                        empty_days_count = 0
                        create_table_if_not_exists(current_date.year, table_prefix)
                        table_name = f"{table_prefix}_{current_date.year}"

                        insert_query = f"""
                        INSERT IGNORE INTO {table_name} (time, open, high, low, close, factor, vol, vol_ccy, vol_ccy_quote, confirm, create_time)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        
                        batch_values = []
                        for _, row in df.iterrows():
                            ts_sec = int(row['time']) // 1000
                            # 转换为北京时间写入，保持一致性
                            batch_values.append((
                                ts_sec,
                                str(row['open']), str(row['high']), str(row['low']), str(row['close']),
                                1.0,
                                str(row['volume']), '', '', 1, datetime.fromtimestamp(ts_sec)
                            ))

                        cursor.executemany(insert_query, batch_values)
                        db_connection.commit()
                        print(f"✅ {target_date_str} 写入完成 ({len(df)} 条)。")

                    # 防止触发 API 频控
                    time.sleep(1.5)
                    current_date -= timedelta(days=1)
                    
                except Exception as e:
                    err_msg = str(e)
                    if "no data" in err_msg or "2100" in err_msg:
                        empty_days_count += 1
                        print(f"====> {target_date_str} API明确返回无数据 ({empty_days_count}/30)")
                        if empty_days_count >= 30: break
                        current_date -= timedelta(days=1)
                    else:
                        print(f"❌ API请求异常: {e}. 等待后重试...")
                        time.sleep(5)
                    
            print(f"--- {symbol} 任务处理完毕 ---")
            
    finally:
        if db_connection: db_connection.close()

if __name__ == "__main__":
    run_data_fetch()
