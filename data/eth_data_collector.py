#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETH数据收集服务
获取ETH相关的数据，包括质押队列数据等
每5分钟执行一次，整点时间保存
"""

import requests
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from tenacity import retry, stop_after_attempt, wait_fixed
from apscheduler.schedulers.blocking import BlockingScheduler
import apscheduler.events

from eth_database import ETHDatabaseService

# ==================== 配置 ====================
# 数据库配置
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'port': 3306,
    'user': 'payment_pro',
    'password': 'nS4kO7tG1jH7cI6oR4b',
    'database': 'quantify'
}

# Beaconcha.in API 配置
BEACONCHA_API_URL = 'https://beaconcha.in/api/v2/ethereum/queues'
BEACONCHA_API_TOKEN = 'CEV6oHTg7paT4bhATDYGyDR6dOg1voF1dzEudXJMH4u'

# Wei到ETH的转换系数（1 ETH = 10^18 wei）
WEI_TO_ETH = 10 ** 18

# 初始化数据库服务
eth_db = ETHDatabaseService(**DB_CONFIG)

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


# ==================== 数据收集函数 ====================
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def get_eth_staking_queue():
    """
    获取ETH质押队列数据
    
    Returns:
        dict: 质押队列数据，失败返回None
    """
    try:
        headers = {
            'Authorization': f'Bearer {BEACONCHA_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'chain': 'mainnet'
        }
        
        logging.info("开始获取ETH质押队列数据...")
        resp = requests.post(BEACONCHA_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        json_data = resp.json()
        
        # 检查API响应
        if 'data' not in json_data:
            logging.warning("ETH质押队列：API响应格式错误")
            return None
        
        data = json_data.get('data', {})
        logging.info("获取到ETH质押队列数据")
        return data
        
    except requests.exceptions.RequestException as e:
        logging.error(f"ETH质押队列：网络请求失败 - {e}")
        return None
    except Exception as e:
        logging.error(f"获取ETH质押队列数据失败：{e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        return None


def wei_to_eth(wei_value):
    """
    将Wei转换为ETH
    
    Args:
        wei_value: Wei值（字符串或整数）
    
    Returns:
        float: ETH值
    """
    try:
        if wei_value is None:
            return 0.0
        # 处理字符串类型的wei值
        wei_int = int(wei_value) if isinstance(wei_value, str) else wei_value
        return float(wei_int) / WEI_TO_ETH
    except (ValueError, TypeError) as e:
        logging.warning(f"Wei转换失败: {wei_value}, 错误: {e}")
        return 0.0


def timestamp_to_datetime(timestamp):
    """
    将Unix时间戳（秒）转换为UTC+8的datetime对象
    
    Args:
        timestamp: Unix时间戳（秒）
    
    Returns:
        datetime: UTC+8时区的datetime对象（无时区信息）
    """
    try:
        if timestamp is None:
            return None
        # 从Unix时间戳创建UTC时间
        dt_utc = datetime.fromtimestamp(int(timestamp), tz=ZoneInfo('UTC'))
        # 转换为UTC+8
        dt_utc8 = dt_utc.astimezone(ZoneInfo('Asia/Shanghai'))
        # 移除时区信息
        return dt_utc8.replace(tzinfo=None)
    except (ValueError, TypeError, OSError) as e:
        logging.warning(f"时间戳转换失败: {timestamp}, 错误: {e}")
        return None


def collect_eth_staking_data():
    """
    收集ETH质押队列数据并保存到数据库
    """
    try:
        # 获取当前时间（UTC+8），并归一化到分钟（秒和微秒设为0）
        now_utc8 = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        ts_datetime_utc8 = now_utc8.replace(second=0, microsecond=0)
        
        # 获取ETH质押队列数据
        queue_data = get_eth_staking_queue()
        
        if not queue_data:
            logging.warning("未获取到ETH质押队列数据")
            return
        
        # 解析deposit_queue数据
        deposit_queue = queue_data.get('deposit_queue', {})
        deposit_count = deposit_queue.get('deposit_count', 0)
        deposit_balance_wei = deposit_queue.get('balance', '0')
        deposit_estimated_processed_at_timestamp = deposit_queue.get('estimated_processed_at')
        deposit_churn_wei = deposit_queue.get('churn', '0')
        
        # 转换为ETH
        deposit_balance_eth = wei_to_eth(deposit_balance_wei)
        deposit_churn_eth = wei_to_eth(deposit_churn_wei)
        
        # 转换时间戳
        deposit_estimated_processed_at = timestamp_to_datetime(deposit_estimated_processed_at_timestamp)
        
        # 解析exit_queue数据
        exit_queue = queue_data.get('exit_queue', {})
        exit_balance_wei = exit_queue.get('balance', '0')
        exit_churn_wei = exit_queue.get('churn', '0')
        
        # 兼容exit_count字段（可能是exit_count或count）
        exit_count = exit_queue.get('exit_count') or exit_queue.get('count', 0)
        
        # 转换为ETH
        exit_balance_eth = wei_to_eth(exit_balance_wei)
        exit_churn_eth = wei_to_eth(exit_churn_wei)
        
        # 解析withdrawal_sweep数据
        withdrawal_sweep = queue_data.get('withdrawal_sweep', {})
        withdrawal_sweep_delay = withdrawal_sweep.get('estimated_sweep_delay')
        withdrawal_sweep_last_validator_index = withdrawal_sweep.get('last_swept_validator_index')
        
        # 解析finality状态
        finality_status = queue_data.get('finality', '')
        
        # 打印获取到的数据
        logging.info("=" * 80)
        logging.info(f"ETH质押队列数据 (ts={ts_datetime_utc8}):")
        logging.info(f"  质押请求数: {deposit_count}")
        logging.info(f"  质押总数量: {deposit_balance_eth:.8f} ETH")
        logging.info(f"  质押预计完成时间: {deposit_estimated_processed_at}")
        logging.info(f"  质押每个epoch最多激活: {deposit_churn_eth:.8f} ETH")
        logging.info(f"  退出队列总数量: {exit_balance_eth:.8f} ETH")
        logging.info(f"  退出队列请求数: {exit_count}")
        logging.info(f"  退出每个epoch最多退出: {exit_churn_eth:.8f} ETH")
        logging.info(f"  提币队列延迟: {withdrawal_sweep_delay} slots")
        logging.info(f"  上次扫完验证者索引: {withdrawal_sweep_last_validator_index}")
        logging.info(f"  最终确认状态: {finality_status}")
        logging.info("=" * 80)
        
        # 保存到数据库
        if not eth_db.connection:
            if not eth_db.connect():
                logging.error("数据库连接失败")
                return
        
        success = eth_db.save_staking_queue_data(
            deposit_count=deposit_count,
            deposit_balance_eth=deposit_balance_eth,
            deposit_estimated_processed_at=deposit_estimated_processed_at,
            deposit_churn_eth=deposit_churn_eth,
            exit_balance_eth=exit_balance_eth,
            exit_count=exit_count,
            exit_churn_eth=exit_churn_eth,
            withdrawal_sweep_delay=withdrawal_sweep_delay,
            withdrawal_sweep_last_validator_index=withdrawal_sweep_last_validator_index,
            finality_status=finality_status,
            ts_datetime=ts_datetime_utc8
        )
        
        if success:
            logging.info("ETH质押队列数据保存成功")
        else:
            logging.error("ETH质押队列数据保存失败")
            
    except Exception as e:
        logging.error(f"收集ETH质押队列数据失败: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")


# ==================== 定时任务配置 ====================
def main():
    """主函数：初始化数据库表并启动定时任务"""
    try:
        # 初始化数据库连接并创建表
        if not eth_db.connect():
            logging.error("数据库连接失败，程序退出")
            return
        
        # 创建表
        eth_db.create_tables()
        
        # 立即执行一次数据收集
        logging.info("立即执行一次ETH质押队列数据收集...")
        collect_eth_staking_data()
        
        # 创建调度器
        scheduler = BlockingScheduler(timezone='Asia/Shanghai')
        
        # 每5分钟执行一次，在整点时间（0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55分）
        scheduler.add_job(
            collect_eth_staking_data,
            trigger='cron',
            minute='0,5,10,15,20,25,30,35,40,45,50,55',
            second=0,
            id='collect_eth_staking_data',
            name='收集ETH质押队列数据',
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
        
        logging.info("ETH数据收集服务启动，每5分钟执行一次")
        logging.info("按 Ctrl+C 停止服务")
        
        # 启动调度器（阻塞）
        scheduler.start()
        
    except KeyboardInterrupt:
        logging.info("收到停止信号，正在关闭服务...")
    except Exception as e:
        logging.error(f"服务启动失败: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
    finally:
        if eth_db.connection:
            eth_db.disconnect()
        logging.info("ETH数据收集服务已停止")


if __name__ == '__main__':
    main()

