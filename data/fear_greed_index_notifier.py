#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
恐慌指数数据提醒服务
在整点后1分钟（如17:01、18:01）获取恐慌指数数据
对比当前和上一小时的数据，如果crypto_fear_greed_value或vix_value发生变化则发送通知
"""

import sys
import pymysql
import requests
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.blocking import BlockingScheduler
import apscheduler.events
import traceback

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 数据库配置
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'port': 3306,
    'user': 'payment_pro',
    'password': 'nS4kO7tG1jH7cI6oR4b',
    'database': 'quantify'
}

# 飞书Webhook地址
LARK_WEBHOOK_URL = "https://open.larksuite.com/open-apis/bot/v2/hook/8fb1eee3-5ad1-457a-88e1-3324fedadb67"


class FearGreedIndexNotifier:
    """恐慌指数数据提醒服务"""
    
    def __init__(self, db_config):
        self.db_config = db_config
        self.connection = None
    
    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database'],
                charset='utf8mb4'
            )
            return True
        except Exception as e:
            logging.error(f"数据库连接失败: {e}")
            return False
    
    def disconnect(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def get_fear_greed_at_time(self, target_time):
        """
        获取指定时间点的恐慌指数数据（整点数据）
        
        Args:
            target_time: 目标时间（datetime对象，应该是整点）
        
        Returns:
            dict: 恐慌指数数据字典，如果未找到返回None
        """
        if not self.connection:
            if not self.connect():
                return None
        
        try:
            self.connection.ping(reconnect=True)
        except Exception:
            if not self.connect():
                return None
        
        cursor = self.connection.cursor()
        try:
            # 查询指定时间点的数据（整点数据）
            sql = """
            SELECT ts, crypto_fear_greed_value, crypto_fear_greed_classification, vix_value
            FROM macro_fear_greed_index
            WHERE ts = %s
            ORDER BY ts DESC
            LIMIT 1
            """
            cursor.execute(sql, (target_time,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'ts': result[0],
                    'crypto_fear_greed_value': int(result[1]) if result[1] is not None else None,
                    'crypto_fear_greed_classification': result[2] if result[2] else None,
                    'vix_value': float(result[3]) if result[3] is not None else None
                }
            return None
        except Exception as e:
            logging.error(f"查询恐慌指数数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return None
        finally:
            cursor.close()
    
    def get_latest_fear_greed(self, current_time):
        """
        获取当前、上一小时、上四小时、上一天的恐慌指数数据
        
        Args:
            current_time: 当前时间（datetime对象）
        
        Returns:
            dict: 包含各个时间点数据的字典
        """
        # 获取当前整点时间（如21:00）
        current_hour = current_time.replace(minute=0, second=0, microsecond=0)
        
        # 计算各个时间点
        one_hour_ago = current_hour - timedelta(hours=1)
        four_hours_ago = current_hour - timedelta(hours=4)
        one_day_ago = current_hour - timedelta(days=1)
        
        # 查询数据
        current_data = self.get_fear_greed_at_time(current_hour)
        one_hour_data = self.get_fear_greed_at_time(one_hour_ago)
        four_hours_data = self.get_fear_greed_at_time(four_hours_ago)
        one_day_data = self.get_fear_greed_at_time(one_day_ago)
        
        return {
            'current': current_data,
            'one_hour_ago': one_hour_data,
            'four_hours_ago': four_hours_data,
            'one_day_ago': one_day_data
        }
    
    def check_value_changed(self, current_data, one_hour_data):
        """
        检查值是否发生变化（与1小时前对比）
        
        Args:
            current_data: 当前数据
            one_hour_data: 上一小时数据
        
        Returns:
            bool: 如果任一值发生变化返回True，否则返回False
        """
        if not current_data or not one_hour_data:
            return False
        
        # 检查crypto_fear_greed_value是否变化
        crypto_changed = (
            current_data.get('crypto_fear_greed_value') is not None and
            one_hour_data.get('crypto_fear_greed_value') is not None and
            current_data['crypto_fear_greed_value'] != one_hour_data['crypto_fear_greed_value']
        )
        
        # 检查vix_value是否变化（允许小的浮点误差）
        vix_changed = False
        if (current_data.get('vix_value') is not None and
            one_hour_data.get('vix_value') is not None):
            vix_diff = abs(current_data['vix_value'] - one_hour_data['vix_value'])
            vix_changed = vix_diff >= 0.01  # 变化超过0.01认为有变化
        
        return crypto_changed or vix_changed
    
    def send_lark_notification(self, comparison_data, current_time):
        """
        发送飞书消息通知
        
        Args:
            comparison_data: 包含各个时间点数据的字典
            current_time: 当前时间
        """
        try:
            current_data = comparison_data['current']
            one_hour_data = comparison_data['one_hour_ago']
            four_hours_data = comparison_data['four_hours_ago']
            one_day_data = comparison_data['one_day_ago']
            
            if not current_data:
                logging.warning("当前数据不存在，跳过推送")
                return
            
            # 构建消息内容
            content_lines = [
                "📊 恐慌指数数据变化提醒",
                "",
                f"⏰ 数据时间: {current_data['ts'].strftime('%Y-%m-%d %H:%M:%S')}",
                "",
            ]
            
            # 加密货币恐慌指数
            current_crypto = current_data.get('crypto_fear_greed_value')
            current_crypto_class = current_data.get('crypto_fear_greed_classification', 'N/A')
            one_hour_crypto = one_hour_data.get('crypto_fear_greed_value') if one_hour_data else None
            four_hours_crypto = four_hours_data.get('crypto_fear_greed_value') if four_hours_data else None
            one_day_crypto = one_day_data.get('crypto_fear_greed_value') if one_day_data else None
            
            content_lines.append("🪙 加密货币恐慌指数 (Fear & Greed Index):")
            if current_crypto is not None:
                content_lines.append(f"  • 当前: {current_crypto} ({current_crypto_class})")
                
                if one_hour_crypto is not None:
                    change = current_crypto - one_hour_crypto
                    change_sign = "+" if change >= 0 else ""
                    content_lines.append(f"  • vs 1小时前: {one_hour_crypto} ({change_sign}{change})")
                
                if four_hours_crypto is not None:
                    change = current_crypto - four_hours_crypto
                    change_sign = "+" if change >= 0 else ""
                    content_lines.append(f"  • vs 4小时前: {four_hours_crypto} ({change_sign}{change})")
                
                if one_day_crypto is not None:
                    change = current_crypto - one_day_crypto
                    change_sign = "+" if change >= 0 else ""
                    content_lines.append(f"  • vs 1天前: {one_day_crypto} ({change_sign}{change})")
            else:
                content_lines.append("  • 当前: N/A")
            
            content_lines.append("")
            
            # VIX恐慌指数
            current_vix = current_data.get('vix_value')
            one_hour_vix = one_hour_data.get('vix_value') if one_hour_data else None
            four_hours_vix = four_hours_data.get('vix_value') if four_hours_data else None
            one_day_vix = one_day_data.get('vix_value') if one_day_data else None
            
            content_lines.append("📈 VIX恐慌指数:")
            if current_vix is not None:
                content_lines.append(f"  • 当前: {current_vix:.2f}")
                
                if one_hour_vix is not None:
                    change = current_vix - one_hour_vix
                    change_pct = (change / one_hour_vix * 100) if one_hour_vix != 0 else 0
                    change_sign = "+" if change >= 0 else ""
                    content_lines.append(f"  • vs 1小时前: {one_hour_vix:.2f} ({change_sign}{change:.2f}, {change_sign}{change_pct:.2f}%)")
                
                if four_hours_vix is not None:
                    change = current_vix - four_hours_vix
                    change_pct = (change / four_hours_vix * 100) if four_hours_vix != 0 else 0
                    change_sign = "+" if change >= 0 else ""
                    content_lines.append(f"  • vs 4小时前: {four_hours_vix:.2f} ({change_sign}{change:.2f}, {change_sign}{change_pct:.2f}%)")
                
                if one_day_vix is not None:
                    change = current_vix - one_day_vix
                    change_pct = (change / one_day_vix * 100) if one_day_vix != 0 else 0
                    change_sign = "+" if change >= 0 else ""
                    content_lines.append(f"  • vs 1天前: {one_day_vix:.2f} ({change_sign}{change:.2f}, {change_sign}{change_pct:.2f}%)")
            else:
                content_lines.append("  • 当前: N/A")
            
            content_lines.append("")
            content_lines.append(f"⏰ 通知时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            content_lines.append("📊 数据来源: OKX")
            
            content_text = "\n".join(content_lines)
            
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
                logging.info("✅ 飞书消息推送成功")
            else:
                logging.warning(f"⚠️ 飞书消息推送返回异常: {result}")
                
        except requests.exceptions.RequestException as e:
            logging.error(f"飞书消息推送失败（网络错误）: {e}")
        except Exception as e:
            logging.error(f"飞书消息推送失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")


# 初始化服务
notifier = FearGreedIndexNotifier(DB_CONFIG)


def check_and_notify_fear_greed():
    """检查恐慌指数数据变化并发送通知"""
    try:
        # 获取当前时间（整点后1分钟，比如17:01）
        now = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        
        logging.info(f"开始检查恐慌指数数据: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not notifier.connect():
            logging.error("数据库连接失败")
            return
        
        # 获取当前、上一小时、上四小时、上一天的数据
        comparison_data = notifier.get_latest_fear_greed(now)
        
        current_data = comparison_data['current']
        one_hour_data = comparison_data['one_hour_ago']
        
        # 检查是否有当前数据
        if not current_data:
            logging.warning("当前整点数据不存在，跳过")
            return
        
        # 详细记录当前值和上一小时的值
        current_crypto = current_data.get('crypto_fear_greed_value')
        current_vix = current_data.get('vix_value')
        one_hour_crypto = one_hour_data.get('crypto_fear_greed_value') if one_hour_data else None
        one_hour_vix = one_hour_data.get('vix_value') if one_hour_data else None
        
        logging.info(f"当前数据: crypto={current_crypto}, vix={current_vix}")
        if one_hour_data:
            logging.info(f"1小时前数据: crypto={one_hour_crypto}, vix={one_hour_vix}")
        else:
            logging.info("1小时前数据: 不存在")
        
        # 检查值是否发生变化（用于日志记录）
        if one_hour_data and notifier.check_value_changed(current_data, one_hour_data):
            logging.info("✅ 检测到恐慌指数数据变化")
        elif one_hour_data:
            logging.info("ℹ️ 恐慌指数数据未发生变化（与1小时前相同）")
        
        # 无论是否有变化，都发送通知
        logging.info("发送恐慌指数数据通知")
        notifier.send_lark_notification(comparison_data, now)
        
        logging.info("恐慌指数数据检查完成")
        
    except Exception as e:
        logging.error(f"检查恐慌指数数据失败: {e}")
        logging.error(f"异常详情: {traceback.format_exc()}")
    finally:
        notifier.disconnect()


# ==================== 主程序 ====================
if __name__ == "__main__":
    # 检查命令行参数
    test_mode = '--test' in sys.argv or '-t' in sys.argv
    
    logging.info("恐慌指数数据提醒服务启动")
    
    if test_mode:
        logging.info("=" * 50)
        logging.info("测试模式：每5分钟执行一次")
        logging.info("=" * 50)
    
    # 立即执行一次
    logging.info("立即执行一次数据检查...")
    check_and_notify_fear_greed()
    
    # 如果是测试模式，执行完就退出
    if test_mode and '--once' in sys.argv:
        logging.info("=" * 50)
        logging.info("测试模式（单次执行）完成，退出")
        logging.info("=" * 50)
        logging.info("提示：运行 'python3 fear_greed_index_notifier.py --test' 可以每5分钟检查一次")
        notifier.disconnect()
        exit(0)
    
    # 创建调度器
    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    
    if test_mode:
        # 测试模式：每5分钟执行一次
        scheduler.add_job(
            check_and_notify_fear_greed,
            trigger='interval',
            minutes=5,
            id='check_fear_greed_notify',
            name='检查恐慌指数数据变化并发送通知（测试模式）',
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        logging.info("测试模式：每5分钟执行一次")
    else:
        # 正常模式：每小时的1分执行（17:01, 18:01等）
        scheduler.add_job(
            check_and_notify_fear_greed,
            trigger='cron',
            minute=1,  # 每小时的第1分钟
            second=0,  # 整秒执行
            id='check_fear_greed_notify',
            name='检查恐慌指数数据变化并发送通知',
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        logging.info("正常模式：每小时1分执行一次（如17:01、18:01）")
    
    # 添加任务执行监听器
    def job_listener(event):
        if event.exception:
            logging.error(f"任务执行失败: {event.job_id} - {event.exception}")
        else:
            logging.debug(f"任务执行成功: {event.job_id}")
    
    scheduler.add_listener(job_listener, apscheduler.events.EVENT_JOB_EXECUTED | apscheduler.events.EVENT_JOB_ERROR)
    
    logging.info("按 Ctrl+C 停止服务")
    logging.info("提示：")
    logging.info("  - 运行 'python3 fear_greed_index_notifier.py --test' 可以每5分钟检查一次（测试模式）")
    logging.info("  - 运行 'python3 fear_greed_index_notifier.py --test --once' 可以只执行一次（测试）")
    logging.info("  - 直接运行 'python3 fear_greed_index_notifier.py' 每小时1分检查一次（正常模式）")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("服务已停止")
        notifier.disconnect()

