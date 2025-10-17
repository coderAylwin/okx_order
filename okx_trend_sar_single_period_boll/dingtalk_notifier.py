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
from datetime import datetime

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
    
    def send_indicator_update(self, timestamp, timeframe, sar_result, position_info=None):
        """
        发送周期结束时的指标更新消息
        
        Args:
            timestamp: 时间戳
            timeframe: 时间周期
            sar_result: SAR指标结果
            position_info: 持仓信息（可选）
        """
        time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        # 构建基础指标信息
        content = f"## 📊 {timeframe}周期指标更新\n\n"
        content += f"**⏰ 时间**: {time_str}\n\n"
        content += f"---\n\n"
        
        # SAR指标信息
        sar_direction = "📈 上升" if sar_result.get('sar_rising') else "📉 下降"
        content += f"**SAR值**: {sar_result.get('sar_value', 0):.2f} {sar_direction}\n\n"
        content += f"**RSI**: {sar_result.get('rsi', 0):.2f}\n\n"
        
        # 布林带信息
        content += f"**布林带**:\n"
        content += f"- 上轨: {sar_result.get('upper', 0):.2f}\n"
        content += f"- 中轨: {sar_result.get('basis', 0):.2f}\n"
        content += f"- 下轨: {sar_result.get('lower', 0):.2f}\n\n"
        
        # 持仓信息
        if position_info:
            content += f"---\n\n"
            content += f"## 💼 持仓信息\n\n"
            
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
        
        title = f"【{timeframe}指标】{time_str}"
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

