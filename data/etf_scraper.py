#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一ETF数据抓取脚本
支持BTC、ETH、SOL三种币种的ETF数据抓取
每小时执行一次，更新所有币种数据
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import os
import logging
import re
from apscheduler.schedulers.blocking import BlockingScheduler
import configparser
from datetime import datetime
from etf_database import ETFDatabaseService

# ETF配置：币种名称、URL、coin_type
ETF_CONFIGS = {
    'BTC': {
        'name': 'Bitcoin',
        'url': 'https://www.coinglass.com/zh/bitcoin-etf',
        'coin_type': 'BTC',
        'simple_header': True  # BTC表头简单，直接get_text即可
    },
    'ETH': {
        'name': 'Ethereum',
        'url': 'https://www.coinglass.com/zh/eth-etf',
        'coin_type': 'ETH',
        'simple_header': False  # ETH表头需要处理嵌套div
    },
    'SOL': {
        'name': 'Solana',
        'url': 'https://www.coinglass.com/zh/sol-etf',
        'coin_type': 'SOL',
        'simple_header': False  # SOL表头需要处理嵌套div
    }
}

# 读取配置文件
config = configparser.ConfigParser()
# 使用脚本所在目录的配置文件
config_file = os.path.join(os.path.dirname(__file__), 'config.ini')
config.read(config_file)
if 'liq_scraper' not in config:
    raise KeyError(f"配置文件中缺少 [liq_scraper] 节，请检查配置文件: {config_file}")
scraper_config = config['liq_scraper']
cron_timezone = scraper_config.get('timezone', 'Asia/Shanghai')
log_dir = os.path.expanduser(scraper_config.get('log_dir', '~/liq_data'))

# 数据库配置
db_host = scraper_config.get('db_host', 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com')
db_port = int(scraper_config.get('db_port', 3306))
db_user = scraper_config.get('db_user', 'payment_pro')
db_password = scraper_config.get('db_password', 'nS4kO7tG1jH7cI6oR4b')
db_database = scraper_config.get('db_database', 'quantify')

# 初始化数据库服务
db_service = ETFDatabaseService(
    host=db_host,
    port=db_port,
    user=db_user,
    password=db_password,
    database=db_database
)

# 设置日志
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'etf_scraper.log')),
        logging.StreamHandler()
    ]
)
logging.info("ETF抓取日志系统初始化完成")
logging.info(f"日志文件路径: {os.path.join(log_dir, 'etf_scraper.log')}")
logging.info(f"调度间隔: 每小时执行一次 ({cron_timezone})")

# 设置 Chrome 选项
chrome_options = Options()
chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--headless=new")


def is_valid_numeric_value(value):
    """
    验证值是否为有效的数值
    支持格式：数字、+数字、-数字、带"万"单位的数字（如"1.2万"、"+1.2万"、"-1.2万"）
    
    Args:
        value: 要验证的值（字符串或字典，字典包含'value'键）
    
    Returns:
        bool: 如果为有效数值返回True，否则返回False
    """
    if not value:
        return False
    
    # 如果是字典，提取value字段
    if isinstance(value, dict):
        value_str = value.get('value', '')
    else:
        value_str = str(value)
    
    if not value_str or not isinstance(value_str, str):
        return False
    
    value_str = value_str.strip()
    
    # 空字符串或"0"视为无效（因为可能是占位符）
    if not value_str or value_str == '0':
        return False
    
    # 检查是否为有效数值格式：
    # 1. 可以有+或-开头
    # 2. 可以有"万"单位
    # 3. 必须是数字（可以有小数点）
    
    # 移除符号和"万"字
    test_str = value_str
    if test_str.startswith('+') or test_str.startswith('-'):
        test_str = test_str[1:]
    
    # 移除"万"字
    test_str = test_str.replace('万', '').strip()
    
    # 检查是否为空（说明只有符号或单位，没有数字）
    if not test_str:
        return False
    
    # 尝试转换为浮点数验证是否为有效数字
    try:
        # 移除可能的逗号（千位分隔符）
        test_str = test_str.replace(',', '')
        float(test_str)
        return True
    except (ValueError, TypeError):
        return False


