#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF流量数据数据库服务
用于管理BTC ETF流量数据的存储和查询
"""

import pymysql
from datetime import datetime
import logging
import traceback


class ETFFlowDatabaseService:
    """ETF流量数据数据库服务类"""
    
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
        """创建ETF流量数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # BTC ETF流量表
            create_btc_etf_table = """
            CREATE TABLE IF NOT EXISTS etf_btc_flow_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE NOT NULL COMMENT '日期',
                gbtc DECIMAL(20, 2) DEFAULT 0 COMMENT 'GBTC流量（USD）',
                ibit DECIMAL(20, 2) DEFAULT 0 COMMENT 'IBIT流量（USD）',
                fbtc DECIMAL(20, 2) DEFAULT 0 COMMENT 'FBTC流量（USD）',
                arkb DECIMAL(20, 2) DEFAULT 0 COMMENT 'ARKB流量（USD）',
                bitb DECIMAL(20, 2) DEFAULT 0 COMMENT 'BITB流量（USD）',
                btco DECIMAL(20, 2) DEFAULT 0 COMMENT 'BTCO流量（USD）',
                hodl DECIMAL(20, 2) DEFAULT 0 COMMENT 'HODL流量（USD）',
                brrr DECIMAL(20, 2) DEFAULT 0 COMMENT 'BRRR流量（USD）',
                ezbc DECIMAL(20, 2) DEFAULT 0 COMMENT 'EZBC流量（USD）',
                btcw DECIMAL(20, 2) DEFAULT 0 COMMENT 'BTCW流量（USD）',
                btc DECIMAL(20, 2) DEFAULT 0 COMMENT 'BTC流量（USD）',
                total DECIMAL(20, 2) DEFAULT 0 COMMENT '总流量（USD）',
                price_usd DECIMAL(20, 2) DEFAULT NULL COMMENT 'BTC价格（USD）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_date (date),
                INDEX idx_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='BTC ETF流量历史表';
            """
            
            # ETH ETF流量表
            create_eth_etf_table = """
            CREATE TABLE IF NOT EXISTS etf_eth_flow_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE NOT NULL COMMENT '日期',
                etha DECIMAL(20, 2) DEFAULT 0 COMMENT 'ETHA流量（USD）',
                feth DECIMAL(20, 2) DEFAULT 0 COMMENT 'FETH流量（USD）',
                ethw DECIMAL(20, 2) DEFAULT 0 COMMENT 'ETHW流量（USD）',
                teth DECIMAL(20, 2) DEFAULT 0 COMMENT 'TETH流量（USD）',
                ethv DECIMAL(20, 2) DEFAULT 0 COMMENT 'ETHV流量（USD）',
                qeth DECIMAL(20, 2) DEFAULT 0 COMMENT 'QETH流量（USD）',
                ezet DECIMAL(20, 2) DEFAULT 0 COMMENT 'EZET流量（USD）',
                ethe DECIMAL(20, 2) DEFAULT 0 COMMENT 'ETHE流量（USD）',
                eth DECIMAL(20, 2) DEFAULT 0 COMMENT 'ETH流量（USD）',
                total DECIMAL(20, 2) DEFAULT 0 COMMENT '总流量（USD）',
                price_usd DECIMAL(20, 2) DEFAULT NULL COMMENT 'ETH价格（USD）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_date (date),
                INDEX idx_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETH ETF流量历史表';
            """
            
            # SOL ETF流量表
            create_sol_etf_table = """
            CREATE TABLE IF NOT EXISTS etf_sol_flow_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE NOT NULL COMMENT '日期',
                bsol DECIMAL(20, 2) DEFAULT 0 COMMENT 'BSOL流量（USD）',
                vsol DECIMAL(20, 2) DEFAULT 0 COMMENT 'VSOL流量（USD）',
                fsol DECIMAL(20, 2) DEFAULT 0 COMMENT 'FSOL流量（USD）',
                tsol DECIMAL(20, 2) DEFAULT 0 COMMENT 'TSOL流量（USD）',
                soez DECIMAL(20, 2) DEFAULT 0 COMMENT 'SOEZ流量（USD）',
                gsol DECIMAL(20, 2) DEFAULT 0 COMMENT 'GSOL流量（USD）',
                total DECIMAL(20, 2) DEFAULT 0 COMMENT '总流量（USD）',
                price_usd DECIMAL(20, 2) DEFAULT NULL COMMENT 'SOL价格（USD）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_date (date),
                INDEX idx_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SOL ETF流量历史表';
            """
            
            # XRP ETF流量表
            create_xrp_etf_table = """
            CREATE TABLE IF NOT EXISTS etf_xrp_flow_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE NOT NULL COMMENT '日期',
                xrp DECIMAL(20, 2) DEFAULT 0 COMMENT 'XRP流量（USD）',
                toxr DECIMAL(20, 2) DEFAULT 0 COMMENT 'TOXR流量（USD）',
                gxrp DECIMAL(20, 2) DEFAULT 0 COMMENT 'GXRP流量（USD）',
                xrpc DECIMAL(20, 2) DEFAULT 0 COMMENT 'XRPC流量（USD）',
                xrpz DECIMAL(20, 2) DEFAULT 0 COMMENT 'XRPZ流量（USD）',
                total DECIMAL(20, 2) DEFAULT 0 COMMENT '总流量（USD）',
                price_usd DECIMAL(20, 2) DEFAULT NULL COMMENT 'XRP价格（USD）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_date (date),
                INDEX idx_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='XRP ETF流量历史表';
            """
            
            cursor.execute(create_btc_etf_table)
            cursor.execute(create_eth_etf_table)
            cursor.execute(create_sol_etf_table)
            cursor.execute(create_xrp_etf_table)
            self.connection.commit()
            logging.info("ETF流量数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def save_etf_flow_data(self, coin, date, etf_flows_dict, total_flow_usd, price_usd):
        """
        保存ETF流量数据
        
        Args:
            coin: 币种（BTC/ETH/SOL/XRP）
            date: 日期（DATE类型）
            etf_flows_dict: ETF流量字典，key为ticker（如GBTC, IBIT等），value为flow_usd
            total_flow_usd: 总流量（USD）
            price_usd: 价格（USD）
        
        Returns:
            str: 'saved'=保存成功, 'updated'=更新成功, False=保存失败
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
        
        # 根据币种选择表名和字段
        if coin == 'ETH':
            table_name = 'etf_eth_flow_history'
            # ETH的ETF ticker列表
            ticker_fields = {
                'ETHA': 'etha',
                'FETH': 'feth',
                'ETHW': 'ethw',
                'TETH': 'teth',
                'ETHV': 'ethv',
                'QETH': 'qeth',
                'EZET': 'ezet',
                'ETHE': 'ethe',
                'ETH': 'eth'
            }
        elif coin == 'SOL':
            table_name = 'etf_sol_flow_history'
            # SOL的ETF ticker列表
            ticker_fields = {
                'BSOL': 'bsol',
                'VSOL': 'vsol',
                'FSOL': 'fsol',
                'TSOL': 'tsol',
                'SOEZ': 'soez',
                'GSOL': 'gsol'
            }
        elif coin == 'XRP':
            table_name = 'etf_xrp_flow_history'
            # XRP的ETF ticker列表
            ticker_fields = {
                'XRP': 'xrp',
                'TOXR': 'toxr',
                'GXRP': 'gxrp',
                'XRPC': 'xrpc',
                'XRPZ': 'xrpz'
            }
        else:  # BTC
            table_name = 'etf_btc_flow_history'
            # BTC的ETF ticker列表
            ticker_fields = {
                'GBTC': 'gbtc',
                'IBIT': 'ibit',
                'FBTC': 'fbtc',
                'ARKB': 'arkb',
                'BITB': 'bitb',
                'BTCO': 'btco',
                'HODL': 'hodl',
                'BRRR': 'brrr',
                'EZBC': 'ezbc',
                'BTCW': 'btcw',
                'BTC': 'btc'
            }
        
        cursor = self.connection.cursor()
        
        try:
            # 检查是否存在该日期的记录
            check_sql = f"SELECT id FROM {table_name} WHERE date = %s"
            cursor.execute(check_sql, (date,))
            existing = cursor.fetchone()
            
            # 获取各个ETF的流量值（转换为float，如果不存在则为0）
            etf_values = {}
            for ticker, field_name in ticker_fields.items():
                etf_values[field_name] = float(etf_flows_dict.get(ticker, 0)) if etf_flows_dict.get(ticker) is not None else 0
            
            total = float(total_flow_usd) if total_flow_usd is not None else 0
            price = float(price_usd) if price_usd is not None else None
            
            # 构建字段名和值的列表
            field_names = list(ticker_fields.values())
            field_values = [etf_values[field] for field in field_names]
            
            if existing:
                # 记录已存在，跳过（不更新）
                logging.debug(f"{coin} ETF流量数据已存在，跳过: date={date}")
                return 'skipped'
            else:
                # 新记录，插入数据
                # 构建INSERT SQL
                field_names_str = ', '.join(field_names)
                placeholders = ', '.join(['%s'] * (len(field_names) + 2))  # +2 for total and price_usd
                insert_sql = f"""
                INSERT INTO {table_name}
                (date, {field_names_str}, total, price_usd)
                VALUES (%s, {placeholders})
                """
                cursor.execute(insert_sql, (date,) + tuple(field_values) + (total, price))
                self.connection.commit()
                logging.info(f"{coin} ETF流量数据保存成功: date={date}, total={total}, price={price}")
                return 'saved'
                
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存ETF流量数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()

