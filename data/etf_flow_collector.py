#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF流量数据收集服务
使用 Coinglass API 获取BTC ETF流量数据
"""

import requests
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from tenacity import retry, stop_after_attempt, wait_fixed
from apscheduler.schedulers.blocking import BlockingScheduler
import apscheduler.events

from etf_flow_database import ETFFlowDatabaseService

# ==================== 配置 ====================
# 数据库配置
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'port': 3306,
    'user': 'payment_pro',
    'password': 'nS4kO7tG1jH7cI6oR4b',
    'database': 'quantify'
}

# Coinglass API 配置
COINGLASS_API_KEY = '408475f9fdea470784103ae628c4fc8d'
COINGLASS_API_BASE_URL = 'https://open-api-v4.coinglass.com/api'

# ETF流量API URL
ETF_FLOW_API_URLS = {
    'BTC': f"{COINGLASS_API_BASE_URL}/etf/bitcoin/flow-history",
    'ETH': f"{COINGLASS_API_BASE_URL}/etf/ethereum/flow-history",
    'SOL': f"{COINGLASS_API_BASE_URL}/etf/solana/flow-history",
    'XRP': f"{COINGLASS_API_BASE_URL}/etf/xrp/flow-history"
}

# 监控的币种
COINS = ['BTC', 'ETH', 'SOL', 'XRP']

# 初始化数据库服务
etf_flow_db = ETFFlowDatabaseService(**DB_CONFIG)

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


# ==================== 数据收集函数 ====================
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def get_etf_flow_history(coin='BTC'):
    """
    获取ETF流量历史数据
    
    Args:
        coin: 币种（BTC/ETH/SOL/XRP）
    
    Returns:
        list: ETF流量数据列表
    """
    try:
        if coin not in ETF_FLOW_API_URLS:
            logging.error(f"不支持的币种: {coin}")
            return []
        
        headers = {
            'CG-API-KEY': COINGLASS_API_KEY,
            'accept': 'application/json'
        }
        
        url = ETF_FLOW_API_URLS[coin]
        logging.info(f"开始获取{coin} ETF流量历史数据...")
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        json_data = resp.json()
        
        # 检查API响应
        if json_data.get('code') != '0':
            error_msg = json_data.get('msg', '未知错误')
            logging.warning(f"{coin} ETF流量：API错误（{json_data.get('code')}: {error_msg}）")
            return []
        
        data = json_data.get('data', [])
        if not isinstance(data, list) or len(data) == 0:
            logging.warning(f"{coin} ETF流量：数据为空")
            return []
        
        logging.info(f"获取到 {len(data)} 条{coin} ETF流量数据")
        return data
        
    except requests.exceptions.RequestException as e:
        logging.error(f"{coin} ETF流量：网络请求失败 - {e}")
        return []
    except Exception as e:
        logging.error(f"获取{coin} ETF流量失败：{e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        return []


def collect_etf_flow_data(coin='BTC'):
    """
    收集ETF流量数据并保存到数据库
    
    Args:
        coin: 币种（BTC/ETH/SOL/XRP）
    """
    try:
        # 获取ETF流量历史数据
        etf_data = get_etf_flow_history(coin)
        
        if not etf_data or len(etf_data) == 0:
            logging.warning(f"未获取到{coin} ETF流量数据")
            return
        
        # 按时间戳排序（从旧到新）
        etf_data_sorted = sorted(etf_data, key=lambda x: int(x.get('timestamp', 0)))
        
        saved_count = 0
        skipped_count = 0
        
        for item in etf_data_sorted:
            try:
                # 解析时间戳
                timestamp_ms = int(item.get('timestamp', 0))
                if timestamp_ms <= 0:
                    logging.warning(f"时间戳无效，跳过: {item}")
                    skipped_count += 1
                    continue
                
                # 转换为日期（UTC+8）
                ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                date = ts_datetime_utc8.date()
                
                # 获取总流量和价格
                total_flow_usd = item.get('flow_usd', 0)
                price_usd = item.get('price_usd')
                
                # 解析ETF流量数据
                etf_flows = item.get('etf_flows', [])
                etf_flows_dict = {}
                
                # 记录原始API返回的所有ticker（用于调试）
                raw_tickers = []
                for etf_flow in etf_flows:
                    raw_ticker = etf_flow.get('etf_ticker', '')
                    raw_flow = etf_flow.get('flow_usd', 0)
                    raw_tickers.append(f"{raw_ticker}={raw_flow}")
                    
                    ticker = raw_ticker.upper()
                    flow_usd = raw_flow
                    if ticker:
                        etf_flows_dict[ticker] = flow_usd
                
                # 添加调试日志
                logging.info(f"{coin} ETF流量数据解析: date={date}, total_flow_usd={total_flow_usd}, price_usd={price_usd}")
                logging.info(f"{coin} API返回的原始ticker数据: {', '.join(raw_tickers)}")
                logging.info(f"{coin} 解析后的ETF ticker字典: {etf_flows_dict}")
                
                # 保存数据到数据库
                result = etf_flow_db.save_etf_flow_data(
                    coin=coin,
                    date=date,
                    etf_flows_dict=etf_flows_dict,
                    total_flow_usd=total_flow_usd,
                    price_usd=price_usd
                )
                
                if result == 'saved':
                    saved_count += 1
                    logging.info(f"{coin} ETF流量数据保存成功: date={date}, total={total_flow_usd}, price={price_usd}")
                elif result == 'skipped':
                    skipped_count += 1
                    logging.debug(f"{coin} ETF流量数据已存在，跳过: date={date}")
                else:
                    skipped_count += 1
                    logging.warning(f"{coin} ETF流量数据保存失败: date={date}")
                    
            except Exception as e:
                logging.warning(f"处理{coin} ETF流量数据失败: {e}")
                import traceback
                logging.warning(f"异常详情: {traceback.format_exc()}")
                skipped_count += 1
                continue
        
        logging.info(f"{coin} ETF流量数据收集完成: 保存={saved_count}, 跳过={skipped_count}, 总计={len(etf_data_sorted)}")
            
    except Exception as e:
        logging.error(f"收集{coin} ETF流量数据失败: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")


def collect_all_coins():
    """收集所有币种的ETF流量数据"""
    logging.info("=" * 60)
    logging.info("开始收集ETF流量数据")
    
    for coin in COINS:
        try:
            collect_etf_flow_data(coin)
        except Exception as e:
            logging.error(f"{coin} ETF流量数据收集异常: {e}")
            import traceback
            logging.error(f"异常详情: {traceback.format_exc()}")
    
    logging.info("ETF流量数据收集完成")
    logging.info("=" * 60)


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
    logging.info("初始化ETF流量数据数据库表...")
    if not etf_flow_db.create_tables():
        logging.error("数据库表初始化失败，退出程序")
        return
    
    # 立即执行一次数据收集
    logging.info("立即执行一次数据收集...")
    collect_all_coins()
    
    # 创建调度器
    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    
    # 添加定时任务：每半小时在整点时间执行（0, 30分）
    scheduler.add_job(
        collect_all_coins,
        trigger='cron',
        minute='0,30',  # 每半小时的整点时间（0分和30分）
        second=0,  # 整秒执行
        id='collect_etf_flow_data',
        name='收集ETF流量数据',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60  # 任务错过执行时间后，60秒内仍可执行
    )
    
    # 添加任务监听器
    scheduler.add_listener(job_listener, apscheduler.events.EVENT_JOB_EXECUTED | apscheduler.events.EVENT_JOB_ERROR)
    
    logging.info("ETF流量数据收集服务启动成功")
    logging.info(f"定时任务：每半小时在整点时间（0, 30分）收集一次ETF流量数据（币种：{', '.join(COINS)}）")
    logging.info("数据对比：根据日期判断，如果日期已存在则跳过，不存在则新增")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("收到停止信号，正在关闭服务...")
        scheduler.shutdown()
        etf_flow_db.disconnect()
        logging.info("服务已关闭")


if __name__ == "__main__":
    main()

