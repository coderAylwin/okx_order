#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Odaily RSS 快讯抓取脚本
抓取 Odaily 快讯 RSS feed 并保存到数据库
"""

import os
import logging
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from apscheduler.schedulers.blocking import BlockingScheduler
import configparser
from odaily_database import OdailyDatabaseService
from bs4 import BeautifulSoup
import html as html_module

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
db_user = scraper_config.get('db_user', 'quantify_read_write')
db_password = scraper_config.get('db_password', '02Ya6fPDo@w67UI%sEaDvPXfT')
db_database = scraper_config.get('db_database', 'quantify')

# 初始化数据库服务
db_service = OdailyDatabaseService(
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
        logging.FileHandler(os.path.join(log_dir, 'odaily_rss_scraper.log')),
        logging.StreamHandler()
    ]
)
logging.info("日志系统初始化完成")
logging.info(f"日志文件路径: {os.path.join(log_dir, 'odaily_rss_scraper.log')}")
logging.info(f"调度间隔: 每30秒执行一次 ({cron_timezone})")

# RSS Feed URL
RSS_URL = "https://rss.odaily.news/rss/newsflash"

# 飞书Webhook地址 新闻消息
LARK_WEBHOOK_URL = "https://open.larksuite.com/open-apis/bot/v2/hook/8fb1eee3-5ad1-457a-88e1-3324fedadb67"


def parse_rss_date(date_str):
    """
    解析 RSS 日期格式并转换为 UTC+8 时区
    格式示例: "Tue, 30 Dec 2025 08:52:26 GMT"
    GMT 是 UTC+0，需要转换为 UTC+8（中国时区）
    
    Args:
        date_str: RSS 日期字符串
        
    Returns:
        datetime: 解析后的日期时间对象（UTC+8时区），如果解析失败返回 None
    """
    try:
        # 使用 email.utils.parsedate_to_datetime 解析 RFC 2822 格式的日期
        # 这个方法会自动识别时区并返回带时区信息的 datetime
        date_obj_utc = parsedate_to_datetime(date_str)
        
        # 转换为 UTC+8 时区（北京时间）
        utc8_timezone = timezone(timedelta(hours=8))
        date_obj_utc8 = date_obj_utc.astimezone(utc8_timezone)
        
        # 返回 naive datetime（MySQL 的 DATETIME 类型不存储时区信息）
        # 此时已经是 UTC+8 的时间了
        result = date_obj_utc8.replace(tzinfo=None)
        logging.debug(f"时区转换: GMT {date_obj_utc} -> UTC+8 {result}")
        return result
        
    except (ValueError, TypeError) as e:
        # 如果 parsedate_to_datetime 失败，尝试手动解析
        try:
            # RSS 日期格式: "Tue, 30 Dec 2025 08:52:26 GMT"
            # strptime 解析后是 naive datetime
            date_obj_gmt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S GMT')
            
            # 将 naive datetime 设置为 UTC 时区（GMT = UTC+0）
            date_obj_utc = date_obj_gmt.replace(tzinfo=timezone.utc)
            
            # 转换为 UTC+8 时区（北京时间）
            utc8_timezone = timezone(timedelta(hours=8))
            date_obj_utc8 = date_obj_utc.astimezone(utc8_timezone)
            
            result = date_obj_utc8.replace(tzinfo=None)
            logging.debug(f"时区转换（手动）: GMT {date_obj_gmt} -> UTC+8 {result}")
            return result
        except ValueError:
            logging.warning(f"无法解析日期格式: {date_str}, 错误: {e}")
            return None


def clean_html_text(html_content):
    """
    从 HTML 内容中提取纯文本
    
    Args:
        html_content: HTML 格式的字符串
        
    Returns:
        str: 纯文本内容
    """
    if not html_content:
        return ""
    
    try:
        # 使用 BeautifulSoup 解析 HTML 并提取文本
        soup = BeautifulSoup(html_content, 'html.parser')
        # 移除所有 HTML 标签，获取纯文本
        text = soup.get_text(separator=' ', strip=True)
        # 清理多余的空白字符
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    except Exception as e:
        logging.warning(f"HTML 解析失败: {e}")
        # 如果解析失败，尝试简单的 HTML 实体解码
        return html_module.unescape(html_content)


def send_lark_notification(title, description_text, link):
    """
    发送飞书消息通知
    
    Args:
        title: 新闻标题
        description_text: 新闻内容（纯文本）
        link: 原文链接
    """
    try:
        # 构建消息内容
        content_lines = [
            f"📰 {title}",
            "",
            f"{description_text}",
            "",
            f"🔗 原文地址: {link}"
        ]
        
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
            logging.info(f"✅ 新闻推送成功: {title[:50]}...")
        else:
            logging.warning(f"⚠️ 新闻推送返回异常: {result}")
            
    except requests.exceptions.RequestException as e:
        logging.error(f"新闻推送失败（网络错误）: {e}")
    except Exception as e:
        logging.error(f"新闻推送失败: {e}")


def scrape_odaily_rss():
    """抓取 Odaily RSS 快讯"""
    logging.info("开始执行 scrape_odaily_rss")
    
    try:
        # 发送 HTTP 请求获取 RSS feed
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
        }
        response = requests.get(RSS_URL, headers=headers, timeout=30)
        response.raise_for_status()
        
        # 解析 XML
        root = ET.fromstring(response.content)
        
        # 查找所有 item 元素
        items = root.findall('.//item')
        # logging.info(f"从 RSS feed 中提取到 {len(items)} 条快讯")
        
        # 连接数据库
        if not db_service.connect():
            logging.error("无法连接到数据库")
            return
        
        # 创建表（如果不存在）
        db_service.create_tables()
        
        # 获取已存在的 link 列表
        existing_links = db_service.get_existing_links()
        
        # 先收集所有新快讯（待保存的）
        news_to_save = []
        skipped_count = 0
        
        # 处理每条快讯，收集需要保存的数据
        for item in items:
            try:
                # 提取各个字段
                title_elem = item.find('title')
                link_elem = item.find('link')
                description_elem = item.find('description')
                pub_date_elem = item.find('pubDate')
                category_elem = item.find('category')
                author_elem = item.find('author')
                
                # 获取文本内容
                title = title_elem.text if title_elem is not None and title_elem.text else ""
                link = link_elem.text if link_elem is not None and link_elem.text else ""
                description_html = description_elem.text if description_elem is not None and description_elem.text else ""
                pub_date_str = pub_date_elem.text if pub_date_elem is not None and pub_date_elem.text else ""
                category = category_elem.text if category_elem is not None and category_elem.text else None
                author = author_elem.text if author_elem is not None and author_elem.text else None
                
                # 验证必要字段
                if not title or not link:
                    logging.warning(f"跳过无效的快讯（缺少必要字段）")
                    continue
                
                # 检查是否已存在（判断是否有新的快讯）
                if link in existing_links:
                    logging.debug(f"快讯已存在，跳过: {title[:50]}...")
                    skipped_count += 1
                    continue
                
                # 解析发布时间（GMT转UTC+8）
                pub_date = parse_rss_date(pub_date_str)
                if not pub_date:
                    logging.warning(f"无法解析发布时间，使用当前时间（UTC+8）: {title[:50]}...")
                    # 使用 UTC+8 时区的当前时间
                    utc8_timezone = timezone(timedelta(hours=8))
                    pub_date = datetime.now(utc8_timezone).replace(tzinfo=None)
                
                # 提取纯文本描述
                description_text = clean_html_text(description_html)
                
                # 收集新快讯数据（待排序后保存）
                news_to_save.append({
                    'title': title,
                    'link': link,
                    'description_html': description_html,
                    'description_text': description_text,
                    'pub_date': pub_date,
                    'category': category,
                    'author': author
                })
                
                # logging.info(f"发现新快讯: {title[:50]}... (发布时间: {pub_date})")
                    
            except Exception as e:
                logging.error(f"处理快讯时出错: {e}", exc_info=True)
                continue
        
        # 按照发布时间从远到近排序（升序：最早的在前面）
        news_to_save.sort(key=lambda x: x['pub_date'])
        
        # 保存排序后的快讯数据
        saved_count = 0
        skipped_count = len(items) - len(news_to_save)  # 已存在的快讯数量
        
        for news in news_to_save:
            if db_service.save_newsflash(
                title=news['title'],
                link=news['link'],
                description=news['description_html'],
                description_text=news['description_text'],
                pub_date=news['pub_date'],
                category=news['category'],
                author=news['author']
            ):
                saved_count += 1
                # 保存成功后发送推送通知
                send_lark_notification(
                    title=news['title'],
                    description_text=news['description_text'],
                    link=news['link']
                )
                # logging.info(f"保存快讯: {news['title'][:50]}... (发布时间: {news['pub_date']})")
            else:
                skipped_count += 1
        
        # logging.info(f"快讯抓取完成: 新增 {saved_count} 条，跳过 {skipped_count} 条（按时间从远到近排序保存）")
        db_service.disconnect()
        
    except requests.RequestException as e:
        logging.error(f"HTTP 请求失败: {e}")
    except ET.ParseError as e:
        logging.error(f"XML 解析失败: {e}")
    except Exception as e:
        logging.error(f"抓取 RSS 时发生错误: {e}", exc_info=True)


if __name__ == "__main__":
    # 初始化数据库表
    try:
        if db_service.connect():
            db_service.create_tables()
            db_service.disconnect()
    except Exception as e:
        logging.warning(f"初始化数据库表失败: {e}，将在运行时重试")
    
    # 立即执行一次
    scrape_odaily_rss()
    
    # 设置定时任务：每30秒执行一次
    scheduler = BlockingScheduler(timezone=cron_timezone)
    scheduler.add_job(scrape_odaily_rss, 'interval', seconds=30)
    logging.info("Odaily RSS 调度器启动，每30秒执行一次")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("调度器停止")

