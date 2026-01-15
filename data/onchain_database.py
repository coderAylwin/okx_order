#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
链上数据数据库服务
用于管理交易所余额等链上数据的存储和查询
"""

import pymysql
from datetime import datetime
import logging
import traceback


class OnchainDatabaseService:
    """链上数据数据库服务类"""
    
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
        """创建链上数据表（每个币种一个表）"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # BTC交易所余额表
            create_btc_table = """
            CREATE TABLE IF NOT EXISTS onchain_exchange_balance_btc (
                id INT AUTO_INCREMENT PRIMARY KEY,
                exchange_name VARCHAR(50) NOT NULL COMMENT '交易所名称',
                total_balance DECIMAL(30, 8) NOT NULL COMMENT '总余额',
                balance_change_1d DECIMAL(30, 8) DEFAULT NULL COMMENT '1日余额变化',
                balance_change_percent_1d DECIMAL(10, 4) DEFAULT NULL COMMENT '1日余额变化百分比',
                balance_change_7d DECIMAL(30, 8) DEFAULT NULL COMMENT '7日余额变化',
                balance_change_percent_7d DECIMAL(10, 4) DEFAULT NULL COMMENT '7日余额变化百分比',
                balance_change_30d DECIMAL(30, 8) DEFAULT NULL COMMENT '30日余额变化',
                balance_change_percent_30d DECIMAL(10, 4) DEFAULT NULL COMMENT '30日余额变化百分比',
                ts DATETIME NOT NULL COMMENT '数据时间戳（UTC+8）',
                is_hourly BOOLEAN DEFAULT FALSE COMMENT '是否为整点时间（用于走势分析）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_exchange_ts (exchange_name, ts),
                INDEX idx_ts (ts),
                INDEX idx_is_hourly (is_hourly),
                INDEX idx_exchange (exchange_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='BTC交易所余额表';
            """
            
            # ETH交易所余额表
            create_eth_table = """
            CREATE TABLE IF NOT EXISTS onchain_exchange_balance_eth (
                id INT AUTO_INCREMENT PRIMARY KEY,
                exchange_name VARCHAR(50) NOT NULL COMMENT '交易所名称',
                total_balance DECIMAL(30, 8) NOT NULL COMMENT '总余额',
                balance_change_1d DECIMAL(30, 8) DEFAULT NULL COMMENT '1日余额变化',
                balance_change_percent_1d DECIMAL(10, 4) DEFAULT NULL COMMENT '1日余额变化百分比',
                balance_change_7d DECIMAL(30, 8) DEFAULT NULL COMMENT '7日余额变化',
                balance_change_percent_7d DECIMAL(10, 4) DEFAULT NULL COMMENT '7日余额变化百分比',
                balance_change_30d DECIMAL(30, 8) DEFAULT NULL COMMENT '30日余额变化',
                balance_change_percent_30d DECIMAL(10, 4) DEFAULT NULL COMMENT '30日余额变化百分比',
                ts DATETIME NOT NULL COMMENT '数据时间戳（UTC+8）',
                is_hourly BOOLEAN DEFAULT FALSE COMMENT '是否为整点时间（用于走势分析）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_exchange_ts (exchange_name, ts),
                INDEX idx_ts (ts),
                INDEX idx_is_hourly (is_hourly),
                INDEX idx_exchange (exchange_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETH交易所余额表';
            """
            
            # XRP交易所余额表
            create_xrp_table = """
            CREATE TABLE IF NOT EXISTS onchain_exchange_balance_xrp (
                id INT AUTO_INCREMENT PRIMARY KEY,
                exchange_name VARCHAR(50) NOT NULL COMMENT '交易所名称',
                total_balance DECIMAL(30, 8) NOT NULL COMMENT '总余额',
                balance_change_1d DECIMAL(30, 8) DEFAULT NULL COMMENT '1日余额变化',
                balance_change_percent_1d DECIMAL(10, 4) DEFAULT NULL COMMENT '1日余额变化百分比',
                balance_change_7d DECIMAL(30, 8) DEFAULT NULL COMMENT '7日余额变化',
                balance_change_percent_7d DECIMAL(10, 4) DEFAULT NULL COMMENT '7日余额变化百分比',
                balance_change_30d DECIMAL(30, 8) DEFAULT NULL COMMENT '30日余额变化',
                balance_change_percent_30d DECIMAL(10, 4) DEFAULT NULL COMMENT '30日余额变化百分比',
                ts DATETIME NOT NULL COMMENT '数据时间戳（UTC+8）',
                is_hourly BOOLEAN DEFAULT FALSE COMMENT '是否为整点时间（用于走势分析）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_exchange_ts (exchange_name, ts),
                INDEX idx_ts (ts),
                INDEX idx_is_hourly (is_hourly),
                INDEX idx_exchange (exchange_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='XRP交易所余额表';
            """
            
            cursor.execute(create_btc_table)
            cursor.execute(create_eth_table)
            cursor.execute(create_xrp_table)
            self.connection.commit()
            logging.info("链上数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def get_latest_exchange_balance(self, coin):
        """
        获取指定币种每个交易所最新的余额数据（按交易所分组，获取每个交易所的最新记录）
        
        Args:
            coin: 币种（BTC/ETH/XRP）
        
        Returns:
            dict: 以exchange_name为key的字典，包含每个交易所的最新数据，如果没有数据则返回空字典
        """
        if not self.connection:
            if not self.connect():
                return {}
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return {}
        
        # 根据币种选择表名
        table_map = {
            'BTC': 'onchain_exchange_balance_btc',
            'ETH': 'onchain_exchange_balance_eth',
            'XRP': 'onchain_exchange_balance_xrp'
        }
        
        if coin not in table_map:
            logging.error(f"不支持的币种: {coin}")
            return {}
        
        table_name = table_map[coin]
        cursor = self.connection.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 获取每个交易所的最新记录（按exchange_name分组，取每个交易所最新的ts）
            sql = f"""
            SELECT e1.exchange_name, e1.total_balance, e1.balance_change_1d, e1.balance_change_percent_1d,
                   e1.balance_change_7d, e1.balance_change_percent_7d, e1.balance_change_30d, e1.balance_change_percent_30d
            FROM {table_name} e1
            INNER JOIN (
                SELECT exchange_name, MAX(ts) as max_ts
                FROM {table_name}
                GROUP BY exchange_name
            ) e2 ON e1.exchange_name = e2.exchange_name AND e1.ts = e2.max_ts
            """
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            # 转换为以exchange_name为key的字典
            latest_data = {}
            for row in rows:
                exchange_name = row['exchange_name']
                latest_data[exchange_name] = {
                    'total_balance': float(row['total_balance']) if row['total_balance'] is not None else None,
                    'balance_change_1d': float(row['balance_change_1d']) if row['balance_change_1d'] is not None else None,
                    'balance_change_percent_1d': float(row['balance_change_percent_1d']) if row['balance_change_percent_1d'] is not None else None,
                    'balance_change_7d': float(row['balance_change_7d']) if row['balance_change_7d'] is not None else None,
                    'balance_change_percent_7d': float(row['balance_change_percent_7d']) if row['balance_change_percent_7d'] is not None else None,
                    'balance_change_30d': float(row['balance_change_30d']) if row['balance_change_30d'] is not None else None,
                    'balance_change_percent_30d': float(row['balance_change_percent_30d']) if row['balance_change_percent_30d'] is not None else None,
                }
            
            return latest_data
            
        except Exception as e:
            logging.error(f"获取{coin}最新交易所余额数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return {}
        finally:
            cursor.close()
    
    def save_exchange_balance(self, coin, exchange_data_list, ts_datetime, is_hourly=False):
        """
        保存交易所余额数据
        
        Args:
            coin: 币种（BTC/ETH/XRP）
            exchange_data_list: 交易所数据列表，每个元素包含交易所的余额信息
            ts_datetime: 数据时间戳（UTC+8）
            is_hourly: 是否为整点时间
        
        Returns:
            dict: 保存结果统计 {'saved': int, 'skipped': int, 'total': int, 'unchanged': int}
        """
        if not self.connection:
            if not self.connect():
                return {'saved': 0, 'skipped': 0, 'total': 0}
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return {'saved': 0, 'skipped': 0, 'total': 0}
        
        # 根据币种选择表名
        table_map = {
            'BTC': 'onchain_exchange_balance_btc',
            'ETH': 'onchain_exchange_balance_eth',
            'XRP': 'onchain_exchange_balance_xrp'
        }
        
        if coin not in table_map:
            logging.error(f"不支持的币种: {coin}")
            return {'saved': 0, 'skipped': 0, 'total': 0}
        
        table_name = table_map[coin]
        cursor = self.connection.cursor()
        
        saved_count = 0
        skipped_count = 0
        unchanged_count = 0
        total_count = len(exchange_data_list)
        
        # 获取最新的数据用于对比
        latest_data = self.get_latest_exchange_balance(coin)
        has_latest_data = len(latest_data) > 0
        
        try:
            sql = f"""
            INSERT INTO {table_name}
            (exchange_name, total_balance, balance_change_1d, balance_change_percent_1d,
             balance_change_7d, balance_change_percent_7d, balance_change_30d, balance_change_percent_30d,
             ts, is_hourly)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                total_balance = VALUES(total_balance),
                balance_change_1d = VALUES(balance_change_1d),
                balance_change_percent_1d = VALUES(balance_change_percent_1d),
                balance_change_7d = VALUES(balance_change_7d),
                balance_change_percent_7d = VALUES(balance_change_percent_7d),
                balance_change_30d = VALUES(balance_change_30d),
                balance_change_percent_30d = VALUES(balance_change_percent_30d),
                is_hourly = VALUES(is_hourly),
                updated_at = CURRENT_TIMESTAMP
            """
            
            for exchange_data in exchange_data_list:
                try:
                    exchange_name = exchange_data.get('exchange_name', '')
                    total_balance = float(exchange_data.get('total_balance', 0))
                    
                    # 过滤掉 total_balance < 100 的数据
                    if total_balance < 100:
                        skipped_count += 1
                        logging.debug(f"{coin} {exchange_name} 余额 {total_balance} < 100，跳过")
                        continue
                    
                    balance_change_1d = float(exchange_data.get('balance_change_1d', 0)) if exchange_data.get('balance_change_1d') is not None else None
                    balance_change_percent_1d = float(exchange_data.get('balance_change_percent_1d', 0)) if exchange_data.get('balance_change_percent_1d') is not None else None
                    balance_change_7d = float(exchange_data.get('balance_change_7d', 0)) if exchange_data.get('balance_change_7d') is not None else None
                    balance_change_percent_7d = float(exchange_data.get('balance_change_percent_7d', 0)) if exchange_data.get('balance_change_percent_7d') is not None else None
                    balance_change_30d = float(exchange_data.get('balance_change_30d', 0)) if exchange_data.get('balance_change_30d') is not None else None
                    balance_change_percent_30d = float(exchange_data.get('balance_change_percent_30d', 0)) if exchange_data.get('balance_change_percent_30d') is not None else None
                    
                    # 对比该交易所的最新数据，如果total_balance相同则跳过
                    if has_latest_data and exchange_name in latest_data:
                        latest = latest_data[exchange_name]
                        latest_total_balance = latest.get('total_balance')
                        
                        # 只对比total_balance，如果相同则跳过保存
                        if latest_total_balance is not None:
                            if abs(total_balance - latest_total_balance) < 0.0001:
                                unchanged_count += 1
                                logging.debug(f"{coin} {exchange_name} total_balance未变化 ({total_balance})，跳过保存")
                                continue
                    
                    cursor.execute(sql, (
                        exchange_name,
                        total_balance,
                        balance_change_1d,
                        balance_change_percent_1d,
                        balance_change_7d,
                        balance_change_percent_7d,
                        balance_change_30d,
                        balance_change_percent_30d,
                        ts_datetime,
                        is_hourly
                    ))
                    saved_count += 1
                    
                except Exception as e:
                    logging.warning(f"保存{coin}交易所余额数据失败 (exchange={exchange_data.get('exchange_name', 'unknown')}): {e}")
                    skipped_count += 1
                    continue
            
            self.connection.commit()
            if saved_count > 0 or unchanged_count > 0:
                logging.info(f"{coin}交易所余额数据保存成功: 保存={saved_count}, 未变化={unchanged_count}, 跳过={skipped_count}, 总计={total_count}")
            return {'saved': saved_count, 'skipped': skipped_count, 'unchanged': unchanged_count, 'total': total_count}
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"批量保存{coin}交易所余额数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return {'saved': 0, 'skipped': 0, 'unchanged': 0, 'total': total_count}
        finally:
            cursor.close()

