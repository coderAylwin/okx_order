import requests
import json
import mysql.connector
from mysql.connector import Error
import time
import logging
import schedule
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# ======================================
# 配置部分
# ======================================

API_KEY = "a0204e72-4450-4b42-805f-fb53abcd7a4d"  # 你的 Arkham API Key
API_BASE = "https://api.arkm.com"

HEADERS = {
    "API-Key": API_KEY,
    "Accept": "application/json"
}

# 要监控的实体（Arkham entity slug，小写连字符）
MONITORED_ENTITIES = [
    "binance",
    "okx",
    "coinbase",
    "bybit",
    "kraken",
    "blackrock",
    "grayscale",
    "microstrategy",
    "gemini",
    "bitfinex"
    # 可继续添加，例如: "gemini", "bitfinex", "huobi", "cumberland", "jump-trading"
]

# 每个链的筛选规则（可随时修改）
CHAIN_ASSET_RULES = {
    "bitcoin": {
        "allowed_symbols": ["BTC"],
        "min_usd_value": 1000000
    },
    "ethereum": {
        "allowed_symbols": ["ETH", "USDT", "USDC", "WBETH", "USD1", "WETH"],
        "min_usd_value": 500000
    },
    "solana": {
        "allowed_symbols": ["SOL", "USDT", "USDC", "BNSOL", "JUPSOL", "mSOL"],
        "min_usd_value": 200000
    },
    "tron": {
        "allowed_symbols": ["USDT"],
        "min_usd_value": 1000000
    }
}

# 数据库连接配置（请根据你的实际情况修改）
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',          # 或 'localhost'、远程 IP
    'port': 3306,
    'database': 'quantify',
    'user': 'payment_pro',               # 你的 MySQL 用户名
    'password': 'nS4kO7tG1jH7cI6oR4b',       # 你的 MySQL 密码
    'raise_on_warnings': True
}

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ======================================
# 工具函数
# ======================================

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        logger.error(f"数据库连接失败: {e}")
        return None

def fetch_entity_balances(entity_slug):
    url = f"{API_BASE}/balances/entity/{entity_slug}"
    params = {"chains": "bitcoin,ethereum,solana,tron"}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=25)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"拉取 {entity_slug} 失败: {e}")
        return None

