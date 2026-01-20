#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观数据收集服务
获取加密货币恐慌指数和VIX恐慌指数
每5分钟执行一次，整点时间保存
"""

import requests
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from tenacity import retry, stop_after_attempt, wait_fixed
from apscheduler.schedulers.blocking import BlockingScheduler
import apscheduler.events
import yfinance as yf
import pytz

from macro_database import MacroDatabaseService

# ==================== 配置 ====================
# 数据库配置
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'port': 3306,
    'user': 'payment_pro',
    'password': 'nS4kO7tG1jH7cI6oR4b',
    'database': 'quantify'
}

# API配置
FEAR_GREED_API_URL = 'https://api.alternative.me/fng/'

# 初始化数据库服务
macro_db = MacroDatabaseService(**DB_CONFIG)

# 注意：不在模块级别创建vix_ticker，避免缓存问题
# 每次调用时重新创建Ticker对象，确保获取最新数据

# 时区设置
ny_tz = pytz.timezone('America/New_York')

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


# ==================== 数据收集函数 ====================
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def get_fear_greed_index(limit=3):
    """
    获取加密货币恐慌指数数据
    
    Args:
        limit: 获取的数据条数
    
    Returns:
        list: 恐慌指数数据列表
    """
    try:
        url = f"{FEAR_GREED_API_URL}?limit={limit}"
        headers = {'accept': 'application/json'}
        
        logging.info(f"开始获取加密货币恐慌指数数据（limit={limit}）...")
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        json_data = resp.json()
        
        if json_data.get('metadata', {}).get('error'):
            error_msg = json_data.get('metadata', {}).get('error')
            logging.warning(f"加密货币恐慌指数：API错误（{error_msg}）")
            return []
        
        data = json_data.get('data', [])
        if not isinstance(data, list) or len(data) == 0:
            logging.warning(f"加密货币恐慌指数：数据为空")
            return []
        
        return data
        
    except requests.exceptions.RequestException as e:
        logging.error(f"加密货币恐慌指数：网络请求失败 - {e}")
        return []
    except Exception as e:
        logging.error(f"获取加密货币恐慌指数失败：{e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        return []


def get_vix_value():
    """
    获取VIX恐慌指数当前值（每次调用都重新创建Ticker对象，避免缓存问题）
    
    Returns:
        float: VIX值，如果获取失败返回None
    """
    try:
        # 每次调用时重新创建Ticker对象，避免使用缓存的旧数据
        vix_ticker = yf.Ticker("^VIX")
        
        # 方法1：使用history方法获取最新数据（最可靠，强制刷新）
        try:
            # 获取最近1天的1分钟K线数据，取最后一条的收盘价
            hist = vix_ticker.history(period="1d", interval="1m", progress=False)
            if not hist.empty:
                latest_vix = float(hist['Close'].iloc[-1])
                latest_time = hist.index[-1]
                logging.info(f"VIX通过history获取: {latest_vix}, 时间: {latest_time}")
                return latest_vix
        except Exception as hist_error:
            logging.debug(f"history方法获取失败，尝试其他方法: {hist_error}")
        
        # 方法2：尝试使用fast_info获取最新价格（更快但可能缓存）
        try:
            fast_info = vix_ticker.fast_info
            if hasattr(fast_info, 'last_price') and fast_info.last_price is not None:
                logging.info(f"VIX fast_info.last_price: {fast_info.last_price}")
                return float(fast_info.last_price)
        except Exception as fast_error:
            logging.debug(f"fast_info获取失败，尝试其他方法: {fast_error}")
        
        # 方法3：使用info获取详细数据（最后备选）
        info = vix_ticker.info
        
        # 打印所有可用的价格字段（用于调试）
        price_fields = {
            'regularMarketPrice': info.get('regularMarketPrice'),
            'currentPrice': info.get('currentPrice'),
            'previousClose': info.get('previousClose'),
            'regularMarketPreviousClose': info.get('regularMarketPreviousClose'),
            'bid': info.get('bid'),
            'ask': info.get('ask'),
            'open': info.get('open'),
            'dayHigh': info.get('dayHigh'),
            'dayLow': info.get('dayLow'),
        }
        logging.info(f"VIX所有价格字段: {price_fields}")
        
        # 优先使用currentPrice（当前价格），如果没有则使用regularMarketPrice（常规市场价格）
        # 如果都没有，则使用previousClose（前收盘价）作为兜底
        vix_value = (info.get('currentPrice') or 
                    info.get('regularMarketPrice') or 
                    info.get('previousClose'))
        
        if vix_value is not None:
            logging.info(f"VIX价格字段详情: currentPrice={info.get('currentPrice')}, regularMarketPrice={info.get('regularMarketPrice')}, previousClose={info.get('previousClose')}, 最终使用值={vix_value}")
            return float(vix_value)
        return None
        
    except Exception as e:
        logging.warning(f"获取VIX值失败: {e}")
        import traceback
        logging.warning(f"异常详情: {traceback.format_exc()}")
        return None


def save_historical_fear_greed_data():
    """
    保存100天的加密货币恐慌指数历史数据
    """
    logging.info("开始保存100天加密货币恐慌指数历史数据...")
    
    # 获取5天的数据（每天一条，所以limit=5）
    fear_greed_data = get_fear_greed_index(limit=5)
    
    if not fear_greed_data:
        logging.warning("未获取到加密货币恐慌指数历史数据")
        return
    
    # 按时间戳排序（从旧到新）
    fear_greed_data_sorted = sorted(fear_greed_data, key=lambda x: int(x.get('timestamp', 0)))
    
    saved_count = 0
    skipped_count = 0
    
    for item in fear_greed_data_sorted:
        try:
            # 解析数据
            crypto_value = int(item.get('value', 0)) if item.get('value') else None
            crypto_classification = item.get('value_classification', '')
            crypto_timestamp = int(item.get('timestamp', 0)) if item.get('timestamp') else None
            
            if crypto_timestamp is None or crypto_value is None:
                continue
            
            # 将时间戳转换为UTC+8时间（整点时间）
            ts_datetime_utc8 = datetime.fromtimestamp(crypto_timestamp, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
            # 调整为整点时间（秒和微秒为0）
            ts_datetime_utc8 = ts_datetime_utc8.replace(second=0, microsecond=0)
            
            # 保存数据（历史数据不包含VIX）
            result = macro_db.save_fear_greed_data(
                ts_datetime=ts_datetime_utc8,
                crypto_value=crypto_value,
                crypto_classification=crypto_classification,
                crypto_timestamp=crypto_timestamp,
                vix_value=None,  # 历史数据先不保存VIX
                check_update=False  # 历史数据不检查更新
            )
            
            if result == 'saved':
                saved_count += 1
            elif result == 'unchanged':
                skipped_count += 1
                
        except Exception as e:
            logging.warning(f"保存历史数据失败: {e}")
            skipped_count += 1
            continue
    
    logging.info(f"历史数据保存完成: 保存={saved_count}, 跳过={skipped_count}, 总计={len(fear_greed_data)}")


def collect_fear_greed_data():
    """
    收集最新的恐慌指数数据（每5分钟执行一次）
    """
    try:
        # 恐慌指数北京时间通常每日8点左右更新，但我们需要每5分钟落库一次（主要记录VIX实时值）
        # 这里取最近3条用于兜底/排查，实际保存用最新一条即可
        fear_greed_data = get_fear_greed_index(limit=3)
        
        if not fear_greed_data or len(fear_greed_data) == 0:
            logging.warning("未获取到加密货币恐慌指数数据")
            return
        
        # 获取最新的一条数据
        latest_item = fear_greed_data[0]
        
        # 打印获取到的数据（便于验证）
        logging.info(f"最新加密货币恐慌指数数据(最新1条): {latest_item}")
        if len(fear_greed_data) > 1:
            logging.debug(f"恐慌指数最近{len(fear_greed_data)}条: {fear_greed_data}")
        
        # 解析数据
        crypto_value = int(latest_item.get('value', 0)) if latest_item.get('value') else None
        crypto_classification = latest_item.get('value_classification', '')
        crypto_timestamp = int(latest_item.get('timestamp', 0)) if latest_item.get('timestamp') else None
        
        if crypto_value is None or crypto_timestamp is None:
            logging.warning("加密货币恐慌指数数据不完整")
            return
        
        # 数据落库时间：用“当前北京时间整分钟”，确保每5分钟都能插入一条记录
        now_utc8 = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        ts_datetime_utc8 = now_utc8.replace(second=0, microsecond=0)
        
        # 获取VIX值
        vix_value = get_vix_value()
        logging.info(f"最新VIX数据: ts={ts_datetime_utc8}, vix_value={vix_value}")
        
        # 保存数据：每5分钟都保存（主要记录VIX实时值），不做“值相同就跳过”的判断
        result = macro_db.save_fear_greed_data(
            ts_datetime=ts_datetime_utc8,
            crypto_value=crypto_value,
            crypto_classification=crypto_classification,
            crypto_timestamp=crypto_timestamp,
            vix_value=vix_value,
            check_update=False
        )
        
        if result == 'saved':
            logging.info(f"恐慌指数数据保存成功: ts={ts_datetime_utc8}, crypto_value={crypto_value}, vix={vix_value}")
        elif result == 'updated':
            logging.info(f"恐慌指数数据更新成功: ts={ts_datetime_utc8}, crypto_value={crypto_value}, vix={vix_value}")
        elif result == 'unchanged':
            logging.debug(f"恐慌指数数据未变化: ts={ts_datetime_utc8}, crypto_value={crypto_value}, vix={vix_value}")
        else:
            logging.warning(f"恐慌指数数据保存失败: ts={ts_datetime_utc8}")
            
    except Exception as e:
        logging.error(f"收集恐慌指数数据失败: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")


def supplement_vix_for_history():
    """
    为历史数据补充VIX值（每5分钟执行一次，补充缺少VIX的记录）
    """
    try:
        # 获取缺少VIX数据的记录（最多100条）
        missing_records = macro_db.get_missing_vix_records(limit=100)
        
        if not missing_records:
            return
        
        logging.info(f"发现 {len(missing_records)} 条缺少VIX数据的记录，开始补充...")
        
        # 获取当前VIX值
        current_vix = get_vix_value()
        
        if current_vix is None:
            logging.warning("无法获取VIX值，跳过补充")
            return
        
        # 尝试获取历史VIX数据（使用yfinance获取历史数据）
        # 注意：yfinance可以获取更长时间的历史数据，但需要根据记录的时间范围来获取
        try:
            # 获取所有缺少VIX的记录的时间范围
            if missing_records:
                # 找到最早和最晚的记录时间
                record_times = []
                for record in missing_records:
                    record_ts = record['ts']
                    if isinstance(record_ts, str):
                        record_ts = datetime.strptime(record_ts, '%Y-%m-%d %H:%M:%S')
                    record_times.append(record_ts)
                
                if record_times:
                    earliest_ts = min(record_times)
                    latest_ts = max(record_times)
                    days_diff = (latest_ts - earliest_ts).days
                    
                    # 根据时间范围获取历史数据（最多获取100天的数据）
                    period_days = min(days_diff + 10, 100)  # 多获取10天作为缓冲
                    
                    # 使用yfinance获取历史数据
                    # period参数：1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
                    if period_days <= 5:
                        period = "5d"
                    elif period_days <= 30:
                        period = "1mo"
                    elif period_days <= 90:
                        period = "3mo"
                    else:
                        period = "1y"
                    
                    logging.info(f"获取VIX历史数据，时间范围: {earliest_ts} 到 {latest_ts}，使用period={period}")
                    # 重新创建Ticker对象，避免使用缓存的旧数据
                    vix_ticker = yf.Ticker("^VIX")
                    hist = vix_ticker.history(period=period, interval="1d")
                    vix_history = {}
                    if not hist.empty:
                        for index, row in hist.iterrows():
                            # 转换为UTC+8时间
                            if hasattr(index, 'tz'):
                                ts_ny = index.tz_convert(ny_tz)
                            else:
                                # 如果没有时区信息，假设是UTC
                                ts_ny = index.replace(tzinfo=pytz.UTC).astimezone(ny_tz)
                            ts_utc8 = ts_ny.astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                            ts_utc8 = ts_utc8.replace(hour=0, minute=0, second=0, microsecond=0)
                            vix_history[ts_utc8] = float(row['Close'])
                        logging.info(f"成功获取 {len(vix_history)} 条VIX历史数据")
                else:
                    vix_history = {}
            else:
                vix_history = {}
        except Exception as e:
            logging.warning(f"获取VIX历史数据失败: {e}")
            import traceback
            logging.warning(f"异常详情: {traceback.format_exc()}")
            vix_history = {}
        
        updated_count = 0
        for record in missing_records:
            try:
                record_ts = record['ts']
                if isinstance(record_ts, str):
                    record_ts = datetime.strptime(record_ts, '%Y-%m-%d %H:%M:%S')
                
                # 尝试从历史数据中获取对应日期的VIX值
                # 将时间调整为当天0点，用于匹配历史数据
                record_date = record_ts.replace(hour=0, minute=0, second=0, microsecond=0)
                
                vix_value = None
                if record_date in vix_history:
                    vix_value = vix_history[record_date]
                else:
                    # 如果历史数据中没有，使用当前VIX值（作为近似值）
                    # 但只对最近的数据使用当前值
                    days_diff = (datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None) - record_ts).days
                    if days_diff <= 7:  # 只对7天内的数据使用当前VIX值
                        vix_value = current_vix
                
                if vix_value is not None:
                    # 更新VIX值
                    result = macro_db.save_fear_greed_data(
                        ts_datetime=record_ts,
                        crypto_value=record.get('crypto_fear_greed_value'),
                        crypto_classification=None,
                        crypto_timestamp=None,
                        vix_value=vix_value,
                        check_update=False
                    )
                    if result in ['saved', 'updated']:
                        updated_count += 1
                        
            except Exception as e:
                logging.warning(f"补充VIX数据失败 (ts={record.get('ts')}): {e}")
                continue
        
        if updated_count > 0:
            logging.info(f"VIX数据补充完成: 更新={updated_count}, 总计={len(missing_records)}")
            
    except Exception as e:
        logging.error(f"补充VIX历史数据失败: {e}")
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
    logging.info("初始化宏观数据数据库表...")
    if not macro_db.create_tables():
        logging.error("数据库表初始化失败，退出程序")
        return
    
    # 首次运行：保存100天的历史数据
    logging.info("首次运行：保存100天加密货币恐慌指数历史数据...")
    save_historical_fear_greed_data()
    
    # 立即执行一次数据收集
    logging.info("立即执行一次数据收集...")
    collect_fear_greed_data()
    
    # 创建调度器
    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    
    # 添加定时任务：每5分钟在整点时间执行（0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55分）
    scheduler.add_job(
        collect_fear_greed_data,
        trigger='cron',
        minute='0,5,10,15,20,25,30,35,40,45,50,55',  # 每5分钟的整点时间
        second=0,  # 整秒执行
        id='collect_fear_greed_data',
        name='收集恐慌指数数据',
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60
    )
    
    # 添加任务监听器
    scheduler.add_listener(job_listener, apscheduler.events.EVENT_JOB_EXECUTED | apscheduler.events.EVENT_JOB_ERROR)
    
    logging.info("宏观数据收集服务启动成功")
    logging.info("定时任务：每5分钟在整点时间收集一次恐慌指数数据（包含加密货币恐慌指数和VIX）")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("收到停止信号，正在关闭服务...")
        scheduler.shutdown()
        macro_db.disconnect()
        logging.info("服务已关闭")


if __name__ == "__main__":
    main()

