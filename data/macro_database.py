#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据数据库服务
用于管理恐慌指数等宏观数据的存储和查询
"""

import pymysql
from datetime import datetime
import logging
import traceback


class MacroDatabaseService:
    """宏观数据数据库服务类"""
    
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
        """创建宏观数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 恐慌指数表
            create_fear_greed_table = """
            CREATE TABLE IF NOT EXISTS macro_fear_greed_index (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ts DATETIME NOT NULL COMMENT '数据时间戳（UTC+8，整点时间）',
                crypto_fear_greed_value INT DEFAULT NULL COMMENT '加密货币恐慌指数值（0-100）',
                crypto_fear_greed_classification VARCHAR(50) DEFAULT NULL COMMENT '加密货币恐慌指数分类（Extreme Fear/Fear/Neutral/Greed/Extreme Greed）',
                crypto_fear_greed_timestamp BIGINT DEFAULT NULL COMMENT '加密货币恐慌指数生成时间戳（Unix时间戳）',
                vix_value DECIMAL(10, 4) DEFAULT NULL COMMENT 'VIX恐慌指数值',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_ts (ts),
                INDEX idx_ts (ts),
                INDEX idx_crypto_value (crypto_fear_greed_value)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='恐慌指数表（加密货币恐慌指数+VIX）';
            """
            
            cursor.execute(create_fear_greed_table)
            self.connection.commit()
            logging.info("宏观数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def get_latest_fear_greed_data(self):
        """
        获取最新的恐慌指数数据
        
        Returns:
            dict: 最新数据，如果没有数据则返回None
        """
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
        
        cursor = self.connection.cursor(pymysql.cursors.DictCursor)
        try:
            sql = """
            SELECT ts, crypto_fear_greed_value, crypto_fear_greed_classification, 
                   crypto_fear_greed_timestamp, vix_value
            FROM macro_fear_greed_index
            ORDER BY ts DESC
            LIMIT 1
            """
            cursor.execute(sql)
            result = cursor.fetchone()
            return result
            
        except Exception as e:
            logging.error(f"获取最新恐慌指数数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return None
        finally:
            cursor.close()
    
    def save_fear_greed_data(self, ts_datetime, crypto_value=None, crypto_classification=None, 
                             crypto_timestamp=None, vix_value=None, check_update=True):
        """
        保存恐慌指数数据
        
        Args:
            ts_datetime: 数据时间戳（UTC+8，整点时间）
            crypto_value: 加密货币恐慌指数值
            crypto_classification: 加密货币恐慌指数分类
            crypto_timestamp: 加密货币恐慌指数生成时间戳（Unix时间戳）
            vix_value: VIX恐慌指数值
            check_update: 是否检查更新（对比最新数据，有变化才保存）
        
        Returns:
            str: 'saved'=保存成功, 'unchanged'=数据未变化, 'updated'=更新成功, False=保存失败
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
            # 如果启用检查更新，先对比最新数据
            if check_update:
                latest_data = self.get_latest_fear_greed_data()
                if latest_data:
                    # 对比加密货币恐慌指数值
                    latest_crypto_value = latest_data.get('crypto_fear_greed_value')
                    if latest_crypto_value is not None and crypto_value is not None:
                        if int(latest_crypto_value) == int(crypto_value):
                            # 加密货币恐慌指数值相同，检查是否需要更新VIX
                            latest_vix = latest_data.get('vix_value')
                            if latest_vix is not None and vix_value is not None:
                                # 两者都有值，如果都相同则跳过
                                if abs(float(latest_vix) - float(vix_value)) < 0.01:
                                    logging.debug(f"恐慌指数数据未变化，跳过保存: ts={ts_datetime}, crypto_value={crypto_value}, vix={vix_value}")
                                    return 'unchanged'
                            elif latest_vix is None and vix_value is not None:
                                # 历史数据没有VIX，现在有VIX，需要更新
                                logging.info(f"历史数据补充VIX: ts={ts_datetime}, vix={vix_value}")
                            else:
                                # 加密货币恐慌指数值相同，且VIX情况相同，跳过
                                logging.debug(f"恐慌指数数据未变化，跳过保存: ts={ts_datetime}, crypto_value={crypto_value}")
                                return 'unchanged'
            
            # 检查是否存在该时间戳的记录
            check_sql = "SELECT id, crypto_fear_greed_value, vix_value FROM macro_fear_greed_index WHERE ts = %s"
            cursor.execute(check_sql, (ts_datetime,))
            existing = cursor.fetchone()
            
            if existing:
                # 记录已存在，更新数据
                record_id, existing_crypto_value, existing_vix = existing
                
                # 如果已有加密货币恐慌指数值，且新值相同，只更新VIX（如果提供）
                if existing_crypto_value is not None and crypto_value is not None:
                    if int(existing_crypto_value) == int(crypto_value):
                        # 只更新VIX（如果提供且不同）
                        if vix_value is not None and (existing_vix is None or abs(float(existing_vix) - float(vix_value)) >= 0.01):
                            update_sql = """
                            UPDATE macro_fear_greed_index
                            SET vix_value = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                            """
                            cursor.execute(update_sql, (vix_value, record_id))
                            self.connection.commit()
                            logging.info(f"恐慌指数数据更新（补充VIX）: ts={ts_datetime}, vix={vix_value}")
                            return 'updated'
                        else:
                            logging.debug(f"恐慌指数数据未变化，跳过更新: ts={ts_datetime}")
                            return 'unchanged'
                
                # 更新所有字段
                update_sql = """
                UPDATE macro_fear_greed_index
                SET crypto_fear_greed_value = %s, crypto_fear_greed_classification = %s,
                    crypto_fear_greed_timestamp = %s, vix_value = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """
                cursor.execute(update_sql, (
                    crypto_value, crypto_classification, crypto_timestamp, vix_value, record_id
                ))
                self.connection.commit()
                logging.info(f"恐慌指数数据更新: ts={ts_datetime}, crypto_value={crypto_value}, vix={vix_value}")
                return 'updated'
            else:
                # 新记录，插入数据
                insert_sql = """
                INSERT INTO macro_fear_greed_index
                (ts, crypto_fear_greed_value, crypto_fear_greed_classification, 
                 crypto_fear_greed_timestamp, vix_value)
                VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(insert_sql, (
                    ts_datetime, crypto_value, crypto_classification, crypto_timestamp, vix_value
                ))
                self.connection.commit()
                logging.info(f"恐慌指数数据保存成功: ts={ts_datetime}, crypto_value={crypto_value}, vix={vix_value}")
                return 'saved'
                
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存恐慌指数数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()
    
    def get_missing_vix_records(self, limit=100):
        """
        获取缺少VIX数据的记录（用于补充历史数据）
        
        Args:
            limit: 返回记录数限制
        
        Returns:
            list: 缺少VIX数据的记录列表
        """
        if not self.connection:
            if not self.connect():
                return []
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return []
        
        cursor = self.connection.cursor(pymysql.cursors.DictCursor)
        try:
            sql = """
            SELECT id, ts, crypto_fear_greed_value
            FROM macro_fear_greed_index
            WHERE vix_value IS NULL
            ORDER BY ts DESC
            LIMIT %s
            """
            cursor.execute(sql, (limit,))
            results = cursor.fetchall()
            return results
            
        except Exception as e:
            logging.error(f"获取缺少VIX数据的记录失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return []
        finally:
            cursor.close()

