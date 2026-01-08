#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安市场数据数据库服务
用于管理币安市场数据的存储和查询
包括：持仓量数据、主动买卖量数据
"""

import pymysql
from datetime import datetime
import logging
import traceback


class BinanceDatabaseService:
    """币安市场数据数据库服务类"""
    
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
        """创建币安市场数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 币安持仓量表
            create_oi_table = """
            CREATE TABLE IF NOT EXISTS binance_open_interest (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号（如BTCUSDT）',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                sum_open_interest DECIMAL(30, 8) NOT NULL COMMENT '总持仓量（币）',
                sum_open_interest_value DECIMAL(30, 8) NOT NULL COMMENT '总持仓量价值（USD）',
                cmc_circulating_supply DECIMAL(30, 8) DEFAULT NULL COMMENT 'CMC流通供应量',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='币安持仓量表';
            """
            
            # 币安主动买卖量表
            create_taker_table = """
            CREATE TABLE IF NOT EXISTS binance_taker_volume (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号（如BTCUSDT）',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                buy_vol DECIMAL(30, 8) NOT NULL COMMENT '主动买入量',
                sell_vol DECIMAL(30, 8) NOT NULL COMMENT '主动卖出量',
                buy_sell_ratio DECIMAL(10, 4) NOT NULL COMMENT '买卖比（buyVol/sellVol）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='币安主动买卖量表';
            """
            
            cursor.execute(create_oi_table)
            cursor.execute(create_taker_table)
            self.connection.commit()
            logging.info("币安市场数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def save_open_interest_batch(self, coin, symbol, data_to_save):
        """
        批量保存币安持仓量数据
        
        Args:
            coin: 币种（BTC/ETH/SOL）
            symbol: 合约符号（如BTCUSDT）
            data_to_save: 数据列表，每个元素为 (ts_datetime, sum_open_interest, sum_open_interest_value, cmc_circulating_supply)
        
        Returns:
            bool: 保存是否成功
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
            sql = """
            INSERT INTO binance_open_interest 
            (coin, symbol, ts, sum_open_interest, sum_open_interest_value, cmc_circulating_supply)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                sum_open_interest = VALUES(sum_open_interest),
                sum_open_interest_value = VALUES(sum_open_interest_value),
                cmc_circulating_supply = VALUES(cmc_circulating_supply),
                updated_at = CURRENT_TIMESTAMP
            """
            
            # 确保数据按时间顺序保存（虽然已经排序，但再次确认）
            sorted_data = sorted(data_to_save, key=lambda x: x[0])
            
            saved_count = 0
            for ts_datetime, sum_open_interest, sum_open_interest_value, cmc_circulating_supply in sorted_data:
                try:
                    cursor.execute(sql, (coin, symbol, ts_datetime, sum_open_interest, sum_open_interest_value, cmc_circulating_supply))
                    saved_count += 1
                except Exception as e:
                    logging.warning(f"保存币安持仓量数据失败 (coin={coin}, symbol={symbol}, ts={ts_datetime}): {e}")
                    continue
            
            self.connection.commit()
            if saved_count > 0:
                logging.info(f"币安持仓量数据保存成功: {coin} {symbol} 共 {saved_count} 条（按时间顺序）")
            return saved_count > 0
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"批量保存币安持仓量数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()
    
    def save_taker_volume_batch(self, coin, symbol, data_to_save):
        """
        批量保存币安主动买卖量数据
        
        Args:
            coin: 币种（BTC/ETH/SOL）
            symbol: 合约符号（如BTCUSDT）
            data_to_save: 数据列表，每个元素为 (ts_datetime, buy_vol, sell_vol, buy_sell_ratio)
        
        Returns:
            bool: 保存是否成功
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
            sql = """
            INSERT INTO binance_taker_volume 
            (coin, symbol, ts, buy_vol, sell_vol, buy_sell_ratio)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                buy_vol = VALUES(buy_vol),
                sell_vol = VALUES(sell_vol),
                buy_sell_ratio = VALUES(buy_sell_ratio),
                updated_at = CURRENT_TIMESTAMP
            """
            
            # 确保数据按时间顺序保存（虽然已经排序，但再次确认）
            sorted_data = sorted(data_to_save, key=lambda x: x[0])
            
            saved_count = 0
            for ts_datetime, buy_vol, sell_vol, buy_sell_ratio in sorted_data:
                try:
                    cursor.execute(sql, (coin, symbol, ts_datetime, buy_vol, sell_vol, buy_sell_ratio))
                    saved_count += 1
                except Exception as e:
                    logging.warning(f"保存币安主动买卖量数据失败 (coin={coin}, symbol={symbol}, ts={ts_datetime}): {e}")
                    continue
            
            self.connection.commit()
            if saved_count > 0:
                logging.info(f"币安主动买卖量数据保存成功: {coin} {symbol} 共 {saved_count} 条（按时间顺序）")
            return saved_count > 0
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"批量保存币安主动买卖量数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()

