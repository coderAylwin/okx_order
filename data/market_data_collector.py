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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
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
import apscheduler.events

from market_data_database import MarketDataDatabaseService
from liquidation_database import LiquidationDatabaseService
from binance_database import BinanceDatabaseService

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

# 支持的币种列表（OKX）
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
    },
    'XRP': {
        'symbol': 'XRP-USDT-SWAP',
        'name': 'XRP'
    }
}

# 币安支持的币种列表
BINANCE_COINS = {
    'BTC': {
        'symbol': 'BTCUSDT',
        'name': 'BTC'
    },
    'ETH': {
        'symbol': 'ETHUSDT',
        'name': 'ETH'
    },
    'SOL': {
        'symbol': 'SOLUSDT',
        'name': 'SOL'
    },
    'XRP': {
        'symbol': 'XRPUSDT',
        'name': 'XRP'
    }
}

# 时区配置
TIMEZONE = 'Asia/Shanghai'

# 飞书Webhook地址（爆仓提醒）
LIQUIDATION_WEBHOOK_URL = "https://open.larksuite.com/open-apis/bot/v2/hook/b2d10580-2a3a-4c7e-b42a-6fceb75d5342"

# 爆仓价值阈值（USD）
LIQUIDATION_THRESHOLD_USD = 100000  # 10万U

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
binance_db = BinanceDatabaseService(**DB_CONFIG)
# 币安爆仓数据库服务（使用BinanceDatabaseService，但单独初始化用于爆仓数据）
binance_liquidation_db = BinanceDatabaseService(**DB_CONFIG)


