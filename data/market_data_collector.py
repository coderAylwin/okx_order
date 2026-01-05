#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX市场数据收集服务
独立运行，定时收集并保存市场数据到数据库
包括：Taker主动量、资金费率、持仓量、多空比、宏观经济数据、爆仓数据（WebSocket实时）
"""

import requests
import time
import logging
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from tenacity import retry, stop_after_attempt, wait_fixed
import json
# 使用 websocket-client 库（需要安装: pip install websocket-client）
# 注意：不要安装 websocket 包，要安装 websocket-client 包
try:
    import websocket
    if not hasattr(websocket, 'WebSocketApp'):
        raise ImportError(
            "错误：检测到错误的 websocket 模块。\n"
            "请卸载 websocket 并安装 websocket-client：\n"
            "  pip uninstall websocket\n"
            "  pip install websocket-client"
        )
except ImportError as e:
    raise ImportError(
        "请安装 websocket-client 库：\n"
        "  pip install websocket-client\n"
        f"原始错误: {e}"
    )
from apscheduler.schedulers.blocking import BlockingScheduler

from market_data_database import MarketDataDatabaseService
from liquidation_database import LiquidationDatabaseService

# ==================== 配置 ====================
# 数据库配置
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',     # 本地MySQL
    'port': 3306,
    'user': 'payment_pro',
    'password': 'nS4kO7tG1jH7cI6oR4b',# 请修改为您的MySQL密码
    'database': 'quantify'
}

FRED_KEY = "dbb32d7a650dcfdc831ff5c26693100b"

# 支持的币种列表
SUPPORTED_COINS = {
    'BTC': {
        'symbol': 'BTC-USDT-SWAP',
        'name': 'BTC'
    },
    'ETH': {
        'symbol': 'ETH-USDT-SWAP',
        'name': 'ETH'
    },
    'SOL': {
        'symbol': 'SOL-USDT-SWAP',
        'name': 'SOL'
    }
}

# 时区配置
TIMEZONE = 'Asia/Shanghai'

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('market_data_collector.log'),
        logging.StreamHandler()
    ]
)

# 初始化数据库服务
market_db = MarketDataDatabaseService(**DB_CONFIG)
liquidation_db = LiquidationDatabaseService(**DB_CONFIG)


# ==================== 爆仓数据WebSocket监听器 ====================
class OKXLiquidationListener:
    """OKX爆仓数据WebSocket监听器（支持多币种）"""
    
    def __init__(self):
        self.ws = None
        self.thread = None
        self.ping_thread = None
        self.lock = threading.Lock()
        self.is_running = False
        self.last_pong_time = time.time()
        self.ping_interval = 20
        self.db_service = liquidation_db
        
        # 连接数据库并创建表
        if self.db_service.connect():
            self.db_service.create_tables()
        
        # 匹配币种的函数
        def match_coin_by_uly(uly):
            if not uly:
                return None
            coin_name = uly.replace('-USDT', '').upper()
            return coin_name if coin_name in SUPPORTED_COINS else None
        
        self.match_coin_by_uly = match_coin_by_uly
    
    def on_message(self, ws, message):
        try:
            if message == "pong":
                self.last_pong_time = time.time()
                return
            
            data = json.loads(message)
            
            if 'event' in data:
                if data['event'] == 'subscribe':
                    logging.info(f"WebSocket 订阅成功：{data.get('arg', {})}")
                elif data['event'] == 'pong':
                    self.last_pong_time = time.time()
                    return
                elif data['event'] == 'error':
                    logging.error(f"WebSocket 订阅错误：{data.get('msg', '未知错误')}")
                    return
            
            if 'data' in data and isinstance(data['data'], list):
                for order in data['data']:
                    if not isinstance(order, dict):
                        continue
                    try:
                        uly = order.get('uly', '')
                        matched_coin = self.match_coin_by_uly(uly)
                        
                        if matched_coin not in SUPPORTED_COINS:
                            continue
                        
                        details = order.get('details', [])
                        if not isinstance(details, list):
                            continue
                        
                        inst_id = order.get('instId', 'N/A')
                        inst_family = order.get('instFamily', 'N/A')
                        
                        # 币种合约面值（每张合约对应的币种数量）
                        contract_size_map = {'BTC': 0.001, 'ETH': 0.1, 'SOL': 1.0}
                        contract_size = contract_size_map.get(matched_coin, 0.1)
                        
                        for detail in details:
                            if not isinstance(detail, dict):
                                continue
                            
                            bk_px = detail.get('bkPx', '0')
                            sz = detail.get('sz', '0')
                            side = detail.get('side', '')
                            pos_side = detail.get('posSide', '')
                            bk_loss = detail.get('bkLoss', '0')
                            ts_str = detail.get('ts', '0')
                            ccy = detail.get('ccy', '')
                            
                            if bk_px and sz and ts_str:
                                try:
                                    # 计算USD价值：sz（张数）× 合约面值 × 价格
                                    usd = float(sz) * contract_size * float(bk_px)
                                    
                                    ts_seconds = int(ts_str) / 1000.0
                                    ts_datetime_utc = datetime.utcfromtimestamp(ts_seconds)
                                    utc8_timezone = ZoneInfo('Asia/Shanghai')
                                    ts_datetime_utc8 = ts_datetime_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(utc8_timezone).replace(tzinfo=None)
                                    
                                    if self.db_service:
                                        try:
                                            self.db_service.save_liquidation(
                                                coin=matched_coin,
                                                inst_id=inst_id if inst_id != 'N/A' else None,
                                                inst_family=inst_family if inst_family != 'N/A' else None,
                                                uly=uly,
                                                bk_px=float(bk_px) if bk_px and bk_px != '0' else None,
                                                sz=float(sz) if sz and sz != '0' else None,
                                                ccy=ccy if ccy else None,
                                                side=side if side else None,
                                                pos_side=pos_side if pos_side else None,
                                                bk_loss=float(bk_loss) if bk_loss and bk_loss != '0' else None,
                                                usd_value=usd,
                                                ts_datetime=ts_datetime_utc8
                                            )
                                        except Exception as db_error:
                                            logging.error(f"保存爆仓数据到数据库失败: {db_error}")
                                except (ValueError, TypeError) as e:
                                    logging.warning(f"爆仓数据处理失败：{e}")
                                    continue
                    except Exception as e:
                        logging.warning(f"订单处理失败：{e}")
                        continue
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logging.error(f"WebSocket消息处理错误：{e}")
    
    def on_error(self, ws, error):
        if "No data received" not in str(error) and "Connection refused" not in str(error):
            logging.error(f"WebSocket 错误：{error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        self.is_running = False
        logging.info(f"WebSocket 关闭（状态码：{close_status_code}），5秒后重连...")
        time.sleep(5)
        if not self.is_running:
            self.start()
    
    def on_open(self, ws):
        try:
            # 只订阅一次，接收所有SWAP合约的爆仓数据，然后根据数据判断币种
            subscribe_msg = {
                "op": "subscribe",
                "args": [{"channel": "liquidation-orders", "instType": "SWAP"}]
            }
            ws.send(json.dumps(subscribe_msg))
            logging.info("WebSocket 连接成功，已订阅所有SWAP合约爆仓数据（将自动过滤BTC/ETH/SOL）")
            self.last_pong_time = time.time()
        except Exception as e:
            logging.error(f"WebSocket 订阅失败：{e}")
    
    def _ping_loop(self):
        while self.is_running:
            time.sleep(self.ping_interval)
            if not self.is_running:
                break
            try:
                if self.ws and hasattr(self.ws, 'sock') and self.ws.sock:
                    if time.time() - self.last_pong_time > self.ping_interval * 2:
                        logging.warning("WebSocket 心跳超时，准备重连...")
                        self.ws.close()
                        break
                    self.ws.send("ping")
                else:
                    break
            except Exception as e:
                break
    
    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.ws = websocket.WebSocketApp("wss://ws.okx.com:8443/ws/v5/public",
                                         on_message=self.on_message,
                                         on_error=self.on_error,
                                         on_close=self.on_close,
                                         on_open=self.on_open)
        self.thread = threading.Thread(target=self.ws.run_forever)
        self.thread.daemon = True
        self.thread.start()
        self.ping_thread = threading.Thread(target=self._ping_loop)
        self.ping_thread.daemon = True
        self.ping_thread.start()
        logging.info("爆仓数据WebSocket监听启动")


# ==================== 数据收集函数 ====================
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_taker_volume(coin, coin_symbol):
    """收集Taker主动量数据"""
    try:
        url = f"https://www.okx.com/api/v5/rubik/stat/taker-volume-contract?instId={coin_symbol}&unit=0&period=5m&limit=6"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
        
        if json_data.get('code') != '0':
            logging.warning(f"{coin} Taker主动量：API错误（{json_data.get('code')}: {json_data.get('msg', '未知错误')}）")
            return False
        
        data = json_data.get('data') or []
        if not isinstance(data, list) or len(data) == 0:
            logging.warning(f"{coin} Taker主动量：数据为空")
            return False

        # 打印数据
        # logging.info(f"{coin} Taker主动量数据：{json_data}")

        # 处理数组格式的数据：[ts, sellVol, buyVol]
        data_to_save = []
        
        for item in data:
            if isinstance(item, list) and len(item) >= 3:
                ts_ms = int(item[0])  # 时间戳（毫秒）
                sell_vol = float(item[1])  # 卖出量
                buy_vol = float(item[2])  # 买入量
                
                # 转换为UTC+8时间
                ts_seconds = ts_ms / 1000.0
                ts_datetime_utc = datetime.utcfromtimestamp(ts_seconds)
                utc8_timezone = ZoneInfo('Asia/Shanghai')
                ts_datetime_utc8 = ts_datetime_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(utc8_timezone).replace(tzinfo=None)
                
                data_to_save.append((ts_datetime_utc8, sell_vol, buy_vol))
        
        # 按ts从小到大排序
        data_to_save.sort(key=lambda x: x[0])
        
        # 批量保存
        if data_to_save:
            result = market_db.save_taker_volume_batch(coin, coin_symbol, data_to_save)
            if not result:
                error_msg = f"{coin} Taker主动量数据保存失败，将重试"
                logging.error(error_msg)
                raise Exception(error_msg)  # 抛出异常以触发重试
            return result
        
        return False
        
    except Exception as e:
        error_msg = f"{coin} Taker主动量收集失败：{type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        raise  # 重新抛出异常以触发重试机制


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_funding_rate(coin, coin_symbol):
    """收集资金费率数据"""
    try:
        url = f"https://www.okx.com/api/v5/public/funding-rate?instId={coin_symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
        
        if json_data.get('code') != '0':
            logging.warning(f"{coin} 资金费率：API错误（{json_data.get('code')}: {json_data.get('msg', '未知错误')}）")
            return False
        
        if not json_data.get('data') or len(json_data['data']) == 0:
            logging.warning(f"{coin} 资金费率：数据为空")
            return False

        # 打印数据
        # logging.info(f"{coin} 资金费率数据：{json_data}")
        
        data_item = json_data['data'][0]
        if isinstance(data_item, dict):
            funding_rate = float(data_item.get('fundingRate', 0))
            funding_rate_pct = funding_rate * 100
        else:
            logging.warning(f"{coin} 资金费率：数据格式错误")
            return False
        
        # 使用当前时间（资金费率是实时值）
        ts_datetime_utc8 = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        
        return market_db.save_funding_rate(coin, coin_symbol, ts_datetime_utc8, funding_rate, funding_rate_pct)
        
    except Exception as e:
        logging.error(f"{coin} 资金费率收集失败：{e}")
        return False


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_open_interest(coin, coin_symbol):
    """收集持仓量数据"""
    try:
        # 先尝试使用 rubik 端点
        url = f"https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history?instId={coin_symbol}&period=5m&limit=3"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
        
        ts_datetime_utc8 = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)

        # 打印数据
        # logging.info(f"{coin} 持仓量数据：{json_data}")
        
        if json_data.get('code') == '0' and json_data.get('data'):
            data = json_data['data']
            if isinstance(data, list) and len(data) >= 1:
                # 处理数组格式的数据：[ts, oi, oiCcy, oiUsd]
                data_to_save = []
                
                for item in data:
                    if isinstance(item, list) and len(item) >= 4:
                        ts_ms = int(item[0])  # 时间戳（毫秒）
                        oi = float(item[1])  # 持仓量（合约数）
                        oi_ccy = float(item[2]) if item[2] else None  # 持仓量（币种单位）
                        oi_usd = float(item[3]) if item[3] else None  # 持仓量（USD单位）
                        
                        # 转换为UTC+8时间
                        ts_seconds = ts_ms / 1000.0
                        ts_datetime_utc = datetime.utcfromtimestamp(ts_seconds)
                        utc8_timezone = ZoneInfo('Asia/Shanghai')
                        ts_datetime_utc8 = ts_datetime_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(utc8_timezone).replace(tzinfo=None)
                        
                        data_to_save.append((ts_datetime_utc8, oi, oi_ccy, oi_usd))
                
                # 按ts从小到大排序
                data_to_save.sort(key=lambda x: x[0])
                
                # 批量保存
                if data_to_save:
                    return market_db.save_open_interest_batch(coin, coin_symbol, data_to_save)
        
        # 如果 rubik 端点失败，使用公开端点
        url_public = f"https://www.okx.com/api/v5/public/open-interest?instId={coin_symbol}"
        resp_public = requests.get(url_public, timeout=10, headers=headers)
        resp_public.raise_for_status()
        json_data_public = resp_public.json()
        
        if json_data_public.get('code') == '0' and json_data_public.get('data') and len(json_data_public['data']) > 0:
            latest_oi = float(json_data_public['data'][0].get('oi', 0))
            if latest_oi > 0:
                return market_db.save_open_interest(coin, coin_symbol, ts_datetime_utc8, latest_oi)
        
        logging.warning(f"{coin} 持仓量：数据获取失败")
        return False
        
    except Exception as e:
        logging.error(f"{coin} 持仓量收集失败：{e}")
        return False


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_long_short_ratio(coin, coin_symbol):
    """收集多空比数据"""
    try:
        url = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio-contract?instId={coin_symbol}&limit=10"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
        
        if json_data.get('code') != '0':
            logging.warning(f"{coin} 多空比：API错误（{json_data.get('code')}: {json_data.get('msg', '未知错误')}）")
            return False
        
        if not json_data.get('data') or len(json_data['data']) < 1:
            logging.warning(f"{coin} 多空比：数据不足")
            return False

        
        # 打印数据
        # logging.info(f"{coin} 多空比数据：{json_data}")
        
        data = json_data['data']
        if isinstance(data[0], list) and len(data[0]) >= 2:
            latest_ratio = float(data[0][1])
            prev_ratio = float(data[1][1]) if len(data) >= 2 else latest_ratio
        elif isinstance(data[0], dict):
            latest_ratio = float(data[0].get('longShortRatio', 1))
            prev_ratio = float(data[1].get('longShortRatio', 1)) if len(data) >= 2 else latest_ratio
        else:
            logging.warning(f"{coin} 多空比：数据格式不支持")
            return False
        
        delta_ratio = latest_ratio - prev_ratio if prev_ratio else None
        
        # 使用当前时间
        ts_datetime_utc8 = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        
        return market_db.save_long_short_ratio(coin, coin_symbol, ts_datetime_utc8, latest_ratio, delta_ratio)
        
    except Exception as e:
        logging.error(f"{coin} 多空比收集失败：{e}")
        return False


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_macro_data():
    """收集宏观经济数据"""
    try:
        ts_datetime_utc8 = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        
        # 原有宏观
        urls = {
            "SOFR": f"https://api.stlouisfed.org/fred/series/observations?series_id=SOFR&api_key={FRED_KEY}&file_type=json&limit=1&sort_order=desc",
            "VIX": f"https://api.stlouisfed.org/fred/series/observations?series_id=VIXCLS&api_key={FRED_KEY}&file_type=json&limit=1&sort_order=desc",
            "DGS10": f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={FRED_KEY}&file_type=json&limit=1&sort_order=desc",
        }
        
        macro = {}
        for name, url in urls.items():
            try:
                resp = requests.get(url, timeout=8).json()
                val = resp["observations"][0]["value"]
                if val == "." or not val.replace(".", "").isdigit():
                    macro[name] = None
                else:
                    macro[name] = float(val)
            except Exception as e:
                macro[name] = None
                logging.warning(f"获取{name}失败：{e}")
        
        # 美盘时段判断
        ny_time = datetime.utcnow() - timedelta(hours=5)
        us_session = "美盘进行中" if 9 <= ny_time.hour < 16 and ny_time.weekday() < 5 else "美盘休市"
        
        # 新增经济数据
        cpi = None
        cpi_yoy = None
        unemployment_rate = None
        japan_rate = None
        
        try:
            # 美国 CPI
            cpi_resp = requests.get(
                f"https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key={FRED_KEY}&file_type=json&limit=2&sort_order=desc",
                timeout=8
            ).json()
            latest_cpi = cpi_resp["observations"][0]["value"]
            prev_cpi = cpi_resp["observations"][1]["value"]
            if latest_cpi != "." and prev_cpi != ".":
                cpi = float(latest_cpi)
                prev_float = float(prev_cpi)
                cpi_yoy = round((cpi - prev_float) / prev_float * 100, 4)
        except Exception as e:
            logging.warning(f"获取CPI失败：{e}")
        
        try:
            # 美国失业率
            unemp_resp = requests.get(
                f"https://api.stlouisfed.org/fred/series/observations?series_id=UNRATE&api_key={FRED_KEY}&file_type=json&limit=1&sort_order=desc",
                timeout=8
            ).json()
            unemp_val = unemp_resp["observations"][0]["value"]
            if unemp_val != ".":
                unemployment_rate = float(unemp_val)
        except Exception as e:
            logging.warning(f"获取失业率失败：{e}")
        
        try:
            # 日本基准利率
            boj_resp = requests.get(
                f"https://api.stlouisfed.org/fred/series/observations?series_id=IRSTCI01JPM156N&api_key={FRED_KEY}&file_type=json&limit=1&sort_order=desc",
                timeout=8
            ).json()
            boj_val = boj_resp["observations"][0]["value"]
            if boj_val != ".":
                japan_rate = float(boj_val)
        except Exception as e:
            logging.warning(f"获取日本基准利率失败：{e}")
        
        return market_db.save_macro_data(ts_datetime_utc8, macro.get('SOFR'), macro.get('VIX'), 
                                        macro.get('DGS10'), cpi, cpi_yoy, unemployment_rate, japan_rate, us_session)
        
    except Exception as e:
        logging.error(f"宏观经济数据收集失败：{e}")
        return False


def collect_frequent_data():
    """收集高频数据（每分钟）：Taker主动量、持仓量"""
    logging.info("=" * 80)
    logging.info("开始收集高频市场数据（每分钟）")
    logging.info("=" * 80)
    
    # 收集每个币种的高频数据
    for coin, config in SUPPORTED_COINS.items():
        coin_symbol = config['symbol']
        logging.info(f"收集 {coin} 高频数据...")
        
        collect_taker_volume(coin, coin_symbol)
        collect_open_interest(coin, coin_symbol)
        
        time.sleep(1)  # 避免请求过快
    
    logging.info("高频市场数据收集完成")
    logging.info("=" * 80)


def collect_periodic_data():
    """收集周期性数据（每5分钟）：资金费率、多空比"""
    logging.info("=" * 80)
    logging.info("开始收集周期性市场数据（每5分钟）")
    logging.info("=" * 80)
    
    # 收集每个币种的周期性数据
    for coin, config in SUPPORTED_COINS.items():
        coin_symbol = config['symbol']
        logging.info(f"收集 {coin} 周期性数据...")
        
        collect_funding_rate(coin, coin_symbol)
        collect_long_short_ratio(coin, coin_symbol)
        
        time.sleep(1)  # 避免请求过快
    
    logging.info("周期性市场数据收集完成")
    logging.info("=" * 80)


def collect_macro_economic_data():
    """收集宏观经济数据（仅在整点时获取）"""
    logging.info("=" * 80)
    logging.info("开始收集宏观经济数据")
    logging.info("=" * 80)
    
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    if now.minute == 0:
        logging.info("当前为整点，收集宏观经济数据...")
        result = collect_macro_data()
        if result:
            logging.info("宏观经济数据收集并保存成功")
        else:
            logging.error("宏观经济数据收集或保存失败")
    else:
        next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        minutes_until_next_hour = (next_hour - now).total_seconds() / 60
        logging.info(f"跳过宏观经济数据收集（非整点），下次整点：{next_hour.strftime('%H:00')}（{int(minutes_until_next_hour)}分钟后）")
    
    logging.info("宏观经济数据收集完成")
    logging.info("=" * 80)


# ==================== 主程序 ====================
if __name__ == "__main__":
    logging.info("市场数据收集服务启动")
    
    # 初始化数据库表
    try:
        if market_db.connect():
            market_db.create_tables()
        if liquidation_db.connect():
            liquidation_db.create_tables()
        logging.info("数据库表初始化完成")
    except Exception as e:
        logging.error(f"数据库初始化失败: {e}")
    
    # 启动爆仓数据WebSocket监听器（后台运行）
    liquidation_listener = OKXLiquidationListener()
    liquidation_listener.start()
    
    # 立即执行一次所有数据收集
    collect_frequent_data()
    collect_periodic_data()
    collect_macro_economic_data()
    
    # 设置定时任务
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    
    # 高频数据：每分钟的第30秒执行（Taker主动量、持仓量）
    # max_instances=2: 允许最多2个实例并发运行，避免任务堆积
    # coalesce=True: 如果任务堆积，合并为一次执行
    # misfire_grace_time=60: 任务错过执行后60秒内仍可执行
    scheduler.add_job(
        collect_frequent_data, 
        'cron', 
        minute='*', 
        second='30',
        max_instances=2,
        coalesce=True,
        misfire_grace_time=60
    )
    # logging.info("高频数据收集调度：每分钟的第30秒（Taker主动量、持仓量）")
    
    # 周期性数据：每5分钟的第30秒执行（资金费率、多空比）
    scheduler.add_job(
        collect_periodic_data, 
        'cron', 
        minute='*/5', 
        second='30',
        max_instances=2,
        coalesce=True,
        misfire_grace_time=300
    )
    # logging.info("周期性数据收集调度：每5分钟的第30秒（资金费率、多空比）")
    
    # 宏观经济数据：每小时的第0分第30秒执行
    scheduler.add_job(
        collect_macro_economic_data, 
        'cron', 
        minute='0', 
        second='0',
        max_instances=2,
        coalesce=True,
        misfire_grace_time=3600
    )
    # logging.info("宏观经济数据收集调度：每小时的第0分第30秒")
    
    logging.info("市场数据收集调度器启动")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("程序被用户中断")
        scheduler.shutdown()

