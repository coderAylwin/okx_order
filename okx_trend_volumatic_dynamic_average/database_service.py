#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import pymysql
import json
from datetime import datetime

class DatabaseService:
    def __init__(self, config=None, host='localhost', port=3306, user='root', password='', database=''):
        """
        初始化数据库连接
        
        Args:
            config: 配置字典（包含host, port, user, password, database）
            host: 数据库主机地址
            port: 数据库端口
            user: 数据库用户名
            password: 数据库密码
            database: 数据库名称
        """
        if config is not None:
            # 如果传入了配置字典，使用配置字典的值
            self.host = config.get('host', 'localhost')
            self.port = config.get('port', 3306)
            self.user = config.get('user', 'root')
            self.password = config.get('password', '')
            self.database = config.get('database', '')
        else:
            # 否则使用单独的参数
            self.host = host
            self.port = port
            self.user = user
            self.password = password
            self.database = database
        
        self.connection = None
        
    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4'
            )
            print(f"成功连接到数据库: {self.host}:{self.port}/{self.database}")
            return True
        except Exception as e:
            print(f"数据库连接失败: {e}")
            return False

    def execute_with_connection(self, callback):
        """
        使用数据库连接执行回调函数，自动处理连接的获取和释放
        这个方法可以有效防止连接泄漏
        """
        connection = None
        try:
            # 正确做法：新建连接
            connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4'
            )
            return callback(connection)
        finally:
            if connection:
                try:
                    connection.close()
                except:
                    pass

    
    def disconnect(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            print("数据库连接已关闭")
    
    def get_kline_data(self, symbol, start_date, end_date, interval='1h'):
        """
        从数据库获取K线数据
        
        Args:
            symbol: 交易对符号，如 'BTCUSDT'
            start_date: 开始时间，格式 'YYYY-MM-DD HH:MM:SS'
            end_date: 结束时间，格式 'YYYY-MM-DD HH:MM:SS'
            interval: 时间间隔，如 '1h', '4h', '1d'
        
        Returns:
            pandas.DataFrame: 包含OHLCV数据的DataFrame
        """
        if not self.connection:
            if not self.connect():
                return pd.DataFrame()
        
        try:
            # 根据不同的数据库表结构，调整SQL查询
            # 这里假设表名为 kline_data，字段为 symbol, timestamp, open, high, low, close, volume
            sql = """
            SELECT 
                timestamp,
                open,
                high, 
                low,
                close,
                volume
            FROM kline_data 
            WHERE symbol = %s 
            AND timestamp BETWEEN %s AND %s
            ORDER BY timestamp ASC
            """
            
            df = pd.read_sql(sql, self.connection, params=[symbol, start_date, end_date])
            
            if df.empty:
                print(f"未找到 {symbol} 在 {start_date} 到 {end_date} 期间的数据")
                return df
            
            # 确保timestamp列为datetime类型
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            print(f"成功获取 {symbol} 数据: {len(df)} 条记录")
            print(f"时间范围: {df['timestamp'].min()} 到 {df['timestamp'].max()}")
            print(f"价格范围: ${df['low'].min():.2f} - ${df['high'].max():.2f}")
            
            return df
            
        except Exception as e:
            print(f"获取数据失败: {e}")
            return pd.DataFrame()
    
    def get_symbols(self):
        """获取数据库中可用的交易对列表"""
        if not self.connection:
            if not self.connect():
                return []
        
        try:
            sql = "SELECT DISTINCT symbol FROM kline_data ORDER BY symbol"
            df = pd.read_sql(sql, self.connection)
            symbols = df['symbol'].tolist()
            print(f"可用交易对: {symbols}")
            return symbols
        except Exception as e:
            print(f"获取交易对列表失败: {e}")
            return []
    
    def save_robot_state(self, robot_id, state_data):
        """保存机器人状态"""
        def execute_save(connection):
            cursor = connection.cursor()
            try:
                # 检查是否存在此机器人记录
                check_query = "SELECT id FROM ml_robot_states WHERE robot_id = %s"
                cursor.execute(check_query, (robot_id,))
                result = cursor.fetchone()
                
                if result:
                    # 更新现有记录
                    update_query = """
                    UPDATE ml_robot_states 
                    SET state = %s, updated_at = %s
                    WHERE robot_id = %s
                    """
                    cursor.execute(update_query, (
                        json.dumps(state_data),
                        datetime.now(),
                        robot_id
                    ))
                else:
                    # 插入新记录
                    insert_query = """
                    INSERT INTO ml_robot_states 
                    (robot_id, state, updated_at) 
                    VALUES (%s, %s, %s)
                    """
                    now = datetime.now()
                    cursor.execute(insert_query, (
                        robot_id,
                        json.dumps(state_data),
                        now
                    ))
                
                connection.commit()
                return cursor.rowcount
            except Exception as e:
                connection.rollback()
                print(f"保存机器人状态失败: {e}")
                raise
            finally:
                cursor.close()
                
        return self.execute_with_connection(execute_save)
    
    def load_robot_state(self, robot_id):
        """从数据库加载机器人状态"""
        if not self.connection:
            if not self.connect():
                return None
        
        try:
            sql = "SELECT state_data FROM robot_states WHERE robot_id = %s ORDER BY created_at DESC LIMIT 1"
            
            with self.connection.cursor() as cursor:
                cursor.execute(sql, (robot_id,))
                result = cursor.fetchone()
            
            if result:
                import json
                state = json.loads(result[0])
                print(f"机器人状态已加载: {robot_id}")
                return state
            else:
                print(f"未找到机器人状态: {robot_id}")
                return None
                
        except Exception as e:
            print(f"加载机器人状态失败: {e}")
            return None

    def get_daily_data(self, long_coin, start_date, end_date):
        """
        从指定币种表获取日线数据（通过聚合1分钟数据）
        Args:
            long_coin: 币种名称，如 'btc', 'eth', 'sol' 等
            start_date: 开始时间，格式 'YYYY-MM-DD HH:MM:SS'（北京时间字符串）
            end_date: 结束时间，格式 'YYYY-MM-DD HH:MM:SS'（北京时间字符串）
        Returns:
            pandas.DataFrame: 包含 timestamp, open, high, low, close, volume 字段的日线数据
        """
        import pandas as pd
        # 确保连接已建立
        if not self.connection:
            if not self.connect():
                print("数据库连接失败")
                return pd.DataFrame()
        
        # 将北京时间字符串转为UTC时间戳
        start_ts = int(pd.Timestamp(start_date, tz='Asia/Shanghai').tz_convert('UTC').timestamp())
        end_ts = int(pd.Timestamp(end_date, tz='Asia/Shanghai').tz_convert('UTC').timestamp())
        
        sql = '''
            SELECT `time`, `open`, `high`, `low`, `close`, `vol`
            FROM ml_btc_history_1m_2025
            WHERE `confirm`=1 AND `time` BETWEEN %s AND %s
            ORDER BY `time` ASC
        '''
        
        df = pd.read_sql(sql, self.connection, params=[start_ts, end_ts])
        if df.empty:
            print('无数据')
            return df
        
        # 字段类型转换
        for col in ['open', 'high', 'low', 'close', 'vol']:
            df[col] = df[col].astype(float)
        
        # 时间戳转datetime（先转为UTC，再转为Asia/Shanghai）
        df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Shanghai')
        
        # 重命名vol为volume
        df = df.rename(columns={'vol': 'volume'})
        
        # 按日期分组，聚合为日线数据
        df['date'] = df['timestamp'].dt.date
        daily_data = []
        
        for date, group in df.groupby('date'):
            daily_kline = {
                'timestamp': pd.Timestamp(date, tz='Asia/Shanghai'),
                'open': group.iloc[0]['open'],
                'high': group['high'].max(),
                'low': group['low'].min(),
                'close': group.iloc[-1]['close'],
                'volume': group['volume'].sum()
            }
            daily_data.append(daily_kline)
        
        daily_df = pd.DataFrame(daily_data)
        
        print(f"成功获取BTC日线数据: {len(daily_df)} 条记录")
        print(f"时间范围: {daily_df['timestamp'].min()} 到 {daily_df['timestamp'].max()}")
        print(f"价格范围: ${daily_df['low'].min():.2f} - ${daily_df['high'].max():.2f}")
        
        return daily_df

    def get_kline_data(self, long_coin, start_date, end_date):
        """
        从多个年份表获取指定币种的1分钟K线数据，支持跨年查询
        Args:
            long_coin: 币种名称，如 'btc', 'eth', 'sol' 等
            start_date: 开始时间，格式 'YYYY-MM-DD HH:MM:SS'（北京时间字符串）
            end_date: 结束时间，格式 'YYYY-MM-DD HH:MM:SS'（北京时间字符串）
        Returns:
            pandas.DataFrame: 包含 timestamp, open, high, low, close, vol 字段
        """
        import pandas as pd
        # 确保连接已建立
        if not self.connection:
            if not self.connect():
                print("数据库连接失败")
                return pd.DataFrame()
        
        # 将北京时间字符串转为UTC时间戳
        start_ts = int(pd.Timestamp(start_date, tz='Asia/Shanghai').tz_convert('UTC').timestamp())
        end_ts = int(pd.Timestamp(end_date, tz='Asia/Shanghai').tz_convert('UTC').timestamp())
        
        # 确定需要查询的年份
        start_year = pd.Timestamp(start_date, tz='Asia/Shanghai').year
        end_year = pd.Timestamp(end_date, tz='Asia/Shanghai').year
        
        # 需要查询的表名列表
        tables_to_query = []
        for year in range(start_year, end_year + 1):
            table_name = f'ml_{long_coin.lower()}_swap_history_1m_{year}'
            tables_to_query.append(table_name)
        
        print(f"需要查询的表: {tables_to_query}")
        
        # 存储所有数据
        all_dataframes = []
        
        for table_name in tables_to_query:
            try:
                # 检查表是否存在
                check_table_sql = f"SHOW TABLES LIKE '{table_name}'"
                table_exists = pd.read_sql(check_table_sql, self.connection)
                
                if table_exists.empty:
                    print(f"表 {table_name} 不存在，跳过")
                    continue
                
                # 查询数据
                sql = f'''
            SELECT `time`, `open`, `high`, `low`, `close`, `vol`
                    FROM {table_name}
            WHERE `confirm`=1 AND `time` BETWEEN %s AND %s
            ORDER BY `time` ASC
        '''
                
                df_year = pd.read_sql(sql, self.connection, params=[start_ts, end_ts])
                
                if not df_year.empty:
                    print(f"从表 {table_name} 获取到 {len(df_year)} 条记录")
                    all_dataframes.append(df_year)
                else:
                    print(f"表 {table_name} 在指定时间范围内无数据")
                    
            except Exception as e:
                print(f"查询表 {table_name} 时出错: {e}")
                continue
        
        # 合并所有数据
        if not all_dataframes:
            print('所有表都无数据')
            return pd.DataFrame()
        
        # 合并数据框
        df = pd.concat(all_dataframes, ignore_index=True)
        
        # 按时间排序（确保合并后的数据是有序的）
        df = df.sort_values('time').reset_index(drop=True)
        
        # 字段类型转换
        for col in ['open', 'high', 'low', 'close', 'vol']:
            df[col] = df[col].astype(float)
        
        # 时间戳转datetime（先转为UTC，再转为Asia/Shanghai）
        df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Shanghai')
        
        # 重命名vol为volume，兼容主策略
        df = df.rename(columns={'vol': 'volume'})
        
        # 保证字段顺序
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        # 去重（以防万一有重复数据）
        df = df.drop_duplicates(subset=['timestamp']).reset_index(drop=True)
        
        # 打印汇总信息
        print(f"\n=== 数据获取汇总 ===")
        print(f"查询的表数量: {len(tables_to_query)}")
        print(f"成功获取数据的表数量: {len(all_dataframes)}")
        print(f"总记录数: {len(df)}")
        print(f"时间范围: {df['timestamp'].min()} - {df['timestamp'].max()}")
        print(f"数据示例:")
        print(df.head())
        
        return df

    def get_hourly_data(self, long_coin, start_date, end_date):
        """
        获取指定币种的小时线数据（通过分钟线聚合生成）
        
        Args:
            long_coin: 币种名称，如 'btc', 'eth', 'sol' 等
            start_date: 开始时间字符串，格式如 '2025-01-01 00:00:00'
            end_date: 结束时间字符串，格式如 '2025-01-31 23:59:59'
            
        Returns:
            pandas.DataFrame: 包含 timestamp, open, high, low, close, volume 字段
        """
        import pandas as pd
        
        # 先获取分钟线数据
        minute_data = self.get_kline_data(long_coin, start_date, end_date)
        if minute_data.empty:
            print('无分钟线数据，无法生成小时线')
            return pd.DataFrame()
        
        # 聚合为小时线
        minute_data_copy = minute_data.copy()
        minute_data_copy['hour'] = minute_data_copy['timestamp'].dt.floor('H')
        
        hourly_data = minute_data_copy.groupby('hour').agg({
            'open': 'first',
            'high': 'max', 
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).reset_index()
        
        hourly_data = hourly_data.rename(columns={'hour': 'timestamp'})
        hourly_data = hourly_data[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        print(f"成功生成BTC小时线数据: {len(hourly_data)} 条记录，时间范围: {hourly_data['timestamp'].min()} - {hourly_data['timestamp'].max()}")
        return hourly_data

    def get_4hourly_data(self, long_coin, start_date, end_date):
        """
        获取指定币种的4小时线数据（通过分钟线聚合生成）
        
        Args:
            long_coin: 币种名称，如 'btc', 'eth', 'sol' 等
            start_date: 开始时间字符串，格式如 '2025-01-01 00:00:00'
            end_date: 结束时间字符串，格式如 '2025-01-31 23:59:59'
            
        Returns:
            pandas.DataFrame: 包含 timestamp, open, high, low, close, volume 字段
        """
        import pandas as pd
        
        # 先获取分钟线数据
        minute_data = self.get_kline_data(long_coin, start_date, end_date)
        if minute_data.empty:
            print('无分钟线数据，无法生成4小时线')
            return pd.DataFrame()
        
        # 聚合为4小时线（每天4个周期：00:00, 04:00, 08:00, 12:00, 16:00, 20:00）
        minute_data_copy = minute_data.copy()
        minute_data_copy['4hour'] = minute_data_copy['timestamp'].dt.floor('4H')
        
        hourly_4h_data = minute_data_copy.groupby('4hour').agg({
            'open': 'first',
            'high': 'max', 
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).reset_index()
        
        hourly_4h_data = hourly_4h_data.rename(columns={'4hour': 'timestamp'})
        hourly_4h_data = hourly_4h_data[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        print(f"成功生成BTC 4小时线数据: {len(hourly_4h_data)} 条记录，时间范围: {hourly_4h_data['timestamp'].min()} - {hourly_4h_data['timestamp'].max()}")
        return hourly_4h_data

    def save_backtest_result(self, config, result):
        """
        将回测结果保存到backtest_result_record表
        
        Args:
            config: 策略配置字典，包含所有参数
            result: 回测结果字典，包含所有回测指标
        
        Returns:
            bool: 保存是否成功
        """
        def execute_save(connection):
            cursor = connection.cursor()
            try:
                # 构建backtest_time字符串
                backtest_time = f"{result['start_date']} 至 {result['end_date']}"
                
                # 当前时间（假设为北京时间）
                from datetime import datetime, timedelta
                create_time = datetime.now()  # UTC+8北京时间
                
                # 插入SQL语句
                insert_sql = """
                INSERT INTO backtest_result_record (
                    max_grid_size, down_pct, up_pct, long_coin, trade_mode,
                    take_profit_type, stop_profit_multiple, first_take_profit_ratio,
                    peak_pattern_timeframe, trough_pattern_timeframe, trough_add_spread_multiples,
                    initial_capital, final_position, final_cash, current_position_amount,
                    net_earning, total_amount, max_drawdown, annual_yield, total_rate,
                    backtest_time, create_time
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s
                )
                """
                
                # 准备数据（根据表结构调整数据类型）
                values = (
                    config['max_grid_size'],                      # int
                    config['down_pct'],                          # float
                    config['up_pct'],                            # float  
                    config['long_coin'],                         # varchar
                    config['trade_mode'],                        # enum
                    config['take_profit_type'],                  # tinyint
                    config['stop_profit_multiple'],             # float
                    config['first_take_profit_ratio'],          # float
                    config['peak_pattern_timeframe'],           # varchar
                    config['trough_pattern_timeframe'],         # varchar
                    config['trough_add_spread_multiples'],      # float
                    round(config['initial_capital'], 2),             # bigint - 初始资金
                    round(result['final_position'], 6),  # bigint - BTC持仓
                    round(result['final_cash'], 2),     # bigint - 最终现金（以分为单位，保留两位小数）
                    round(result['position_groups_value'],2),  # bigint - 当前持仓金额（以分为单位，保留两位小数）
                    round(result['net_earning'],2),    # bigint - 净收益（以分为单位，保留两位小数）
                    round(result['total_amount'],2),   # bigint - 账户总价值（以分为单位，保留两位小数）
                    round(result['max_drawdown'],2),   # bigint - 最大回撤（百分比×100，如27.08%存为2708）
                    round(result['annual_yield'], 2),           # float - 年化收益率（保留两位小数）
                    round(result['total_rate'], 2),             # float - 总收益率（保留两位小数）
                    backtest_time,                              # varchar - 回测时间区间
                    create_time                                 # timestamp - 创建时间
                )
                
                cursor.execute(insert_sql, values)
                connection.commit()
                
                print(f"回测结果已保存到数据库，插入记录ID: {cursor.lastrowid}")
                return True
                
            except Exception as e:
                connection.rollback()
                print(f"保存回测结果失败: {e}")
                return False
            finally:
                cursor.close()
        
        return self.execute_with_connection(execute_save)

# 使用示例
if __name__ == "__main__":
    # 配置数据库连接参数
    db_config = {
        'host': 'localhost',
        'port': 3306,
        'user': 'root',
        'password': 'your_password',
        'database': 'trading_data'
    }
    
    # 创建数据库服务实例
    db_service = DatabaseService(**db_config)