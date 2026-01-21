#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETH数据数据库服务
用于管理ETH相关数据的存储和查询
包括：质押队列数据等
"""

import pymysql
from datetime import datetime
import logging
import traceback


class ETHDatabaseService:
    """ETH数据数据库服务类"""
    
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
        """创建ETH数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        
        try:
            # ETH质押队列数据表
            create_staking_queue_table = """
            CREATE TABLE IF NOT EXISTS eth_staking_queue (
                id INT AUTO_INCREMENT PRIMARY KEY,
                deposit_count INT DEFAULT 0 COMMENT '质押请求数（待激活的32 ETH存款请求数）',
                deposit_balance_eth DECIMAL(30, 8) DEFAULT 0 COMMENT '质押总数量（ETH）',
                deposit_estimated_processed_at DATETIME DEFAULT NULL COMMENT '质押预计完成时间（UTC+8）',
                deposit_churn_eth DECIMAL(30, 8) DEFAULT 0 COMMENT '质押每个epoch最多能激活的验证者数量（ETH）',
                exit_balance_eth DECIMAL(30, 8) DEFAULT 0 COMMENT '退出队列总数量（ETH）',
                exit_count INT DEFAULT 0 COMMENT '退出队列请求数',
                exit_estimated_processed_at DATETIME DEFAULT NULL COMMENT '退出预计完成时间（UTC+8）',
                exit_churn_eth DECIMAL(30, 8) DEFAULT 0 COMMENT '退出每个epoch最多允许退出的数量（ETH）',
                withdrawal_sweep_delay INT DEFAULT NULL COMMENT '预估扫完当前待提币队列还需要多少个slot',
                withdrawal_sweep_last_validator_index INT DEFAULT NULL COMMENT '上一次扫完的验证者索引',
                finality_status VARCHAR(50) DEFAULT NULL COMMENT '最终确认状态',
                eligibleether DOUBLE DEFAULT NULL COMMENT '有资格参与验证的ETH总量（ETH）',
                totalvalidatorbalance DOUBLE DEFAULT NULL COMMENT '所有验证者的总余额（ETH）',
                averagevalidatorbalance DOUBLE DEFAULT NULL COMMENT '平均每个验证者的余额（ETH）',
                validatorscount INT DEFAULT NULL COMMENT '当前活跃验证者数量',
                ts DATETIME NOT NULL COMMENT '数据收集时间（UTC+8，整点时间）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETH质押队列数据表';
            """
            
            cursor.execute(create_staking_queue_table)
            
            # 检查并添加缺失的字段（如果表已存在但缺少字段）
            self.check_and_update_table_schema(cursor)
            
            self.connection.commit()
            logging.info("ETH数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def check_and_update_table_schema(self, cursor):
        """检查并更新表结构，添加缺失的字段"""
        try:
            # 需要检查的字段列表
            fields_to_check = [
                {
                    'name': 'exit_estimated_processed_at',
                    'sql': """
                        ALTER TABLE eth_staking_queue 
                        ADD COLUMN exit_estimated_processed_at DATETIME DEFAULT NULL 
                        COMMENT '退出预计完成时间（UTC+8）' 
                        AFTER exit_count
                    """
                },
                {
                    'name': 'eligibleether',
                    'sql': """
                        ALTER TABLE eth_staking_queue 
                        ADD COLUMN eligibleether DOUBLE DEFAULT NULL 
                        COMMENT '有资格参与验证的ETH总量（ETH）' 
                        AFTER finality_status
                    """
                },
                {
                    'name': 'totalvalidatorbalance',
                    'sql': """
                        ALTER TABLE eth_staking_queue 
                        ADD COLUMN totalvalidatorbalance DOUBLE DEFAULT NULL 
                        COMMENT '所有验证者的总余额（ETH）' 
                        AFTER eligibleether
                    """
                },
                {
                    'name': 'averagevalidatorbalance',
                    'sql': """
                        ALTER TABLE eth_staking_queue 
                        ADD COLUMN averagevalidatorbalance DOUBLE DEFAULT NULL 
                        COMMENT '平均每个验证者的余额（ETH）' 
                        AFTER totalvalidatorbalance
                    """
                },
                {
                    'name': 'validatorscount',
                    'sql': """
                        ALTER TABLE eth_staking_queue 
                        ADD COLUMN validatorscount INT DEFAULT NULL 
                        COMMENT '当前活跃验证者数量' 
                        AFTER averagevalidatorbalance
                    """
                }
            ]
            
            for field in fields_to_check:
                try:
                    # 检查字段是否存在
                    cursor.execute(f"""
                        SELECT COUNT(*) 
                        FROM information_schema.COLUMNS 
                        WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = 'eth_staking_queue' 
                        AND COLUMN_NAME = '{field['name']}'
                    """)
                    result = cursor.fetchone()
                    field_exists = result[0] > 0 if result else False
                    
                    # 如果字段存在，查询字段类型
                    field_type = None
                    if field_exists:
                        cursor.execute(f"""
                            SELECT DATA_TYPE 
                            FROM information_schema.COLUMNS 
                            WHERE TABLE_SCHEMA = DATABASE() 
                            AND TABLE_NAME = 'eth_staking_queue' 
                            AND COLUMN_NAME = '{field['name']}'
                            LIMIT 1
                        """)
                        type_result = cursor.fetchone()
                        field_type = type_result[0] if type_result else None
                    
                    if not field_exists:
                        # 字段不存在，添加字段
                        logging.info(f"检测到表缺少 {field['name']} 字段，正在添加...")
                        cursor.execute(field['sql'])
                        logging.info(f"成功添加 {field['name']} 字段")
                    elif field['name'] in ['eligibleether', 'totalvalidatorbalance', 'averagevalidatorbalance']:
                        # 如果字段存在但不是DOUBLE类型，需要修改为DOUBLE
                        if field_type not in ['double', 'DOUBLE']:
                            logging.info(f"检测到 {field['name']} 字段类型为{field_type}，正在修改为DOUBLE...")
                            # 提取注释内容
                            comment_text = '有资格参与验证的ETH总量（ETH）' if field['name'] == 'eligibleether' else \
                                         '所有验证者的总余额（ETH）' if field['name'] == 'totalvalidatorbalance' else \
                                         '平均每个验证者的余额（ETH）'
                            modify_sql = f"""
                                ALTER TABLE eth_staking_queue 
                                MODIFY COLUMN {field['name']} DOUBLE DEFAULT NULL 
                                COMMENT '{comment_text}'
                            """
                            cursor.execute(modify_sql)
                            logging.info(f"成功修改 {field['name']} 字段类型为DOUBLE")
                except Exception as field_error:
                    logging.warning(f"检查/添加字段 {field['name']} 时出错: {field_error}")
                    import traceback
                    logging.warning(f"异常详情: {traceback.format_exc()}")
        except Exception as e:
            logging.warning(f"检查表结构时出错: {e}")
    
    def save_staking_queue_data(self, deposit_count, deposit_balance_eth, deposit_estimated_processed_at,
                                deposit_churn_eth, exit_balance_eth, exit_count, exit_estimated_processed_at,
                                exit_churn_eth, withdrawal_sweep_delay, withdrawal_sweep_last_validator_index,
                                finality_status, eligibleether=None, totalvalidatorbalance=None,
                                averagevalidatorbalance=None, validatorscount=None, ts_datetime=None):
        """
        保存ETH质押队列数据
        
        Args:
            deposit_count: 质押请求数
            deposit_balance_eth: 质押总数量（ETH）
            deposit_estimated_processed_at: 质押预计完成时间（datetime对象，UTC+8）
            deposit_churn_eth: 质押每个epoch最多能激活的验证者数量（ETH）
            exit_balance_eth: 退出队列总数量（ETH）
            exit_count: 退出队列请求数
            exit_estimated_processed_at: 退出预计完成时间（datetime对象，UTC+8）
            exit_churn_eth: 退出每个epoch最多允许退出的数量（ETH）
            withdrawal_sweep_delay: 预估扫完当前待提币队列还需要多少个slot
            withdrawal_sweep_last_validator_index: 上一次扫完的验证者索引
            finality_status: 最终确认状态
            eligibleether: 有资格参与验证的ETH总量（ETH，已转换为ETH并保留2位小数）
            totalvalidatorbalance: 所有验证者的总余额（ETH，已转换为ETH并保留2位小数）
            averagevalidatorbalance: 平均每个验证者的余额（ETH，已转换为ETH并保留2位小数）
            validatorscount: 当前活跃验证者数量
            ts_datetime: 数据收集时间（datetime对象，UTC+8）
        
        Returns:
            bool: 保存成功返回True，失败返回False
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
        
        # 在保存前再次检查并更新表结构（确保字段存在）
        cursor = self.connection.cursor()
        try:
            self.check_and_update_table_schema(cursor)
            self.connection.commit()
        except Exception as schema_error:
            logging.warning(f"检查表结构时出错: {schema_error}")
        finally:
            cursor.close()
        
        cursor = self.connection.cursor()
        
        try:
            sql = """
            INSERT INTO eth_staking_queue (
                deposit_count, deposit_balance_eth, deposit_estimated_processed_at,
                deposit_churn_eth, exit_balance_eth, exit_count, exit_estimated_processed_at,
                exit_churn_eth, withdrawal_sweep_delay, withdrawal_sweep_last_validator_index,
                finality_status, eligibleether, totalvalidatorbalance, averagevalidatorbalance,
                validatorscount, ts
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            
            values = (
                deposit_count,
                deposit_balance_eth,
                deposit_estimated_processed_at,
                deposit_churn_eth,
                exit_balance_eth,
                exit_count,
                exit_estimated_processed_at,
                exit_churn_eth,
                withdrawal_sweep_delay,
                withdrawal_sweep_last_validator_index,
                finality_status,
                eligibleether,
                totalvalidatorbalance,
                averagevalidatorbalance,
                validatorscount,
                ts_datetime
            )
            
            # 添加调试日志
            logging.info(f"准备保存数据: eligibleether={eligibleether}, totalvalidatorbalance={totalvalidatorbalance}, "
                        f"averagevalidatorbalance={averagevalidatorbalance}, validatorscount={validatorscount}")
            logging.info(f"SQL参数数量: {len(values)}, SQL占位符数量: {sql.count('%s')}")
            
            cursor.execute(sql, values)
            self.connection.commit()
            logging.info(f"ETH质押队列数据保存成功: ts={ts_datetime}, deposit_count={deposit_count}, "
                        f"validatorscount={validatorscount}")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存ETH质押队列数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()

