#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OKX WebSocket 订单簿监听器
实时获取订单簿数据（books5）
"""

import json
import threading
import time
from datetime import datetime
import websocket


class OKXOrderbookWatcher:
    """OKX订单簿监听器 - WebSocket实时订阅"""
    
    def __init__(self, symbols, test_mode=False):
        """
        初始化订单簿监听器
        
        Args:
            symbols: 交易对列表，如 ['ETH-USDT-SWAP', 'BTC-USDT-SWAP']
            test_mode: 是否测试模式
        """
        self.symbols = symbols if isinstance(symbols, list) else [symbols]
        self.test_mode = test_mode
        
        # WebSocket URL
        if test_mode:
            self.ws_url = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"
        else:
            self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        
        # 订单簿数据缓存 {symbol: {'bids': [...], 'asks': [...], 'timestamp': ...}}
        self.orderbooks = {}
        
        # WebSocket连接
        self.ws = None
        self.ws_thread = None
        self.running = False
        
        # 锁，保证线程安全
        self.lock = threading.Lock()
        
        print(f"📡 OKX订单簿监听器初始化")
        print(f"   交易对: {', '.join(self.symbols)}")
        print(f"   模式: {'测试' if test_mode else '实盘'}")
    
    def start(self):
        """启动订单簿监听"""
        if self.running:
            print("⚠️  订单簿监听器已在运行")
            return
        
        self.running = True
        self.ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
        self.ws_thread.start()
        
        # 等待连接建立
        print("⏳ 等待WebSocket连接...")
        time.sleep(2)
        
        if self.orderbooks:
            print("✅ 订单簿监听器启动成功")
        else:
            print("⚠️  订单簿监听器启动，但尚未收到数据")
    
    def _run_websocket(self):
        """运行WebSocket连接（在独立线程中）"""
        while self.running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                
                # 运行WebSocket（阻塞）
                self.ws.run_forever()
                
                # 如果断开，等待5秒后重连
                if self.running:
                    print("🔄 WebSocket断开，5秒后重连...")
                    time.sleep(5)
                    
            except Exception as e:
                print(f"❌ WebSocket运行异常: {e}")
                if self.running:
                    time.sleep(5)
    
    def _on_open(self, ws):
        """WebSocket连接建立"""
        print("✅ WebSocket连接已建立")
        
        # 订阅所有交易对的订单簿
        for symbol in self.symbols:
            subscribe_msg = {
                "op": "subscribe",
                "args": [
                    {
                        "channel": "books5",
                        "instId": symbol
                    }
                ]
            }
            ws.send(json.dumps(subscribe_msg))
            print(f"📡 已订阅 {symbol} 订单簿")
    
    def _on_message(self, ws, message):
        """接收WebSocket消息"""
        try:
            data = json.loads(message)
            
            # 处理订阅确认消息
            if 'event' in data:
                if data['event'] == 'subscribe':
                    print(f"✅ 订阅成功: {data.get('arg', {}).get('instId')}")
                return
            
            # 处理订单簿数据
            if 'data' in data and data.get('arg', {}).get('channel') == 'books5':
                self._process_orderbook(data)
                
        except Exception as e:
            print(f"❌ 处理消息失败: {e}")
    
    def _on_error(self, ws, error):
        """WebSocket错误"""
        print(f"❌ WebSocket错误: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭"""
        print(f"🔌 WebSocket连接关闭: {close_status_code} - {close_msg}")
    
    def _process_orderbook(self, data):
        """处理订单簿数据"""
        try:
            symbol = data['arg']['instId']
            orderbook_data = data['data'][0]
            
            # 解析买卖盘
            bids = [[float(bid[0]), float(bid[1])] for bid in orderbook_data['bids']]
            asks = [[float(ask[0]), float(ask[1])] for ask in orderbook_data['asks']]
            
            # 更新缓存（线程安全）
            with self.lock:
                self.orderbooks[symbol] = {
                    'bids': bids,  # [[price, size], ...] 从高到低排序
                    'asks': asks,  # [[price, size], ...] 从低到高排序
                    'timestamp': datetime.now(),
                    'ts': orderbook_data.get('ts')
                }
            
            # 打印订单簿更新（每10次打印一次，避免刷屏）
            # if not hasattr(self, '_update_count'):
            #     self._update_count = {}
            # self._update_count[symbol] = self._update_count.get(symbol, 0) + 1
            # if self._update_count[symbol] % 10 == 0:
            #     print(f"📊 {symbol} 订单簿更新: 买1={bids[0][0]:.2f}, 卖1={asks[0][0]:.2f}")
                
        except Exception as e:
            print(f"❌ 处理订单簿数据失败: {e}")
    
    def stop(self):
        """停止订单簿监听"""
        self.running = False
        if self.ws:
            self.ws.close()
        print("🛑 订单簿监听器已停止")
    
    def _run_websocket(self):
        """运行WebSocket连接（在独立线程中）"""
        while self.running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                
                # 运行WebSocket（阻塞）
                self.ws.run_forever()
                
                # 如果断开，等待5秒后重连
                if self.running:
                    print("🔄 WebSocket断开，5秒后重连...")
                    time.sleep(5)
                    
            except Exception as e:
                print(f"❌ WebSocket运行异常: {e}")
                if self.running:
                    time.sleep(5)
    
    def _on_open(self, ws):
        """WebSocket连接建立"""
        print("✅ WebSocket连接已建立")
        
        # 订阅所有交易对的订单簿
        for symbol in self.symbols:
            subscribe_msg = {
                "op": "subscribe",
                "args": [
                    {
                        "channel": "books5",
                        "instId": symbol
                    }
                ]
            }
            ws.send(json.dumps(subscribe_msg))
            print(f"📡 已订阅 {symbol} 订单簿")
    
    def _on_message(self, ws, message):
        """接收WebSocket消息"""
        try:
            data = json.loads(message)
            
            # 处理订阅确认消息
            if 'event' in data:
                if data['event'] == 'subscribe':
                    print(f"✅ 订阅成功: {data.get('arg', {}).get('instId')}")
                return
            
            # 处理订单簿数据
            if 'data' in data and data.get('arg', {}).get('channel') == 'books5':
                self._process_orderbook(data)
                
        except Exception as e:
            print(f"❌ 处理消息失败: {e}")
    
    def _on_error(self, ws, error):
        """WebSocket错误"""
        print(f"❌ WebSocket错误: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭"""
        print(f"🔌 WebSocket连接关闭: {close_status_code} - {close_msg}")
    
    def _process_orderbook(self, data):
        """处理订单簿数据"""
        try:
            symbol = data['arg']['instId']
            orderbook_data = data['data'][0]
            
            # 解析买卖盘
            bids = [[float(bid[0]), float(bid[1])] for bid in orderbook_data['bids']]
            asks = [[float(ask[0]), float(ask[1])] for ask in orderbook_data['asks']]
            
            # 更新缓存（线程安全）
            with self.lock:
                self.orderbooks[symbol] = {
                    'bids': bids,  # [[price, size], ...] 从高到低排序
                    'asks': asks,  # [[price, size], ...] 从低到高排序
                    'timestamp': datetime.now(),
                    'ts': orderbook_data.get('ts')
                }
            
            # 打印订单簿更新（每10次打印一次，避免刷屏）
            # if not hasattr(self, '_update_count'):
            #     self._update_count = {}
            # self._update_count[symbol] = self._update_count.get(symbol, 0) + 1
            # if self._update_count[symbol] % 10 == 0:
            #     print(f"📊 {symbol} 订单簿更新: 买1={bids[0][0]:.2f}, 卖1={asks[0][0]:.2f}")
                
        except Exception as e:
            print(f"❌ 处理订单簿数据失败: {e}")
    
    def get_orderbook(self, symbol):
        """
        获取订单簿数据
        
        Args:
            symbol: 交易对符号
        
        Returns:
            dict: {'bids': [...], 'asks': [...], 'timestamp': ...}
            如果没有数据，返回 None
        """
        with self.lock:
            return self.orderbooks.get(symbol)
    
    def get_best_bid_ask(self, symbol):
        """
        获取最优买卖价
        
        Args:
            symbol: 交易对符号
        
        Returns:
            tuple: (bid1_price, ask1_price) 或 (None, None)
        """
        orderbook = self.get_orderbook(symbol)
        if not orderbook:
            return None, None
        
        bid1 = orderbook['bids'][0][0] if orderbook['bids'] else None
        ask1 = orderbook['asks'][0][0] if orderbook['asks'] else None
        
        return bid1, ask1
    
    def get_bid_price(self, symbol, level=1):
        """
        获取买盘价格
        
        Args:
            symbol: 交易对符号
            level: 档位（1-5），1=买1，3=买3
        
        Returns:
            float: 买盘价格，如果没有数据返回 None
        """
        orderbook = self.get_orderbook(symbol)
        if not orderbook or len(orderbook['bids']) < level:
            return None
        
        return orderbook['bids'][level - 1][0]
    
    def get_ask_price(self, symbol, level=1):
        """
        获取卖盘价格
        
        Args:
            symbol: 交易对符号
            level: 档位（1-5），1=卖1，3=卖3
        
        Returns:
            float: 卖盘价格，如果没有数据返回 None
        """
        orderbook = self.get_orderbook(symbol)
        if not orderbook or len(orderbook['asks']) < level:
            return None
        
        return orderbook['asks'][level - 1][0]
    
    def get_spread(self, symbol):
        """
        获取买卖价差
        
        Args:
            symbol: 交易对符号
        
        Returns:
            float: 价差（卖1 - 买1），如果没有数据返回 None
        """
        bid1, ask1 = self.get_best_bid_ask(symbol)
        if bid1 is None or ask1 is None:
            return None
        
        return ask1 - bid1
    
    def print_orderbook(self, symbol, depth=5):
        """
        打印订单簿（用于调试）
        
        Args:
            symbol: 交易对符号
            depth: 显示深度
        """
        orderbook = self.get_orderbook(symbol)
        if not orderbook:
            print(f"❌ 没有 {symbol} 的订单簿数据")
            return
        
        print(f"\n{'='*50}")
        print(f"📊 {symbol} 订单簿")
        print(f"⏰ 时间: {orderbook['timestamp'].strftime('%H:%M:%S')}")
        print(f"{'='*50}")
        
        # 卖盘（从上到下：卖5 -> 卖1）
        for i in range(min(depth, len(orderbook['asks'])) - 1, -1, -1):
            price, size = orderbook['asks'][i]
            print(f"卖{i+1}: {price:>10.2f}  |  {size:>8.4f}")
        
        print(f"{'-'*50}")
        
        # 价差
        if orderbook['bids'] and orderbook['asks']:
            spread = orderbook['asks'][0][0] - orderbook['bids'][0][0]
            print(f"价差: {spread:>10.2f}")
        
        print(f"{'-'*50}")
        
        # 买盘（从上到下：买1 -> 买5）
        for i in range(min(depth, len(orderbook['bids']))):
            price, size = orderbook['bids'][i]
            print(f"买{i+1}: {price:>10.2f}  |  {size:>8.4f}")
        
        print(f"{'='*50}\n")


# 测试代码
if __name__ == '__main__':
    # 创建订单簿监听器
    watcher = OKXOrderbookWatcher(['ETH-USDT-SWAP'], test_mode=False)
    
    # 启动监听
    watcher.start()
    
    # 等待几秒，让数据稳定
    time.sleep(5)
    
    # 测试获取数据
    print("\n📊 测试获取订单簿数据:")
    
    symbol = 'ETH-USDT-SWAP'
    
    # 1. 获取买3/卖3价格
    bid3 = watcher.get_bid_price(symbol, level=3)
    ask3 = watcher.get_ask_price(symbol, level=3)
    print(f"买3价: {bid3}")
    print(f"卖3价: {ask3}")
    
    # 2. 获取价差
    spread = watcher.get_spread(symbol)
    print(f"价差: {spread}")
    
    # 3. 打印完整订单簿
    watcher.print_orderbook(symbol)
    
    # 保持运行
    try:
        while True:
            time.sleep(10)
            watcher.print_orderbook(symbol)
    except KeyboardInterrupt:
        print("\n退出...")
        watcher.stop()

