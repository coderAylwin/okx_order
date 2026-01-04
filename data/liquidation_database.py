#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爆仓数据数据库服务
用于管理爆仓数据的存储和查询
"""

import pymysql
from datetime import datetime
import logging


class LiquidationDatabaseService:
    """爆仓数据库服务类"""
    
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
        """创建爆仓数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 创建爆仓数据表
            create_table = """
            CREATE TABLE IF NOT EXISTS liquidation_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                inst_id VARCHAR(100) DEFAULT NULL COMMENT '合约ID',
                inst_family VARCHAR(100) DEFAULT NULL COMMENT '合约族',
                uly VARCHAR(50) DEFAULT NULL COMMENT '标的资产',
                bk_px DECIMAL(20, 8) DEFAULT NULL COMMENT '爆仓价格',
                sz DECIMAL(20, 8) DEFAULT NULL COMMENT '数量（合约张数）',
                ccy VARCHAR(20) DEFAULT NULL COMMENT '币种代码',
                side VARCHAR(10) DEFAULT NULL COMMENT '方向（buy/sell）',
                pos_side VARCHAR(10) DEFAULT NULL COMMENT '持仓方向（long/short）',
                bk_loss DECIMAL(20, 8) DEFAULT NULL COMMENT '爆仓损失',
                usd_value DECIMAL(20, 2) DEFAULT NULL COMMENT 'USD价值',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_coin (coin),
                INDEX idx_ts (ts),
                INDEX idx_coin_ts (coin, ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='爆仓数据表';
            """
            
            cursor.execute(create_table)
            self.connection.commit()
            logging.info("爆仓数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def save_liquidation(self, coin, inst_id, inst_family, uly, bk_px, sz, ccy, side, pos_side, bk_loss, usd_value, ts_datetime):
        """
        保存爆仓数据
        
        Args:
            coin: 币种（BTC/ETH/SOL）
            inst_id: 合约ID
            inst_family: 合约族
            uly: 标的资产
            bk_px: 爆仓价格
            sz: 数量（合约张数）
            ccy: 币种代码
            side: 方向（buy/sell）
            pos_side: 持仓方向（long/short）
            bk_loss: 爆仓损失
            usd_value: USD价值
            ts_datetime: 时间戳（datetime对象，UTC+8）
            
        Returns:
            bool: 保存是否成功
        """
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            sql = """
            INSERT INTO liquidation_data 
            (coin, inst_id, inst_family, uly, bk_px, sz, ccy, side, pos_side, bk_loss, usd_value, ts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                coin, inst_id, inst_family, uly,
                bk_px if bk_px and bk_px != '0' else None,
                sz if sz and sz != '0' else None,
                ccy if ccy else None,
                side if side else None,
                pos_side if pos_side else None,
                bk_loss if bk_loss and bk_loss != '0' else None,
                usd_value,
                ts_datetime
            ))
            self.connection.commit()
            logging.debug(f"爆仓数据保存成功: {coin} {ts_datetime}")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存爆仓数据失败: {e}")
            return False
        finally:
            cursor.close()

