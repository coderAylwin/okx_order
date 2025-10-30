#!/bin/bash

# OKX VIDYA策略实盘交易启动脚本

# 设置工作目录
cd "$(dirname "$0")"

# 设置Python环境（如果需要）
# export PATH="/Users/Aylwin/.pyenv/versions/3.11.2/bin:$PATH"

# 启动实盘交易
python3 live_trading_VIDYA.py

# 如果脚本退出，打印消息
echo "交易程序已退出"

