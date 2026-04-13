#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立爆仓监控脚本（OKX + Binance）

功能：
1. 监听 OKX / Binance 的爆仓 WebSocket
2. 仅处理 MONITORED_COINS 中的币种
3. 仅当 USD 价值 >= LIQUIDATION_THRESHOLD_USD 时推送飞书

运行：
  pip install requests websocket-client
  python data/liquidation_monitor.py
"""

import json
import logging
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

# 使用 websocket-client（不是 websocket）
try:
    import websocket
    if not hasattr(websocket, 'WebSocketApp'):
        raise ImportError("检测到错误 websocket 包，请安装 websocket-client")
except Exception as e:
    raise ImportError("请先安装 websocket-client：pip install websocket-client") from e


# ==================== 配置 ====================
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/66c61d2e-50bf-4b36-a8ce-e737e12dab9e"

# 监控币种过滤（改这里）
MONITORED_COINS = {"BTC", "ETH", "RAVE"}

# 仅推送大于等于该阈值的爆仓（USD）
LIQUIDATION_THRESHOLD_USD = 500

# OKX 各币种每张合约面值（币本位数量）
OKX_CONTRACT_SIZE = {
    "BTC": 0.01,
    "ETH": 0.1,
    "RAVE": 10.0
}


# ==================== 日志 ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def format_usd(value: float) -> str:
    if value >= 10000:
        return f"{value / 10000:.2f} 万美元"
    return f"{value:,.2f} 美元"


def send_feishu_message(content: str) -> None:
    payload = {
        "msg_type": "text",
        "content": {"text": content},
    }
    try:
        resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0:
            logging.info("✅ 飞书消息推送成功")
        else:
            logging.warning(f"⚠️ 飞书返回异常: {data}")
    except Exception as e:
        logging.error(f"飞书推送失败: {e}")


def build_message(exchange: str, coin: str, usd_value: float, liq_type: str, side: str, price: float, qty: float, ts_dt: datetime) -> str:
    lines = [
        f"🚨 {exchange} 大额爆仓提醒",
        "",
        f"💰 币种: {coin}",
        f"💵 价值: {format_usd(usd_value)}",
        f"📊 类型: {liq_type}",
    ]
    if side:
        lines.append(f"📈 方向: {side}")
    if price is not None:
        lines.append(f"💲 价格: {price:,.4f}")
    if qty is not None:
        lines.append(f"📦 数量: {qty:,.4f}")
    lines.append(f"⏰ 时间: {ts_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


class OKXLiquidationListener:
    def __init__(self):
        self.ws = None
        self.thread = None
        self.ping_thread = None
        self.running = False
        self.last_pong = time.time()
        self.ping_interval = 20

    def on_message(self, _ws, message):
        try:
            if message == "pong":
                self.last_pong = time.time()
                return

            data = json.loads(message)
            if data.get("event") == "pong":
                self.last_pong = time.time()
                return
            if data.get("event") == "subscribe":
                logging.info("OKX 订阅成功")
                return

            orders = data.get("data", [])
            if not isinstance(orders, list):
                return

            for order in orders:
                uly = (order.get("uly") or "").upper()
                coin = uly.replace("-USDT", "")
                if coin not in MONITORED_COINS:
                    continue

                details = order.get("details", [])
                if not isinstance(details, list):
                    continue

                contract_size = OKX_CONTRACT_SIZE.get(coin, 0.0)
                if contract_size <= 0:
                    continue

                for d in details:
                    try:
                        bk_px = float(d.get("bkPx", 0) or 0)
                        sz = float(d.get("sz", 0) or 0)
                        ts_ms = int(d.get("ts", 0) or 0)
                        pos_side = (d.get("posSide", "") or "").lower()
                        side = (d.get("side", "") or "").upper()
                        if bk_px <= 0 or sz <= 0 or ts_ms <= 0:
                            continue

                        usd_value = bk_px * sz * contract_size
                        if usd_value < LIQUIDATION_THRESHOLD_USD:
                            continue

                        liq_type = "多单爆仓" if pos_side == "long" else ("空单爆仓" if pos_side == "short" else "未知")
                        side_txt = "卖出" if side == "SELL" else ("买入" if side == "BUY" else "")
                        ts_dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

                        msg = build_message("OKX", coin, usd_value, liq_type, side_txt, bk_px, sz, ts_dt)
                        send_feishu_message(msg)
                    except Exception:
                        continue
        except Exception as e:
            logging.error(f"OKX 消息处理错误: {e}")

    def on_open(self, ws):
        sub = {"op": "subscribe", "args": [{"channel": "liquidation-orders", "instType": "SWAP"}]}
        ws.send(json.dumps(sub))
        self.last_pong = time.time()
        logging.info(f"OKX 监听已启动，过滤币种: {sorted(MONITORED_COINS)}")

    def on_error(self, _ws, error):
        logging.warning(f"OKX WebSocket 错误: {error}")

    def on_close(self, _ws, code, msg):
        logging.warning(f"OKX WebSocket 关闭: code={code}, msg={msg}，5秒后重连")
        self.running = False
        time.sleep(5)
        self.start()

    def _ping_loop(self):
        while self.running:
            time.sleep(self.ping_interval)
            try:
                if self.ws and self.ws.sock:
                    if time.time() - self.last_pong > self.ping_interval * 2:
                        self.ws.close()
                        break
                    self.ws.send("ping")
            except Exception:
                break

    def start(self):
        if self.running:
            return
        self.running = True
        self.ws = websocket.WebSocketApp(
            "wss://ws.okx.com:8443/ws/v5/public",
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.thread.start()
        self.ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self.ping_thread.start()


class BinanceLiquidationListener:
    def __init__(self):
        self.ws = None
        self.thread = None
        self.ping_thread = None
        self.running = False
        self.last_pong = time.time()
        self.ping_interval = 20

    def _stream_url(self) -> str:
        streams = [f"{coin.lower()}usdt@forceOrder" for coin in MONITORED_COINS]
        return "wss://fstream.binance.com/stream?streams=" + "/".join(streams)

    def on_message(self, _ws, message):
        try:
            if message in ("pong", b"pong"):
                self.last_pong = time.time()
                return

            payload = json.loads(message)
            if "stream" in payload and "data" in payload:
                payload = payload["data"]

            if payload.get("e") != "forceOrder":
                return

            order = payload.get("o", {})
            symbol = (order.get("s", "") or "").upper()
            if not symbol.endswith("USDT"):
                return
            coin = symbol.replace("USDT", "")
            if coin not in MONITORED_COINS:
                return

            side_raw = (order.get("S", "") or "").upper()  # SELL=多单爆仓, BUY=空单爆仓
            liq_type = "多单爆仓" if side_raw == "SELL" else ("空单爆仓" if side_raw == "BUY" else "未知")
            side_txt = "卖出" if side_raw == "SELL" else ("买入" if side_raw == "BUY" else "")

            qty = float(order.get("q", 0) or 0)
            price = float(order.get("p", 0) or 0)
            ts_ms = int(order.get("T", 0) or payload.get("E", 0) or 0)
            if qty <= 0 or price <= 0 or ts_ms <= 0:
                return

            usd_value = qty * price
            if usd_value < LIQUIDATION_THRESHOLD_USD:
                return

            ts_dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
            msg = build_message("Binance", coin, usd_value, liq_type, side_txt, price, qty, ts_dt)
            send_feishu_message(msg)
        except Exception as e:
            logging.error(f"Binance 消息处理错误: {e}")

    def on_open(self, _ws):
        self.last_pong = time.time()
        logging.info(f"Binance 监听已启动，过滤币种: {sorted(MONITORED_COINS)}")

    def on_error(self, _ws, error):
        logging.warning(f"Binance WebSocket 错误: {error}")

    def on_close(self, _ws, code, msg):
        logging.warning(f"Binance WebSocket 关闭: code={code}, msg={msg}，5秒后重连")
        self.running = False
        time.sleep(5)
        self.start()

    def _ping_loop(self):
        while self.running:
            time.sleep(self.ping_interval)
            try:
                if self.ws and self.ws.sock:
                    if time.time() - self.last_pong > self.ping_interval * 3:
                        self.ws.close()
                        break
                    self.ws.send("ping")
            except Exception:
                break

    def start(self):
        if self.running:
            return
        self.running = True
        self.ws = websocket.WebSocketApp(
            self._stream_url(),
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.thread.start()
        self.ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self.ping_thread.start()


def main():
    logging.info("=" * 60)
    logging.info("OKX + Binance 爆仓监控启动")
    logging.info(f"监控币种: {sorted(MONITORED_COINS)}")
    logging.info(f"阈值: {LIQUIDATION_THRESHOLD_USD:,.0f} USD")
    logging.info("=" * 60)

    okx_listener = OKXLiquidationListener()
    binance_listener = BinanceLiquidationListener()

    okx_listener.start()
    binance_listener.start()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logging.info("监控已停止")


if __name__ == "__main__":
    main()
