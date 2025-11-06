import threading
import time
import traceback
from datetime import datetime

import ccxt
import mysql.connector
import pytz
from mysql.connector.pooling import MySQLConnectionPool

# 数据库配置
local_config = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'user': 'payment_pro',
    'password': 'nS4kO7tG1jH7cI6oR4b',
    'database': 'quantify',
    'port': '3306',
    'auth_plugin': '',
    'pool_name': 'okx_pool',  # 添加简短的连接池名称
    'pool_size': 10,  # 设置连接池大小
}


def execute_with_cursor(pool: MySQLConnectionPool, callback, *args, **kwargs):
    """
     使用数据库连接执行回调函数， 自动处理连接的获取和释放
     这个方法可以有效防止连接泄漏
    """
    retries = 0
    connection = None
    cursor = None
    while True:
        try:
            connection = pool.get_connection()
            cursor = connection.cursor()
            return callback(cursor, *args, **kwargs)
        except mysql.connector.errors.PoolError as e:
            print(f"[execute] 连接池已满，等待 {1} 秒后重试 ({retries + 1})...")
            time.sleep(1)
            retries += 1
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    print(traceback.format_exc())
            if connection:
                try:
                    connection.close()
                except:
                    print(traceback.format_exc())


def update_with_cursor(pool: MySQLConnectionPool, callback, *args, **kwargs):
    """
     使用数据库连接执行回调函数， 自动处理连接的获取和释放
     这个方法可以有效防止连接泄漏
    """
    retries = 0
    connection = None
    cursor = None
    try:
        connection = pool.get_connection()
        cursor = connection.cursor()
        result = callback(cursor, *args, **kwargs)
        connection.commit()
        return result
    except mysql.connector.errors.PoolError as e:
        print(f"[execute] 连接池已满，等待 {1} 秒后重试 ({retries + 1})...")
        time.sleep(1)
        retries += 1
    except:
        print(traceback.format_exc())
        if connection:
            try:
                connection.rollback()
            except:
                print(traceback.format_exc())
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                print(traceback.format_exc())
        if connection:
            try:
                connection.close()
            except:
                print(traceback.format_exc())


exchange = ccxt.okx({
    'apiKey': '853e3e4c-70cc-4a3c-a119-eaa5ee4bce8f',
    'secret': '54257766BAAB64240CE9158AC3F9A2BC',
    'password': "!Aa123456",
    'enableRateLimit': True
})

prase_ohlcv_original = exchange.parse_ohlcv


def prase_ohlcv_custom(ohlcv, market):
    res = prase_ohlcv_original(ohlcv, market)
    res.append(exchange.safe_number(ohlcv, 6))
    res.append(exchange.safe_number(ohlcv, 7))
    res.append(exchange.safe_integer(ohlcv, 8))
    res.append(ohlcv)
    return res


# ccxt 默认没有返回交易额，使用自定义解析方法将数据暴露出来
exchange.parse_ohlcv = prase_ohlcv_custom

exchange.load_markets()


def get_table_name(coin, swap: bool, inverse: bool, year):
    return f"ml_{coin}{'_usd' if inverse else ''}{'_swap' if swap else ''}_history_1m_{year}"