def has_valid_data(etf_data):
    """
    检查ETF数据字典中是否包含至少一个有效数值
    
    Args:
        etf_data: ETF数据字典，键为ETF名称，值为包含'value'的字典
    
    Returns:
        bool: 如果至少有一个有效数值返回True，否则返回False
    """
    if not etf_data or not isinstance(etf_data, dict):
        return False
    
    for etf_name, value_data in etf_data.items():
        if is_valid_numeric_value(value_data):
            return True
    
    return False


def extract_header_names(header_row, simple_header=False):
    """
    提取表头列名
    
    Args:
        header_row: BeautifulSoup的tr元素
        simple_header: 是否为简单表头（BTC为True，ETH/SOL为False）
    
    Returns:
        list: ETF名称列表
    """
    etf_names = []
    headers = header_row.find_all('th')
    # 跳过第一列（时间），提取从第二列开始的所有列名
    for header in headers[1:]:  # 从第二列开始到最后
        if simple_header:
            # BTC: 直接获取文本
            header_text = header.get_text(strip=True)
        else:
            # ETH/SOL: 处理表头可能包含多个div的情况，提取第一个文本
            header_div = header.find('div')
            if header_div:
                # 查找第一个子div的文本
                first_div = header_div.find('div')
                if first_div:
                    header_text = first_div.get_text(strip=True)
                else:
                    header_text = header_div.get_text(strip=True)
            else:
                header_text = header.get_text(strip=True)
        
        if header_text:
            etf_names.append(header_text)
    
    return etf_names


def extract_date_from_cell(date_cell, simple_header=False):
    """
    从日期单元格提取日期文本，并检查是否包含两个日期
    
    Args:
        date_cell: BeautifulSoup的td元素
        simple_header: 是否为简单表头（BTC为True，ETH/SOL为False）
    
    Returns:
        tuple: (date_text, has_two_dates)
            date_text: 日期文本
            has_two_dates: 是否包含两个日期（如果是，应跳过该行）
    """
    if simple_header:
        # BTC: 直接获取文本
        date_text = date_cell.get_text(strip=True)
        # 检查是否包含两个日期
        if date_text and ' ' in date_text and len(date_text.split()) >= 2:
            date_parts = date_text.split()
            date_count = sum(1 for part in date_parts if '-' in part and len(part.split('-')) == 3)
            has_two_dates = date_count >= 2
        else:
            has_two_dates = False
    else:
        # ETH/SOL: 先获取完整文本（不strip，保留所有空白字符以便检查）
        full_date_text = date_cell.get_text()
        # 使用正则表达式匹配日期格式 YYYY-MM-DD，检查是否有两个或更多日期
        date_pattern = r'\d{4}-\d{2}-\d{2}'
        dates_found = re.findall(date_pattern, full_date_text)
        has_two_dates = len(dates_found) >= 2
        
        # 提取第一个日期（用于后续处理）
        if dates_found:
            date_text = dates_found[0]
        else:
            # 如果没有匹配到日期格式，尝试从div中提取
            date_div = date_cell.find('div')
            if date_div:
                # 查找第一个子div（日期）
                first_date_div = date_div.find('div')
                if first_date_div:
                    date_text = first_date_div.get_text(strip=True)
                else:
                    date_text = date_div.get_text(strip=True)
            else:
                date_text = full_date_text.strip()
    
    return date_text, has_two_dates


