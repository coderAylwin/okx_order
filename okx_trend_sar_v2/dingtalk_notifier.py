#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import hmac
import hashlib
import base64
import urllib.parse
import subprocess
import tempfile
import os
from datetime import datetime, timedelta

class DingTalkNotifier:
    """钉钉消息推送器"""
    
    def __init__(self, webhook_url, secret=None):
        """
        初始化钉钉推送器
        
        Args:
            webhook_url: 钉钉webhook地址
            secret: 加签密钥（如果机器人设置了加签）
        """
        self.webhook_url = webhook_url
        self.secret = secret
    
    def _generate_sign(self):
        """
        生成钉钉加签
        
        Returns:
            tuple: (timestamp, sign)
        """
        if not self.secret:
            return None, None
        
        # 获取当前时间戳（毫秒）
        timestamp = str(round(time.time() * 1000))
        
        # 拼接签名字符串
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, self.secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        
        # 使用HmacSHA256算法计算签名
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        
        # Base64编码
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        
        return timestamp, sign
    
    def send_message(self, title, content):
        """
        发送markdown消息到钉钉
        
        Args:
            title: 消息标题
            content: 消息内容（支持markdown格式）
        """
        try:
            # 生成签名（如果有密钥）
            timestamp, sign = self._generate_sign()
            
            # 构建完整的URL
            url = self.webhook_url
            if timestamp and sign:
                # 添加签名参数到URL
                separator = '&' if '?' in url else '?'
                url = f"{url}{separator}timestamp={timestamp}&sign={sign}"
            
            headers = {'Content-Type': 'application/json'}
            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": content
                }
            }
            
            # 使用curl命令避免Python SSL问题
            # 创建临时文件存储JSON数据
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                json_file = f.name
            
            try:
                # 构建curl命令
                curl_cmd = [
                    'curl', '-X', 'POST',
                    url,
                    '-H', 'Content-Type: application/json',
                    '-d', f'@{json_file}',
                    '--max-time', '10'
                ]
                
                # 执行curl命令
                result = subprocess.run(
                    curl_cmd,
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                # 解析响应
                if result.returncode == 0:
                    response_data = json.loads(result.stdout)
                    if response_data.get('errcode') == 0:
                        print(f"✅ 钉钉消息推送成功: {title}")
                    else:
                        print(f"❌ 钉钉消息推送失败: {response_data.get('errmsg', '未知错误')}")
                    return response_data
                else:
                    print(f"❌ curl执行失败: {result.stderr}")
                    return None
                    
            finally:
                # 清理临时文件
                try:
                    os.unlink(json_file)
                except:
                    pass
        except Exception as e:
            print(f"❌ 钉钉消息推送异常: {str(e)}")
            return None
    
    def send_indicator_update(self, timestamp, timeframe, sar_result, position_info=None, atr_info=None):
        """
        发送周期结束时的指标更新消息
        
        Args:
            timestamp: 时间戳
            timeframe: 时间周期
            sar_result: SAR指标结果
            position_info: 持仓信息（可选）
        """
        # 🔴 计算完整周期时间范围
        period_minutes = int(timeframe.replace('m', '').replace('h', '')) if 'm' in timeframe else int(timeframe.replace('h', '')) * 60
        
        # 计算周期开始时间（向下取整到周期边界）
        period_start = timestamp.replace(second=0, microsecond=0)
        period_start_minute = (period_start.minute // period_minutes) * period_minutes
        period_start = period_start.replace(minute=period_start_minute)
        
        # 计算周期结束时间
        period_end = period_start + timedelta(minutes=period_minutes) - timedelta(seconds=1)
        
        # 格式化时间范围
        time_range = f"{period_start.strftime('%Y-%m-%d %H:%M:%S')} - {period_end.strftime('%H:%M:%S')}"
        
        # 构建基础指标信息
        content = f"## 📊 {timeframe}周期指标更新\n\n"
        content += f"**⏰ 时间**: {time_range}\n\n"
        content += f"---\n\n"
        
        # SAR指标信息
        sar_direction = "📈 上升" if sar_result.get('sar_rising') else "📉 下降"
        content += f"**SAR值**: {sar_result.get('sar_value', 0):.2f} {sar_direction}\n\n"
        
        # RSI指标信息（添加开仓条件判断）
        rsi_value = sar_result.get('rsi', 0)
        rsi_long_condition = rsi_value <= 75
        rsi_short_condition = rsi_value >= 25
        rsi_long_status = "✅" if rsi_long_condition else "❌"
        rsi_short_status = "✅" if rsi_short_condition else "❌"
        content += f"**RSI**: {rsi_value:.2f} | 多单条件: {rsi_long_status} (≤75) | 空单条件: {rsi_short_status} (≥25)\n\n"
        
        # 布林带信息
        content += f"**布林带**:\n"
        content += f"- 上轨: {sar_result.get('upper', 0):.2f}\n"
        content += f"- 中轨: {sar_result.get('basis', 0):.2f}\n"
        content += f"- 下轨: {sar_result.get('lower', 0):.2f}\n\n"
        
        # ATR波动率信息
        if atr_info:
            atr_ratio = atr_info.get('atr_ratio', 0)
            atr_condition = atr_ratio <= 1.3
            atr_status = "✅" if atr_condition else "❌"
            content += f"**波动率**: 比率 {atr_ratio:.4f} | 开仓条件: {atr_status} (≤1.3)\n\n"
        
        # 风险收益比信息（基于当前价格和SAR值计算）
        current_price = sar_result.get('current_price', sar_result.get('sar_value', 0))
        if current_price > 0:
            sar_value = sar_result.get('sar_value', 0)
            if sar_value > 0:
                # 计算多单风险收益比（假设以当前价格开仓）
                long_stop_loss_pct = abs(current_price - sar_value) / current_price * 100
                long_take_profit_pct = 0.55  # 固定止盈0.55%
                long_risk_reward_ok = long_stop_loss_pct >= long_take_profit_pct
                long_status = "✅" if long_risk_reward_ok else "❌"
                
                # 计算空单风险收益比（假设以当前价格开仓）
                short_stop_loss_pct = abs(sar_value - current_price) / current_price * 100
                short_take_profit_pct = 0.55  # 固定止盈0.55%
                short_risk_reward_ok = short_stop_loss_pct >= short_take_profit_pct
                short_status = "✅" if short_risk_reward_ok else "❌"
                
                content += f"**风险收益比** (基于当前价格${current_price:.2f}):\n"
                content += f"- 多单: 止损{long_stop_loss_pct:.2f}% vs 止盈{long_take_profit_pct:.2f}% {long_status}\n"
                content += f"- 空单: 止损{short_stop_loss_pct:.2f}% vs 止盈{short_take_profit_pct:.2f}% {short_status}\n"
                content += f"*注：实际开仓时的风险收益比以开仓信号价格为准*\n\n"
        
        # 持仓信息
        if position_info:
            content += f"---\n\n"
            content += f"## 💼 策略持仓状态\n\n"
            content += f"*注：此为策略逻辑层面的持仓状态，非OKX实际持仓*\n\n"
            
            position_type = position_info.get('position')
            if position_type:
                position_emoji = "🟢" if position_type == 'long' else "🔴"
                position_text = "做多" if position_type == 'long' else "做空"
                content += f"**持仓方向**: {position_emoji} {position_text}\n\n"
                
                entry_price = position_info.get('entry_price', 0)
                current_price = position_info.get('current_price', 0)
                stop_loss = position_info.get('stop_loss_level', 0)
                take_profit = position_info.get('take_profit_level')
                
                content += f"**开仓价格**: ${entry_price:.2f}\n\n"
                content += f"**当前价格**: ${current_price:.2f}\n\n"
                content += f"**止损价格**: ${stop_loss:.2f}\n\n"
                
                if take_profit:
                    content += f"**止盈价格**: ${take_profit:.2f}\n\n"
                
                # 计算盈亏
                if position_type == 'long':
                    profit_loss_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    profit_loss_pct = ((entry_price - current_price) / entry_price) * 100
                
                profit_emoji = "📈" if profit_loss_pct > 0 else "📉"
                content += f"**当前盈亏**: {profit_emoji} {profit_loss_pct:+.2f}%\n\n"
            else:
                content += f"**持仓状态**: ⚪ 空仓\n\n"
        
        title = f"【{timeframe}指标】{time_range}"
        self.send_message(title, content)
    
    def send_open_position(self, timestamp, direction, entry_price, reason, position_info):
        """
        发送开仓消息
        
        Args:
            timestamp: 时间戳
            direction: 开仓方向 ('long' 或 'short')
            entry_price: 开仓价格
            reason: 开仓原因
            position_info: 持仓详细信息
        """
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        position_emoji = "🟢" if direction == 'long' else "🔴"
        position_text = "做多" if direction == 'long' else "做空"
        
        content = f"## {position_emoji} 开仓通知 - {position_text}\n\n"
        content += f"**⏰ 时间**: {time_str}\n\n"
        content += f"---\n\n"
        
        content += f"**开仓价格**: ${entry_price:.2f}\n\n"
        content += f"**投入资金**: ${position_info.get('invested_amount', 0):,.2f}\n\n"
        content += f"**持仓份额**: {position_info.get('position_shares', 0):.4f}\n\n"
        
        stop_loss = position_info.get('stop_loss')
        if stop_loss:
            content += f"**止损价格**: ${stop_loss:.2f}\n\n"
        
        take_profit = position_info.get('take_profit')
        if take_profit:
            content += f"**止盈价格**: ${take_profit:.2f}\n\n"
        
        max_loss = position_info.get('max_loss')
        if max_loss:
            content += f"**最大亏损**: ${max_loss:.2f}\n\n"
        
        content += f"---\n\n"
        content += f"**开仓原因**:\n\n{reason}\n\n"
        
        title = f"【开仓】{position_text} ${entry_price:.2f}"
        self.send_message(title, content)
    
    def send_close_position(self, timestamp, position_type, entry_price, exit_price, 
                           profit_loss, return_rate, reason):
        """
        发送平仓消息
        
        Args:
            timestamp: 时间戳
            position_type: 持仓类型 ('long' 或 'short')
            entry_price: 开仓价格
            exit_price: 平仓价格
            profit_loss: 盈亏金额
            return_rate: 收益率
            reason: 平仓原因
        """
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        position_text = "做多" if position_type == 'long' else "做空"
        result_emoji = "✅" if profit_loss > 0 else "❌"
        result_text = "盈利" if profit_loss > 0 else "亏损"
        
        content = f"## {result_emoji} 平仓通知 - {position_text}\n\n"
        content += f"**⏰ 时间**: {time_str}\n\n"
        content += f"---\n\n"
        
        content += f"**开仓价格**: ${entry_price:.2f}\n\n"
        content += f"**平仓价格**: ${exit_price:.2f}\n\n"
        
        profit_emoji = "📈" if profit_loss > 0 else "📉"
        content += f"**{result_text}金额**: {profit_emoji} ${profit_loss:+,.2f}\n\n"
        content += f"**收益率**: {profit_emoji} {return_rate:+.2f}%\n\n"
        
        content += f"---\n\n"
        content += f"**平仓原因**:\n\n{reason}\n\n"
        
        title = f"【平仓】{result_text} {return_rate:+.2f}%"
        self.send_message(title, content)
    
    def send_delta_volume_update(self, timestamp, delta_volume_percent, delta_volume_period, 
                                 stop_loss_threshold, position=None, current_price=None,
                                 total_buy_volume=None, total_sell_volume=None, 
                                 current_kline_volume=None, history_count=None):
        """
        发送Delta Volume更新消息
        
        Args:
            timestamp: 时间戳
            delta_volume_percent: Delta Volume百分比
            delta_volume_period: Delta Volume周期
            stop_loss_threshold: 止损阈值
            position: 当前持仓 ('long', 'short', None)
            current_price: 当前价格（可选）
            total_buy_volume: 总买入量（可选）
            total_sell_volume: 总卖出量（可选）
            current_kline_volume: 当前K线成交量（可选）
            history_count: 历史K线数量（可选）
        """
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        # 计算绝对值，判断是否接近止损阈值
        abs_delta = abs(delta_volume_percent)
        threshold_percent = stop_loss_threshold * 100
        
        # 判断市场情绪
        if delta_volume_percent > 0:
            sentiment = "📈 买入压力"
            sentiment_emoji = "🟢"
        elif delta_volume_percent < 0:
            sentiment = "📉 卖出压力"
            sentiment_emoji = "🔴"
        else:
            sentiment = "➡️ 中性"
            sentiment_emoji = "⚪"
        
        # 判断是否接近止损阈值
        if position == 'long':
            # 多单：关注卖出压力
            if delta_volume_percent < -stop_loss_threshold * 100:
                warning = "⚠️ **接近止损阈值！**"
                warning_emoji = "🚨"
            elif delta_volume_percent < -stop_loss_threshold * 50:  # 50%阈值
                warning = "⚠️ 注意卖出压力"
                warning_emoji = "⚠️"
            else:
                warning = "✅ 正常"
                warning_emoji = "✅"
        elif position == 'short':
            # 空单：关注买入压力
            if delta_volume_percent > stop_loss_threshold * 100:
                warning = "⚠️ **接近止损阈值！**"
                warning_emoji = "🚨"
            elif delta_volume_percent > stop_loss_threshold * 50:  # 50%阈值
                warning = "⚠️ 注意买入压力"
                warning_emoji = "⚠️"
            else:
                warning = "✅ 正常"
                warning_emoji = "✅"
        else:
            warning = "无持仓"
            warning_emoji = "⚪"
        
        content = f"## 📊 Delta Volume 更新\n\n"
        content += f"**⏰ 时间**: {time_str}\n\n"
        content += f"---\n\n"
        
        if position:
            position_text = "做多" if position == 'long' else "做空"
            content += f"**持仓状态**: {position_text}\n\n"
        
        if current_price:
            content += f"**当前价格**: ${current_price:.2f}\n\n"
        
        content += f"**Delta Volume**: {delta_volume_percent:+.2f}%\n\n"
        content += f"**市场情绪**: {sentiment_emoji} {sentiment}\n\n"
        
        # 添加成交量详情
        if total_buy_volume is not None and total_sell_volume is not None:
            total_volume = total_buy_volume + total_sell_volume
            content += f"**成交量详情**:\n"
            content += f"- 总买入量: {total_buy_volume:,.0f}\n"
            content += f"- 总卖出量: {total_sell_volume:,.0f}\n"
            content += f"- 总成交量: {total_volume:,.0f}\n\n"
        
        if current_kline_volume is not None and current_kline_volume > 0:
            content += f"**当前K线成交量**: {current_kline_volume:,.0f}\n\n"
        
        if history_count is not None:
            content += f"**历史K线数**: {history_count}/{delta_volume_period}\n\n"
        
        content += f"**周期长度**: {delta_volume_period}个K线\n\n"
        content += f"**止损阈值**: ±{threshold_percent:.0f}%\n\n"
        
        content += f"---\n\n"
        content += f"**风险提示**: {warning_emoji} {warning}\n\n"
        
        # 如果接近止损阈值，添加详细信息
        if position == 'long' and delta_volume_percent < -stop_loss_threshold * 100:
            content += f"⚠️ 多单警告：卖出压力{abs_delta:.2f}% ≥ {threshold_percent:.0f}%，可能触发Delta Volume止损\n\n"
        elif position == 'short' and delta_volume_percent > stop_loss_threshold * 100:
            content += f"⚠️ 空单警告：买入压力{abs_delta:.2f}% ≥ {threshold_percent:.0f}%，可能触发Delta Volume止损\n\n"
        
        title = f"【Delta Volume】{delta_volume_percent:+.2f}%"
        result = self.send_message(title, content)
        return result
    
    def send_order_notification(self, order_type, symbol, side, amount, price, 
                                stop_loss_info=None, take_profit_info=None, 
                                order_result=None, extra_info=None):
        """
        发送订单通知（V2版本 - 支持限价单和条件单）
        
        Args:
            order_type: 订单类型 ('OPEN_LONG', 'OPEN_SHORT', 'STOP_LOSS', 'TAKE_PROFIT')
            symbol: 交易对
            side: 方向 ('buy' 或 'sell')
            amount: 数量
            price: 价格
            stop_loss_info: 止损信息 {'price': xxx, 'order_type': 'limit/conditional', 'order_id': xxx}
            take_profit_info: 止盈信息 {'price': xxx, 'order_type': 'limit/conditional', 'order_id': xxx}
            order_result: 订单执行结果
            extra_info: 额外信息 (invested_amount, leverage等)
        """
        time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 📊 开仓通知
        if order_type in ['OPEN_LONG', 'OPEN_SHORT']:
            position_emoji = "🟢" if order_type == 'OPEN_LONG' else "🔴"
            position_text = "做多" if order_type == 'OPEN_LONG' else "做空"
            
            content = f"## {position_emoji} 开仓成功 - {position_text}\n\n"
            content += f"**⏰ 时间**: {time_str}\n\n"
            content += f"---\n\n"
            
            # 交易对和订单信息
            content += f"**📊 交易对**: {symbol}\n\n"
            content += f"**💰 开仓价格**: ${price:.2f}\n\n"
            content += f"**📦 合约数量**: {amount} 张\n\n"
            
            if extra_info:
                if 'invested_amount' in extra_info:
                    content += f"**💵 投入资金**: ${extra_info['invested_amount']:,.2f} USDT\n\n"
                if 'leverage' in extra_info:
                    content += f"**⚡ 杠杆倍数**: {extra_info['leverage']}x\n\n"
            
            if order_result and order_result.get('entry_order'):
                entry_order_id = order_result['entry_order'].get('id', 'N/A')
                content += f"**🆔 订单ID**: `{entry_order_id}`\n\n"
            
            content += f"---\n\n"
            
            # 🛡️ 止损信息
            if stop_loss_info:
                sl_price = stop_loss_info.get('price')
                sl_type = stop_loss_info.get('order_type', 'unknown')
                sl_order_id = stop_loss_info.get('order_id')
                
                sl_emoji = "🛡️" if sl_type == 'limit' else "⚠️"
                sl_type_text = "限价单" if sl_type == 'limit' else "条件单"
                
                content += f"**{sl_emoji} 止损单**: ${sl_price:.2f} ({sl_type_text})\n\n"
                
                if sl_order_id:
                    content += f"   - 订单ID: `{sl_order_id}`\n\n"
                
                if sl_type == 'conditional':
                    content += f"   - 💡 价格接近时将优化为限价单\n\n"
            
            # 💰 止盈信息
            if take_profit_info:
                tp_price = take_profit_info.get('price')
                tp_type = take_profit_info.get('order_type', 'limit')
                tp_order_id = take_profit_info.get('order_id')
                
                content += f"**💰 止盈单**: ${tp_price:.2f} ({tp_type})\n\n"
                
                if tp_order_id:
                    content += f"   - 订单ID: `{tp_order_id}`\n\n"
            
            # 风险收益比
            if stop_loss_info and take_profit_info:
                sl_pct = abs(price - stop_loss_info['price']) / price * 100
                tp_pct = abs(take_profit_info['price'] - price) / price * 100
                r_r_ratio = sl_pct / tp_pct if tp_pct > 0 else 0
                
                content += f"---\n\n"
                content += f"**📊 风险收益比**: {r_r_ratio:.2f}:1\n\n"
                content += f"   - 止损比例: {sl_pct:.2f}%\n\n"
                content += f"   - 止盈比例: {tp_pct:.2f}%\n\n"
            
            title = f"【开仓】{position_text} ${price:.2f}"
            self.send_message(title, content)
        
        # 🛡️ 止损更新通知
        elif order_type == 'UPDATE_STOP_LOSS':
            content = f"## 🛡️ 止损单更新\n\n"
            content += f"**⏰ 时间**: {time_str}\n\n"
            content += f"---\n\n"
            
            content += f"**📊 交易对**: {symbol}\n\n"
            
            if stop_loss_info:
                old_price = stop_loss_info.get('old_price')
                new_price = stop_loss_info.get('new_price', price)
                sl_type = stop_loss_info.get('order_type', 'limit')
                sl_order_id = stop_loss_info.get('order_id')
                
                sl_emoji = "🛡️" if sl_type == 'limit' else "⚠️"
                sl_type_text = "限价单" if sl_type == 'limit' else "条件单"
                
                if old_price:
                    price_change = ((new_price - old_price) / old_price) * 100
                    arrow = "⬆️" if price_change > 0 else "⬇️"
                    content += f"**旧止损价**: ${old_price:.2f}\n\n"
                    content += f"**新止损价**: ${new_price:.2f} {arrow}\n\n"
                    content += f"**价格变动**: {price_change:+.2f}%\n\n"
                else:
                    content += f"**新止损价**: ${new_price:.2f}\n\n"
                
                content += f"**{sl_emoji} 订单类型**: {sl_type_text}\n\n"
                
                if sl_order_id:
                    content += f"**🆔 订单ID**: `{sl_order_id}`\n\n"
                
                if sl_type == 'conditional':
                    content += f"\n💡 **提示**: 当前为条件单（价格限制），价格接近时将自动优化为限价单\n\n"
            
            title = f"【止损更新】${price:.2f}"
            self.send_message(title, content)
        
        # 💰 止盈设置通知
        elif order_type == 'SET_TAKE_PROFIT':
            content = f"## 💰 止盈单设置\n\n"
            content += f"**⏰ 时间**: {time_str}\n\n"
            content += f"---\n\n"
            
            content += f"**📊 交易对**: {symbol}\n\n"
            
            if take_profit_info:
                tp_price = take_profit_info.get('price', price)
                tp_type = take_profit_info.get('order_type', 'limit')
                tp_order_id = take_profit_info.get('order_id')
                
                content += f"**💰 止盈价格**: ${tp_price:.2f}\n\n"
                content += f"**📋 订单类型**: {tp_type}\n\n"
                
                if tp_order_id:
                    content += f"**🆔 订单ID**: `{tp_order_id}`\n\n"
            
            title = f"【止盈设置】${price:.2f}"
            self.send_message(title, content)

