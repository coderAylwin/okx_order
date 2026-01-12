#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据数据库服务
用于管理OKX市场数据的存储和查询
包括：Taker主动量、资金费率、持仓量、多空比、宏观经济数据
"""

import pymysql
from datetime import datetime
import logging
import traceback


class MarketDataDatabaseService:
    """市场数据数据库服务类"""
    
    def __init__(self, host='localhost', port=3306, user='root', password='', database='quantify'):
        """
        初始化数据库连接
        
        Args:
            host: 数据库主机
            port: 数据库端口
            user: 数据库用户名
            password: 数据库密码
            database: 数据库名称
        """
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
            logging.info(f"成功连接到数据库: {self.host}:{self.port}/{self.database}")
            return True
        except Exception as e:
            logging.error(f"数据库连接失败: {e}")
            return False
    
    def disconnect(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None
            logging.debug("数据库连接已关闭")
    
    def create_tables(self):
        """创建市场数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 1. Taker主动量表
            create_taker_table = """
            CREATE TABLE IF NOT EXISTS okx_taker_volume (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                buy_vol DECIMAL(30, 8) NOT NULL COMMENT '买入量（币）',
                sell_vol DECIMAL(30, 8) NOT NULL COMMENT '卖出量（币）',
                ratio DECIMAL(10, 4) DEFAULT NULL COMMENT '买/卖比',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OKX Taker主动量表';
            """
            
            # 2. 资金费率表
            create_funding_table = """
            CREATE TABLE IF NOT EXISTS okx_funding_rate (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                funding_rate DECIMAL(10, 8) NOT NULL COMMENT '资金费率',
                funding_rate_pct DECIMAL(10, 6) DEFAULT NULL COMMENT '资金费率（百分比）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OKX资金费率表';
            """
            
            # 3. 持仓量表
            create_oi_table = """
            CREATE TABLE IF NOT EXISTS okx_open_interest (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                open_interest DECIMAL(30, 8) NOT NULL COMMENT '持仓量（合约数）oi',
                oi_ccy DECIMAL(30, 8) DEFAULT NULL COMMENT '持仓量（币种单位）oiCcy',
                oi_usd DECIMAL(30, 8) DEFAULT NULL COMMENT '持仓量（USD单位）oiUsd',
                delta_oi DECIMAL(20, 2) DEFAULT NULL COMMENT '持仓量变化',
                pct_change DECIMAL(10, 4) DEFAULT NULL COMMENT '持仓量变化百分比',
                taker_buy DECIMAL(20, 2) DEFAULT NULL COMMENT 'Taker买入量',
                taker_sell DECIMAL(20, 2) DEFAULT NULL COMMENT 'Taker卖出量',
                net_taker DECIMAL(20, 2) DEFAULT NULL COMMENT '净Taker量',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OKX持仓量表';
            """
            
            # 4. 多空比表
            create_ls_table = """
            CREATE TABLE IF NOT EXISTS okx_long_short_ratio (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                long_short_ratio DECIMAL(10, 4) NOT NULL COMMENT '多空比',
                delta_ratio DECIMAL(10, 4) DEFAULT NULL COMMENT '多空比变化',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OKX多空比表';
            """
            
            # 5. 宏观经济数据表
            create_macro_table = """
            CREATE TABLE IF NOT EXISTS macro_economic_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                sofr DECIMAL(10, 4) DEFAULT NULL COMMENT 'SOFR利率（%）',
                vix DECIMAL(10, 4) DEFAULT NULL COMMENT 'VIX指数',
                dgs10 DECIMAL(10, 4) DEFAULT NULL COMMENT '10年美债收益率（%）',
                cpi DECIMAL(15, 4) DEFAULT NULL COMMENT '美国CPI',
                cpi_yoy DECIMAL(10, 4) DEFAULT NULL COMMENT 'CPI同比变化（%）',
                unemployment_rate DECIMAL(10, 4) DEFAULT NULL COMMENT '失业率（%）',
                japan_rate DECIMAL(10, 4) DEFAULT NULL COMMENT '日本基准利率（%）',
                us_session VARCHAR(20) DEFAULT NULL COMMENT '美盘时段',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观经济数据表';
            """
            
            cursor.execute(create_taker_table)
            cursor.execute(create_funding_table)
            cursor.execute(create_oi_table)
            cursor.execute(create_ls_table)
            cursor.execute(create_macro_table)
            
            # 更新okx_taker_volume表结构（如果字段不存在）
            try:
                # 检查updated_at字段是否存在
                check_updated_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'okx_taker_volume' 
                AND COLUMN_NAME = 'updated_at'
                """
                cursor.execute(check_updated_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] == 0:
                    # 字段不存在，添加字段并移除minutes_window
                    alter_table_sql = """
                    ALTER TABLE okx_taker_volume 
                    ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间' AFTER created_at
                    """
                    cursor.execute(alter_table_sql)
                    logging.info("已为 okx_taker_volume 表添加 updated_at 字段")
                
                # 检查minutes_window字段是否存在，如果存在则删除
                check_minutes_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'okx_taker_volume' 
                AND COLUMN_NAME = 'minutes_window'
                """
                cursor.execute(check_minutes_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] > 0:
                    # 字段存在，删除字段
                    alter_table_sql = """
                    ALTER TABLE okx_taker_volume 
                    DROP COLUMN minutes_window
                    """
                    cursor.execute(alter_table_sql)
                    logging.info("已从 okx_taker_volume 表删除 minutes_window 字段")
                
                # 检查唯一索引是否存在
                check_index_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.STATISTICS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'okx_taker_volume' 
                AND INDEX_NAME = 'uk_coin_symbol_ts'
                """
                cursor.execute(check_index_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] == 0:
                    # 唯一索引不存在，添加唯一索引
                    alter_index_sql = """
                    ALTER TABLE okx_taker_volume 
                    ADD UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts)
                    """
                    cursor.execute(alter_index_sql)
                    logging.info("已为 okx_taker_volume 表添加唯一索引 uk_coin_symbol_ts")
            except Exception as alter_error:
                logging.debug(f"检查/修改okx_taker_volume表结构（可能已经正确）: {alter_error}")
            
            # 更新okx_open_interest表结构（如果字段不存在）
            try:
                # 检查oi_ccy字段是否存在
                check_ccy_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'okx_open_interest' 
                AND COLUMN_NAME = 'oi_ccy'
                """
                cursor.execute(check_ccy_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] == 0:
                    # 字段不存在，添加字段和唯一索引
                    alter_table_sql = """
                    ALTER TABLE okx_open_interest 
                    ADD COLUMN oi_ccy DECIMAL(30, 8) DEFAULT NULL COMMENT '持仓量（币种单位）oiCcy' AFTER open_interest,
                    ADD COLUMN oi_usd DECIMAL(30, 8) DEFAULT NULL COMMENT '持仓量（USD单位）oiUsd' AFTER oi_ccy,
                    ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间' AFTER created_at
                    """
                    cursor.execute(alter_table_sql)
                    logging.info("已为 okx_open_interest 表添加 oi_ccy 和 oi_usd 字段")
                
                # 检查唯一索引是否存在
                check_index_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.STATISTICS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'okx_open_interest' 
                AND INDEX_NAME = 'uk_coin_symbol_ts'
                """
                cursor.execute(check_index_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] == 0:
                    # 唯一索引不存在，添加唯一索引
                    alter_index_sql = """
                    ALTER TABLE okx_open_interest 
                    ADD UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts)
                    """
                    cursor.execute(alter_index_sql)
                    logging.info("已为 okx_open_interest 表添加唯一索引 uk_coin_symbol_ts")
            except Exception as alter_error:
                logging.debug(f"检查/修改表结构（可能已经正确）: {alter_error}")
            
            # 更新okx_long_short_ratio表结构（如果字段不存在）
            try:
                # 检查long_short_ratio_by_ccy字段是否存在
                check_ccy_ratio_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'okx_long_short_ratio' 
                AND COLUMN_NAME = 'long_short_ratio_by_ccy'
                """
                cursor.execute(check_ccy_ratio_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] == 0:
                    # 字段不存在，添加字段
                    alter_table_sql = """
                    ALTER TABLE okx_long_short_ratio 
                    ADD COLUMN long_short_ratio_by_ccy DECIMAL(10, 4) DEFAULT NULL COMMENT '多空比（按币种汇总）' AFTER delta_ratio
                    """
                    cursor.execute(alter_table_sql)
                    logging.info("已为 okx_long_short_ratio 表添加 long_short_ratio_by_ccy 字段")
                
                # 检查top_trader_account_ratio字段是否存在
                check_top_account_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'okx_long_short_ratio' 
                AND COLUMN_NAME = 'top_trader_account_ratio'
                """
                cursor.execute(check_top_account_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] == 0:
                    # 字段不存在，添加字段
                    alter_table_sql = """
                    ALTER TABLE okx_long_short_ratio 
                    ADD COLUMN top_trader_account_ratio DECIMAL(10, 4) DEFAULT NULL COMMENT '精英交易员多空持仓人数比' AFTER long_short_ratio_by_ccy
                    """
                    cursor.execute(alter_table_sql)
                    logging.info("已为 okx_long_short_ratio 表添加 top_trader_account_ratio 字段")
                
                # 检查top_trader_position_ratio字段是否存在
                check_top_position_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'okx_long_short_ratio' 
                AND COLUMN_NAME = 'top_trader_position_ratio'
                """
                cursor.execute(check_top_position_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] == 0:
                    # 字段不存在，添加字段
                    alter_table_sql = """
                    ALTER TABLE okx_long_short_ratio 
                    ADD COLUMN top_trader_position_ratio DECIMAL(10, 4) DEFAULT NULL COMMENT '精英交易员多空持仓仓位比' AFTER top_trader_account_ratio
                    """
                    cursor.execute(alter_table_sql)
                    logging.info("已为 okx_long_short_ratio 表添加 top_trader_position_ratio 字段")
                
                # 检查唯一索引是否存在
                check_index_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.STATISTICS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'okx_long_short_ratio' 
                AND INDEX_NAME = 'uk_coin_symbol_ts'
                """
                cursor.execute(check_index_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] == 0:
                    # 唯一索引不存在，添加唯一索引
                    alter_index_sql = """
                    ALTER TABLE okx_long_short_ratio 
                    ADD UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts)
                    """
                    cursor.execute(alter_index_sql)
                    logging.info("已为 okx_long_short_ratio 表添加唯一索引 uk_coin_symbol_ts")
            except Exception as alter_error:
                logging.debug(f"检查/修改okx_long_short_ratio表结构（可能已经正确）: {alter_error}")
            
            self.connection.commit()
            logging.info("市场数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def get_taker_volume_by_ts(self, coin, symbol, ts_datetime):
        """根据coin, symbol, ts查询Taker主动量数据"""
        if not self.connection:
            if not self.connect():
                logging.error(f"查询Taker主动量数据失败：数据库连接未建立 (coin={coin}, symbol={symbol}, ts={ts_datetime})")
                return None
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            error_detail = f"{type(ping_error).__name__}: {str(ping_error)}"
            if hasattr(ping_error, 'args') and ping_error.args:
                error_detail += f", args={ping_error.args}"
            logging.warning(f"数据库连接检查失败，尝试重新连接: {error_detail}")
            if not self.connect():
                logging.error(f"查询Taker主动量数据失败：数据库重连失败 (coin={coin}, symbol={symbol}, ts={ts_datetime})")
                return None
        
        cursor = self.connection.cursor()
        try:
            sql = """
            SELECT buy_vol, sell_vol 
            FROM okx_taker_volume 
            WHERE coin = %s AND symbol = %s AND ts = %s
            """
            cursor.execute(sql, (coin, symbol, ts_datetime))
            result = cursor.fetchone()
            if result:
                return {
                    'buy_vol': float(result[0]) if result[0] else None,
                    'sell_vol': float(result[1]) if result[1] else None
                }
            return None
        except pymysql.Error as e:
            error_code = e.args[0] if len(e.args) > 0 else 'N/A'
            error_msg_detail = e.args[1] if len(e.args) > 1 else (e.args[0] if len(e.args) == 1 else 'N/A')
            error_msg = f"查询Taker主动量数据时发生异常 (pymysql.Error): 错误码={error_code}, 错误信息={error_msg_detail}, 异常类型={type(e).__name__}, coin={coin}, symbol={symbol}, ts={ts_datetime}"
            # 查询失败不应该阻止保存操作，使用warning级别而不是error，返回 None 表示数据不存在（将尝试插入）
            logging.warning(error_msg)
            logging.debug(f"异常详情: {traceback.format_exc()}")
            return None
        except Exception as e:
            error_msg = f"查询Taker主动量数据时发生异常 (Exception): 异常类型={type(e).__name__}, 错误信息={str(e)}, args={e.args if hasattr(e, 'args') else 'N/A'}, coin={coin}, symbol={symbol}, ts={ts_datetime}"
            # 查询失败不应该阻止保存操作，使用warning级别而不是error，返回 None 表示数据不存在（将尝试插入）
            logging.warning(error_msg)
            logging.debug(f"异常详情: {traceback.format_exc()}")
            return None
        finally:
            cursor.close()
    
    def save_taker_volume(self, coin, symbol, ts_datetime, buy_vol, sell_vol, ratio=None):
        """保存Taker主动量数据（单条）"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 检查数据是否已存在
            existing = self.get_taker_volume_by_ts(coin, symbol, ts_datetime)
            
            if existing:
                # 数据已存在，比较 buy_vol, sell_vol 是否一致
                buy_equal = abs(float(existing['buy_vol']) - float(buy_vol)) < 0.0001
                sell_equal = abs(float(existing['sell_vol']) - float(sell_vol)) < 0.0001
                
                if buy_equal and sell_equal:
                    logging.debug(f"Taker主动量数据已存在且一致，跳过更新: {coin} {symbol} {ts_datetime}")
                    return True
                else:
                    # 数据不一致，更新
                    sql = """
                    UPDATE okx_taker_volume 
                    SET buy_vol = %s, sell_vol = %s, ratio = %s
                    WHERE coin = %s AND symbol = %s AND ts = %s
                    """
                    cursor.execute(sql, (buy_vol, sell_vol, ratio, coin, symbol, ts_datetime))
                    self.connection.commit()
                    logging.info(f"Taker主动量数据已更新: {coin} {symbol} {ts_datetime}")
                    return True
            else:
                # 数据不存在，新增
                sql = """
                INSERT INTO okx_taker_volume 
                (coin, symbol, ts, buy_vol, sell_vol, ratio)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (coin, symbol, ts_datetime, buy_vol, sell_vol, ratio))
                self.connection.commit()
                logging.debug(f"Taker主动量数据保存成功: {coin} {symbol} {ts_datetime}")
                return True
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存Taker主动量数据失败: {e}")
            return False
        finally:
            cursor.close()
    
    def save_taker_volume_batch(self, coin, symbol, data_list):
        """
        批量保存Taker主动量数据
        data_list: [(ts_datetime, sell_vol, buy_vol), ...]
        """
        if not self.connection:
            if not self.connect():
                return False
        
        if not data_list:
            return True
        
        insert_count = 0
        update_count = 0
        skip_count = 0
        
        cursor = self.connection.cursor()
        try:
            for ts_datetime, sell_vol, buy_vol in data_list:
                ratio = buy_vol / sell_vol if sell_vol > 0 else None
                
                # 检查数据是否已存在
                existing = self.get_taker_volume_by_ts(coin, symbol, ts_datetime)
                
                if existing:
                    # 数据已存在，比较 buy_vol, sell_vol 是否一致
                    buy_equal = abs(float(existing['buy_vol']) - float(buy_vol)) < 0.0001
                    sell_equal = abs(float(existing['sell_vol']) - float(sell_vol)) < 0.0001
                    
                    if buy_equal and sell_equal:
                        skip_count += 1
                        logging.debug(f"Taker主动量数据已存在且一致，跳过: {coin} {symbol} {ts_datetime}")
                    else:
                        # 数据不一致，更新
                        sql = """
                        UPDATE okx_taker_volume 
                        SET buy_vol = %s, sell_vol = %s, ratio = %s
                        WHERE coin = %s AND symbol = %s AND ts = %s
                        """
                        cursor.execute(sql, (buy_vol, sell_vol, ratio, coin, symbol, ts_datetime))
                        update_count += 1
                        logging.debug(f"Taker主动量数据已更新: {coin} {symbol} {ts_datetime}")
                else:
                    # 数据不存在，新增
                    sql = """
                    INSERT INTO okx_taker_volume 
                    (coin, symbol, ts, buy_vol, sell_vol, ratio)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql, (coin, symbol, ts_datetime, buy_vol, sell_vol, ratio))
                    insert_count += 1
                    logging.debug(f"Taker主动量数据新增: {coin} {symbol} {ts_datetime}")
            
            self.connection.commit()
            logging.info(f"Taker主动量批量保存完成: {coin} {symbol} - 新增:{insert_count} 更新:{update_count} 跳过:{skip_count}")
            return True
        except pymysql.Error as e:
            self.connection.rollback()
            error_msg = f"批量保存Taker主动量数据失败 (pymysql.Error): 错误码={e.args[0]}, 错误信息={e.args[1] if len(e.args) > 1 else 'N/A'}, coin={coin}, symbol={symbol}"
            logging.error(error_msg)
            logging.error(f"异常详情: {traceback.format_exc()}")
            raise Exception(error_msg)
        except Exception as e:
            self.connection.rollback()
            error_msg = f"批量保存Taker主动量数据失败 (Exception): {type(e).__name__}: {str(e)}, coin={coin}, symbol={symbol}"
            logging.error(error_msg)
            logging.error(f"异常详情: {traceback.format_exc()}")
            raise
        finally:
            cursor.close()
    
    def save_funding_rate(self, coin, symbol, ts_datetime, funding_rate, funding_rate_pct=None):
        """保存资金费率数据"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            sql = """
            INSERT INTO okx_funding_rate 
            (coin, symbol, ts, funding_rate, funding_rate_pct)
            VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (coin, symbol, ts_datetime, funding_rate, funding_rate_pct))
            self.connection.commit()
            logging.debug(f"资金费率数据保存成功: {coin} {ts_datetime}")
            return True
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存资金费率数据失败: {e}")
            return False
        finally:
            cursor.close()
    
    def get_open_interest_by_ts(self, coin, symbol, ts_datetime):
        """根据coin, symbol, ts查询持仓量数据"""
        if not self.connection:
            if not self.connect():
                logging.warning(f"查询持仓量数据失败：数据库连接未建立 (coin={coin}, symbol={symbol}, ts={ts_datetime})")
                return None
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            error_detail = f"{type(ping_error).__name__}: {str(ping_error)}"
            if hasattr(ping_error, 'args') and ping_error.args:
                error_detail += f", args={ping_error.args}"
            logging.warning(f"数据库连接检查失败，尝试重新连接: {error_detail}")
            if not self.connect():
                logging.warning(f"查询持仓量数据失败：数据库重连失败 (coin={coin}, symbol={symbol}, ts={ts_datetime})")
                return None
        
        cursor = self.connection.cursor()
        try:
            sql = """
            SELECT open_interest, oi_ccy, oi_usd 
            FROM okx_open_interest 
            WHERE coin = %s AND symbol = %s AND ts = %s
            """
            cursor.execute(sql, (coin, symbol, ts_datetime))
            result = cursor.fetchone()
            if result:
                return {
                    'open_interest': float(result[0]) if result[0] else None,
                    'oi_ccy': float(result[1]) if result[1] else None,
                    'oi_usd': float(result[2]) if result[2] else None
                }
            return None
        except pymysql.Error as e:
            error_code = e.args[0] if len(e.args) > 0 else 'N/A'
            error_msg_detail = e.args[1] if len(e.args) > 1 else (e.args[0] if len(e.args) == 1 else 'N/A')
            error_msg = f"查询持仓量数据时发生异常 (pymysql.Error): 错误码={error_code}, 错误信息={error_msg_detail}, 异常类型={type(e).__name__}, coin={coin}, symbol={symbol}, ts={ts_datetime}"
            # 查询失败不应该阻止保存操作，使用warning级别而不是error，返回 None 表示数据不存在（将尝试插入）
            logging.warning(error_msg)
            logging.debug(f"异常详情: {traceback.format_exc()}")
            return None
        except Exception as e:
            error_msg = f"查询持仓量数据时发生异常 (Exception): 异常类型={type(e).__name__}, 错误信息={str(e)}, args={e.args if hasattr(e, 'args') else 'N/A'}, coin={coin}, symbol={symbol}, ts={ts_datetime}"
            # 查询失败不应该阻止保存操作，使用warning级别而不是error，返回 None 表示数据不存在（将尝试插入）
            logging.warning(error_msg)
            logging.debug(f"异常详情: {traceback.format_exc()}")
            return None
        finally:
            cursor.close()
    
    def save_open_interest(self, coin, symbol, ts_datetime, open_interest, oi_ccy=None, oi_usd=None,
                          delta_oi=None, pct_change=None, taker_buy=None, taker_sell=None, net_taker=None):
        """保存持仓量数据（单条）"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 检查数据是否已存在
            existing = self.get_open_interest_by_ts(coin, symbol, ts_datetime)
            
            if existing:
                # 数据已存在，比较 oi, oiCcy, oiUsd 是否一致
                oi_equal = abs(float(existing['open_interest']) - float(open_interest)) < 0.0001
                ccy_equal = (existing['oi_ccy'] is None and oi_ccy is None) or \
                           (existing['oi_ccy'] is not None and oi_ccy is not None and 
                            abs(float(existing['oi_ccy']) - float(oi_ccy)) < 0.0001)
                usd_equal = (existing['oi_usd'] is None and oi_usd is None) or \
                           (existing['oi_usd'] is not None and oi_usd is not None and 
                            abs(float(existing['oi_usd']) - float(oi_usd)) < 0.0001)
                
                if oi_equal and ccy_equal and usd_equal:
                    logging.debug(f"持仓量数据已存在且一致，跳过更新: {coin} {symbol} {ts_datetime}")
                    return True
                else:
                    # 数据不一致，更新
                    sql = """
                    UPDATE okx_open_interest 
                    SET open_interest = %s, oi_ccy = %s, oi_usd = %s,
                        delta_oi = %s, pct_change = %s, 
                        taker_buy = %s, taker_sell = %s, net_taker = %s
                    WHERE coin = %s AND symbol = %s AND ts = %s
                    """
                    cursor.execute(sql, (open_interest, oi_ccy, oi_usd, delta_oi, pct_change,
                                        taker_buy, taker_sell, net_taker, coin, symbol, ts_datetime))
                    self.connection.commit()
                    logging.info(f"持仓量数据已更新: {coin} {symbol} {ts_datetime}")
                    return True
            else:
                # 数据不存在，新增
                sql = """
                INSERT INTO okx_open_interest 
                (coin, symbol, ts, open_interest, oi_ccy, oi_usd, delta_oi, pct_change, taker_buy, taker_sell, net_taker)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (coin, symbol, ts_datetime, open_interest, oi_ccy, oi_usd,
                                    delta_oi, pct_change, taker_buy, taker_sell, net_taker))
                self.connection.commit()
                logging.debug(f"持仓量数据保存成功: {coin} {symbol} {ts_datetime}")
                return True
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存持仓量数据失败: {e}")
            return False
        finally:
            cursor.close()
    
    def save_open_interest_batch(self, coin, symbol, data_list):
        """
        批量保存持仓量数据
        data_list: [(ts_datetime, oi, oi_ccy, oi_usd), ...]
        """
        if not self.connection:
            if not self.connect():
                return False
        
        if not data_list:
            return True
        
        insert_count = 0
        update_count = 0
        skip_count = 0
        
        cursor = self.connection.cursor()
        try:
            for ts_datetime, oi, oi_ccy, oi_usd in data_list:
                # 检查数据是否已存在
                existing = self.get_open_interest_by_ts(coin, symbol, ts_datetime)
                
                if existing:
                    # 数据已存在，比较 oi, oiCcy, oiUsd 是否一致
                    oi_equal = abs(float(existing['open_interest']) - float(oi)) < 0.0001
                    ccy_equal = (existing['oi_ccy'] is None and oi_ccy is None) or \
                               (existing['oi_ccy'] is not None and oi_ccy is not None and 
                                abs(float(existing['oi_ccy']) - float(oi_ccy)) < 0.0001)
                    usd_equal = (existing['oi_usd'] is None and oi_usd is None) or \
                               (existing['oi_usd'] is not None and oi_usd is not None and 
                                abs(float(existing['oi_usd']) - float(oi_usd)) < 0.0001)
                    
                    if oi_equal and ccy_equal and usd_equal:
                        skip_count += 1
                        logging.debug(f"持仓量数据已存在且一致，跳过: {coin} {symbol} {ts_datetime}")
                    else:
                        # 数据不一致，更新
                        sql = """
                        UPDATE okx_open_interest 
                        SET open_interest = %s, oi_ccy = %s, oi_usd = %s
                        WHERE coin = %s AND symbol = %s AND ts = %s
                        """
                        cursor.execute(sql, (oi, oi_ccy, oi_usd, coin, symbol, ts_datetime))
                        update_count += 1
                        logging.debug(f"持仓量数据已更新: {coin} {symbol} {ts_datetime}")
                else:
                    # 数据不存在，新增
                    sql = """
                    INSERT INTO okx_open_interest 
                    (coin, symbol, ts, open_interest, oi_ccy, oi_usd)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql, (coin, symbol, ts_datetime, oi, oi_ccy, oi_usd))
                    insert_count += 1
                    logging.debug(f"持仓量数据新增: {coin} {symbol} {ts_datetime}")
            
            self.connection.commit()
            logging.info(f"持仓量批量保存完成: {coin} {symbol} - 新增:{insert_count} 更新:{update_count} 跳过:{skip_count}")
            return True
        except Exception as e:
            self.connection.rollback()
            logging.error(f"批量保存持仓量数据失败: {e}")
            return False
        finally:
            cursor.close()
    
    def get_long_short_ratio_by_ts(self, coin, symbol, ts_datetime):
        """根据coin, symbol, ts查询多空比数据"""
        if not self.connection:
            if not self.connect():
                return None
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return None
        
        cursor = self.connection.cursor()
        try:
            sql = """
            SELECT long_short_ratio, delta_ratio, long_short_ratio_by_ccy, 
                   top_trader_account_ratio, top_trader_position_ratio
            FROM okx_long_short_ratio 
            WHERE coin = %s AND symbol = %s AND ts = %s
            """
            cursor.execute(sql, (coin, symbol, ts_datetime))
            result = cursor.fetchone()
            if result:
                return {
                    'long_short_ratio': float(result[0]) if result[0] else None,
                    'delta_ratio': float(result[1]) if result[1] else None,
                    'long_short_ratio_by_ccy': float(result[2]) if result[2] else None,
                    'top_trader_account_ratio': float(result[3]) if result[3] else None,
                    'top_trader_position_ratio': float(result[4]) if result[4] else None
                }
            return None
        except Exception as e:
            logging.warning(f"查询多空比数据失败: {e}")
            return None
        finally:
            cursor.close()
    
    def save_long_short_ratio(self, coin, symbol, ts_datetime, long_short_ratio, delta_ratio=None, 
                             long_short_ratio_by_ccy=None, top_trader_account_ratio=None, top_trader_position_ratio=None):
        """保存多空比数据（完整保存）"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            sql = """
            INSERT INTO okx_long_short_ratio 
            (coin, symbol, ts, long_short_ratio, delta_ratio, long_short_ratio_by_ccy, 
             top_trader_account_ratio, top_trader_position_ratio)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                long_short_ratio = VALUES(long_short_ratio),
                delta_ratio = VALUES(delta_ratio),
                long_short_ratio_by_ccy = VALUES(long_short_ratio_by_ccy),
                top_trader_account_ratio = VALUES(top_trader_account_ratio),
                top_trader_position_ratio = VALUES(top_trader_position_ratio)
            """
            cursor.execute(sql, (coin, symbol, ts_datetime, long_short_ratio, delta_ratio, 
                               long_short_ratio_by_ccy, top_trader_account_ratio, top_trader_position_ratio))
            self.connection.commit()
            logging.debug(f"多空比数据保存成功: {coin} {ts_datetime} (合约比={long_short_ratio}, 币种比={long_short_ratio_by_ccy}, 精英人数比={top_trader_account_ratio}, 精英仓位比={top_trader_position_ratio})")
            return True
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存多空比数据失败: {e}")
            return False
        finally:
            cursor.close()
    
    def save_long_short_ratio_partial(self, coin, symbol, ts_datetime, 
                                     long_short_ratio=None, delta_ratio=None,
                                     long_short_ratio_by_ccy=None, 
                                     top_trader_account_ratio=None, 
                                     top_trader_position_ratio=None):
        """
        部分保存多空比数据（只更新传入的字段，其他字段保持不变）
        返回: 'saved'（新增）、'updated'（更新）、'skipped'（跳过，数据相同）
        """
        if not self.connection:
            if not self.connect():
                return False
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 查询现有数据
            existing = self.get_long_short_ratio_by_ts(coin, symbol, ts_datetime)
            
            if existing:
                # 数据已存在，检查是否需要更新
                need_update = False
                update_fields = []
                update_values = []
                
                if long_short_ratio is not None:
                    if existing['long_short_ratio'] is None or abs(existing['long_short_ratio'] - long_short_ratio) >= 0.0001:
                        update_fields.append("long_short_ratio = %s")
                        update_values.append(long_short_ratio)
                        need_update = True
                
                if delta_ratio is not None:
                    if existing['delta_ratio'] is None or abs(existing['delta_ratio'] - delta_ratio) >= 0.0001:
                        update_fields.append("delta_ratio = %s")
                        update_values.append(delta_ratio)
                        need_update = True
                
                if long_short_ratio_by_ccy is not None:
                    if existing['long_short_ratio_by_ccy'] is None or abs(existing['long_short_ratio_by_ccy'] - long_short_ratio_by_ccy) >= 0.0001:
                        update_fields.append("long_short_ratio_by_ccy = %s")
                        update_values.append(long_short_ratio_by_ccy)
                        need_update = True
                
                if top_trader_account_ratio is not None:
                    if existing['top_trader_account_ratio'] is None or abs(existing['top_trader_account_ratio'] - top_trader_account_ratio) >= 0.0001:
                        update_fields.append("top_trader_account_ratio = %s")
                        update_values.append(top_trader_account_ratio)
                        need_update = True
                
                if top_trader_position_ratio is not None:
                    if existing['top_trader_position_ratio'] is None or abs(existing['top_trader_position_ratio'] - top_trader_position_ratio) >= 0.0001:
                        update_fields.append("top_trader_position_ratio = %s")
                        update_values.append(top_trader_position_ratio)
                        need_update = True
                
                if need_update:
                    # 需要更新
                    sql = f"""
                    UPDATE okx_long_short_ratio 
                    SET {', '.join(update_fields)}
                    WHERE coin = %s AND symbol = %s AND ts = %s
                    """
                    update_values.extend([coin, symbol, ts_datetime])
                    cursor.execute(sql, update_values)
                    self.connection.commit()
                    logging.info(f"多空比数据已更新: {coin} {symbol} {ts_datetime} - 更新字段: {', '.join(update_fields)}")
                    return 'updated'
                else:
                    # 数据相同，跳过
                    logging.debug(f"多空比数据已存在且一致，跳过: {coin} {symbol} {ts_datetime}")
                    return 'skipped'
            else:
                # 数据不存在，插入新记录
                # 构建INSERT语句，只包含传入的非None字段
                insert_fields = ['coin', 'symbol', 'ts']
                insert_values = [coin, symbol, ts_datetime]
                placeholders = ['%s', '%s', '%s']
                
                if long_short_ratio is not None:
                    insert_fields.append('long_short_ratio')
                    insert_values.append(long_short_ratio)
                    placeholders.append('%s')
                
                if delta_ratio is not None:
                    insert_fields.append('delta_ratio')
                    insert_values.append(delta_ratio)
                    placeholders.append('%s')
                
                if long_short_ratio_by_ccy is not None:
                    insert_fields.append('long_short_ratio_by_ccy')
                    insert_values.append(long_short_ratio_by_ccy)
                    placeholders.append('%s')
                
                if top_trader_account_ratio is not None:
                    insert_fields.append('top_trader_account_ratio')
                    insert_values.append(top_trader_account_ratio)
                    placeholders.append('%s')
                
                if top_trader_position_ratio is not None:
                    insert_fields.append('top_trader_position_ratio')
                    insert_values.append(top_trader_position_ratio)
                    placeholders.append('%s')
                
                sql = f"""
                INSERT INTO okx_long_short_ratio ({', '.join(insert_fields)})
                VALUES ({', '.join(placeholders)})
                """
                cursor.execute(sql, insert_values)
                self.connection.commit()
                logging.info(f"多空比数据新增: {coin} {symbol} {ts_datetime} - 字段: {', '.join([f for f in insert_fields if f not in ['coin', 'symbol', 'ts']])}")
                return 'saved'
                
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存多空比数据失败: {e}")
            import traceback
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()
    
    def save_macro_data(self, ts_datetime, sofr=None, vix=None, dgs10=None, cpi=None, 
                       cpi_yoy=None, unemployment_rate=None, japan_rate=None, us_session=None):
        """保存宏观经济数据"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            sql = """
            INSERT INTO macro_economic_data 
            (ts, sofr, vix, dgs10, cpi, cpi_yoy, unemployment_rate, japan_rate, us_session)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (ts_datetime, sofr, vix, dgs10, cpi, cpi_yoy, 
                                unemployment_rate, japan_rate, us_session))
            self.connection.commit()
            logging.info(f"宏观经济数据保存成功: {ts_datetime} (SOFR={sofr}, VIX={vix}, DGS10={dgs10}, CPI={cpi}, CPI_YoY={cpi_yoy}, 失业率={unemployment_rate}, 日本利率={japan_rate}, 美盘={us_session})")
            return True
        except pymysql.Error as e:
            self.connection.rollback()
            error_code = e.args[0] if len(e.args) > 0 else 'N/A'
            error_msg_detail = e.args[1] if len(e.args) > 1 else (e.args[0] if len(e.args) == 1 else 'N/A')
            error_msg = f"保存宏观经济数据失败 (pymysql.Error): 错误码={error_code}, 错误信息={error_msg_detail}, 异常类型={type(e).__name__}, ts={ts_datetime}"
            logging.error(error_msg)
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        except Exception as e:
            self.connection.rollback()
            error_msg = f"保存宏观经济数据失败 (Exception): 异常类型={type(e).__name__}, 错误信息={str(e)}, ts={ts_datetime}"
            logging.error(error_msg)
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()