def scrape_etf_data_for_coin(coin_symbol):
    """
    抓取指定币种的ETF数据
    
    Args:
        coin_symbol: 币种符号 ('BTC', 'ETH', 'SOL')
    """
    if coin_symbol not in ETF_CONFIGS:
        logging.error(f"不支持的币种: {coin_symbol}")
        return
    
    config = ETF_CONFIGS[coin_symbol]
    coin_type = config['coin_type']
    url = config['url']
    coin_name = config['name']
    simple_header = config['simple_header']
    
    logging.info(f"开始执行 {coin_name} ETF数据抓取 ({coin_symbol})")
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get(url)
        
        # 等待表格容器加载
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "ant-table-container")))
        
        # 延时 + 刷新，确保动态数据加载
        time.sleep(10)
        driver.refresh()
        time.sleep(5)
        
        # 解析源代码
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 查找表格容器
        table_container = soup.find('div', class_='ant-table-container')
        if not table_container:
            logging.error(f"{coin_name} ETF: 未找到表格容器")
            return
        
        # 查找表头，获取所有列名
        thead = table_container.find('thead')
        etf_names = []
        if thead:
            header_row = thead.find('tr')
            if header_row:
                etf_names = extract_header_names(header_row, simple_header)
        
        logging.info(f"{coin_name} ETF: 找到数据列: {etf_names} (共 {len(etf_names)} 列)")
        
        # 查找表格数据
        tbody = table_container.find('tbody')
        if not tbody:
            logging.error(f"{coin_name} ETF: 未找到表格数据")
            return
        
        # 提取所有数据行（排除测量行）
        daily_rows = []  # 每日数据
        total_row = None  # 总计数据
        
        rows = tbody.find_all('tr', class_='ant-table-row')
        
        for row in rows:
            # 获取行的 data-row-key 属性（日期或"总计"）
            row_key = row.get('data-row-key', '')
            
            # 提取该行的所有单元格
            cells = row.find_all('td')
            if not cells:
                continue
            
            # 第一列是日期或"总计"
            date_cell = cells[0]
            date_text, has_two_dates = extract_date_from_cell(date_cell, simple_header)
            
            # 过滤掉包含两个日期的行（这是近一年的数据，不需要保存）
            if has_two_dates:
                logging.info(f"{coin_name} ETF: 跳过包含两个日期的行: {date_text}")
                continue
            
            # 判断是总计行还是日期行
            # SOL还需要检查 row_key == 'total'
            if coin_symbol == 'SOL':
                is_total_row = (row_key == '总计' or row_key == 'total' or date_text == '总计' or '总计' in date_text)
            else:
                is_total_row = (row_key == '总计' or date_text == '总计' or '总计' in date_text)
            
            # 提取数据列（跳过第一列，从第二列开始到最后一列）
            row_data = {'date': date_text, 'is_total': is_total_row}
            
            for i, cell in enumerate(cells[1:], start=1):
                # 查找 Number div（注意：class可能包含多个类名，如 "Number undefined rise-color"）
                all_divs = cell.find_all('div')
                number_div = None
                for div in all_divs:
                    div_classes = div.get('class', [])
                    if isinstance(div_classes, list) and any('Number' in cls for cls in div_classes):
                        number_div = div
                        break
                    elif isinstance(div_classes, str) and 'Number' in div_classes:
                        number_div = div
                        break
                
                if number_div:
                    value = number_div.get_text(strip=True)
                    # 获取所有类名并判断是涨还是跌
                    classes = number_div.get('class', [])
                    class_str = ' '.join(classes) if isinstance(classes, list) else str(classes)
                    is_rise = 'rise-color' in class_str
                    is_fall = 'fall-color' in class_str
                    
                    # 获取对应的ETF名称（如果索引有效）
                    etf_name = etf_names[i-1] if i-1 < len(etf_names) else f'COL_{i-1}'
                    row_data[etf_name] = {
                        'value': value,
                        'type': 'rise' if is_rise else ('fall' if is_fall else 'neutral')
                    }
                else:
                    # 如果没有Number div，直接获取文本
                    etf_name = etf_names[i-1] if i-1 < len(etf_names) else f'COL_{i-1}'
                    cell_text = cell.get_text(strip=True)
                    row_data[etf_name] = {
                        'value': cell_text,
                        'type': 'neutral'
                    }
            
            if is_total_row:
                total_row = row_data
            else:
                daily_rows.append(row_data)
        
        # 打印数据
        logging.info(f"{coin_name} ETF: 共提取 {len(daily_rows)} 行每日数据")
        if total_row:
            logging.info(f"{coin_name} ETF: 找到总计数据行")
        
        # 保存数据到数据库
        try:
            # 检查是否有数据需要保存
            if not daily_rows and not total_row:
                logging.warning(f"{coin_name} ETF: 没有抓取到任何数据，跳过保存")
                return
            
            # 初始化数据库连接并创建表
            if db_service.connect():
                db_service.create_tables()
                
                # 查询数据库中已存在的日期
                existing_dates = db_service.get_existing_dates(coin_type=coin_type)
                
                # 准备要保存的每日数据（过滤已存在的日期，并按日期从小到大排序）
                new_daily_rows = []
                for row in daily_rows:
                    date_str = row['date']
                    # 解析日期，检查格式是否正确
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        date_key = date_obj.strftime('%Y-%m-%d')
                        
                        # 只保存不存在的日期
                        if date_key not in existing_dates:
                            # 构建ETF数据字典（排除date和is_total字段）
                            etf_data = {k: v for k, v in row.items() if k not in ['date', 'is_total']}
                            # 验证数据是否有效
                            if has_valid_data(etf_data):
                                new_daily_rows.append((date_obj, row))
                            else:
                                logging.warning(f"{coin_name} ETF: 日期 {date_str} 的数据无效（无有效数值），跳过保存")
                    except ValueError:
                        logging.warning(f"{coin_name} ETF: 日期格式不正确，跳过: {date_str}")
                        continue
                
                # 按日期从小到大排序（从旧到新）
                new_daily_rows.sort(key=lambda x: x[0])
                
                # 保存新的每日数据
                saved_count = 0
                for date_obj, row in new_daily_rows:
                    date_str = date_obj.strftime('%Y-%m-%d')
                    # 构建ETF数据字典（排除date和is_total字段）
                    etf_data = {k: v for k, v in row.items() if k not in ['date', 'is_total']}
                    if db_service.save_daily_data(date_str, etf_data, coin_type=coin_type):
                        saved_count += 1
                
                if saved_count > 0:
                    logging.info(f"{coin_name} ETF: 共保存 {saved_count} 条新的每日数据")
                else:
                    logging.info(f"{coin_name} ETF: 没有新的有效每日数据需要保存")
                
                # 保存总计数据（使用当前日期作为日期字段）
                if total_row:
                    # 构建ETF数据字典（排除date、is_total和总计字段）
                    etf_data = {k: v for k, v in total_row.items() if k not in ['date', 'is_total', '总计']}
                    # 验证总计数据是否有效
                    if has_valid_data(etf_data):
                        today_str = datetime.now().strftime('%Y-%m-%d')
                        db_service.save_total_data(today_str, etf_data, coin_type=coin_type)
                        logging.info(f"{coin_name} ETF: 总计数据已保存到数据库")
                    else:
                        logging.warning(f"{coin_name} ETF: 总计数据无效（无有效数值），跳过保存")
                
                logging.info(f"{coin_name} ETF: 数据保存流程完成")
                db_service.disconnect()
        except Exception as db_error:
            logging.error(f"{coin_name} ETF: 保存数据到数据库失败: {str(db_error)}", exc_info=True)
    
    except Exception as e:
        logging.error(f"{coin_name} ETF: 发生错误: {str(e)}", exc_info=True)
    
    finally:
        driver.quit()


