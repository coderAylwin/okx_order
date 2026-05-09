#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
链上数据收集服务
使用 Coinglass API 获取交易所余额等链上数据
每5分钟执行一次，整点时间标记为 is_hourly=True
"""

import requests
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from tenacity import retry, stop_after_attempt, wait_fixed
from apscheduler.schedulers.blocking import BlockingScheduler
import apscheduler.events

from onchain_database import OnchainDatabaseService

# ==================== 配置 ====================
# 数据库配置
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'port': 3306,
    'user': 'quantify_read_write',
    'password': '02Ya6fPDo@w67UI%sEaDvPXfT',
    'database': 'quantify'
}

# Coinglass API 配置
COINGLASS_API_KEY = '408475f9fdea470784103ae628c4fc8d'
COINGLASS_API_BASE_URL = 'https://open-api-v4.coinglass.com/api'

# Blockchair API 配置
BLOCKCHAIR_API_URL = 'https://api.blockchair.com/bitcoin/stats'

# 监控的币种
COINS = ['BTC', 'ETH', 'XRP']

# 初始化数据库服务
onchain_db = OnchainDatabaseService(**DB_CONFIG)

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


# ==================== 数据收集函数 ====================
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_exchange_balance(coin):
    """
    收集指定币种的交易所余额数据
    
    Args:
        coin: 币种（BTC/ETH/XRP）
    
    Returns:
        bool: 收集是否成功
    """
    try:
        url = f"{COINGLASS_API_BASE_URL}/exchange/balance/list"
        headers = {
            'CG-API-KEY': COINGLASS_API_KEY,
            'accept': 'application/json'
        }
        params = {
            'symbol': coin
        }
        
        logging.info(f"开始获取{coin}交易所余额数据...")
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        json_data = resp.json()
        
        # 检查API响应
        if json_data.get('code') != '0':
            error_msg = json_data.get('msg', '未知错误')
            logging.warning(f"{coin}交易所余额：API错误（{json_data.get('code')}: {error_msg}）")
            return False
        
        data = json_data.get('data', [])
        if not isinstance(data, list) or len(data) == 0:
            logging.warning(f"{coin}交易所余额：数据为空")
            return False
        
        # 获取当前时间（UTC+8）
        now_utc8 = datetime.now(ZoneInfo('Asia/Shanghai'))
        
        # 将时间调整为整点时间（保留小时和分钟，秒和微秒设为0）
        # 例如：19:40:01 -> 19:40:00
        ts_datetime_utc8 = now_utc8.replace(second=0, microsecond=0)
        
        # 判断是否为整点时间（分钟为0，即整点）
        is_hourly = (now_utc8.minute == 0)
        
        # 保存数据到数据库
        result = onchain_db.save_exchange_balance(
            coin=coin,
            exchange_data_list=data,
            ts_datetime=ts_datetime_utc8,
            is_hourly=is_hourly
        )
        
        if result['saved'] > 0 or result.get('unchanged', 0) > 0:
            logging.info(f"{coin}交易所余额数据收集成功: 保存={result['saved']}, 未变化={result.get('unchanged', 0)}, 跳过={result['skipped']}, 总计={result['total']}, 整点={is_hourly}")
            return True
        else:
            logging.warning(f"{coin}交易所余额数据收集完成，但未保存任何数据")
            return False
        
    except requests.exceptions.RequestException as e:
        logging.error(f"{coin}交易所余额：网络请求失败 - {e}")
        return False
    except Exception as e:
        logging.error(f"{coin}交易所余额收集失败：{e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        return False


def collect_all_coins():
    """收集所有币种的交易所余额数据"""
    logging.info("=" * 60)
    logging.info("开始收集链上交易所余额数据")
    
    success_count = 0
    for coin in COINS:
        try:
            if collect_exchange_balance(coin):
                success_count += 1
        except Exception as e:
            logging.error(f"{coin}数据收集异常: {e}")
            import traceback
            logging.error(f"异常详情: {traceback.format_exc()}")
    
    logging.info(f"链上数据收集完成: 成功={success_count}/{len(COINS)}")
    logging.info("=" * 60)


# ==================== BTC链上统计数据收集 ====================
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def get_btc_stats():
    """
    获取BTC链上统计数据
    
    Returns:
        dict: 统计数据字典，如果失败返回None
    """
    try:
        logging.info("开始获取BTC链上统计数据...")
        resp = requests.get(BLOCKCHAIR_API_URL, timeout=30)
        resp.raise_for_status()
        json_data = resp.json()
        
        # 检查API响应
        if json_data.get('context', {}).get('code') != 200:
            error_msg = json_data.get('context', {}).get('error', '未知错误')
            logging.warning(f"BTC链上数据：API错误（{error_msg}）")
            return None
        
        data = json_data.get('data')
        if not isinstance(data, dict):
            logging.warning(f"BTC链上数据：数据格式错误")
            return None
        
        logging.info(f"成功获取BTC链上统计数据")
        return data
        
    except requests.exceptions.RequestException as e:
        logging.error(f"BTC链上数据：网络请求失败 - {e}")
        return None
    except Exception as e:
        logging.error(f"获取BTC链上数据失败：{e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        return None


def collect_btc_stats():
    """收集BTC链上统计数据并保存到数据库"""
    try:
        # 获取统计数据
        stats_data = get_btc_stats()
        
        if not stats_data:
            logging.warning("未获取到BTC链上统计数据")
            return
        
        # 使用当前时间（UTC+8）作为时间戳，对齐到10分钟的整点
        now_utc8 = datetime.now(ZoneInfo('Asia/Shanghai'))
        # 对齐到10分钟的整点（0, 10, 20, 30, 40, 50分）
        minute_aligned = (now_utc8.minute // 10) * 10
        ts_datetime_utc8 = now_utc8.replace(minute=minute_aligned, second=0, microsecond=0)
        
        # 保存数据到数据库
        result = onchain_db.save_btc_stats(stats_data, ts_datetime_utc8)
        
        if result:
            logging.info(f"BTC链上统计数据保存成功: ts={ts_datetime_utc8}")
        else:
            logging.error(f"BTC链上统计数据保存失败: ts={ts_datetime_utc8}")
            
    except Exception as e:
        logging.error(f"收集BTC链上统计数据失败: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")


# ==================== 定时任务 ====================
def job_listener(event):
    """任务执行监听器"""
    if event.exception:
        logging.error(f"任务执行失败: {event.job_id} - {event.exception}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
    else:
        logging.debug(f"任务执行成功: {event.job_id}")


def main():
    """主函数"""
    # 初始化数据库表
    logging.info("初始化链上数据数据库表...")
    if not onchain_db.create_tables():
        logging.error("数据库表初始化失败，退出程序")
        return
    
    # 立即执行一次数据收集
    logging.info("立即执行一次数据收集...")
    collect_all_coins()
    collect_btc_stats()
    
    # 创建调度器
    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    
    # 添加定时任务：每5分钟在整点时间执行（0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55分）
    scheduler.add_job(
        collect_all_coins,
        trigger='cron',
        minute='0,5,10,15,20,25,30,35,40,45,50,55',  # 每5分钟的整点时间
        second=0,  # 整秒执行
        id='collect_onchain_data',
        name='收集链上交易所余额数据',
        max_instances=1,  # 同一时间只允许一个实例运行
        coalesce=True,  # 如果任务堆积，只执行最后一次
        misfire_grace_time=60  # 任务错过执行时间后，60秒内仍可执行
    )
    
    # 添加定时任务：每10分钟收集一次BTC链上统计数据（0, 10, 20, 30, 40, 50分）
    scheduler.add_job(
        collect_btc_stats,
        trigger='cron',
        minute='0,10,20,30,40,50',  # 每10分钟的整点时间
        second=0,  # 整秒执行
        id='collect_btc_stats',
        name='收集BTC链上统计数据',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120  # 任务错过执行时间后，120秒内仍可执行
    )
    
    # 添加任务监听器
    scheduler.add_listener(job_listener, apscheduler.events.EVENT_JOB_EXECUTED | apscheduler.events.EVENT_JOB_ERROR)
    
    logging.info("链上数据收集服务启动成功")
    logging.info("定时任务1：每5分钟在整点时间（0,5,10,15,20,25,30,35,40,45,50,55分）收集一次交易所余额数据")
    logging.info("定时任务2：每10分钟在整点时间（0,10,20,30,40,50分）收集一次BTC链上统计数据")
    logging.info("ts字段保存为整点时间（秒和微秒为0），整点时间（分钟为0）的数据将标记为 is_hourly=True")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("收到停止信号，正在关闭服务...")
        scheduler.shutdown()
        onchain_db.disconnect()
        logging.info("服务已关闭")


if __name__ == "__main__":
    main()

