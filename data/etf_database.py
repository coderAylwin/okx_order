#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
比特币ETF数据库服务
用于管理ETF数据的存储和查询
"""

import pymysql
from datetime import datetime
import logging
import re


class ETFDatabaseService:
    """ETF数据库服务类"""
    
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
            logging.info("数据库连接已关闭")
    
    @staticmethod
    def convert_wan_to_number(value_str):
        """
        将带"万"字的数字转换为具体数字
        例如: "1.2万" -> "12000", "+1.2万" -> "12000", "-1.2万" -> "-12000"
        
        Args:
            value_str: 原始值字符串，可能包含"万"字
            
        Returns:
            str: 转换后的数字字符串，如果不包含"万"则返回原值
        """
        if not value_str or not isinstance(value_str, str):
            return value_str
        
        value_str = value_str.strip()
        
        # 如果不包含"万"字，直接返回
        if '万' not in value_str:
            return value_str
        
        try:
            # 提取符号（+或-）
            is_negative = False
            if value_str.startswith('-'):
                is_negative = True
                value_str = value_str[1:]
            elif value_str.startswith('+'):
                value_str = value_str[1:]
            
            # 移除"万"字
            number_part = value_str.replace('万', '').strip()
            
            # 转换为浮点数并乘以10000
            number = float(number_part) * 10000
            
            # 使用round四舍五入，避免浮点数精度问题（如 1.14 * 10000 = 11399.999999999998）
            number = round(number)
            
            # 如果是负数，加回负号
            if is_negative:
                number = -number
            
            # 转换为字符串（已经是整数，直接转换）
            return str(int(number))
                
        except (ValueError, AttributeError) as e:
            logging.warning(f"转换'万'字数字失败: {value_str}, 错误: {e}")
            return value_str  # 转换失败时返回原值
    
    def create_tables(self):
        """创建ETF数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 创建每日数据表：bitcoin_etf_daily
            # 存储每天每个机构的净流入流出数据
            create_daily_table = """
            CREATE TABLE IF NOT EXISTS bitcoin_etf_daily (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE NOT NULL COMMENT '日期',
                gbtc VARCHAR(50) DEFAULT NULL COMMENT 'GBTC净流入流出',
                ibit VARCHAR(50) DEFAULT NULL COMMENT 'IBIT净流入流出',
                fbtc VARCHAR(50) DEFAULT NULL COMMENT 'FBTC净流入流出',
                arkb VARCHAR(50) DEFAULT NULL COMMENT 'ARKB净流入流出',
                bitb VARCHAR(50) DEFAULT NULL COMMENT 'BITB净流入流出',
                btco VARCHAR(50) DEFAULT NULL COMMENT 'BTCO净流入流出',
                hodl VARCHAR(50) DEFAULT NULL COMMENT 'HODL净流入流出',
                brrr VARCHAR(50) DEFAULT NULL COMMENT 'BRRR净流入流出',
                ezbc VARCHAR(50) DEFAULT NULL COMMENT 'EZBC净流入流出',
                btcw VARCHAR(50) DEFAULT NULL COMMENT 'BTCW净流入流出',
                btc VARCHAR(50) DEFAULT NULL COMMENT 'BTC净流入流出',
                total VARCHAR(50) DEFAULT NULL COMMENT '总计',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='比特币ETF每日数据表';
            """
            
            # 创建总计数据表：bitcoin_etf_total（公用表，支持BTC、ETH和SOL）
            create_total_table = """
            CREATE TABLE IF NOT EXISTS bitcoin_etf_total (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE NOT NULL COMMENT '数据日期',
                coin_type VARCHAR(10) NOT NULL DEFAULT 'BTC' COMMENT '币种类型：BTC/ETH/SOL',
                institution VARCHAR(20) NOT NULL COMMENT '机构代码',
                total_value VARCHAR(50) DEFAULT NULL COMMENT '累计总计值（净流入用+，净流出用-）',
                value_type VARCHAR(10) DEFAULT NULL COMMENT '类型：rise涨/fall跌/neutral中性',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_date_coin_institution (date, coin_type, institution),
                INDEX idx_coin_type (coin_type),
                INDEX idx_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETF机构总计数据表（BTC、ETH和SOL共用）';
            """
            
            # 创建以太坊ETF每日数据表
            create_eth_daily_table = """
            CREATE TABLE IF NOT EXISTS ethereum_etf_daily (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE NOT NULL COMMENT '日期',
                ethe VARCHAR(50) DEFAULT NULL COMMENT 'ETHE (Grayscale) 净流入流出',
                eth VARCHAR(50) DEFAULT NULL COMMENT 'ETH (Grayscale) 净流入流出',
                etha VARCHAR(50) DEFAULT NULL COMMENT 'ETHA (Blackrock) 净流入流出',
                ethw VARCHAR(50) DEFAULT NULL COMMENT 'ETHW (Bitwise) 净流入流出',
                feth VARCHAR(50) DEFAULT NULL COMMENT 'FETH (Fidelity) 净流入流出',
                ethv VARCHAR(50) DEFAULT NULL COMMENT 'ETHV (VanEck) 净流入流出',
                ezet VARCHAR(50) DEFAULT NULL COMMENT 'EZET (Franklin) 净流入流出',
                teth VARCHAR(50) DEFAULT NULL COMMENT 'TETH (21 Shares) 净流入流出',
                qeth VARCHAR(50) DEFAULT NULL COMMENT 'QETH (Invesco) 净流入流出',
                total VARCHAR(50) DEFAULT NULL COMMENT '总计',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='以太坊ETF每日数据表';
            """
            
            # 创建索拉纳ETF每日数据表
            create_sol_daily_table = """
            CREATE TABLE IF NOT EXISTS solana_etf_daily (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE NOT NULL COMMENT '日期',
                bsol VARCHAR(50) DEFAULT NULL COMMENT 'BSOL (Bitwise) 净流入流出',
                gsol VARCHAR(50) DEFAULT NULL COMMENT 'GSOL (Grayscale) 净流入流出',
                vsol VARCHAR(50) DEFAULT NULL COMMENT 'VSOL (VanEck) 净流入流出',
                fsol VARCHAR(50) DEFAULT NULL COMMENT 'FSOL (Fidelity) 净流入流出',
                tsol VARCHAR(50) DEFAULT NULL COMMENT 'TSOL (21 Shares) 净流入流出',
                total VARCHAR(50) DEFAULT NULL COMMENT '总计',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='索拉纳ETF每日数据表';
            """
            
            cursor.execute(create_daily_table)
            cursor.execute(create_total_table)
            cursor.execute(create_eth_daily_table)
            cursor.execute(create_sol_daily_table)
            
            # 如果bitcoin_etf_total表已存在但缺少coin_type字段，尝试添加
            try:
                # 检查coin_type字段是否存在
                check_column_sql = """
                SELECT COUNT(*) as cnt 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'bitcoin_etf_total' 
                AND COLUMN_NAME = 'coin_type'
                """
                cursor.execute(check_column_sql, (self.database,))
                result = cursor.fetchone()
                if result and result[0] == 0:
                    # 字段不存在，添加字段
                    alter_table_sql = """
                    ALTER TABLE bitcoin_etf_total 
                    ADD COLUMN coin_type VARCHAR(10) NOT NULL DEFAULT 'BTC' COMMENT '币种类型：BTC/ETH' AFTER date,
                    DROP INDEX uk_date_institution,
                    ADD UNIQUE KEY uk_date_coin_institution (date, coin_type, institution),
                    ADD INDEX idx_coin_type (coin_type),
                    ADD INDEX idx_date (date)
                    """
                    cursor.execute(alter_table_sql)
                    logging.info("已为 bitcoin_etf_total 表添加 coin_type 字段")
            except Exception as alter_error:
                logging.debug(f"检查/修改表结构（可能已经正确）: {alter_error}")
            
            self.connection.commit()
            logging.info("ETF数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def get_existing_dates(self, coin_type='BTC'):
        """
        查询数据库中已存在的日期列表
        
        Args:
            coin_type: 币种类型，'BTC' 或 'ETH'，默认 'BTC'
        
        Returns:
            set: 已存在的日期集合
        """
        if not self.connection:
            if not self.connect():
                return set()
        
        cursor = self.connection.cursor()
        try:
            if coin_type == 'ETH':
                sql = "SELECT date FROM ethereum_etf_daily"
            elif coin_type == 'SOL':
                sql = "SELECT date FROM solana_etf_daily"
            else:
                sql = "SELECT date FROM bitcoin_etf_daily"
            cursor.execute(sql)
            results = cursor.fetchall()
            dates = {str(row[0]) for row in results}
            logging.info(f"数据库中{coin_type}已存在 {len(dates)} 条日期记录")
            return dates
        except Exception as e:
            logging.error(f"查询已存在日期失败: {e}")
            return set()
        finally:
            cursor.close()
    
    def save_daily_data(self, date_str, etf_data, coin_type='BTC'):
        """
        保存每日数据
        
        Args:
            date_str: 日期字符串，格式 'YYYY-MM-DD'
            etf_data: ETF数据字典，包含各机构的净流入流出数据
            coin_type: 币种类型，'BTC' 或 'ETH'，默认 'BTC'
        """
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 将日期字符串转换为DATE类型
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            except:
                # 如果日期格式不对，尝试其他格式
                date_obj = datetime.strptime(date_str.split()[0], '%Y-%m-%d').date()
            
            # 根据币种类型选择不同的表名和机构列表
            if coin_type == 'ETH':
                table_name = 'ethereum_etf_daily'
                institutions = ['ETHE', 'ETH', 'ETHA', 'ETHW', 'FETH', 'ETHV', 'EZET', 'TETH', 'QETH']
            elif coin_type == 'SOL':
                table_name = 'solana_etf_daily'
                institutions = ['BSOL', 'GSOL', 'VSOL', 'FSOL', 'TSOL']
            else:
                table_name = 'bitcoin_etf_daily'
                institutions = ['GBTC', 'IBIT', 'FBTC', 'ARKB', 'BITB', 'BTCO', 'HODL', 'BRRR', 'EZBC', 'BTCW', 'BTC']
            
            # 构建插入/更新SQL（数据库字段名是小写）
            columns = ['date'] + [inst.lower() for inst in institutions] + ['total']
            placeholders = ['%s'] * len(columns)
            values = [date_obj]
            
            # 填充机构数据（转换带"万"字的数字）
            for inst in institutions:
                if inst in etf_data:
                    original_value = etf_data[inst]['value']
                    converted_value = self.convert_wan_to_number(original_value)
                    values.append(converted_value)
                else:
                    values.append(None)
            
            # 填充总计数据（转换带"万"字的数字）
            if '总计' in etf_data:
                original_value = etf_data['总计']['value']
                converted_value = self.convert_wan_to_number(original_value)
                values.append(converted_value)
            else:
                values.append(None)
            
            # 使用INSERT ... ON DUPLICATE KEY UPDATE
            update_cols = ', '.join([f"{col} = VALUES({col})" for col in columns[1:]])
            sql = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON DUPLICATE KEY UPDATE {update_cols}
            """
            
            cursor.execute(sql, values)
            self.connection.commit()
            
            logging.info(f"{coin_type}每日数据保存成功: {date_str}")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存每日数据失败: {e}")
            return False
        finally:
            cursor.close()
    
    def save_total_data(self, date_str, etf_data, coin_type='BTC'):
        """
        保存总计数据（BTC和ETH共用）
        
        Args:
            date_str: 日期字符串，格式 'YYYY-MM-DD'
            etf_data: ETF数据字典，包含各机构的累计总计数据（通常只有"总计"行的数据）
            coin_type: 币种类型，'BTC' 或 'ETH'，默认 'BTC'
        """
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 将日期字符串转换为DATE类型
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            except:
                # 如果日期格式不对，尝试其他格式
                date_obj = datetime.strptime(date_str.split()[0], '%Y-%m-%d').date()
            
            # 根据币种类型选择不同的机构列表（不包括总计）
            if coin_type == 'ETH':
                institutions = ['ETHE', 'ETH', 'ETHA', 'ETHW', 'FETH', 'ETHV', 'EZET', 'TETH', 'QETH']
            elif coin_type == 'SOL':
                institutions = ['BSOL', 'GSOL', 'VSOL', 'FSOL', 'TSOL']
            else:
                institutions = ['GBTC', 'IBIT', 'FBTC', 'ARKB', 'BITB', 'BTCO', 'HODL', 'BRRR', 'EZBC', 'BTCW', 'BTC']
            
            # 先查询当前日期、当前币种已存在的所有记录
            check_sql = "SELECT institution, total_value, value_type FROM bitcoin_etf_total WHERE date = %s AND coin_type = %s"
            cursor.execute(check_sql, (date_obj, coin_type))
            existing_records = {row[0]: {'total_value': row[1], 'value_type': row[2]} for row in cursor.fetchall()}
            
            # 保存每个机构的累计总计（转换带"万"字的数字，并添加正负号）
            for inst in institutions:
                if inst in etf_data:
                    value_data = etf_data[inst]
                    original_value = value_data.get('value', None)
                    value_type = value_data.get('type', 'neutral')
                    
                    # 转换带"万"字的数字为字符串
                    value_str = self.convert_wan_to_number(original_value) if original_value else None
                    
                    # 处理正负号：净流入用+，净流出用-
                    final_value = None
                    if value_str:
                        try:
                            # 清理字符串
                            cleaned_value = str(value_str).strip().replace(',', '')
                            
                            # 提取符号和数字部分
                            is_negative = cleaned_value.startswith('-')
                            if cleaned_value.startswith('+') or cleaned_value.startswith('-'):
                                cleaned_value = cleaned_value[1:]
                            
                            # 转换为数字
                            number = float(cleaned_value)
                            
                            # 如果原始值是负数，number应该是负数
                            if is_negative:
                                number = -number
                            
                            # 根据value_type来确定最终保存的格式
                            # value_type优先级：rise表示净流入（+），fall表示净流出（-）
                            if value_type == 'rise':
                                # 净流入，使用+号（确保是正数）
                                final_value = f"+{abs(number)}"
                            elif value_type == 'fall':
                                # 净流出，使用-号（确保是负数）
                                final_value = f"-{abs(number)}"
                            else:
                                # neutral，根据数值本身的正负
                                if number > 0:
                                    final_value = f"+{number}"
                                elif number < 0:
                                    final_value = str(number)  # 负数本身就有-号
                                else:
                                    final_value = "0"
                            
                            # 如果是整数，去掉小数点
                            if '.' in final_value:
                                try:
                                    # 提取数字部分（去掉+或-号）
                                    num_str = final_value.lstrip('+-')
                                    num_val = float(num_str)
                                    if num_val == int(num_val):
                                        # 如果是整数，去掉.0
                                        int_str = str(int(num_val))
                                        # 保留符号
                                        if final_value.startswith('+'):
                                            final_value = f"+{int_str}"
                                        elif final_value.startswith('-'):
                                            final_value = f"-{int_str}"
                                        else:
                                            final_value = int_str
                                except:
                                    pass
                                    
                        except (ValueError, TypeError) as e:
                            logging.warning(f"无法处理数值: {value_str}, 错误: {e}")
                            final_value = value_str  # 转换失败时使用原值
                    
                    # 检查是否存在，存在则比较数据，不一致才更新；不存在才插入
                    if inst in existing_records:
                        # 记录已存在，比较数据是否一致
                        existing_record = existing_records[inst]
                        existing_value = existing_record.get('total_value')
                        existing_type = existing_record.get('value_type')
                        
                        # 比较数据是否一致（处理 None 的情况）
                        existing_value_str = str(existing_value) if existing_value is not None else 'None'
                        final_value_str = str(final_value) if final_value is not None else 'None'
                        
                        if existing_value_str == final_value_str and existing_type == value_type:
                            # 数据一致，跳过
                            logging.debug(f"机构 {inst} 在 {date_str} 的数据未变化，跳过更新")
                            continue
                        else:
                            # 数据不一致，执行更新
                            update_sql = """
                            UPDATE bitcoin_etf_total 
                            SET total_value = %s, value_type = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE date = %s AND coin_type = %s AND institution = %s
                            """
                            cursor.execute(update_sql, (final_value, value_type, date_obj, coin_type, inst))
                            logging.info(f"更新{coin_type}机构 {inst} 在 {date_str} 的数据: {existing_value} -> {final_value}")
                    else:
                        # 记录不存在，执行插入
                        insert_sql = """
                        INSERT INTO bitcoin_etf_total (date, coin_type, institution, total_value, value_type)
                        VALUES (%s, %s, %s, %s, %s)
                        """
                        cursor.execute(insert_sql, (date_obj, coin_type, inst, final_value, value_type))
                        logging.info(f"插入{coin_type}机构 {inst} 在 {date_str} 的新数据: {final_value}")
            
            self.connection.commit()
            logging.info(f"总计数据保存成功: {date_str}")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存总计数据失败: {e}")
            return False
        finally:
            cursor.close()

