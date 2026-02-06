#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX交易所数据提醒服务
在整点后1分钟（如17:01、18:01）获取BTC、ETH、SOL的多空比和持仓量数据
对比当前、上一小时、上四小时、上一天的数据变化
发送飞书消息提醒
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
# LARK_WEBHOOK_URL = "https://open.larksuite.com/open-apis/bot/v2/hook/b5745320-444f-43b8-a09e-dee2a62f7731"
LARK_WEBHOOK_URL = "https://open.larksuite.com/open-apis/bot/v2/hook/8fb1eee3-5ad1-457a-88e1-3324fedadb67"

# 币种配置
COINS = ['BTC', 'ETH', 'SOL']
COIN_SYMBOLS = {
    'BTC': 'BTC-USDT-SWAP',
    'ETH': 'ETH-USDT-SWAP',
    'SOL': 'SOL-USDT-SWAP'
}


class ExchangeDataNotifier:
    """交易所数据提醒服务"""
    
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
    
    def get_latest_data_at_time(self, coin, symbol, target_time):
        """
        获取指定时间点附近的最新数据
        数据通常是每5分钟更新一次（如16:55, 17:00, 17:05等）
        所以查询时找目标时间之前最近的数据
        
        Args:
            coin: 币种
            symbol: 合约符号
            target_time: 目标时间（datetime对象）
        
        Returns:
            dict: 数据字典，如果未找到返回None
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
            # 查询目标时间之前的最新数据（允许10分钟误差范围）
            # 例如：如果目标是17:01，会找到16:55或17:00的数据
            sql = """
            SELECT ts, long_short_ratio, top_trader_account_ratio, top_trader_position_ratio
            FROM okx_long_short_ratio
            WHERE coin = %s AND symbol = %s AND ts <= %s
            ORDER BY ts DESC
            LIMIT 1
            """
            cursor.execute(sql, (coin, symbol, target_time))
            result = cursor.fetchone()
            
            if result:
                return {
                    'ts': result[0],
                    'long_short_ratio': float(result[1]) if result[1] is not None else None,
                    'top_trader_account_ratio': float(result[2]) if result[2] is not None else None,
                    'top_trader_position_ratio': float(result[3]) if result[3] is not None else None
                }
            return None
        except Exception as e:
            logging.error(f"查询数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return None
        finally:
            cursor.close()
    
    def get_open_interest_at_time(self, coin, symbol, target_time):
        """
        获取指定时间点附近的持仓量数据
        
        Args:
            coin: 币种
            symbol: 合约符号
            target_time: 目标时间（datetime对象）
        
        Returns:
            dict: 持仓量数据字典，如果未找到返回None
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
            # 查询目标时间之前的最新持仓量数据（整点数据）
            sql = """
            SELECT ts, open_interest, oi_ccy, oi_usd
            FROM okx_open_interest
            WHERE coin = %s AND symbol = %s AND ts <= %s
            ORDER BY ts DESC
            LIMIT 1
            """
            cursor.execute(sql, (coin, symbol, target_time))
            result = cursor.fetchone()
            
            if result:
                return {
                    'ts': result[0],
                    'open_interest': float(result[1]) if result[1] is not None else None,
                    'oi_ccy': float(result[2]) if result[2] is not None else None,
                    'oi_usd': float(result[3]) if result[3] is not None else None
                }
            return None
        except Exception as e:
            logging.error(f"查询持仓量数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return None
        finally:
            cursor.close()
    
    def get_comparison_data(self, coin, symbol, current_time):
        """
        获取对比数据：当前、上一小时、上四小时、上一天
        注意：对比时间要保持相同的分钟数（如18:55对应17:55、14:55、前一天18:55）
        
        Args:
            coin: 币种
            symbol: 合约符号
            current_time: 当前时间（datetime对象）
        
        Returns:
            dict: 包含各个时间点的数据
        """
        # 先获取当前最新数据
        current_data = self.get_latest_data_at_time(coin, symbol, current_time)
        
        if not current_data:
            return {
                'current': None,
                'one_hour_ago': None,
                'four_hours_ago': None,
                'one_day_ago': None
            }
        
        # 使用当前数据的实际时间来计算对比时间点（保持相同的分钟数）
        current_data_time = current_data['ts']
        
        # 计算对比时间点（保持相同的分钟和秒）
        one_hour_ago = current_data_time - timedelta(hours=1)
        four_hours_ago = current_data_time - timedelta(hours=4)
        one_day_ago = current_data_time - timedelta(days=1)
        
        # 获取各个时间点的多空比数据
        one_hour_data = self.get_latest_data_at_time(coin, symbol, one_hour_ago)
        four_hours_data = self.get_latest_data_at_time(coin, symbol, four_hours_ago)
        one_day_data = self.get_latest_data_at_time(coin, symbol, one_day_ago)
        
        # 获取各个时间点的持仓量数据（整点数据）
        # 对于持仓量，需要找整点时间的数据
        current_oi_time = current_data_time.replace(minute=0, second=0, microsecond=0)
        one_hour_oi_time = current_oi_time - timedelta(hours=1)
        four_hours_oi_time = current_oi_time - timedelta(hours=4)
        one_day_oi_time = current_oi_time - timedelta(days=1)
        
        current_oi_data = self.get_open_interest_at_time(coin, symbol, current_oi_time)
        one_hour_oi_data = self.get_open_interest_at_time(coin, symbol, one_hour_oi_time)
        four_hours_oi_data = self.get_open_interest_at_time(coin, symbol, four_hours_oi_time)
        one_day_oi_data = self.get_open_interest_at_time(coin, symbol, one_day_oi_time)
        
        return {
            'current': current_data,
            'one_hour_ago': one_hour_data,
            'four_hours_ago': four_hours_data,
            'one_day_ago': one_day_data,
            'current_oi': current_oi_data,
            'one_hour_ago_oi': one_hour_oi_data,
            'four_hours_ago_oi': four_hours_oi_data,
            'one_day_ago_oi': one_day_oi_data
        }
    
    def format_value_change(self, current_value, prev_value):
        """格式化数值变化"""
        if current_value is None:
            return "N/A"
        if prev_value is None:
            return f"{current_value:.4f}"
        
        change = current_value - prev_value
        change_pct = (change / prev_value * 100) if prev_value != 0 else 0
        
        if change > 0:
            return f"{current_value:.4f}（+{change:.4f}, +{change_pct:.2f}%）"
        elif change < 0:
            return f"{current_value:.4f}（{change:.4f}, {change_pct:.2f}%）"
        else:
            return f"{current_value:.4f}（无变化）"
    
    def send_lark_notification(self, coin, comparison_data, current_time):
        """
        发送飞书消息通知
        
        Args:
            coin: 币种
            comparison_data: 对比数据字典
            current_time: 当前时间
        """
        try:
            current = comparison_data['current']
            one_hour = comparison_data['one_hour_ago']
            four_hours = comparison_data['four_hours_ago']
            one_day = comparison_data['one_day_ago']
            
            if not current:
                logging.warning(f"{coin} 当前数据不存在，跳过推送")
                return
            
            # 构建消息内容
            content_lines = [
                f"📊 {coin} 交易所数据提醒",
                "",
                f"⏰ 数据时间: {current['ts'].strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "📈 全部用户多空比 (long_short_ratio):",
            ]
            
            # 多空比对比 - 显示当前值和对比
            current_lsr = current['long_short_ratio']
            if current_lsr is not None:
                content_lines.append(f"  • 当前: {current_lsr:.4f}")
                
                if one_hour and one_hour['long_short_ratio'] is not None:
                    change_1h = current_lsr - one_hour['long_short_ratio']
                    change_1h_pct = (change_1h / one_hour['long_short_ratio'] * 100) if one_hour['long_short_ratio'] != 0 else 0
                    change_sign = "+" if change_1h >= 0 else ""
                    content_lines.append(f"  • vs 1小时前: {one_hour['long_short_ratio']:.4f} ({change_sign}{change_1h:.4f}, {change_sign}{change_1h_pct:.2f}%)")
                    content_lines.append(f"    时间: {one_hour['ts'].strftime('%Y-%m-%d %H:%M:%S')}")
                
                if four_hours and four_hours['long_short_ratio'] is not None:
                    change_4h = current_lsr - four_hours['long_short_ratio']
                    change_4h_pct = (change_4h / four_hours['long_short_ratio'] * 100) if four_hours['long_short_ratio'] != 0 else 0
                    change_sign = "+" if change_4h >= 0 else ""
                    content_lines.append(f"  • vs 4小时前: {four_hours['long_short_ratio']:.4f} ({change_sign}{change_4h:.4f}, {change_sign}{change_4h_pct:.2f}%)")
                    content_lines.append(f"    时间: {four_hours['ts'].strftime('%Y-%m-%d %H:%M:%S')}")
                
                if one_day and one_day['long_short_ratio'] is not None:
                    change_1d = current_lsr - one_day['long_short_ratio']
                    change_1d_pct = (change_1d / one_day['long_short_ratio'] * 100) if one_day['long_short_ratio'] != 0 else 0
                    change_sign = "+" if change_1d >= 0 else ""
                    content_lines.append(f"  • vs 1天前: {one_day['long_short_ratio']:.4f} ({change_sign}{change_1d:.4f}, {change_sign}{change_1d_pct:.2f}%)")
                    content_lines.append(f"    时间: {one_day['ts'].strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                content_lines.append("  • 当前: N/A")
            
            content_lines.append("")
            content_lines.append("👥 精英交易员多空持仓人数比 (top_trader_account_ratio):")
            
            # 精英交易员人数比对比
            current_account = current['top_trader_account_ratio']
            if current_account is not None:
                content_lines.append(f"  • 当前: {current_account:.4f}")
                
                if one_hour and one_hour['top_trader_account_ratio'] is not None:
                    change_1h = current_account - one_hour['top_trader_account_ratio']
                    change_1h_pct = (change_1h / one_hour['top_trader_account_ratio'] * 100) if one_hour['top_trader_account_ratio'] != 0 else 0
                    change_sign = "+" if change_1h >= 0 else ""
                    content_lines.append(f"  • vs 1小时前: {one_hour['top_trader_account_ratio']:.4f} ({change_sign}{change_1h:.4f}, {change_sign}{change_1h_pct:.2f}%)")
                
                if four_hours and four_hours['top_trader_account_ratio'] is not None:
                    change_4h = current_account - four_hours['top_trader_account_ratio']
                    change_4h_pct = (change_4h / four_hours['top_trader_account_ratio'] * 100) if four_hours['top_trader_account_ratio'] != 0 else 0
                    change_sign = "+" if change_4h >= 0 else ""
                    content_lines.append(f"  • vs 4小时前: {four_hours['top_trader_account_ratio']:.4f} ({change_sign}{change_4h:.4f}, {change_sign}{change_4h_pct:.2f}%)")
                
                if one_day and one_day['top_trader_account_ratio'] is not None:
                    change_1d = current_account - one_day['top_trader_account_ratio']
                    change_1d_pct = (change_1d / one_day['top_trader_account_ratio'] * 100) if one_day['top_trader_account_ratio'] != 0 else 0
                    change_sign = "+" if change_1d >= 0 else ""
                    content_lines.append(f"  • vs 1天前: {one_day['top_trader_account_ratio']:.4f} ({change_sign}{change_1d:.4f}, {change_sign}{change_1d_pct:.2f}%)")
            else:
                content_lines.append("  • 当前: N/A")
            
            content_lines.append("")
            content_lines.append("💰 精英交易员多空持仓仓位比 (top_trader_position_ratio):")
            
            # 精英交易员仓位比对比
            current_position = current['top_trader_position_ratio']
            if current_position is not None:
                content_lines.append(f"  • 当前: {current_position:.4f}")
                
                if one_hour and one_hour['top_trader_position_ratio'] is not None:
                    change_1h = current_position - one_hour['top_trader_position_ratio']
                    change_1h_pct = (change_1h / one_hour['top_trader_position_ratio'] * 100) if one_hour['top_trader_position_ratio'] != 0 else 0
                    change_sign = "+" if change_1h >= 0 else ""
                    content_lines.append(f"  • vs 1小时前: {one_hour['top_trader_position_ratio']:.4f} ({change_sign}{change_1h:.4f}, {change_sign}{change_1h_pct:.2f}%)")
                
                if four_hours and four_hours['top_trader_position_ratio'] is not None:
                    change_4h = current_position - four_hours['top_trader_position_ratio']
                    change_4h_pct = (change_4h / four_hours['top_trader_position_ratio'] * 100) if four_hours['top_trader_position_ratio'] != 0 else 0
                    change_sign = "+" if change_4h >= 0 else ""
                    content_lines.append(f"  • vs 4小时前: {four_hours['top_trader_position_ratio']:.4f} ({change_sign}{change_4h:.4f}, {change_sign}{change_4h_pct:.2f}%)")
                
                if one_day and one_day['top_trader_position_ratio'] is not None:
                    change_1d = current_position - one_day['top_trader_position_ratio']
                    change_1d_pct = (change_1d / one_day['top_trader_position_ratio'] * 100) if one_day['top_trader_position_ratio'] != 0 else 0
                    change_sign = "+" if change_1d >= 0 else ""
                    content_lines.append(f"  • vs 1天前: {one_day['top_trader_position_ratio']:.4f} ({change_sign}{change_1d:.4f}, {change_sign}{change_1d_pct:.2f}%)")
            else:
                content_lines.append("  • 当前: N/A")
            
            # 添加持仓量数据
            current_oi = comparison_data.get('current_oi')
            one_hour_oi = comparison_data.get('one_hour_ago_oi')
            four_hours_oi = comparison_data.get('four_hours_ago_oi')
            one_day_oi = comparison_data.get('one_day_ago_oi')
            
            if current_oi:
                content_lines.append("")
                content_lines.append("💼 合约持仓量 (open_interest):")
                
                current_oi_value = current_oi.get('open_interest')
                if current_oi_value is not None:
                    content_lines.append(f"  • 当前: {current_oi_value:,.2f} 张")
                    
                    if one_hour_oi and one_hour_oi.get('open_interest') is not None:
                        change_1h = current_oi_value - one_hour_oi['open_interest']
                        change_1h_pct = (change_1h / one_hour_oi['open_interest'] * 100) if one_hour_oi['open_interest'] != 0 else 0
                        change_sign = "+" if change_1h >= 0 else ""
                        content_lines.append(f"  • vs 1小时前: {one_hour_oi['open_interest']:,.2f} 张 ({change_sign}{change_1h:,.2f}, {change_sign}{change_1h_pct:.2f}%)")
                        content_lines.append(f"    时间: {one_hour_oi['ts'].strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    if four_hours_oi and four_hours_oi.get('open_interest') is not None:
                        change_4h = current_oi_value - four_hours_oi['open_interest']
                        change_4h_pct = (change_4h / four_hours_oi['open_interest'] * 100) if four_hours_oi['open_interest'] != 0 else 0
                        change_sign = "+" if change_4h >= 0 else ""
                        content_lines.append(f"  • vs 4小时前: {four_hours_oi['open_interest']:,.2f} 张 ({change_sign}{change_4h:,.2f}, {change_sign}{change_4h_pct:.2f}%)")
                        content_lines.append(f"    时间: {four_hours_oi['ts'].strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    if one_day_oi and one_day_oi.get('open_interest') is not None:
                        change_1d = current_oi_value - one_day_oi['open_interest']
                        change_1d_pct = (change_1d / one_day_oi['open_interest'] * 100) if one_day_oi['open_interest'] != 0 else 0
                        change_sign = "+" if change_1d >= 0 else ""
                        content_lines.append(f"  • vs 1天前: {one_day_oi['open_interest']:,.2f} 张 ({change_sign}{change_1d:,.2f}, {change_sign}{change_1d_pct:.2f}%)")
                        content_lines.append(f"    时间: {one_day_oi['ts'].strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 显示USD价值
                if current_oi.get('oi_usd') is not None:
                    oi_usd_value = current_oi['oi_usd']
                    if oi_usd_value >= 100000000:  # 大于1亿
                        oi_usd_display = f"{oi_usd_value / 100000000:.2f} 亿美元"
                    elif oi_usd_value >= 10000:  # 大于1万
                        oi_usd_display = f"{oi_usd_value / 10000:.2f} 万美元"
                    else:
                        oi_usd_display = f"{oi_usd_value:,.2f} 美元"
                    content_lines.append(f"  • 持仓量价值: {oi_usd_display}")
            
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
                logging.info(f"✅ {coin} 飞书消息推送成功")
            else:
                logging.warning(f"⚠️ {coin} 飞书消息推送返回异常: {result}")
                
        except requests.exceptions.RequestException as e:
            logging.error(f"{coin} 飞书消息推送失败（网络错误）: {e}")
        except Exception as e:
            logging.error(f"{coin} 飞书消息推送失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")


# 初始化服务
notifier = ExchangeDataNotifier(DB_CONFIG)


def collect_and_notify_exchange_data():
    """收集交易所数据并发送通知"""
    try:
        # 获取当前时间（整点后1分钟，比如17:01）
        now = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        
        logging.info(f"开始收集交易所数据: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not notifier.connect():
            logging.error("数据库连接失败")
            return
        
        # 遍历每个币种
        for coin in COINS:
            symbol = COIN_SYMBOLS[coin]
            
            try:
                # 获取对比数据
                comparison_data = notifier.get_comparison_data(coin, symbol, now)
                
                # 检查是否有当前数据
                if not comparison_data['current']:
                    logging.warning(f"{coin} 当前多空比数据不存在，跳过")
                    continue
                
                # 发送飞书通知
                notifier.send_lark_notification(coin, comparison_data, now)
                
            except Exception as e:
                logging.error(f"{coin} 处理失败: {e}")
                logging.error(f"异常详情: {traceback.format_exc()}")
                continue
        
        logging.info("交易所数据收集和通知完成")
        
    except Exception as e:
        logging.error(f"收集多空比数据失败: {e}")
        logging.error(f"异常详情: {traceback.format_exc()}")
    finally:
        notifier.disconnect()


# ==================== 主程序 ====================
if __name__ == "__main__":
    # 检查命令行参数
    test_mode = '--test' in sys.argv or '-t' in sys.argv
    
    logging.info("OKX交易所数据提醒服务启动")
    
    if test_mode:
        logging.info("=" * 50)
        logging.info("测试模式：每5分钟执行一次")
        logging.info("=" * 50)
    
    # 立即执行一次
    logging.info("立即执行一次数据收集...")
    collect_and_notify_exchange_data()
    
    # 如果是测试模式，执行完就退出
    if test_mode and '--once' in sys.argv:
        logging.info("=" * 50)
        logging.info("测试模式（单次执行）完成，退出")
        logging.info("=" * 50)
        logging.info("提示：运行 'python3 okx_long_short_ratio_notifier.py --test' 可以每5分钟推送一次")
        notifier.disconnect()
        exit(0)
    
    # 创建调度器
    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    
    if test_mode:
        # 测试模式：每5分钟执行一次
        scheduler.add_job(
            collect_and_notify_exchange_data,
            trigger='interval',
            minutes=5,
            id='collect_exchange_data_notify',
            name='收集交易所数据并发送通知（测试模式）',
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        logging.info("测试模式：每5分钟执行一次")
    else:
        # 正常模式：每小时的1分执行（17:01, 18:01等）
        scheduler.add_job(
            collect_and_notify_exchange_data,
            trigger='cron',
            minute=1,  # 每小时的第1分钟
            second=0,  # 整秒执行
            id='collect_exchange_data_notify',
            name='收集交易所数据并发送通知',
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
    logging.info("  - 运行 'python3 okx_long_short_ratio_notifier.py --test' 可以每5分钟推送一次（测试模式）")
    logging.info("  - 运行 'python3 okx_long_short_ratio_notifier.py --test --once' 可以只执行一次（测试）")
    logging.info("  - 直接运行 'python3 okx_long_short_ratio_notifier.py' 每小时1分推送一次（正常模式）")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("服务已停止")
        notifier.disconnect()