def scrape_all_etf_data():
    """
    抓取所有币种的ETF数据
    """
    logging.info("=" * 80)
    logging.info("开始执行ETF数据抓取任务（所有币种）")
    logging.info("=" * 80)
    
    for coin_symbol in ETF_CONFIGS.keys():
        try:
            scrape_etf_data_for_coin(coin_symbol)
            logging.info(f"{coin_symbol} ETF数据抓取完成")
            logging.info("-" * 80)
        except Exception as e:
            logging.error(f"{coin_symbol} ETF数据抓取失败: {str(e)}", exc_info=True)
            logging.info("-" * 80)
    
    logging.info("所有ETF数据抓取任务完成")
    logging.info("=" * 80)


if __name__ == "__main__":
    # 初始化数据库表
    try:
        if db_service.connect():
            db_service.create_tables()
            db_service.disconnect()
            logging.info("数据库表初始化完成")
    except Exception as e:
        logging.warning(f"初始化数据库表失败: {e}，将在运行时重试")
    
    # 立即执行一次
    scrape_all_etf_data()
    
    # 设置调度器，每小时执行一次
    scheduler = BlockingScheduler(timezone=cron_timezone)
    scheduler.add_job(scrape_all_etf_data, 'interval', hours=1)
    logging.info("ETF抓取调度器启动，每小时执行一次")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("调度器停止")

