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
    'user': 'quantify_read_write',
    'password': '02Ya6fPDo@w67UI%sEaDvPXfT',
    'database': 'quantify'
}

# Beaconcha.in API 配置
BEACONCHA_API_URL = 'https://beaconcha.in/api/v2/ethereum/queues'
# BEACONCHA_API_TOKEN = 'CEV6oHTg7paT4bhATDYGyDR6dOg1voF1dzEudXJMH4u'
BEACONCHA_API_TOKEN = 'OVy4hxmL5nJnWi72SIBWGfR5pCPSWQAMb1nHL1WdbxL'
BEACONCHA_EPOCH_API_URL = 'https://beaconcha.in/api/v1/epoch/latest'

# Gwei到ETH的转换系数（1 ETH = 10^9 Gwei = 10^18 wei）
# 注意：API返回的值实际上是Gwei单位，不是wei
GWEI_TO_ETH = 10 ** 9

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


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def get_eth_epoch_latest():
    """
    获取ETH最新epoch数据
    
    Returns:
        dict: epoch数据，失败返回None
    """
    try:
        # 尝试两种方式：带token和不带token（v1 API可能是公开的）
        headers_with_token = {
            'Authorization': f'Bearer {BEACONCHA_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        headers_without_token = {
            'Content-Type': 'application/json'
        }
        
        logging.info("开始获取ETH最新epoch数据...")
        
        # 先尝试不带token的方式（v1 API通常是公开的）
        try:
            resp = requests.get(BEACONCHA_EPOCH_API_URL, headers=headers_without_token, timeout=30)
            resp.raise_for_status()
            json_data = resp.json()
            logging.info(f"ETH epoch API请求成功（不带token）")
        except:
            # 如果失败，尝试带token
            logging.info("尝试使用token获取ETH epoch数据...")
            resp = requests.get(BEACONCHA_EPOCH_API_URL, headers=headers_with_token, timeout=30)
            resp.raise_for_status()
            json_data = resp.json()
            logging.info(f"ETH epoch API请求成功（带token）")
        
        # 添加调试日志：打印原始响应
        logging.info(f"ETH epoch API响应: status={json_data.get('status')}")
        logging.info(f"ETH epoch API原始数据（前500字符）: {str(json_data)[:500]}")
        
        # 检查API响应
        if json_data.get('status') != 'OK':
            logging.warning(f"ETH epoch数据：API响应状态错误，status={json_data.get('status')}, 完整响应: {json_data}")
            return None
        
        data = json_data.get('data', {})
        if not isinstance(data, dict):
            logging.warning(f"ETH epoch数据：数据格式错误，data类型={type(data)}, data值={data}")
            return None
        
        # 打印解析后的数据字段
        eligibleether = data.get('eligibleether')
        totalvalidatorbalance = data.get('totalvalidatorbalance')
        averagevalidatorbalance = data.get('averagevalidatorbalance')
        validatorscount = data.get('validatorscount')
        
        logging.info(f"ETH epoch数据字段解析: eligibleether={eligibleether} (type={type(eligibleether)}), "
                    f"totalvalidatorbalance={totalvalidatorbalance} (type={type(totalvalidatorbalance)}), "
                    f"averagevalidatorbalance={averagevalidatorbalance} (type={type(averagevalidatorbalance)}), "
                    f"validatorscount={validatorscount} (type={type(validatorscount)})")
        
        # 检查数据是否有效
        if eligibleether is None and totalvalidatorbalance is None:
            logging.warning(f"ETH epoch数据：关键字段为空，可能数据格式不正确。完整data: {data}")
        
        logging.info("获取到ETH最新epoch数据")
        return data
        
    except requests.exceptions.RequestException as e:
        logging.error(f"ETH epoch数据：网络请求失败 - {e}")
        import traceback
        logging.error(f"请求异常详情: {traceback.format_exc()}")
        return None
    except Exception as e:
        logging.error(f"获取ETH epoch数据失败：{e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        return None


def gwei_to_eth(gwei_value):
    """
    将Gwei转换为ETH（API返回的值实际上是Gwei单位）
    
    Args:
        gwei_value: Gwei值（字符串或整数）
    
    Returns:
        float: ETH值
    """
    try:
        if gwei_value is None:
            return 0.0
        # 处理字符串类型的gwei值
        gwei_int = int(gwei_value) if isinstance(gwei_value, str) else gwei_value
        return float(gwei_int) / GWEI_TO_ETH
    except (ValueError, TypeError) as e:
        logging.warning(f"Gwei转换失败: {gwei_value}, 错误: {e}")
        return 0.0

# 为了保持兼容性，保留wei_to_eth函数名，但实际处理的是Gwei
def wei_to_eth(wei_value):
    """
    将Gwei转换为ETH（API返回的值实际上是Gwei单位，不是真正的wei）
    
    Args:
        wei_value: Gwei值（字符串或整数，虽然函数名叫wei_to_eth，但实际输入是Gwei）
    
    Returns:
        float: ETH值
    """
    return gwei_to_eth(wei_value)


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
        
        # 获取ETH最新epoch数据
        epoch_data = get_eth_epoch_latest()
        
        if not epoch_data:
            logging.warning("未获取到ETH epoch数据，将继续保存质押队列数据")
        
        # 解析deposit_queue数据
        # 注意：需要检查API返回的单位，可能是wei或Gwei
        deposit_queue = queue_data.get('deposit_queue', {})
        deposit_count = deposit_queue.get('deposit_count', 0)
        deposit_balance_raw = deposit_queue.get('balance', '0')
        deposit_estimated_processed_at_timestamp = deposit_queue.get('estimated_processed_at')
        deposit_churn_raw = deposit_queue.get('churn', '0')
        
        # 添加调试日志
        logging.info(f"deposit_queue原始数据: balance={deposit_balance_raw}, churn={deposit_churn_raw}")
        
        # 检查值的大小来判断单位
        # 如果值非常大（> 10^15），可能是wei单位，需要除以10^18转换为ETH
        # 如果值在合理范围内（< 10^10），可能是ETH单位或Gwei单位
        try:
            deposit_balance_raw_float = float(deposit_balance_raw) if deposit_balance_raw else 0.0
            deposit_churn_raw_float = float(deposit_churn_raw) if deposit_churn_raw else 0.0
            
            # 如果值非常大（> 10^15），可能是wei单位，需要转换为ETH
            if deposit_balance_raw_float > 10**15:
                # 可能是wei单位，需要除以10^18
                deposit_balance_eth = deposit_balance_raw_float / (10**18)
                logging.info(f"deposit_balance看起来是wei单位，已转换为ETH: {deposit_balance_eth}")
            elif deposit_balance_raw_float > 10**9:
                # 可能是Gwei单位，需要除以10^9
                deposit_balance_eth = deposit_balance_raw_float / (10**9)
                logging.info(f"deposit_balance看起来是Gwei单位，已转换为ETH: {deposit_balance_eth}")
            else:
                # 已经是ETH单位
                deposit_balance_eth = deposit_balance_raw_float
                logging.info(f"deposit_balance已经是ETH单位: {deposit_balance_eth}")
            
            if deposit_churn_raw_float > 10**15:
                deposit_churn_eth = deposit_churn_raw_float / (10**18)
                logging.info(f"deposit_churn看起来是wei单位，已转换为ETH: {deposit_churn_eth}")
            elif deposit_churn_raw_float > 10**9:
                deposit_churn_eth = deposit_churn_raw_float / (10**9)
                logging.info(f"deposit_churn看起来是Gwei单位，已转换为ETH: {deposit_churn_eth}")
            else:
                deposit_churn_eth = deposit_churn_raw_float
                logging.info(f"deposit_churn已经是ETH单位: {deposit_churn_eth}")
                
        except (ValueError, TypeError) as e:
            deposit_balance_eth = 0.0
            deposit_churn_eth = 0.0
            logging.warning(f"deposit_balance/churn转换失败: balance={deposit_balance_raw}, churn={deposit_churn_raw}, 错误: {e}")
        
        # 转换时间戳
        deposit_estimated_processed_at = timestamp_to_datetime(deposit_estimated_processed_at_timestamp)
        
        # 解析exit_queue数据
        # 注意：需要检查API返回的单位，可能是wei或Gwei
        exit_queue = queue_data.get('exit_queue', {})
        exit_balance_raw = exit_queue.get('balance', '0')
        exit_churn_raw = exit_queue.get('churn', '0')
        exit_estimated_processed_at_timestamp = exit_queue.get('estimated_processed_at')
        
        # 兼容exit_count字段（可能是exit_count或count）
        exit_count = exit_queue.get('exit_count') or exit_queue.get('count', 0)
        
        # 添加调试日志
        logging.info(f"exit_queue原始数据: balance={exit_balance_raw}, churn={exit_churn_raw}")
        
        # 检查值的大小来判断单位
        try:
            exit_balance_raw_float = float(exit_balance_raw) if exit_balance_raw else 0.0
            exit_churn_raw_float = float(exit_churn_raw) if exit_churn_raw else 0.0
            
            # 如果值非常大（> 10^15），可能是wei单位，需要转换为ETH
            if exit_balance_raw_float > 10**15:
                # 可能是wei单位，需要除以10^18
                exit_balance_eth = exit_balance_raw_float / (10**18)
                logging.info(f"exit_balance看起来是wei单位，已转换为ETH: {exit_balance_eth}")
            elif exit_balance_raw_float > 10**9:
                # 可能是Gwei单位，需要除以10^9
                exit_balance_eth = exit_balance_raw_float / (10**9)
                logging.info(f"exit_balance看起来是Gwei单位，已转换为ETH: {exit_balance_eth}")
            else:
                # 已经是ETH单位
                exit_balance_eth = exit_balance_raw_float
                logging.info(f"exit_balance已经是ETH单位: {exit_balance_eth}")
            
            if exit_churn_raw_float > 10**15:
                exit_churn_eth = exit_churn_raw_float / (10**18)
                logging.info(f"exit_churn看起来是wei单位，已转换为ETH: {exit_churn_eth}")
            elif exit_churn_raw_float > 10**9:
                exit_churn_eth = exit_churn_raw_float / (10**9)
                logging.info(f"exit_churn看起来是Gwei单位，已转换为ETH: {exit_churn_eth}")
            else:
                exit_churn_eth = exit_churn_raw_float
                logging.info(f"exit_churn已经是ETH单位: {exit_churn_eth}")
                
        except (ValueError, TypeError) as e:
            exit_balance_eth = 0.0
            exit_churn_eth = 0.0
            logging.warning(f"exit_balance/churn转换失败: balance={exit_balance_raw}, churn={exit_churn_raw}, 错误: {e}")
        
        # 转换退出预计完成时间
        exit_estimated_processed_at = timestamp_to_datetime(exit_estimated_processed_at_timestamp)
        
        # 解析withdrawal_sweep数据
        withdrawal_sweep = queue_data.get('withdrawal_sweep', {})
        withdrawal_sweep_delay = withdrawal_sweep.get('estimated_sweep_delay')
        withdrawal_sweep_last_validator_index = withdrawal_sweep.get('last_swept_validator_index')
        
        # 解析finality状态
        finality_status = queue_data.get('finality', '')
        
        # 解析epoch数据（将wei转换为ETH，保留两位小数）
        eligibleether = None
        totalvalidatorbalance = None
        averagevalidatorbalance = None
        validatorscount = None
        
        if epoch_data:
            # 获取wei值
            eligibleether_wei = epoch_data.get('eligibleether')
            totalvalidatorbalance_wei = epoch_data.get('totalvalidatorbalance')
            averagevalidatorbalance_wei = epoch_data.get('averagevalidatorbalance')
            validatorscount = epoch_data.get('validatorscount')
            
            # 将wei转换为ETH并保留两位小数
            if eligibleether_wei is not None:
                eligibleether = round(wei_to_eth(eligibleether_wei), 2)
            if totalvalidatorbalance_wei is not None:
                totalvalidatorbalance = round(wei_to_eth(totalvalidatorbalance_wei), 2)
            if averagevalidatorbalance_wei is not None:
                averagevalidatorbalance = round(wei_to_eth(averagevalidatorbalance_wei), 2)
            
        else:
            logging.warning("epoch_data为空，新字段将保存为NULL")
        
        # 添加调试日志：打印所有要保存的值
        logging.info(f"准备保存ETH质押队列数据:")
        logging.info(f"  deposit_balance_eth={deposit_balance_eth}")
        logging.info(f"  deposit_churn_eth={deposit_churn_eth}")
        logging.info(f"  exit_balance_eth={exit_balance_eth}")
        logging.info(f"  exit_churn_eth={exit_churn_eth}")
        
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
            exit_estimated_processed_at=exit_estimated_processed_at,
            exit_churn_eth=exit_churn_eth,
            withdrawal_sweep_delay=withdrawal_sweep_delay,
            withdrawal_sweep_last_validator_index=withdrawal_sweep_last_validator_index,
            finality_status=finality_status,
            eligibleether=eligibleether,
            totalvalidatorbalance=totalvalidatorbalance,
            averagevalidatorbalance=averagevalidatorbalance,
            validatorscount=validatorscount,
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
        
        # 每30分钟执行一次，在整点时间（0, 30分）
        scheduler.add_job(
            collect_eth_staking_data,
            trigger='cron',
            minute='0,30',
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