def save_filtered_data(entity_slug, data):
    if not data or "balances" not in data:
        logger.warning(f"{entity_slug} 返回数据为空或无 balances 字段")
        return 0

    conn = get_db_connection()
    if not conn:
        return 0

    cursor = conn.cursor()
    inserted_raw = False
    inserted_filtered = 0

    try:
        # -----------------------
        # 1. 存储原始完整数据（raw）
        # -----------------------
        quote_time_str = None
        for chain_assets in data.get("balances", {}).values():
            if chain_assets and isinstance(chain_assets, list) and len(chain_assets) > 0 and "quoteTime" in chain_assets[0]:
                raw_quote = chain_assets[0]["quoteTime"]  # e.g. '2026-01-28T07:22:45.905Z'
                try:
                    # 解析 UTC 时间
                    dt_utc = datetime.fromisoformat(raw_quote.replace('Z', '+00:00'))
                    # 加 8 小时 → UTC+8
                    dt_local = dt_utc + timedelta(hours=8)
                    # 转字符串（到秒）
                    quote_time_str = dt_local.strftime('%Y-%m-%d %H:%M:%S')
                except Exception as e:
                    logger.warning(f"quoteTime 转换失败: {raw_quote}, 错误: {e}")
                break

        # 使用 Decimal 确保大数值精度（支持上千亿）
        total_usd = Decimal('0')
        for chain_assets in data.get("balances", {}).values():
            for asset in chain_assets:
                usd_val = asset.get("usd", 0) or 0
                try:
                    # 转换为 Decimal，确保精度
                    total_usd += Decimal(str(usd_val))
                except (ValueError, InvalidOperation, TypeError) as e:
                    logger.warning(f"资产USD值转换失败: {usd_val}, 错误: {e}")
                    continue

        logger.info(f"{entity_slug} 计算的总USD值: {total_usd:,.2f}")
        
        # 确保 Decimal 格式化为标准格式（2位小数，不使用科学计数法）
        # 使用 quantize 确保精度为2位小数
        total_usd_formatted = total_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_usd_str = format(total_usd_formatted, 'f')  # 使用 'f' 格式，不使用科学计数法
        
        logger.debug(f"格式化后的 total_usd 字符串: {total_usd_str}")

        # 筛选 raw_balances：只保留符合 CHAIN_ASSET_RULES 规则的数据
        filtered_balances = {}
        for chain, assets in data.get("balances", {}).items():
            if chain not in CHAIN_ASSET_RULES:
                continue
            
            rules = CHAIN_ASSET_RULES[chain]
            allowed_symbols = set(rules.get("allowed_symbols", []))
            min_usd = rules.get("min_usd_value", 0)
            
            filtered_assets = []
            for asset in assets:
                symbol = asset.get("symbol")
                usd_raw = asset.get("usd", 0) or 0
                
                try:
                    usd = Decimal(str(usd_raw))
                except (ValueError, InvalidOperation, TypeError):
                    continue
                
                # 只保留符合规则的资产
                if symbol in allowed_symbols and usd >= Decimal(str(min_usd)):
                    filtered_assets.append(asset)
            
            if filtered_assets:
                filtered_balances[chain] = filtered_assets
        
        cursor.execute("""
            INSERT INTO arkham_raw_fetch 
            (fetch_at, quote_time, source_type, entity_slug, total_usd, raw_total_balance, raw_total_24h_ago, raw_balances)
            VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s)
        """, (
            quote_time_str,
            "exchange",  # 可根据实体动态判断 exchange/institution
            entity_slug,
            total_usd_str,  # 格式化后的字符串，确保格式正确
            json.dumps(data.get("totalBalance", {})),
            json.dumps(data.get("totalBalance24hAgo", {})),
            json.dumps(filtered_balances)  # 只保存筛选后的数据
        ))
        inserted_raw = True

        # -----------------------
        # 2. 存储筛选后的明细
        # -----------------------
        insert_filtered_sql = """
            INSERT INTO arkham_asset_holdings
            (fetch_at, entity_slug, chain, asset_symbol, asset_id, balance, usd_value, price, price_change_24h, price_change_pct)
            VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        rows_to_insert = []

        for chain, assets in data.get("balances", {}).items():
            if chain not in CHAIN_ASSET_RULES:
                continue

            rules = CHAIN_ASSET_RULES[chain]
            allowed_symbols = set(rules.get("allowed_symbols", []))
            min_usd = rules.get("min_usd_value", 0)

            for asset in assets:
                symbol = asset.get("symbol")
                usd_raw = asset.get("usd", 0) or 0
                
                # 转换为 Decimal 进行比较和存储
                try:
                    usd = Decimal(str(usd_raw))
                except (ValueError, InvalidOperation, TypeError):
                    logger.warning(f"资产 {symbol} USD值转换失败: {usd_raw}")
                    continue

                if symbol in allowed_symbols and usd >= Decimal(str(min_usd)):
                    # 将所有数值字段转换为 Decimal 并格式化（确保精度和格式正确）
                    def format_decimal(value, decimal_places=2):
                        """格式化 Decimal 值为字符串，确保精度和格式正确"""
                        if value is None:
                            return None
                        try:
                            if isinstance(value, Decimal):
                                formatted = value.quantize(Decimal('0.' + '0' * decimal_places), rounding=ROUND_HALF_UP)
                            else:
                                formatted = Decimal(str(value)).quantize(Decimal('0.' + '0' * decimal_places), rounding=ROUND_HALF_UP)
                            return format(formatted, 'f')  # 使用 'f' 格式，不使用科学计数法
                        except (ValueError, InvalidOperation, TypeError):
                            return None
                    
                    try:
                        balance = Decimal(str(asset.get("balance"))) if asset.get("balance") else None
                    except (ValueError, InvalidOperation, TypeError):
                        balance = None
                    
                    try:
                        price = Decimal(str(asset.get("price"))) if asset.get("price") else None
                    except (ValueError, InvalidOperation, TypeError):
                        price = None
                    
                    try:
                        price_change_24h = Decimal(str(asset.get("priceChange24h"))) if asset.get("priceChange24h") else None
                    except (ValueError, InvalidOperation, TypeError):
                        price_change_24h = None
                    
                    try:
                        price_change_pct = Decimal(str(asset.get("priceChange24hPercent"))) if asset.get("priceChange24hPercent") else None
                    except (ValueError, InvalidOperation, TypeError):
                        price_change_pct = None
                    
                    # 格式化所有 Decimal 值
                    # balance: DECIMAL(36,12) - 12位小数
                    # usd_value: DECIMAL(30,2) - 2位小数
                    # price: DECIMAL(30,8) - 8位小数
                    # price_change_24h: DECIMAL(18,4) - 4位小数
                    # price_change_pct: DECIMAL(18,6) - 6位小数
                    rows_to_insert.append((
                        entity_slug,
                        chain,
                        symbol,
                        asset.get("id"),
                        format_decimal(balance, 12) if balance is not None else None,
                        format_decimal(usd, 2) if usd is not None else None,  # usd_value: DECIMAL(30,2)
                        format_decimal(price, 8) if price is not None else None,  # price: DECIMAL(30,8)
                        format_decimal(price_change_24h, 4) if price_change_24h is not None else None,  # DECIMAL(18,4)
                        format_decimal(price_change_pct, 6) if price_change_pct is not None else None  # DECIMAL(18,6)
                    ))

        if rows_to_insert:
            cursor.executemany(insert_filtered_sql, rows_to_insert)
            inserted_filtered = len(rows_to_insert)

        conn.commit()

        log_msg = f"{entity_slug} 保存完成："
        if inserted_raw:
            log_msg += "1 条 raw 记录 | "
        log_msg += f"{inserted_filtered} 条筛选资产记录"
        logger.info(log_msg)

    except Error as e:
        logger.error(f"MySQL 保存失败 {entity_slug}: {e}")
        conn.rollback()
        inserted_filtered = 0
    finally:
        cursor.close()
        conn.close()

    return inserted_filtered

# ======================================
# 主任务
# ======================================

def job():
    start_time = datetime.now()
    logger.info(f"========== Arkham 余额监控任务开始 @ {start_time.strftime('%Y-%m-%d %H:%M:%S')} ==========")

    total_inserted = 0
    success_entities = 0

    for entity in MONITORED_ENTITIES:
        logger.info(f"处理实体: {entity}")
        data = fetch_entity_balances(entity)
        if data:
            count = save_filtered_data(entity, data)
            if count > 0:
                total_inserted += count
                success_entities += 1
        time.sleep(3)  # 防止 rate limit 过快

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(
        f"任务结束 | 成功实体: {success_entities}/{len(MONITORED_ENTITIES)} | "
        f"总插入筛选记录: {total_inserted} | 用时: {duration:.1f} 秒"
    )

# ======================================
# 启动
# ======================================

if __name__ == "__main__":
    logger.info("Arkham 余额监控程序启动...")
    
    # 初次立即执行一次（方便测试）
    job()

    # 定时任务：每 1 小时执行
    schedule.every(1).hours.do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)