# ==================== 推送函数 ====================
def send_liquidation_notification(exchange, coin, usd_value, liquidation_type=None, side=None, pos_side=None, price=None, quantity=None, ts_datetime=None):
    """
    发送爆仓提醒通知
    
    Args:
        exchange: 交易所名称（'OKX' 或 'Binance'）
        coin: 币种
        usd_value: USD价值
        liquidation_type: 爆仓类型（'LONG'/'SHORT'，仅币安）
        side: 订单方向（'SELL'/'BUY'）
        pos_side: 持仓方向（'long'/'short'，仅OKX）
        price: 价格
        quantity: 数量
        ts_datetime: 时间戳
    """
    try:
        # 格式化USD价值
        if usd_value >= 10000:  # 大于等于1万，显示为万美元
            usd_display = f"{usd_value / 10000:.2f} 万美元"
        else:
            usd_display = f"{usd_value:,.2f} 美元"
        
        # 构建消息内容
        content_lines = [
            f"🚨 {exchange} 大额爆仓提醒",
            "",
            f"💰 币种: {coin}",
            f"💵 价值: {usd_display}",
        ]
        
        # 添加爆仓类型信息
        # OKX使用pos_side判断，币安使用liquidation_type判断
        if pos_side:
            # OKX的pos_side: 'long'表示多单，'short'表示空单
            if pos_side.lower() == 'long':
                type_display = "多单爆仓"
            elif pos_side.lower() == 'short':
                type_display = "空单爆仓"
            else:
                type_display = f"持仓方向: {pos_side}"
            content_lines.append(f"📊 类型: {type_display}")
        elif liquidation_type:
            # 币安的liquidation_type: 'LONG'表示多单爆仓，'SHORT'表示空单爆仓
            type_display = "多单爆仓" if liquidation_type == 'LONG' else "空单爆仓"
            content_lines.append(f"📊 类型: {type_display}")
        
        if side:
            side_display = "卖出" if side == 'SELL' else "买入"
            content_lines.append(f"📈 方向: {side_display}")
        
        if price:
            content_lines.append(f"💲 价格: {price:,.4f}")
        
        if quantity:
            content_lines.append(f"📦 数量: {quantity:,.4f}")
        
        if ts_datetime:
            content_lines.append(f"⏰ 时间: {ts_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        
        content_text = "\n".join(content_lines)
        
        # 飞书Webhook消息格式
        payload = {
            "msg_type": "text",
            "content": {
                "text": content_text
            }
        }
        
        response = requests.post(LIQUIDATION_WEBHOOK_URL, json=payload, timeout=5)
        response.raise_for_status()
        
        result = response.json()
        if result.get('code') == 0:
            logging.info(f"✅ {exchange} 爆仓提醒推送成功: {coin} {usd_display}")
        else:
            logging.warning(f"⚠️ {exchange} 爆仓提醒推送返回异常: {result}")
            
    except requests.exceptions.RequestException as e:
        logging.error(f"{exchange} 爆仓提醒推送失败（网络错误）: {e}")
    except Exception as e:
        logging.error(f"{exchange} 爆仓提醒推送失败: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")


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
                        contract_size_map = {'BTC': 0.01, 'ETH': 0.1, 'SOL': 1.0, 'XRP': 100.0}
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
                                            
                                            # 检查是否超过阈值，如果超过则推送
                                            if usd >= LIQUIDATION_THRESHOLD_USD:
                                                send_liquidation_notification(
                                                    exchange='OKX',
                                                    coin=matched_coin,
                                                    usd_value=usd,
                                                    side=side,
                                                    pos_side=pos_side if pos_side else None,
                                                    price=float(bk_px) if bk_px and bk_px != '0' else None,
                                                    quantity=float(sz) if sz and sz != '0' else None,
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
            logging.info("WebSocket 连接成功，已订阅所有SWAP合约爆仓数据（将自动过滤BTC/ETH/SOL/XRP）")
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


# ==================== 币安爆仓数据WebSocket监听器 ====================
class BinanceLiquidationListener:
    """币安爆仓数据WebSocket监听器"""
    
    def __init__(self):
        self.ws = None
        self.thread = None
        self.ping_thread = None
        self.lock = threading.Lock()
        self.is_running = False
        self.last_pong_time = time.time()
        self.ping_interval = 20  # 每20秒发送一次ping
        self.db_service = binance_liquidation_db
        
        # 连接数据库并创建表
        if self.db_service.connect():
            self.db_service.create_tables()
        
        # 币种映射（symbol -> coin）
        self.symbol_to_coin = {
            'BTCUSDT': 'BTC',
            'ETHUSDT': 'ETH',
            'SOLUSDT': 'SOL'
        }
    
    def on_message(self, ws, message):
        try:
            # 记录原始消息（限制长度避免日志过大）
            message_preview = message[:500] if len(message) > 500 else message
            logging.debug(f"币安WebSocket收到原始消息（长度={len(message)}）: {message_preview}")
            
            # 处理pong响应
            if message == "pong" or message == b"pong":
                logging.debug("币安WebSocket收到pong响应")
                self.last_pong_time = time.time()
                return
            
            # 尝试解析JSON
            try:
                data = json.loads(message)
            except json.JSONDecodeError as e:
                logging.warning(f"币安WebSocket消息JSON解析失败: {e}, 消息内容: {message_preview}")
                return
            
            logging.debug(f"币安WebSocket解析后的数据: {json.dumps(data, ensure_ascii=False)[:500]}")
            
            # 处理错误消息
            if isinstance(data, dict) and 'error' in data:
                error_info = data.get('error', {})
                error_code = error_info.get('code', 'N/A')
                error_msg = error_info.get('msg', 'N/A')
                logging.error(f"币安WebSocket错误响应: code={error_code}, msg={error_msg}")
                logging.error(f"币安WebSocket完整错误消息: {json.dumps(data, ensure_ascii=False)}")
                return
            
            # 处理组合streams格式：{"stream":"<streamName>","data":<rawPayload>}
            if isinstance(data, dict) and 'stream' in data and 'data' in data:
                stream_name = data.get('stream', '')
                logging.debug(f"币安WebSocket收到组合stream消息: stream={stream_name}")
                data = data['data']
                # 验证stream名称是否是我们订阅的
                if '@forceOrder' not in stream_name:
                    logging.debug(f"币安WebSocket忽略非forceOrder stream: {stream_name}")
                    return
            elif isinstance(data, dict) and 'e' in data:
                # 直接是事件数据（单一stream格式）
                logging.debug(f"币安WebSocket收到单一stream事件: e={data.get('e')}")
                pass
            else:
                # 其他格式的消息，记录但不处理
                logging.debug(f"币安WebSocket收到未知格式消息: keys={list(data.keys()) if isinstance(data, dict) else type(data)}")
                return
            
            # 检查事件类型
            if data.get('e') == 'forceOrder':
                logging.debug(f"币安WebSocket处理forceOrder事件")
                order_data = data.get('o', {})
                if not isinstance(order_data, dict):
                    logging.warning(f"币安WebSocket forceOrder事件数据格式错误: order_data={order_data}")
                    return
                
                symbol = order_data.get('s', '').upper()  # 交易对（如BTCUSDT）
                coin = self.symbol_to_coin.get(symbol)
                
                logging.debug(f"币安WebSocket处理爆仓数据: symbol={symbol}, coin={coin}")
                
                if not coin:
                    # 不是我们监控的币种，跳过
                    logging.debug(f"币安WebSocket跳过未监控的币种: {symbol}")
                    return
                
                try:
                    # 提取订单信息
                    side = order_data.get('S', '')  # 订单方向（SELL/BUY）
                    
                    # 判断爆仓类型：
                    # - SELL = 多单爆仓（持有多单被强制平仓，需要卖出）
                    # - BUY = 空单爆仓（持有空单被强制平仓，需要买入）
                    liquidation_type = None
                    if side == 'SELL':
                        liquidation_type = 'LONG'  # 多单爆仓
                    elif side == 'BUY':
                        liquidation_type = 'SHORT'  # 空单爆仓
                    
                    order_type = order_data.get('o', '')  # 订单类型（LIMIT/MARKET/STOP等）
                    time_in_force = order_data.get('f', '')  # 有效方式（GTC/IOC/FOK等）
                    quantity = float(order_data.get('q', 0)) if order_data.get('q') else None  # 订单数量
                    price = float(order_data.get('p', 0)) if order_data.get('p') else None  # 订单价格
                    avg_price = float(order_data.get('ap', 0)) if order_data.get('ap') else None  # 平均价格
                    order_status = order_data.get('X', '')  # 订单状态（FILLED等）
                    last_filled_qty = float(order_data.get('l', 0)) if order_data.get('l') else None  # 订单最近成交量
                    cumulative_filled_qty = float(order_data.get('z', 0)) if order_data.get('z') else None  # 订单累计成交量
                    
                    # 事件时间戳
                    event_time_ms = int(data.get('E', 0))  # 事件时间
                    trade_time_ms = int(order_data.get('T', 0))  # 交易时间
                    
                    # 使用交易时间，如果没有则使用事件时间
                    timestamp_ms = trade_time_ms if trade_time_ms > 0 else event_time_ms
                    
                    if timestamp_ms <= 0:
                        logging.warning(f"币安爆仓数据时间戳无效: {coin} {symbol}")
                        return
                    
                    # 转换为UTC+8时间
                    ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                    
                    # 计算USD价值
                    usd_value = None
                    if quantity and price:
                        usd_value = quantity * price
                    
                    # 保存到数据库
                    if self.db_service:
                        try:
                            logging.debug(f"币安WebSocket保存爆仓数据: {coin} {symbol}, side={side}, liquidation_type={liquidation_type}, order_type={order_type}, time_in_force={time_in_force}, quantity={quantity}, price={price}, usd_value={usd_value}")
                            self.db_service.save_liquidation(
                                coin=coin,
                                symbol=symbol,
                                side=side if side else None,
                                liquidation_type=liquidation_type,
                                order_type=order_type if order_type else None,
                                time_in_force=time_in_force if time_in_force else None,
                                quantity=quantity,
                                price=price,
                                avg_price=avg_price,
                                order_status=order_status if order_status else None,
                                last_filled_qty=last_filled_qty,
                                cumulative_filled_qty=cumulative_filled_qty,
                                usd_value=usd_value,
                                ts_datetime=ts_datetime_utc8
                            )
                            logging.info(f"币安WebSocket成功保存爆仓数据: {coin} {symbol}, 类型={liquidation_type}, USD价值={usd_value}")
                            
                            # 检查是否超过阈值，如果超过则推送
                            if usd_value and usd_value >= LIQUIDATION_THRESHOLD_USD:
                                send_liquidation_notification(
                                    exchange='Binance',
                                    coin=coin,
                                    usd_value=usd_value,
                                    liquidation_type=liquidation_type,
                                    side=side,
                                    price=price,
                                    quantity=quantity,
                                    ts_datetime=ts_datetime_utc8
                                )
                        except Exception as db_error:
                            logging.error(f"保存币安爆仓数据到数据库失败: {db_error}")
                            import traceback
                            logging.error(f"异常详情: {traceback.format_exc()}")
                    else:
                        logging.warning("币安WebSocket db_service未初始化，无法保存数据")
                except (ValueError, TypeError) as e:
                    logging.warning(f"币安爆仓数据处理失败：{e}")
                    import traceback
                    logging.warning(f"异常详情: {traceback.format_exc()}")
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logging.error(f"币安WebSocket消息处理错误：{e}")
            import traceback
            logging.error(f"异常详情: {traceback.format_exc()}")
    
    def on_error(self, ws, error):
        error_str = str(error)
        if "No data received" not in error_str and "Connection refused" not in error_str:
            logging.error(f"币安WebSocket 错误：{error}")
            logging.error(f"币安WebSocket 错误详情：type={type(error)}, args={error.args if hasattr(error, 'args') else 'N/A'}")
            import traceback
            logging.error(f"币安WebSocket 错误堆栈：{traceback.format_exc()}")
    
    def on_close(self, ws, close_status_code, close_msg):
        logging.info(f"币安WebSocket on_close回调触发，状态码：{close_status_code}，消息：{close_msg}")
        self.is_running = False
        logging.info(f"币安WebSocket 关闭（状态码：{close_status_code}），5秒后重连...")
        time.sleep(5)
        if not self.is_running:
            logging.info("币安WebSocket 开始重连...")
            self.start()
    
    def on_open(self, ws):
        try:
            logging.info(f"币安WebSocket on_open回调触发，连接URL: {ws.url if hasattr(ws, 'url') else 'N/A'}")
            # 币安WebSocket连接成功后，不需要发送订阅消息（组合streams方式）
            logging.info("币安WebSocket 连接成功，已订阅BTCUSDT、ETHUSDT、SOLUSDT、XRPUSDT爆仓数据")
            self.last_pong_time = time.time()
        except Exception as e:
            logging.error(f"币安WebSocket 初始化失败：{e}")
            import traceback
            logging.error(f"币安WebSocket 初始化异常详情：{traceback.format_exc()}")
    
    def _ping_loop(self):
        """发送ping保持连接"""
        while self.is_running:
            time.sleep(self.ping_interval)
            if not self.is_running:
                logging.debug("币安WebSocket ping循环退出：is_running=False")
                break
            try:
                if self.ws and hasattr(self.ws, 'sock') and self.ws.sock:
                    # 检查是否需要重连（如果超过10分钟没有收到pong）
                    time_since_last_pong = time.time() - self.last_pong_time
                    if time_since_last_pong > 600:  # 10分钟
                        logging.warning(f"币安WebSocket 心跳超时（{time_since_last_pong:.1f}秒未收到pong），准备重连...")
                        self.ws.close()
                        break
                    # 币安WebSocket：服务端每3分钟发送ping，客户端需要在10分钟内回复pong
                    # 我们不需要主动发送pong，只需要响应服务端的ping
                    # 但为了保持连接，可以定期检查连接状态
                    logging.debug(f"币安WebSocket心跳检查：距离上次pong {time_since_last_pong:.1f}秒")
                else:
                    logging.debug("币安WebSocket ping循环退出：连接不存在")
                    break
            except Exception as e:
                logging.warning(f"币安WebSocket ping循环异常：{e}")
                break
    
    def start(self):
        if self.is_running:
            logging.warning("币安WebSocket已经在运行，跳过重复启动")
            return
        self.is_running = True
        # 使用组合streams方式订阅四个币种的爆仓数据
        streams = "btcusdt@forceOrder/ethusdt@forceOrder/solusdt@forceOrder/xrpusdt@forceOrder"
        ws_url = f"wss://fstream.binance.com/stream?streams={streams}"
        logging.info(f"币安WebSocket准备连接，URL: {ws_url}")
        self.ws = websocket.WebSocketApp(ws_url,
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
        logging.info("币安爆仓数据WebSocket监听启动")


# ==================== 数据收集函数 ====================
def collect_taker_volume_with_db(coin, coin_symbol, db_service):
    """收集Taker主动量数据（使用指定的数据库连接）"""
    try:
        url = f"https://www.okx.com/api/v5/rubik/stat/taker-volume-contract?instId={coin_symbol}&unit=0&period=5m&limit=5"
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
            result = db_service.save_taker_volume_batch(coin, coin_symbol, data_to_save)
            if not result:
                logging.error(f"{coin} Taker主动量数据保存失败")
            return result
        
        return False
        
    except Exception as e:
        error_msg = f"{coin} Taker主动量收集失败：{type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        return False


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_taker_volume(coin, coin_symbol):
    """收集Taker主动量数据"""
    result = collect_taker_volume_with_db(coin, coin_symbol, market_db)
    if not result:
        raise Exception(f"{coin} Taker主动量数据保存失败，将重试")
    return result


def collect_funding_rate_with_db(coin, coin_symbol, db_service):
    """收集资金费率数据（使用指定的数据库连接）"""
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
        
        data_item = json_data['data'][0]
        if isinstance(data_item, dict):
            funding_rate = float(data_item.get('fundingRate', 0))
            funding_rate_pct = funding_rate * 100
        else:
            logging.warning(f"{coin} 资金费率：数据格式错误")
            return False
        
        # 使用当前时间（资金费率是实时值）
        ts_datetime_utc8 = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        
        return db_service.save_funding_rate(coin, coin_symbol, ts_datetime_utc8, funding_rate, funding_rate_pct)
        
    except Exception as e:
        logging.error(f"{coin} 资金费率收集失败：{e}")
        return False


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_funding_rate(coin, coin_symbol):
    """收集资金费率数据"""
    return collect_funding_rate_with_db(coin, coin_symbol, market_db)


def collect_open_interest_with_db(coin, coin_symbol, db_service):
    """收集持仓量数据（使用指定的数据库连接）"""
    try:
        # 先尝试使用 rubik 端点
        url = f"https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history?instId={coin_symbol}&period=5m&limit=5"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
        
        ts_datetime_utc8 = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        
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
                    return db_service.save_open_interest_batch(coin, coin_symbol, data_to_save)
        
        # 如果 rubik 端点失败，使用公开端点
        url_public = f"https://www.okx.com/api/v5/public/open-interest?instId={coin_symbol}"
        resp_public = requests.get(url_public, timeout=10, headers=headers)
        resp_public.raise_for_status()
        json_data_public = resp_public.json()
        
        if json_data_public.get('code') == '0' and json_data_public.get('data') and len(json_data_public['data']) > 0:
            latest_oi = float(json_data_public['data'][0].get('oi', 0))
            if latest_oi > 0:
                return db_service.save_open_interest(coin, coin_symbol, ts_datetime_utc8, latest_oi)
        
        logging.warning(f"{coin} 持仓量：数据获取失败")
        return False
        
    except Exception as e:
        logging.error(f"{coin} 持仓量收集失败：{e}")
        return False


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_open_interest(coin, coin_symbol):
    """收集持仓量数据"""
    return collect_open_interest_with_db(coin, coin_symbol, market_db)


def collect_long_short_ratio_with_db(coin, coin_symbol, db_service):
    """收集多空比数据（使用指定的数据库连接）- 每个接口独立保存"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        total_saved = 0
        total_updated = 0
        total_skipped = 0
        
        # 接口1：按合约获取多空比
        try:
            url1 = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio-contract?instId={coin_symbol}&limit=5"
            resp1 = requests.get(url1, timeout=10, headers=headers)
            resp1.raise_for_status()
            json_data1 = resp1.json()
        
            if json_data1.get('code') == '0' and json_data1.get('data') and len(json_data1['data']) >= 1:
                data1 = json_data1['data']
                logging.info(f"{coin} 多空比（合约）：{data1}")
        
                # 计算delta_ratio需要前一个时间点的数据
                prev_ratio = None
                sorted_data = []
                
                for item in data1:
                    if isinstance(item, list) and len(item) >= 2:
                        timestamp_ms = int(item[0])
                        ratio = float(item[1])
                        sorted_data.append((timestamp_ms, ratio))
                    elif isinstance(item, dict):
                        timestamp_ms = int(item.get('timestamp', 0))
                        ratio = float(item.get('longShortRatio', 0))
                        if timestamp_ms > 0:
                            sorted_data.append((timestamp_ms, ratio))
                
                # 按时间戳排序
                sorted_data.sort(key=lambda x: x[0])
                
                for timestamp_ms, ratio in sorted_data:
                    delta_ratio = (ratio - prev_ratio) if prev_ratio is not None else None
                    
                    # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
                    ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                    
                    # 检查并保存接口1的数据（每条数据都进行一致性检查）
                    result = db_service.save_long_short_ratio_partial(
                        coin, coin_symbol, ts_datetime_utc8, 
                        long_short_ratio=ratio, 
                        delta_ratio=delta_ratio
                    )
                    if result == 'saved':
                        total_saved += 1
                        logging.debug(f"{coin} 多空比（合约）数据新增: {ts_datetime_utc8} ratio={ratio}")
                    elif result == 'updated':
                        total_updated += 1
                        logging.debug(f"{coin} 多空比（合约）数据更新: {ts_datetime_utc8} ratio={ratio}")
                    elif result == 'skipped':
                        total_skipped += 1
                        logging.debug(f"{coin} 多空比（合约）数据一致，跳过: {ts_datetime_utc8} ratio={ratio}")
                    
                    prev_ratio = ratio
            else:
                logging.warning(f"{coin} 多空比（合约）：API错误或数据为空")
        except Exception as e1:
            logging.warning(f"{coin} 多空比（合约）获取失败：{e1}")
        
        # 接口2：按币种获取多空比（过去半小时数据）
        try:
            # 计算过去半小时的时间范围（UTC+8时间）
            now_utc8 = datetime.now(ZoneInfo('Asia/Shanghai'))
            end_time = now_utc8
            begin_time = now_utc8 - timedelta(minutes=30)
            
            # 转换为UTC时间戳（毫秒）
            end_timestamp_ms = int(end_time.replace(tzinfo=ZoneInfo('Asia/Shanghai')).astimezone(ZoneInfo('UTC')).timestamp() * 1000)
            begin_timestamp_ms = int(begin_time.replace(tzinfo=ZoneInfo('Asia/Shanghai')).astimezone(ZoneInfo('UTC')).timestamp() * 1000)
            
            url2 = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={coin}&period=5m&begin={begin_timestamp_ms}&end={end_timestamp_ms}"
            resp2 = requests.get(url2, timeout=10, headers=headers)
            resp2.raise_for_status()
            json_data2 = resp2.json()
            
            logging.info(f"{coin} 多空比（币种）：{json_data2}")
            
            if json_data2.get('code') == '0' and json_data2.get('data') and len(json_data2['data']) >= 1:
                data2 = json_data2['data']
                
                for item in data2:
                    if isinstance(item, list) and len(item) >= 2:
                        timestamp_ms = int(item[0])
                        ratio = float(item[1])
                    elif isinstance(item, dict):
                        timestamp_ms = int(item.get('timestamp', 0))
                        ratio = float(item.get('ratio', 0))
                    else:
                        continue
                    
                    if timestamp_ms <= 0:
                        continue
                    
                    # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
                    ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                    
                    # 检查并保存接口2的数据（每条数据都进行一致性检查）
                    result = db_service.save_long_short_ratio_partial(
                        coin, coin_symbol, ts_datetime_utc8, 
                        long_short_ratio_by_ccy=ratio
                    )
                    if result == 'saved':
                        total_saved += 1
                        logging.debug(f"{coin} 多空比（币种）数据新增: {ts_datetime_utc8} ratio={ratio}")
                    elif result == 'updated':
                        total_updated += 1
                        logging.debug(f"{coin} 多空比（币种）数据更新: {ts_datetime_utc8} ratio={ratio}")
                    elif result == 'skipped':
                        total_skipped += 1
                        logging.debug(f"{coin} 多空比（币种）数据一致，跳过: {ts_datetime_utc8} ratio={ratio}")
        except Exception as e2:
            logging.warning(f"{coin} 多空比（币种）获取失败：{e2}")
        
        # 接口3：精英交易员合约多空持仓人数比
        try:
            url3 = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio-contract-top-trader?instId={coin_symbol}&limit=5"
            resp3 = requests.get(url3, timeout=10, headers=headers)
            resp3.raise_for_status()
            json_data3 = resp3.json()
            
            logging.info(f"{coin} 多空比（精英交易员人数）：{json_data3}")
            
            if json_data3.get('code') == '0' and json_data3.get('data') and len(json_data3['data']) >= 1:
                data3 = json_data3['data']
                
                for item in data3:
                    if isinstance(item, list) and len(item) >= 2:
                        timestamp_ms = int(item[0])
                        ratio = float(item[1])
                    elif isinstance(item, dict):
                        timestamp_ms = int(item.get('timestamp', 0))
                        ratio = float(item.get('longShortAcctRatio', 0))
                    else:
                        continue
                    
                    if timestamp_ms <= 0:
                        continue
                    
                    # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
                    ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
        
                    # 检查并保存接口3的数据（每条数据都进行一致性检查）
                    result = db_service.save_long_short_ratio_partial(
                        coin, coin_symbol, ts_datetime_utc8, 
                        top_trader_account_ratio=ratio
                    )
                    if result == 'saved':
                        total_saved += 1
                        logging.debug(f"{coin} 多空比（精英人数）数据新增: {ts_datetime_utc8} ratio={ratio}")
                    elif result == 'updated':
                        total_updated += 1
                        logging.debug(f"{coin} 多空比（精英人数）数据更新: {ts_datetime_utc8} ratio={ratio}")
                    elif result == 'skipped':
                        total_skipped += 1
                        logging.debug(f"{coin} 多空比（精英人数）数据一致，跳过: {ts_datetime_utc8} ratio={ratio}")
        except Exception as e3:
            logging.warning(f"{coin} 多空比（精英交易员人数）获取失败：{e3}")
        
        # 接口4：精英交易员合约多空持仓仓位比
        try:
            url4 = f"https://www.okx.com/api/v5/rubik/stat/contracts/long-short-position-ratio-contract-top-trader?instId={coin_symbol}&limit=5"
            resp4 = requests.get(url4, timeout=10, headers=headers)
            resp4.raise_for_status()
            json_data4 = resp4.json()
            
            logging.info(f"{coin} 多空比（精英交易员仓位）：{json_data4}")
            
            if json_data4.get('code') == '0' and json_data4.get('data') and len(json_data4['data']) >= 1:
                data4 = json_data4['data']
                
                for item in data4:
                    if isinstance(item, list) and len(item) >= 2:
                        timestamp_ms = int(item[0])
                        ratio = float(item[1])
                    elif isinstance(item, dict):
                        timestamp_ms = int(item.get('timestamp', 0))
                        ratio = float(item.get('longShortPosRatio', 0))
                    else:
                        continue
                    
                    if timestamp_ms <= 0:
                        continue
                    
                    # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
                    ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                    
                    # 检查并保存接口4的数据（每条数据都进行一致性检查）
                    result = db_service.save_long_short_ratio_partial(
                        coin, coin_symbol, ts_datetime_utc8, 
                        top_trader_position_ratio=ratio
                    )
                    if result == 'saved':
                        total_saved += 1
                        logging.debug(f"{coin} 多空比（精英仓位）数据新增: {ts_datetime_utc8} ratio={ratio}")
                    elif result == 'updated':
                        total_updated += 1
                        logging.debug(f"{coin} 多空比（精英仓位）数据更新: {ts_datetime_utc8} ratio={ratio}")
                    elif result == 'skipped':
                        total_skipped += 1
                        logging.debug(f"{coin} 多空比（精英仓位）数据一致，跳过: {ts_datetime_utc8} ratio={ratio}")
        except Exception as e4:
            logging.warning(f"{coin} 多空比（精英交易员仓位）获取失败：{e4}")
        
        if total_saved > 0 or total_updated > 0:
            logging.info(f"{coin} 多空比数据保存完成: 新增={total_saved}, 更新={total_updated}, 跳过={total_skipped}")
            return True
        else:
            logging.debug(f"{coin} 多空比数据全部已存在，无需保存")
            return True
        
    except Exception as e:
        logging.error(f"{coin} 多空比收集失败：{e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        return False


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_long_short_ratio(coin, coin_symbol):
    """收集多空比数据"""
    return collect_long_short_ratio_with_db(coin, coin_symbol, market_db)


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


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_binance_open_interest(coin, coin_symbol):
    """收集币安持仓量数据"""
    try:
        url = f"https://fapi.binance.com/futures/data/openInterestHist?symbol={coin_symbol}&period=5m&limit=5"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
        
        if not isinstance(json_data, list) or len(json_data) == 0:
            logging.warning(f"{coin} 币安持仓量：数据为空")
            return False

        # 处理数据
        data_to_save = []
        
        for item in json_data:
            if isinstance(item, dict):
                timestamp_ms = int(item.get('timestamp', 0))
                sum_open_interest = float(item.get('sumOpenInterest', 0))
                sum_open_interest_value = float(item.get('sumOpenInterestValue', 0))
                cmc_circulating_supply = float(item.get('CMCCirculatingSupply', 0)) if item.get('CMCCirculatingSupply') else None
                
                # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
                ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                
                data_to_save.append((ts_datetime_utc8, sum_open_interest, sum_open_interest_value, cmc_circulating_supply))
        
        # 按ts从小到大排序
        data_to_save.sort(key=lambda x: x[0])
        
        # 批量保存
        if data_to_save:
            # 为每个线程创建独立的数据库连接
            thread_db = BinanceDatabaseService(**DB_CONFIG)
            try:
                if not thread_db.connect():
                    logging.error(f"{coin} 币安数据库连接失败")
                    return False
                
                result = thread_db.save_open_interest_batch(coin, coin_symbol, data_to_save)
                if not result:
                    error_msg = f"{coin} 币安持仓量数据保存失败，将重试"
                    logging.error(error_msg)
                    raise Exception(error_msg)  # 抛出异常以触发重试
                return result
            finally:
                try:
                    thread_db.disconnect()
                except:
                    pass
        
        return False
        
    except Exception as e:
        error_msg = f"{coin} 币安持仓量收集失败：{type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        raise  # 重新抛出异常以触发重试机制


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_binance_taker_volume(coin, coin_symbol):
    """收集币安主动买卖量数据"""
    try:
        url = f"https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={coin_symbol}&period=5m&limit=5"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
        
        if not isinstance(json_data, list) or len(json_data) == 0:
            logging.warning(f"{coin} 币安主动买卖量：数据为空")
            return False

        # 处理数据
        data_to_save = []
        
        for item in json_data:
            if isinstance(item, dict):
                timestamp_ms = int(item.get('timestamp', 0))
                buy_vol = float(item.get('buyVol', 0))
                sell_vol = float(item.get('sellVol', 0))
                buy_sell_ratio = float(item.get('buySellRatio', 0))
                
                # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）；去掉微秒与 DB DATETIME 一致，避免重复插入触发唯一键冲突
                ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None, microsecond=0)
                
                data_to_save.append((ts_datetime_utc8, buy_vol, sell_vol, buy_sell_ratio))
        
        # 按ts从小到大排序
        data_to_save.sort(key=lambda x: x[0])
        
        # 批量保存
        if data_to_save:
            # 为每个线程创建独立的数据库连接
            thread_db = BinanceDatabaseService(**DB_CONFIG)
            try:
                if not thread_db.connect():
                    logging.error(f"{coin} 币安数据库连接失败")
                    return False
                
                result = thread_db.save_taker_volume_batch(coin, coin_symbol, data_to_save)
                if not result:
                    error_msg = f"{coin} 币安主动买卖量数据保存失败，将重试（具体原因见上方或 binance_database 日志）"
                    logging.error(error_msg)
                    raise Exception(error_msg)  # 抛出异常以触发重试
                return result
            finally:
                try:
                    thread_db.disconnect()
                except:
                    pass
        
        return False
        
    except Exception as e:
        error_msg = f"{coin} 币安主动买卖量收集失败：{type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        raise  # 重新抛出异常以触发重试机制


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_binance_basis(coin, coin_symbol):
    """收集币安基差数据"""
    try:
        url = f"https://fapi.binance.com/futures/data/basis?pair={coin_symbol}&contractType=PERPETUAL&period=5m&limit=5"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
        
        if not isinstance(json_data, list) or len(json_data) == 0:
            logging.warning(f"{coin} 币安基差：数据为空")
            return False

        # 处理数据
        data_to_save = []
        
        for item in json_data:
            if isinstance(item, dict):
                timestamp_ms = int(item.get('timestamp', 0))
                index_price = float(item.get('indexPrice', 0))
                futures_price = float(item.get('futuresPrice', 0))
                basis = float(item.get('basis', 0))
                basis_rate = float(item.get('basisRate', 0)) if item.get('basisRate') else None
                annualized_basis_rate = float(item.get('annualizedBasisRate', 0)) if item.get('annualizedBasisRate') else None
                contract_type = item.get('contractType', 'PERPETUAL')
                pair = item.get('pair', coin_symbol)
                
                if timestamp_ms <= 0:
                    continue
                
                # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
                ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                
                data_to_save.append((ts_datetime_utc8, index_price, futures_price, basis, basis_rate, annualized_basis_rate))
        
        # 按ts从小到大排序
        data_to_save.sort(key=lambda x: x[0])
        
        # 批量保存
        if data_to_save:
            # 为每个线程创建独立的数据库连接
            thread_db = BinanceDatabaseService(**DB_CONFIG)
            try:
                if not thread_db.connect():
                    logging.error(f"{coin} 币安数据库连接失败")
                    return False
                
                result = thread_db.save_basis_batch(coin, coin_symbol, 'PERPETUAL', data_to_save)
                if not result:
                    error_msg = f"{coin} 币安基差数据保存失败，将重试"
                    logging.error(error_msg)
                    raise Exception(error_msg)  # 抛出异常以触发重试
                return result
            finally:
                try:
                    thread_db.disconnect()
                except:
                    pass
        
        return False
        
    except Exception as e:
        error_msg = f"{coin} 币安基差收集失败：{type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        raise  # 重新抛出异常以触发重试机制


def collect_binance_long_short_ratio_with_db(coin, coin_symbol, db_service):
    """收集币安多空比数据（使用指定的数据库连接）- 每个接口独立保存"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        total_saved = 0
        total_updated = 0
        total_skipped = 0
        
        # 接口1：大户持仓量多空比
        try:
            url1 = f"https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol={coin_symbol}&period=5m&limit=5"
            resp1 = requests.get(url1, timeout=10, headers=headers)
            resp1.raise_for_status()
            json_data1 = resp1.json()
            
            if isinstance(json_data1, list) and len(json_data1) >= 1:
                data1 = json_data1
                
                for item in data1:
                    if isinstance(item, dict):
                        timestamp_ms = int(item.get('timestamp', 0))
                        long_short_ratio = float(item.get('longShortRatio', 0))
                        
                        if timestamp_ms <= 0:
                            continue
                        
                        # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
                        ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                        
                        # 检查并保存接口1的数据（每条数据都进行一致性检查）
                        result = db_service.save_binance_long_short_ratio_partial(
                            coin, coin_symbol, ts_datetime_utc8, 
                            top_position_ratio=long_short_ratio
                        )
                        if result == 'saved':
                            total_saved += 1
                            logging.debug(f"{coin} 币安多空比（大户持仓量）数据新增: {ts_datetime_utc8} ratio={long_short_ratio}")
                        elif result == 'updated':
                            total_updated += 1
                            logging.debug(f"{coin} 币安多空比（大户持仓量）数据更新: {ts_datetime_utc8} ratio={long_short_ratio}")
                        elif result == 'skipped':
                            total_skipped += 1
                            logging.debug(f"{coin} 币安多空比（大户持仓量）数据一致，跳过: {ts_datetime_utc8} ratio={long_short_ratio}")
            else:
                logging.warning(f"{coin} 币安多空比（大户持仓量）：API错误或数据为空")
        except Exception as e1:
            logging.warning(f"{coin} 币安多空比（大户持仓量）获取失败：{e1}")
        
        # 接口2：大户账户数多空比
        try:
            url2 = f"https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol={coin_symbol}&period=5m&limit=5"
            resp2 = requests.get(url2, timeout=10, headers=headers)
            resp2.raise_for_status()
            json_data2 = resp2.json()
            
            if isinstance(json_data2, list) and len(json_data2) >= 1:
                data2 = json_data2
                
                for item in data2:
                    if isinstance(item, dict):
                        timestamp_ms = int(item.get('timestamp', 0))
                        long_short_ratio = float(item.get('longShortRatio', 0))
                        
                        if timestamp_ms <= 0:
                            continue
                        
                        # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
                        ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                        
                        # 检查并保存接口2的数据（每条数据都进行一致性检查）
                        result = db_service.save_binance_long_short_ratio_partial(
                            coin, coin_symbol, ts_datetime_utc8, 
                            top_account_ratio=long_short_ratio
                        )
                        if result == 'saved':
                            total_saved += 1
                            logging.debug(f"{coin} 币安多空比（大户账户数）数据新增: {ts_datetime_utc8} ratio={long_short_ratio}")
                        elif result == 'updated':
                            total_updated += 1
                            logging.debug(f"{coin} 币安多空比（大户账户数）数据更新: {ts_datetime_utc8} ratio={long_short_ratio}")
                        elif result == 'skipped':
                            total_skipped += 1
                            logging.debug(f"{coin} 币安多空比（大户账户数）数据一致，跳过: {ts_datetime_utc8} ratio={long_short_ratio}")
        except Exception as e2:
            logging.warning(f"{coin} 币安多空比（大户账户数）获取失败：{e2}")
        
        # 接口3：多空持仓人数比
        try:
            url3 = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={coin_symbol}&period=5m&limit=5"
            resp3 = requests.get(url3, timeout=10, headers=headers)
            resp3.raise_for_status()
            json_data3 = resp3.json()
            
            if isinstance(json_data3, list) and len(json_data3) >= 1:
                data3 = json_data3
                
                for item in data3:
                    if isinstance(item, dict):
                        timestamp_ms = int(item.get('timestamp', 0))
                        long_short_ratio = float(item.get('longShortRatio', 0))
                        
                        if timestamp_ms <= 0:
                            continue
                        
                        # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
                        ts_datetime_utc8 = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
                        
                        # 检查并保存接口3的数据（每条数据都进行一致性检查）
                        result = db_service.save_binance_long_short_ratio_partial(
                            coin, coin_symbol, ts_datetime_utc8, 
                            global_account_ratio=long_short_ratio
                        )
                        if result == 'saved':
                            total_saved += 1
                            logging.debug(f"{coin} 币安多空比（多空持仓人数）数据新增: {ts_datetime_utc8} ratio={long_short_ratio}")
                        elif result == 'updated':
                            total_updated += 1
                            logging.debug(f"{coin} 币安多空比（多空持仓人数）数据更新: {ts_datetime_utc8} ratio={long_short_ratio}")
                        elif result == 'skipped':
                            total_skipped += 1
                            logging.debug(f"{coin} 币安多空比（多空持仓人数）数据一致，跳过: {ts_datetime_utc8} ratio={long_short_ratio}")
        except Exception as e3:
            logging.warning(f"{coin} 币安多空比（多空持仓人数）获取失败：{e3}")
        
        if total_saved > 0 or total_updated > 0:
            logging.info(f"{coin} 币安多空比数据保存完成: 新增={total_saved}, 更新={total_updated}, 跳过={total_skipped}")
            return True
        else:
            logging.debug(f"{coin} 币安多空比数据全部已存在，无需保存")
            return True
        
    except Exception as e:
        logging.error(f"{coin} 币安多空比收集失败：{e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        return False


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_binance_long_short_ratio(coin, coin_symbol):
    """收集币安多空比数据"""
    # 为每个线程创建独立的数据库连接
    thread_db = BinanceDatabaseService(**DB_CONFIG)
    try:
        if not thread_db.connect():
            logging.error(f"{coin} 币安数据库连接失败")
            return False
        
        return collect_binance_long_short_ratio_with_db(coin, coin_symbol, thread_db)
    finally:
        try:
            thread_db.disconnect()
        except:
            pass


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
def collect_binance_funding_rate(coin, coin_symbol):
    """收集币安资金费率数据（实时资金费率）"""
    try:
        # 使用 /fapi/v1/fundingRate 接口获取最新的资金费率
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={coin_symbol}&limit=1"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        json_data = resp.json()
        
        if not isinstance(json_data, list) or len(json_data) == 0:
            logging.warning(f"{coin} 币安资金费率：数据为空")
            return False
        
        # 获取最新的资金费率数据
        item = json_data[0]
        if isinstance(item, dict):
            funding_rate = float(item.get('fundingRate', 0))
            funding_time_ms = int(item.get('fundingTime', 0))
            
            if funding_time_ms <= 0:
                logging.warning(f"{coin} 币安资金费率：时间戳无效")
                return False
            
            # 使用接口返回的时间戳转换为UTC+8时间（确保时间戳准确性）
            ts_datetime_utc8 = datetime.fromtimestamp(funding_time_ms / 1000.0, tz=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)
            funding_rate_pct = funding_rate * 100
            
            # 为每个线程创建独立的数据库连接
            thread_db = BinanceDatabaseService(**DB_CONFIG)
            try:
                if not thread_db.connect():
                    logging.error(f"{coin} 币安数据库连接失败")
                    return False
                
                result = thread_db.save_funding_rate(
                    coin, coin_symbol, ts_datetime_utc8,
                    funding_rate, funding_rate_pct
                )
                if result:
                    logging.info(f"{coin} 币安资金费率数据保存成功: rate={funding_rate} ({funding_rate_pct}%), time={ts_datetime_utc8}")
                return result
            finally:
                try:
                    thread_db.disconnect()
                except:
                    pass
        else:
            logging.warning(f"{coin} 币安资金费率：数据格式错误")
            return False
        
    except Exception as e:
        error_msg = f"{coin} 币安资金费率收集失败：{type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        raise  # 重新抛出异常以触发重试机制


def collect_binance_data():
    """收集币安数据（每分钟）：持仓量、主动买卖量（串行执行确保ID连续）"""
    try:
        start_time = time.time()
        
        # 串行执行每个币种的数据收集，确保ID连续（不使用线程池）
        for coin, config in BINANCE_COINS.items():
            coin_symbol = config['symbol']
            try:
                collect_binance_open_interest(coin, coin_symbol)
                collect_binance_taker_volume(coin, coin_symbol)
                collect_binance_basis(coin, coin_symbol)
                collect_binance_long_short_ratio(coin, coin_symbol)
                collect_binance_funding_rate(coin, coin_symbol)
            except Exception as e:
                logging.error(f"{coin} 币安数据收集失败: {e}")
                import traceback
                logging.error(f"{coin} 币安数据收集异常详情: {traceback.format_exc()}")
                continue  # 继续处理下一个币种
        
        elapsed_time = time.time() - start_time
        if elapsed_time > 30:
            logging.warning(f"币安市场数据收集耗时 {elapsed_time:.2f} 秒，可能影响下次执行")
    except Exception as e:
        # 顶层异常捕获，确保不会影响调度器
        logging.error(f"币安数据收集任务发生未预期异常: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")


def collect_frequent_data():
    """收集高频数据（每分钟）：Taker主动量、持仓量"""
    try:
        start_time = time.time()
        # logging.info("=" * 80)
        # logging.info("开始收集高频市场数据（每分钟）")
        # logging.info("=" * 80)
    
        def collect_coin_data(coin, coin_symbol):
            """收集单个币种的数据（每个线程使用独立的数据库连接）"""
            # 为每个线程创建独立的数据库连接
            thread_db = MarketDataDatabaseService(**DB_CONFIG)
            try:
                if not thread_db.connect():
                    logging.error(f"{coin} 数据库连接失败")
                    return False
                
                # 使用线程本地数据库连接收集数据
                collect_taker_volume_with_db(coin, coin_symbol, thread_db)
                collect_open_interest_with_db(coin, coin_symbol, thread_db)
                return True
            except Exception as e:
                logging.error(f"{coin} 高频数据收集失败: {e}")
                import traceback
                logging.error(f"{coin} 高频数据收集异常详情: {traceback.format_exc()}")
                return False
            finally:
                # 确保关闭线程本地连接
                try:
                    thread_db.disconnect()
                except:
                    pass
        
        # 使用线程池并行收集多个币种的数据，提高效率
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            for coin, config in SUPPORTED_COINS.items():
                coin_symbol = config['symbol']
                future = executor.submit(collect_coin_data, coin, coin_symbol)
                futures[future] = coin
            
            # 等待所有任务完成，设置超时（最多30秒）
            for future in futures:
                coin = futures[future]
                try:
                    future.result(timeout=30)
                except FutureTimeoutError:
                    logging.warning(f"{coin} 高频数据收集超时（30秒）")
                except Exception as e:
                    logging.error(f"{coin} 高频数据收集异常: {e}")
                    import traceback
                    logging.error(f"{coin} 高频数据收集异常详情: {traceback.format_exc()}")
        
        elapsed_time = time.time() - start_time
        if elapsed_time > 30:
            logging.warning(f"高频市场数据收集耗时 {elapsed_time:.2f} 秒，可能影响下次执行")
        # logging.info("高频市场数据收集完成")
        # logging.info("=" * 80)
    except Exception as e:
        # 顶层异常捕获，确保不会影响调度器
        logging.error(f"高频数据收集任务发生未预期异常: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")


def collect_periodic_data():
    """收集周期性数据（每5分钟）：资金费率、多空比"""
    try:
        start_time = time.time()
        # logging.info("=" * 80)
        # logging.info("开始收集周期性市场数据（每5分钟）")
        # logging.info("=" * 80)
    
        def collect_coin_data(coin, coin_symbol):
            """收集单个币种的数据（每个线程使用独立的数据库连接）"""
            # 为每个线程创建独立的数据库连接
            thread_db = MarketDataDatabaseService(**DB_CONFIG)
            try:
                if not thread_db.connect():
                    logging.error(f"{coin} 数据库连接失败")
                    return False
                
                # 使用线程本地数据库连接收集数据
                collect_funding_rate_with_db(coin, coin_symbol, thread_db)
                collect_long_short_ratio_with_db(coin, coin_symbol, thread_db)
                return True
            except Exception as e:
                logging.error(f"{coin} 周期性数据收集失败: {e}")
                import traceback
                logging.error(f"{coin} 周期性数据收集异常详情: {traceback.format_exc()}")
                return False
            finally:
                # 确保关闭线程本地连接
                try:
                    thread_db.disconnect()
                except:
                    pass
        
        # 使用线程池并行收集多个币种的数据，提高效率
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            for coin, config in SUPPORTED_COINS.items():
                coin_symbol = config['symbol']
                future = executor.submit(collect_coin_data, coin, coin_symbol)
                futures[future] = coin
            
            # 等待所有任务完成，设置超时（最多60秒）
            for future in futures:
                coin = futures[future]
                try:
                    future.result(timeout=60)
                except FutureTimeoutError:
                    logging.warning(f"{coin} 周期性数据收集超时（60秒）")
                except Exception as e:
                    logging.error(f"{coin} 周期性数据收集异常: {e}")
                    import traceback
                    logging.error(f"{coin} 周期性数据收集异常详情: {traceback.format_exc()}")
        
        elapsed_time = time.time() - start_time
        if elapsed_time > 60:
            logging.warning(f"周期性市场数据收集耗时 {elapsed_time:.2f} 秒，可能影响下次执行")
        # logging.info("周期性市场数据收集完成")
        # logging.info("=" * 80)
    except Exception as e:
        # 顶层异常捕获，确保不会影响调度器
        logging.error(f"周期性数据收集任务发生未预期异常: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")


def collect_macro_economic_data():
    """收集宏观经济数据（仅在整点时获取）"""
    try:
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
    except Exception as e:
        # 顶层异常捕获，确保不会影响调度器
        logging.error(f"宏观经济数据收集任务发生未预期异常: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")


# ==================== 主程序 ====================
if __name__ == "__main__":
    logging.info("市场数据收集服务启动")
    
    # 初始化数据库表
    try:
        if market_db.connect():
            market_db.create_tables()
        if liquidation_db.connect():
            liquidation_db.create_tables()
        if binance_db.connect():
            binance_db.create_tables()
        logging.info("数据库表初始化完成")
    except Exception as e:
        logging.error(f"数据库初始化失败: {e}")
    
    # 启动OKX爆仓数据WebSocket监听器（后台运行）
    try:
        liquidation_listener = OKXLiquidationListener()
        liquidation_listener.start()
        logging.info("OKX爆仓数据WebSocket监听器启动成功")
    except Exception as e:
        logging.error(f"OKX爆仓数据WebSocket监听器启动失败: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        logging.warning("将继续运行其他数据收集任务，但OKX爆仓数据将无法收集")
    
    # 启动币安爆仓数据WebSocket监听器（后台运行）
    try:
        binance_liquidation_listener = BinanceLiquidationListener()
        binance_liquidation_listener.start()
        logging.info("币安爆仓数据WebSocket监听器启动成功")
    except Exception as e:
        logging.error(f"币安爆仓数据WebSocket监听器启动失败: {e}")
        import traceback
        logging.error(f"异常详情: {traceback.format_exc()}")
        logging.warning("将继续运行其他数据收集任务，但币安爆仓数据将无法收集")
    
    # 立即执行一次所有数据收集（即使失败也不影响后续定时任务）
    try:
        collect_frequent_data()
    except Exception as e:
        logging.error(f"初始高频数据收集失败: {e}")
    
    try:
        collect_periodic_data()
    except Exception as e:
        logging.error(f"初始周期性数据收集失败: {e}")
    
    try:
        collect_binance_data()
    except Exception as e:
        logging.error(f"初始币安数据收集失败: {e}")
    
    try:
        collect_macro_economic_data()
    except Exception as e:
        logging.error(f"初始宏观经济数据收集失败: {e}")
    
    # 设置定时任务
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    
    # 高频数据：每分钟的第30秒执行（Taker主动量、持仓量）
    # max_instances=5: 允许最多5个实例并发运行，避免任务堆积
    # coalesce=True: 如果任务堆积，合并为一次执行
    # misfire_grace_time=30: 任务错过执行后30秒内仍可执行（减少堆积）
    scheduler.add_job(
        collect_frequent_data, 
        'cron', 
        minute='*', 
        second='30',
        max_instances=5,
        coalesce=True,
        misfire_grace_time=30
    )
    # logging.info("高频数据收集调度：每分钟的第30秒（Taker主动量、持仓量）")
    
    # 周期性数据：每5分钟的第30秒执行（资金费率、多空比）
    scheduler.add_job(
        collect_periodic_data, 
        'cron', 
        minute='*/5', 
        second='30',
        max_instances=3,
        coalesce=True,
        misfire_grace_time=120
    )
    # logging.info("周期性数据收集调度：每5分钟的第30秒（资金费率、多空比）")
    
    # 币安数据：每分钟的第35秒执行（持仓量、主动买卖量）
    scheduler.add_job(
        collect_binance_data, 
        'cron', 
        minute='*', 
        second='35',
        max_instances=5,
        coalesce=True,
        misfire_grace_time=30
    )
    # logging.info("币安数据收集调度：每分钟的第35秒（持仓量、主动买卖量）")
    
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
    
    # 添加调度器异常监听器，确保任务异常不会导致调度器崩溃
    def job_listener(event):
        """监听任务执行事件"""
        if event.exception:
            logging.error(f"定时任务执行失败: {event.job_id}, 异常: {event.exception}")
            import traceback
            logging.error(f"异常详情: {traceback.format_exc()}")
        else:
            logging.debug(f"定时任务执行成功: {event.job_id}")
    
    scheduler.add_listener(job_listener, 
                          apscheduler.events.EVENT_JOB_EXECUTED | 
                          apscheduler.events.EVENT_JOB_ERROR)
    
    logging.info("市场数据收集调度器启动")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("程序被用户中断")
        scheduler.shutdown()
    except Exception as e:
        # 捕获所有未预期的异常，确保程序不会静默崩溃
        logging.critical(f"调度器发生严重错误: {e}")
        import traceback
        logging.critical(f"异常详情: {traceback.format_exc()}")
        try:
            scheduler.shutdown()
        except:
            pass
        raise  # 重新抛出异常，让系统知道程序异常退出