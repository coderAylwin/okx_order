#!/bin/bash

# =============================================
# OKX 实盘交易启动脚本
# =============================================

echo "=================================="
echo "🚀 OKX 实盘交易系统"
echo "=================================="
echo ""

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 显示配置信息
echo "📋 当前配置:"
echo "  - 配置文件: okx_config.py"
echo "  - 策略文件: strategy_configs.py"
echo ""

# 询问运行模式
echo "请选择运行模式:"
echo "  1) 测试模式（只打印，不下单）"
echo "  2) 模拟盘（OKX沙盒环境）"
echo "  3) 实盘（真实交易）⚠️"
echo ""
read -p "请输入选项 (1/2/3): " mode_choice

case $mode_choice in
    1)
        echo "✅ 选择: 测试模式"
        export TEST_MODE=1
        ;;
    2)
        echo "✅ 选择: 模拟盘模式"
        export TEST_MODE=0
        export LIVE_MODE=0
        ;;
    3)
        echo "⚠️  选择: 实盘模式"
        echo "⚠️  警告: 将在真实市场交易！"
        read -p "确认继续？(yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            echo "❌ 已取消"
            exit 0
        fi
        export TEST_MODE=0
        export LIVE_MODE=1
        ;;
    *)
        echo "❌ 无效选项"
        exit 1
        ;;
esac

echo ""
echo "=================================="
echo "🚀 启动交易机器人..."
echo "=================================="
echo ""

# 启动程序（使用增强版）
python3 live_trading_with_stop_orders.py

echo ""
echo "=================================="
echo "✅ 程序已退出"
echo "=================================="