def create_table_if_not_exists(cursor, coin, swap: bool, inverse: bool, year):
    table_name = get_table_name(coin, swap, inverse, year)
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS `{table_name}` (
      `id` int UNSIGNED NOT NULL AUTO_INCREMENT,
      `open` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NULL DEFAULT NULL COMMENT '开盘价格',
      `high` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NULL DEFAULT NULL COMMENT '最高价格',
      `low` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NULL DEFAULT NULL COMMENT '最低价格',
      `close` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NULL DEFAULT NULL COMMENT '收盘价格',
      `vol` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NULL DEFAULT NULL COMMENT '交易量-合约（张）',
      `vol_ccy` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NULL DEFAULT NULL COMMENT '交易量-（币）',
      `vol_ccy_quote` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NULL DEFAULT NULL COMMENT '交易量，以计价货币为单位',
      `confirm` tinyint(1) NULL DEFAULT 1 COMMENT 'K线状态 0：K线未完结 1：K线已完结',
      `time` int NULL DEFAULT 0 COMMENT '时间戳',
      `create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      PRIMARY KEY (`id`) USING BTREE,
      UNIQUE INDEX `time`(`time` ASC) USING BTREE,
      UNIQUE INDEX `create_time`(`create_time` ASC) USING BTREE
    ) ENGINE = InnoDB AUTO_INCREMENT = 1 AVG_ROW_LENGTH = 1 CHARACTER SET = utf8mb3 COLLATE = utf8mb3_general_ci COMMENT = '{coin}-1m-历史数据订单信息表' ROW_FORMAT = DYNAMIC;
    """
    cursor.execute(create_table_query)


def do_get_latest_time_value(cursor, table_name):
    query = f"SELECT time FROM {table_name} ORDER BY time DESC LIMIT 1"
    cursor.execute(query)
    result = cursor.fetchone()
    return result[0] if result else None


def get_latest_time_value(pool, coin, swap: bool, inverse: bool, year):
    table_name = get_table_name(coin, swap, inverse, year)
    for i in range(3):
        try:
            return execute_with_cursor(pool, do_get_latest_time_value, table_name)
        except:
            pass
    return None


def table_exists(cursor, coin, swap: bool, inverse: bool, year):
    table_name = get_table_name(coin, swap, inverse, year)
    query = f"""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'quantify' AND table_name = '{table_name}';
            """
    cursor.execute(query)
    result = cursor.fetchone()
    return result[0] > 0


lock = threading.Lock()
last_call_time = None
limiter_time = 0.1  # 限制请求频率，单位秒


def fetch_ohlc_with_limiter(symbol, since, limit):
    global last_call_time
    with lock:
        if last_call_time is not None:
            elapsed_time = time.time() - last_call_time
            if elapsed_time < limiter_time:
                time.sleep(limiter_time - elapsed_time)
        while True:
            try:
                datas = exchange.fetch_ohlcv(symbol, '1m', since, limit)
                last_call_time = time.time()
                return datas
            except Exception as e:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{now}] symbol: {symbol:<15} 查询K线数据失败，e: {e}，等待 {limiter_time} 秒后重试...")
                time.sleep(limiter_time)


beijing_tz = pytz.timezone('Asia/Shanghai')


def fetch_and_save_kline_data(symbol):
    # 对每个交易对：
    # 从当前年份开始，查询表是否存在，如果不存在则查询上一年的表，直至2018年，如果2018年也不存在，则创建表，然后开始拉取数据
    #   如果没有任何数据，则从2018年1月1号开始查询数据，bitget 最多一次能查询90天的数据，所以如果没有数据，就把查询开始时间向后推90天，直至有数据
    #   如果某一年有数据，则直接从最近一条数据开始查询
    # 查询到数据后，则下一次查询的时间就根据本次查询得到的数据的最后一条的时间，向后推1分钟即可

    # 为每个线程创建独立的连接池
    thread_pool_config = local_config.copy()
    thread_pool_config['pool_name'] = f"pool_{symbol.replace('/', '_').replace(':', '_')}"
    
    pool = MySQLConnectionPool(**thread_pool_config)

    market = exchange.market(symbol)
    okx_symbol = market['id']
    base_ccy = market['base'].lower()
    is_swap = market['swap']
    is_inverse = market['inverse']

    # 计算开始时间
    start_year = 2025
    real_start_year = None
    year = datetime.now().year
    while year >= start_year:
        if execute_with_cursor(pool, table_exists, base_ccy, is_swap, is_inverse, year):
            real_start_year = year
            break
        year -= 1

    latest_time = None
    has_data = False
    if real_start_year:
        # 某一年有数据，则直接从最近一条数据开始查询
        latest_time = get_latest_time_value(pool, base_ccy, is_swap, is_inverse, real_start_year)
        if latest_time:
            has_data = True
            since = (latest_time + 60) * 1000  # 转换为毫秒级别
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            last_data_time = datetime.fromtimestamp(latest_time, beijing_tz)
            new_since_time = datetime.fromtimestamp(since // 1000, beijing_tz)
            print(
                f"[{now}] symbol: {symbol:<15} last_data_time: {last_data_time}, new_since_time: {new_since_time}")
        else:
            print(f'[{symbol}] no since time')
            return
    else:
        # 没有任何数据，则从2025年1月1号开始查询数据
        # 转换为毫秒级别
        since = int(datetime(start_year, 1, 1).timestamp()) * 1000

    forward = not has_data
    backward = False

    exists_tables = []

    while True:
        try:
            datas = fetch_ohlc_with_limiter(symbol, since, 100)

            if len(datas) > 0:
                # 去掉未确认的数据
                datas = [data for data in datas if data[8] == 1]

            # ccxt 单次最多能查100条数据
            if len(datas) == 0:
                if forward:
                    # 第一次拉数据时，快速向前推进查询范围
                    shift = 10 * 24 * 60 * 60 * 1000
                elif backward:
                    backward = False
                    shift = 100 * 60 * 1000
                    first_since = since + shift
                    first_since_str = datetime.fromtimestamp(first_since // 1000, beijing_tz)
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(
                        f"[{now}] symbol: {symbol:<15} 向后回退时间，已找到第一条数据的开始时间 first since: {first_since_str}")
                else:
                    shift = 100 * 60 * 1000
                if since + shift < int(datetime.now().timestamp()) * 1000:
                    since += shift
                else:
                    time.sleep(10)  # 等待一下再获取
                continue
            else:
                if forward:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{now}] symbol: {symbol:<15} 向前快进时间，已找到数据，开始向后回退时间查找第一条数据")
                    forward = False
                    backward = True
                if backward:
                    shift = 24 * 60 * 60 * 1000
                    since -= shift
                    since_str = datetime.fromtimestamp(since // 1000, beijing_tz)
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{now}] symbol: {symbol:<15} 向后回退时间, new since: {since_str}")
                    continue

            # 遍历并保存数据到MySQL
            # 打印格式化的当前时间、数量、第一条数据的时间
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            first_data_time = datetime.fromtimestamp(int(datas[0][0]) // 1000, beijing_tz)
            last_data_time = datetime.fromtimestamp(int(datas[-1][0]) // 1000, beijing_tz)
            print(
                f"[{now}] symbol: {symbol:<15} count: {len(datas)}, first_data_time: {first_data_time}, last_data_time: {last_data_time}")

            # 准备批量插入的数据列表
            batch_data = {}
            for data in datas:
                timestamp = int(data[0]) // 1000  # 转换为秒
                open_price = data[1]
                high_price = data[2]
                low_price = data[3]
                close_price = data[4]
                volume = data[5]
                vol_ccy = data[6]
                vol_ccy_quote = data[7]
                confirm = data[8]
                create_time = datetime.fromtimestamp(timestamp, beijing_tz)

                # 创建表（如果不存在）
                year = create_time.year
                table_name = get_table_name(base_ccy, is_swap, is_inverse, year)
                if table_name not in exists_tables:
                    update_with_cursor(pool, create_table_if_not_exists, base_ccy, is_swap, is_inverse, year)
                    exists_tables.append(table_name)

                # 构造批量插入的数据项
                if year not in batch_data:
                    batch_data[year] = []
                batch_data[year].append(
                    (timestamp, open_price, high_price, low_price, close_price, volume, vol_ccy, vol_ccy_quote, confirm,
                     create_time))

            def insert_data(cursor, table_name, data):
                insert_query = f"""
                INSERT INTO {table_name} (time, open, high, low, close, vol, vol_ccy, vol_ccy_quote, confirm, create_time) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.executemany(insert_query, data)

            # 批量插入数据到表中
            for year, data in batch_data.items():
                table_name = get_table_name(base_ccy, is_swap, is_inverse, year)
                update_with_cursor(pool, insert_data, table_name, data)
                # 更新 since 参数为最新的 timestamp
                since = data[-1][0] * 1000

            since += 1000 * 60

        except Exception as e:
            print(f"====>since:{since}")
            print(f"Exception occurred: {e}. Retrying...")
            time.sleep(10)  # 等待一段时间后重试
            # 获取最新的 time 值
            print(f"====>year:{year}")
            try:
                latest_time = get_latest_time_value(pool, base_ccy, is_swap, is_inverse, year)
                if latest_time:
                    since = (latest_time + 60) * 1000  # 转换为毫秒级别
                    print(f"====>new since:{since}")
            except:
                pass
            continue  # 继续下一次循环


# 所有要拉取的交易对列表
symbols = [
    #'BTC/USDT',
     'BTC/USDT:USDT',
    # 'BTC/USD:BTC',
    # 'ETH/USDT',
     'ETH/USDT:USDT',
    # 'ETH/USD:ETH',
    # 'SOL/USDT',
     'SOL/USDT:USDT',
    # 'SOL/USD:SOL',
    # 'DOGE/USDT',
    # 'DOGE/USDT:USDT',
    # 'DOGE/USD:DOGE',
  
]

# 创建线程
threads = []
for symbol in symbols:
    thread = threading.Thread(target=fetch_and_save_kline_data, args=(symbol,), daemon=True)
    threads.append(thread)
    thread.start()

# 阻塞主线程等待所有线程完成（或一直运行）
try:
    for t in threads:
        t.join()
except KeyboardInterrupt:
    print("程序手动终止")