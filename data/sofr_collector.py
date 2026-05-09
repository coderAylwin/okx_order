#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOFR数据收集服务
1. 从XML文件导入历史数据
2. 定时从API获取最新数据
"""

import os
import sys
import xml.etree.ElementTree as ET
import requests
import json
import pymysql
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
import apscheduler.events
import traceback

# 飞书Webhook地址
LARK_WEBHOOK_URL = "https://open.larksuite.com/open-apis/bot/v2/hook/b5745320-444f-43b8-a09e-dee2a62f7731"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class SOFRDatabaseService:
    """SOFR数据数据库服务类"""
    
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
        """创建SOFR数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            create_table = """
            CREATE TABLE IF NOT EXISTS sofr_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                effective_date DATE NOT NULL COMMENT '生效日期',
                ref_rate_type VARCHAR(20) DEFAULT 'SOFR' COMMENT '参考利率类型',
                daily_rate DECIMAL(10, 4) NOT NULL COMMENT '日利率（%）',
                rate_percentile_1st DECIMAL(10, 4) DEFAULT NULL COMMENT '1%分位数',
                rate_percentile_25th DECIMAL(10, 4) DEFAULT NULL COMMENT '25%分位数',
                rate_percentile_75th DECIMAL(10, 4) DEFAULT NULL COMMENT '75%分位数',
                rate_percentile_99th DECIMAL(10, 4) DEFAULT NULL COMMENT '99%分位数',
                trading_volume INT DEFAULT NULL COMMENT '交易量（十亿美元）',
                revision_indicator BOOLEAN DEFAULT FALSE COMMENT '修订标识',
                business_id VARCHAR(50) DEFAULT NULL COMMENT '业务ID',
                post_id VARCHAR(100) DEFAULT NULL COMMENT '发布ID',
                post_dt DATE DEFAULT NULL COMMENT '发布日期',
                insert_ts DATETIME DEFAULT NULL COMMENT '插入时间戳',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_effective_date (effective_date),
                INDEX idx_effective_date (effective_date),
                INDEX idx_post_dt (post_dt)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SOFR利率数据表';
            """
            
            cursor.execute(create_table)
            self.connection.commit()
            logging.info("SOFR数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def check_date_exists(self, effective_date, show_query_log=False):
        """检查指定日期是否存在，并返回详细信息"""
        if not self.connection:
            if not self.connect():
                return False, None
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception:
            if not self.connect():
                return False, None
        
        cursor = self.connection.cursor()
        try:
            # 显示详细的查询信息
            # if show_query_log:
            #     logging.info(f"  🔍 正在查询数据库:")
            #     logging.info(f"     - 数据库: {self.get_db_info()}")
            #     logging.info(f"     - 表名: sofr_data")
            #     logging.info(f"     - 查询日期: {effective_date} (类型: {type(effective_date).__name__})")
            #     logging.info(f"     - SQL: SELECT * FROM sofr_data WHERE effective_date = %s")
            
            sql = "SELECT id, effective_date, daily_rate, business_id, created_at, updated_at FROM sofr_data WHERE effective_date = %s"
            cursor.execute(sql, (effective_date,))
            result = cursor.fetchone()
            
            # 如果找到了，检查是否有重复记录，并显示完整信息
            if result and show_query_log:
                # 查询所有匹配的记录（检查是否有重复）
                cursor.execute(sql, (effective_date,))
                all_results = cursor.fetchall()
                if len(all_results) > 1:
                    # logging.warning(f"  ⚠️ 发现多条记录！共 {len(all_results)} 条:")
                    for idx, rec in enumerate(all_results, 1):
                        logging.warning(f"     [{idx}] ID={rec[0]}, 日期={rec[1]}, 利率={rec[2]}%, business_id={rec[3]}, 创建时间={rec[4]}")
                else:
                    # logging.info(f"  ✅ 数据库查询结果: 找到记录")
                    # # 显示完整的记录信息用于对比
                    # logging.info(f"  📋 完整记录信息:")
                    # logging.info(f"     - ID: {result[0]}")
                    # logging.info(f"     - effective_date: {result[1]} (类型: {type(result[1]).__name__})")
                    # logging.info(f"     - daily_rate: {result[2]}")
                    # logging.info(f"     - business_id: {result[3]}")
                    # logging.info(f"     - created_at: {result[4]}")
                    # logging.info(f"     - updated_at: {result[5]}")
                    # 执行原始SQL查询用于对比
                    date_str = effective_date.strftime('%Y-%m-%d')
                    # logging.info(f"  🔍 原始SQL查询: SELECT * FROM sofr_data WHERE effective_date = '{date_str}'")
                    # logging.info(f"  💡 提示: 请在数据库中执行上述SQL确认记录是否存在")
            
            # 如果没找到，尝试用字符串格式查询（用于调试）
            if not result and show_query_log:
                date_str = effective_date.strftime('%Y-%m-%d')
                # logging.info(f"  ⚠️ 使用日期对象查询未找到，尝试使用字符串格式查询: '{date_str}'")
                cursor.execute("SELECT id, effective_date, daily_rate, business_id, created_at, updated_at FROM sofr_data WHERE effective_date = %s", (date_str,))
                result_str = cursor.fetchone()
                if result_str:
                    # logging.warning(f"  ⚠️ 使用字符串格式查询找到了记录！ID={result_str[0]}, 日期={result_str[1]}")
                    result = result_str
            
            # 如果还是没找到，查询所有最近的记录用于调试
            if not result and show_query_log:
                # logging.info(f"  🔍 查询最近的10条记录用于调试:")
                cursor.execute("SELECT id, effective_date, daily_rate, business_id FROM sofr_data ORDER BY effective_date DESC LIMIT 10")
                recent = cursor.fetchall()
                for rec in recent:
                    logging.info(f"     - ID={rec[0]}, 日期={rec[1]} (类型: {type(rec[1]).__name__}), 利率={rec[2]}%, business_id={rec[3]}")
            
            if show_query_log and not result:
                logging.info(f"  ❌ 数据库查询结果: 未找到记录")
            
            if result:
                return True, {
                    'id': result[0],
                    'effective_date': result[1],
                    'daily_rate': result[2],
                    'business_id': result[3],
                    'created_at': result[4],
                    'updated_at': result[5]
                }
            return False, None
        except Exception as e:
            logging.error(f"查询日期是否存在失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False, None
        finally:
            cursor.close()
    
    def get_db_info(self):
        """获取数据库连接信息"""
        return f"{self.host}:{self.port}/{self.database}"
    
    def get_previous_date_data(self, effective_date):
        """获取上一日的数据"""
        if not self.connection:
            if not self.connect():
                return None
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception:
            if not self.connect():
                return None
        
        cursor = self.connection.cursor()
        try:
            sql = """
            SELECT effective_date, daily_rate, rate_percentile_1st, rate_percentile_25th,
                   rate_percentile_75th, rate_percentile_99th, trading_volume
            FROM sofr_data 
            WHERE effective_date < %s 
            ORDER BY effective_date DESC 
            LIMIT 1
            """
            cursor.execute(sql, (effective_date,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'effective_date': result[0],
                    'daily_rate': result[1],
                    'rate_percentile_1st': result[2],
                    'rate_percentile_25th': result[3],
                    'rate_percentile_75th': result[4],
                    'rate_percentile_99th': result[5],
                    'trading_volume': result[6]
                }
            return None
        except Exception as e:
            logging.error(f"查询上一日数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return None
        finally:
            cursor.close()
    
    def save_sofr_data(self, effective_date, daily_rate, rate_percentile_1st=None,
                       rate_percentile_25th=None, rate_percentile_75th=None,
                       rate_percentile_99th=None, trading_volume=None,
                       revision_indicator=False, business_id=None, post_id=None,
                       post_dt=None, insert_ts=None):
        """保存SOFR数据"""
        if not self.connection:
            if not self.connect():
                return False
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            sql = """
            INSERT INTO sofr_data 
            (effective_date, ref_rate_type, daily_rate, rate_percentile_1st,
             rate_percentile_25th, rate_percentile_75th, rate_percentile_99th,
             trading_volume, revision_indicator, business_id, post_id, post_dt, insert_ts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                daily_rate = VALUES(daily_rate),
                rate_percentile_1st = VALUES(rate_percentile_1st),
                rate_percentile_25th = VALUES(rate_percentile_25th),
                rate_percentile_75th = VALUES(rate_percentile_75th),
                rate_percentile_99th = VALUES(rate_percentile_99th),
                trading_volume = VALUES(trading_volume),
                revision_indicator = VALUES(revision_indicator),
                business_id = VALUES(business_id),
                post_id = VALUES(post_id),
                post_dt = VALUES(post_dt),
                insert_ts = VALUES(insert_ts),
                updated_at = CURRENT_TIMESTAMP
            """
            cursor.execute(sql, (
                effective_date, 'SOFR', daily_rate, rate_percentile_1st,
                rate_percentile_25th, rate_percentile_75th, rate_percentile_99th,
                trading_volume, revision_indicator, business_id, post_id, post_dt, insert_ts
            ))
            affected_rows = cursor.rowcount
            self.connection.commit()
            
            if affected_rows == 1:
                logging.info(f"SOFR数据插入成功: {effective_date}")
            elif affected_rows == 2:
                logging.info(f"SOFR数据更新成功: {effective_date}")
            else:
                logging.warning(f"SOFR数据保存，影响行数: {affected_rows}, 日期: {effective_date}")
            return True
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存SOFR数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()


# 初始化数据库服务
db_config = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'port': 3306,
    'user': 'quantify_read_write',
    'password': '02Ya6fPDo@w67UI%sEaDvPXfT',
    'database': 'quantify'
}

sofr_db = SOFRDatabaseService(**db_config)


def parse_xml_and_save():
    """解析XML文件并保存历史数据"""
    xml_file_path = os.path.join(os.path.dirname(__file__), 'sofr.xml')
    
    if not os.path.exists(xml_file_path):
        logging.error(f"XML文件不存在: {xml_file_path}")
        return False
    
    logging.info(f"开始解析XML文件: {xml_file_path}")
    
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        
        # 获取所有rate节点
        rates = root.findall('.//rate')
        logging.info(f"找到 {len(rates)} 条历史数据")
        
        # 解析数据并存储到列表
        data_list = []
        for rate in rates:
            try:
                effective_date_str = rate.find('effectiveDate').text
                daily_rate = float(rate.find('percentRate').text)
                
                # 解析可选字段
                percentile_1 = rate.find('percentPercentile1')
                percentile_1_val = float(percentile_1.text) if percentile_1 is not None and percentile_1.text else None
                
                percentile_25 = rate.find('percentPercentile25')
                percentile_25_val = float(percentile_25.text) if percentile_25 is not None and percentile_25.text else None
                
                percentile_75 = rate.find('percentPercentile75')
                percentile_75_val = float(percentile_75.text) if percentile_75 is not None and percentile_75.text else None
                
                percentile_99 = rate.find('percentPercentile99')
                percentile_99_val = float(percentile_99.text) if percentile_99 is not None and percentile_99.text else None
                
                volume = rate.find('volumeInBillions')
                volume_val = int(volume.text) if volume is not None and volume.text else None
                
                revision = rate.find('revisionIndicator')
                revision_val = revision.text.strip().lower() == 'true' if revision is not None and revision.text else False
                
                data_list.append({
                    'effective_date': effective_date_str,
                    'daily_rate': daily_rate,
                    'rate_percentile_1st': percentile_1_val,
                    'rate_percentile_25th': percentile_25_val,
                    'rate_percentile_75th': percentile_75_val,
                    'rate_percentile_99th': percentile_99_val,
                    'trading_volume': volume_val,
                    'revision_indicator': revision_val
                })
            except Exception as e:
                logging.warning(f"解析rate节点失败: {e}")
                continue
        
        # 按日期排序（早的在前面）
        data_list.sort(key=lambda x: x['effective_date'])
        
        logging.info(f"成功解析 {len(data_list)} 条数据，开始保存到数据库...")
        logging.info("注意：每条数据都会实时查询数据库检查是否存在，不使用缓存")
        
        # 保存数据（每条数据都实时查询数据库）
        saved_count = 0
        skipped_count = 0
        for data in data_list:
            effective_date = datetime.strptime(data['effective_date'], '%Y-%m-%d').date()
            
            # 实时查询数据库检查是否已存在（不使用缓存）
            exists, db_record = sofr_db.check_date_exists(effective_date, show_query_log=False)
            if exists:
                skipped_count += 1
                logging.debug(f"数据已存在，跳过: {effective_date} (ID: {db_record['id']})")
                continue
            
            # 数据不存在，保存
            if sofr_db.save_sofr_data(
                effective_date=effective_date,
                daily_rate=data['daily_rate'],
                rate_percentile_1st=data['rate_percentile_1st'],
                rate_percentile_25th=data['rate_percentile_25th'],
                rate_percentile_75th=data['rate_percentile_75th'],
                rate_percentile_99th=data['rate_percentile_99th'],
                trading_volume=data['trading_volume'],
                revision_indicator=data['revision_indicator']
            ):
                saved_count += 1
            else:
                logging.warning(f"保存数据失败: {effective_date}")
        
        logging.info(f"XML数据导入完成: 新增 {saved_count} 条，跳过 {skipped_count} 条")
        return True
        
    except Exception as e:
        logging.error(f"解析XML文件失败: {e}")
        logging.error(f"异常详情: {traceback.format_exc()}")
        return False


def send_lark_notification(effective_date, daily_rate, data_json, item):
    """
    发送飞书消息通知
    
    Args:
        effective_date: 生效日期
        daily_rate: 日利率
        data_json: API返回的数据JSON
        item: API返回的原始item
    """
    try:
        # 构建消息内容
        rate_percentile_1st = data_json.get('ratePercentile1st')
        rate_percentile_25th = data_json.get('ratePercentile25th')
        rate_percentile_75th = data_json.get('ratePercentile75th')
        rate_percentile_99th = data_json.get('ratePercentile99th')
        trading_volume = data_json.get('tradingVolume')
        business_id = item.get('businessId')
        
        # 查询上一日的数据
        prev_data = sofr_db.get_previous_date_data(effective_date)
        
        # 格式化日利率（带前值）
        daily_rate_display = f"{daily_rate}%"
        if prev_data and prev_data['daily_rate'] is not None:
            prev_rate = float(prev_data['daily_rate'])
            daily_rate_display = f"{daily_rate}%（前值：{prev_rate:.2f}%）"
        
        # 格式化分位数（带前值）
        def format_percentile(current, prev_value, field_name):
            if current is not None:
                if prev_value is not None:
                    prev_val = float(prev_value)
                    return f"{current}%（前值：{prev_val:.2f}%）"
                return f"{current}%"
            return 'N/A'
        
        percentile_1st_display = format_percentile(
            rate_percentile_1st, 
            prev_data['rate_percentile_1st'] if prev_data else None,
            'rate_percentile_1st'
        )
        percentile_25th_display = format_percentile(
            rate_percentile_25th,
            prev_data['rate_percentile_25th'] if prev_data else None,
            'rate_percentile_25th'
        )
        percentile_75th_display = format_percentile(
            rate_percentile_75th,
            prev_data['rate_percentile_75th'] if prev_data else None,
            'rate_percentile_75th'
        )
        percentile_99th_display = format_percentile(
            rate_percentile_99th,
            prev_data['rate_percentile_99th'] if prev_data else None,
            'rate_percentile_99th'
        )
        
        # 格式化交易量（带前值）
        trading_volume_display = 'N/A'
        if trading_volume is not None:
            trading_volume_trillion = trading_volume / 1000.0
            if prev_data and prev_data['trading_volume'] is not None:
                prev_volume_trillion = prev_data['trading_volume'] / 1000.0
                trading_volume_display = f"{trading_volume_trillion:.2f}（前值：{prev_volume_trillion:.2f}）万亿美元"
            else:
                trading_volume_display = f"{trading_volume_trillion:.2f} 万亿美元"
        
        # 构建文本消息
        content_text = f"""📊 SOFR新数据通知

📅 生效日期: {effective_date}
💰 日利率: {daily_rate_display}
📈 分位数:
  • 1%分位数: {percentile_1st_display}
  • 25%分位数: {percentile_25th_display}
  • 75%分位数: {percentile_75th_display}
  • 99%分位数: {percentile_99th_display}
📊 交易量: {trading_volume_display}
⏰ 通知时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔗 参考地址: https://www.newyorkfed.org/markets/reference-rates/sofr
"""
        
        # 飞书Webhook消息格式
        payload = {
            "msg_type": "text",
            "content": {
                "text": content_text
            }
        }
        
        response = requests.post(LARK_WEBHOOK_URL, json=payload, timeout=5)
        response.raise_for_status()
        
        result = response.json()
        if result.get('code') == 0:
            logging.info(f"✅ 飞书消息推送成功: {effective_date}")
        else:
            logging.warning(f"⚠️ 飞书消息推送返回异常: {result}")
            
    except requests.exceptions.RequestException as e:
        logging.error(f"飞书消息推送失败（网络错误）: {e}")
    except Exception as e:
        logging.error(f"飞书消息推送失败: {e}")
        logging.error(f"异常详情: {traceback.format_exc()}")


def fetch_latest_sofr_data():
    """从API获取最新的SOFR数据"""
    # 计算日期范围：最近7天
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    
    url = "https://markets.newyorkfed.org/read"
    params = {
        'startDt': start_date.strftime('%Y-%m-%d'),
        'endDt': end_date.strftime('%Y-%m-%d'),
        'eventCodes': 520,
        'productCode': 50,
        'sort': 'postDt:-1,eventCode:1',
        'limit': 100,
        'startPosition': 0
    }
    
    # logging.info(f"开始从API获取SOFR数据: {start_date} 至 {end_date}")
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if 'data' not in data or not data['data']:
            logging.info("API返回数据为空")
            return True
        
        logging.info(f"API返回 {len(data['data'])} 条数据")
        
        # 先解析所有数据，并按日期排序（早的在前面）
        parsed_data_list = []
        for item in data['data']:
            try:
                # 解析data字段（JSON字符串）
                data_json = json.loads(item['data'])
                
                ref_rate_dt_str = data_json.get('refRateDt')
                if not ref_rate_dt_str:
                    logging.warning(f"缺少refRateDt字段，跳过: {item.get('businessId')}")
                    continue
                
                effective_date = datetime.strptime(ref_rate_dt_str, '%Y-%m-%d').date()
                
                # 解析insert_ts（API返回的是UTC时间，需要转换为UTC+8）
                insert_ts_str = item.get('insertTs')
                insert_ts = None
                if insert_ts_str:
                    try:
                        # 解析为UTC时间（API返回的格式没有时区信息，默认为UTC）
                        dt_utc = datetime.strptime(insert_ts_str, '%Y-%m-%dT%H:%M:%S.%f')
                        dt_utc = dt_utc.replace(tzinfo=ZoneInfo('UTC'))
                        # 转换为UTC+8时间
                        dt_utc8 = dt_utc.astimezone(ZoneInfo('Asia/Shanghai'))
                        # 移除时区信息（数据库存储无时区的datetime）
                        insert_ts = dt_utc8.replace(tzinfo=None)
                        logging.debug(f"insertTs转换: {insert_ts_str} (UTC) -> {insert_ts} (UTC+8)")
                    except:
                        try:
                            # 尝试不带毫秒的格式
                            dt_utc = datetime.strptime(insert_ts_str, '%Y-%m-%dT%H:%M:%S')
                            dt_utc = dt_utc.replace(tzinfo=ZoneInfo('UTC'))
                            dt_utc8 = dt_utc.astimezone(ZoneInfo('Asia/Shanghai'))
                            insert_ts = dt_utc8.replace(tzinfo=None)
                            logging.debug(f"insertTs转换: {insert_ts_str} (UTC) -> {insert_ts} (UTC+8)")
                        except Exception as e:
                            logging.warning(f"解析insertTs失败: {insert_ts_str}, 错误: {e}")
                            pass
                
                # 解析post_dt
                post_dt_str = item.get('postDt')
                post_dt = None
                if post_dt_str:
                    try:
                        post_dt = datetime.strptime(post_dt_str, '%Y-%m-%d').date()
                    except:
                        pass
                
                parsed_data_list.append({
                    'effective_date': effective_date,
                    'data_json': data_json,
                    'item': item,
                    'insert_ts': insert_ts,
                    'post_dt': post_dt
                })
            except Exception as e:
                logging.error(f"解析API数据项失败: {e}")
                logging.error(f"数据项: {item.get('businessId', 'unknown')}")
                logging.error(f"异常详情: {traceback.format_exc()}")
                continue
        
        # 按日期排序（早的在前面）
        parsed_data_list.sort(key=lambda x: x['effective_date'])
        
        # 显示日期范围
        if parsed_data_list:
            dates = [d['effective_date'] for d in parsed_data_list]
            logging.info(f"解析后的日期范围: {dates[0]} 至 {dates[-1]} (共{len(dates)}条，已按时间顺序排序)")
        
        # 按时间顺序保存数据
        saved_count = 0
        skipped_count = 0
        
        for parsed_data in parsed_data_list:
            effective_date = parsed_data['effective_date']
            data_json = parsed_data['data_json']
            item = parsed_data['item']
            insert_ts = parsed_data['insert_ts']
            post_dt = parsed_data['post_dt']
            
            try:
                # 实时查询数据库检查是否已存在（不依赖缓存集合）
                # logging.info(f"检查日期: {effective_date} (businessId: {item.get('businessId')})")
                exists, db_record = sofr_db.check_date_exists(effective_date, show_query_log=True)
                if exists:
                    skipped_count += 1
                    db_info = sofr_db.get_db_info()
                    # logging.info(f"  ⚠️ 数据已存在，跳过: {effective_date}")
                    # logging.info(f"  └─ 数据库: {db_info} | 记录ID: {db_record['id']} | 利率: {db_record['daily_rate']}% | 创建时间: {db_record['created_at']} | 更新时间: {db_record['updated_at']}")
                    # logging.info(f"  └─ 提示: 如果确认数据库中不存在此数据，可能是删除后定时任务又自动插入了")
                    continue
                
                # 数据不存在，准备保存
                logging.info(f"✅ 发现新数据: {effective_date} (businessId: {item.get('businessId')})")
                
                # 保存数据
                if sofr_db.save_sofr_data(
                    effective_date=effective_date,
                    daily_rate=data_json.get('dailyRate'),
                    rate_percentile_1st=data_json.get('ratePercentile1st'),
                    rate_percentile_25th=data_json.get('ratePercentile25th'),
                    rate_percentile_75th=data_json.get('ratePercentile75th'),
                    rate_percentile_99th=data_json.get('ratePercentile99th'),
                    trading_volume=data_json.get('tradingVolume'),
                    revision_indicator=data_json.get('revisionIndicator', False),
                    business_id=item.get('businessId'),
                    post_id=item.get('postId'),
                    post_dt=post_dt,
                    insert_ts=insert_ts
                ):
                    saved_count += 1
                    logging.info(f"✅ 保存新数据: {effective_date} - {data_json.get('dailyRate')}%")
                    
                    # 发送飞书通知
                    send_lark_notification(
                        effective_date=effective_date,
                        daily_rate=data_json.get('dailyRate'),
                        data_json=data_json,
                        item=item
                    )
                else:
                    logging.warning(f"保存数据失败: {effective_date}")
                    
            except Exception as e:
                logging.error(f"处理API数据项失败: {e}")
                logging.error(f"数据项: {item.get('businessId', 'unknown')}")
                logging.error(f"异常详情: {traceback.format_exc()}")
                continue
        
        logging.info(f"API数据获取完成: 新增 {saved_count} 条，跳过 {skipped_count} 条")
        return True
        
    except requests.exceptions.RequestException as e:
        logging.error(f"API请求失败: {e}")
        return False
    except Exception as e:
        logging.error(f"获取API数据失败: {e}")
        logging.error(f"异常详情: {traceback.format_exc()}")
        return False


# ==================== 测试函数 ====================
def test_query_date(test_date_str):
    """测试查询指定日期（用于调试）"""
    logging.info("=" * 50)
    logging.info(f"测试查询日期: {test_date_str}")
    logging.info("=" * 50)
    
    if not sofr_db.connect():
        logging.error("数据库连接失败")
        return
    
    try:
        test_date = datetime.strptime(test_date_str, '%Y-%m-%d').date()
        logging.info(f"转换后的日期对象: {test_date} (类型: {type(test_date).__name__})")
        
        exists, record = sofr_db.check_date_exists(test_date, show_query_log=True)
        
        if exists:
            logging.info(f"✅ 找到记录: {record}")
        else:
            logging.info(f"❌ 未找到记录")
            
            # 查询所有记录看看
            cursor = sofr_db.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM sofr_data")
            total = cursor.fetchone()[0]
            logging.info(f"数据库中总记录数: {total}")
            
            cursor.execute("SELECT effective_date FROM sofr_data ORDER BY effective_date DESC LIMIT 10")
            recent_dates = cursor.fetchall()
            logging.info(f"最近的10个日期:")
            for d in recent_dates:
                logging.info(f"  - {d[0]} (类型: {type(d[0]).__name__})")
            cursor.close()
    except Exception as e:
        logging.error(f"测试失败: {e}")
        logging.error(f"异常详情: {traceback.format_exc()}")
    finally:
        sofr_db.disconnect()


# ==================== 主程序 ====================
if __name__ == "__main__":
    # 检查命令行参数 - 查询测试模式
    if '--query' in sys.argv:
        if len(sys.argv) >= 3:
            test_date_str = sys.argv[2]
            test_query_date(test_date_str)
        else:
            print("用法: python3 sofr_collector.py --query 2026-02-03")
        exit(0)
    
    # 检查命令行参数 - 测试模式
    test_mode = '--test' in sys.argv or '-t' in sys.argv
    
    logging.info("SOFR数据收集服务启动")
    logging.info(f"数据库连接信息: {sofr_db.get_db_info()}")
    
    if test_mode:
        logging.info("=" * 50)
        logging.info("测试模式：只执行一次API数据获取，不启动定时任务")
        logging.info("=" * 50)
    
    # 初始化数据库表
    try:
        if sofr_db.connect():
            sofr_db.create_tables()
        logging.info("数据库表初始化完成")
        
        # 显示数据库中最近的几条记录用于确认
        try:
            cursor = sofr_db.connection.cursor()
            cursor.execute("SELECT effective_date, daily_rate, business_id, created_at FROM sofr_data ORDER BY effective_date DESC LIMIT 5")
            recent_records = cursor.fetchall()
            if recent_records:
                logging.info("数据库中最近的5条记录:")
                for record in recent_records:
                    logging.info(f"  - {record[0]} | 利率: {record[1]}% | business_id: {record[2]} | 创建时间: {record[3]}")
            cursor.close()
        except Exception as e:
            logging.debug(f"查询最近记录失败（不影响运行）: {e}")
    except Exception as e:
        logging.error(f"数据库初始化失败: {e}")
        exit(1)
    
    # 先导入XML历史数据（仅在非测试模式下）
    # if not test_mode:
    #     logging.info("=" * 50)
    #     logging.info("步骤1: 导入XML历史数据")
    #     logging.info("=" * 50)
    #     try:
    #         parse_xml_and_save()
    #     except Exception as e:
    #         logging.error(f"导入XML历史数据失败: {e}")
    #         logging.error(f"异常详情: {traceback.format_exc()}")
    
    # 立即执行一次API获取（获取最新数据）
    logging.info("=" * 50)
    logging.info("步骤2: 获取最新API数据")
    logging.info("=" * 50)
    try:
        fetch_latest_sofr_data()
    except Exception as e:
        logging.error(f"获取最新API数据失败: {e}")
        logging.error(f"异常详情: {traceback.format_exc()}")
    
    # 如果是测试模式，执行完就退出
    if test_mode:
        logging.info("=" * 50)
        logging.info("测试模式执行完成，退出")
        logging.info("=" * 50)
        logging.info("提示：删除数据后，运行 'python3 sofr_collector.py --test' 可以立即测试是否能自动补齐")
        sofr_db.disconnect()
        exit(0)
    
    # 创建调度器，每5分钟执行一次
    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    
    scheduler.add_job(
        fetch_latest_sofr_data,
        trigger='interval',
        minutes=5,
        id='fetch_latest_sofr_data',
        name='获取最新SOFR数据',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300
    )
    
    # 添加任务执行监听器
    def job_listener(event):
        if event.exception:
            logging.error(f"任务执行失败: {event.job_id} - {event.exception}")
        else:
            logging.debug(f"任务执行成功: {event.job_id}")
    
    scheduler.add_listener(job_listener, apscheduler.events.EVENT_JOB_EXECUTED | apscheduler.events.EVENT_JOB_ERROR)
    
    logging.info("SOFR数据收集服务启动，每5分钟执行一次")
    logging.info("按 Ctrl+C 停止服务")
    logging.info("提示：")
    logging.info("  - 运行 'python3 sofr_collector.py --test' 可以立即测试数据补齐功能")
    logging.info("  - 运行 'python3 sofr_collector.py --query 2026-02-03' 可以测试查询指定日期")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("服务已停止")
        sofr_db.disconnect()

