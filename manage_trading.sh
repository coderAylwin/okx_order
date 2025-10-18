#!/bin/bash

# 交易程序管理脚本
SCRIPT_DIR="/home/ubuntu/okx_order/okx_trend_sar_single_period_boll"
SCRIPT_NAME="live_trading_with_stop_orders.py"
PROJECT_NAME="trading_bot"

# 路径配置
PID_FILE="$SCRIPT_DIR/${PROJECT_NAME}.pid"
LOG_DIR="$SCRIPT_DIR/logs"
CURRENT_DATE=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/${PROJECT_NAME}_${CURRENT_DATE}.log"

# 创建必要的目录
mkdir -p $LOG_DIR

cd $SCRIPT_DIR

# 获取当前日志文件路径
get_log_file() {
    echo "$LOG_DIR/${PROJECT_NAME}_$(date +%Y%m%d).log"
}

# 检查程序是否在运行
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat $PID_FILE)
        if ps -p $PID > /dev/null 2>&1; then
            return 0
        else
            rm -f $PID_FILE
        fi
    fi
    return 1
}

case "$1" in
    start)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动交易程序..."
        
        if is_running; then
            PID=$(cat $PID_FILE)
            echo "程序已在运行 (PID: $PID)"
            exit 1
        fi
        
        # 激活虚拟环境并启动程序
        source /home/ubuntu/okx_order/venv/bin/activate
        nohup python $SCRIPT_NAME >> $(get_log_file) 2>&1 &
        
        # 保存PID
        echo $! > $PID_FILE
        echo "程序已启动 (PID: $(cat $PID_FILE))"
        echo "日志文件: $(get_log_file)"
        echo "使用 './manage_trading.sh logs' 查看实时日志"
        ;;
        
    stop)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 停止交易程序..."
        
        if is_running; then
            PID=$(cat $PID_FILE)
            echo "停止进程: $PID"
            
            # 先尝试正常停止
            kill $PID
            sleep 5
            
            # 如果还在运行，强制停止
            if ps -p $PID > /dev/null 2>&1; then
                echo "强制停止进程: $PID"
                kill -9 $PID
            fi
            
            rm -f $PID_FILE
            echo "程序已停止"
        else
            echo "程序未在运行"
            
            # 清理可能存在的旧PID文件
            if [ -f "$PID_FILE" ]; then
                rm -f $PID_FILE
            fi
        fi
        ;;
        
    restart)
        echo "重启交易程序..."
        $0 stop
        sleep 3
        $0 start
        ;;
        
    status)
        echo "交易程序状态:"
        if is_running; then
            PID=$(cat $PID_FILE)
            echo "✅ 运行中 (PID: $PID)"
            echo "📅 启动时间: $(ps -p $PID -o lstart=)"
            echo "⏱️  运行时间: $(ps -p $PID -o etime=)"
            echo "📊 今日日志: $(get_log_file)"
            echo "💾 内存使用: $(ps -p $PID -o rss= | awk '{printf "%.1f MB\n", $1/1024}')"
        else
            echo "❌ 未运行"
        fi
        ;;
        
    logs)
        # 日志查看功能
        case "$2" in
            today|"")
                echo "查看今日实时日志 (Ctrl+C 退出):"
                tail -f $(get_log_file)
                ;;
            yesterday)
                YESTERDAY=$(date -d "yesterday" +%Y%m%d)
                YESTERDAY_LOG="$LOG_DIR/${PROJECT_NAME}_${YESTERDAY}.log"
                if [ -f "$YESTERDAY_LOG" ]; then
                    echo "查看昨日日志:"
                    tail -100 $YESTERDAY_LOG
                else
                    echo "昨天的日志文件不存在: $YESTERDAY_LOG"
                fi
                ;;
            error)
                echo "查看错误日志:"
                grep -i "error\|exception\|fail\|traceback" $(get_log_file) | tail -50
                ;;
            stats)
                echo "今日日志统计:"
                LOG_FILE=$(get_log_file)
                if [ -f "$LOG_FILE" ]; then
                    echo "总行数: $(wc -l < $LOG_FILE)"
                    echo "错误数: $(grep -i "error" $LOG_FILE | wc -l)"
                    echo "异常数: $(grep -i "exception" $LOG_FILE | wc -l)"
                    echo "最后更新时间: $(stat -c %y $LOG_FILE)"
                else
                    echo "今日日志文件不存在"
                fi
                ;;
            list)
                echo "可用的日志文件:"
                ls -la $LOG_DIR/${PROJECT_NAME}_*.log 2>/dev/null | sort -r || echo "没有找到日志文件"
                ;;
            *)
                echo "用法: $0 logs {today|yesterday|error|stats|list}"
                echo "  today     - 查看今日实时日志"
                echo "  yesterday - 查看昨日日志"
                echo "  error     - 查看错误信息"
                echo "  stats     - 日志统计信息"
                echo "  list      - 列出所有日志文件"
                ;;
        esac
        ;;
        
    monitor)
        # 监控模式
        echo "进入监控模式 (Ctrl+C 退出)"
        echo "每5秒刷新一次状态"
        while true; do
            clear
            echo "=== 交易程序监控 ==="
            echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
            echo
            $0 status
            echo
            echo "最近日志:"
            tail -10 $(get_log_file) 2>/dev/null || echo "暂无日志"
            echo
            echo "按 Ctrl+C 退出监控"
            sleep 5
        done
        ;;
        
    *)
        echo "交易程序管理脚本"
        echo "用法: $0 {start|stop|restart|status|logs|monitor}"
        echo "  start   - 启动程序 (后台运行)"
        echo "  stop    - 停止程序"
        echo "  restart - 重启程序"
        echo "  status  - 查看程序状态"
        echo "  logs    - 查看日志 (today|yesterday|error|stats|list)"
        echo "  monitor - 进入监控模式"
        exit 1
        ;;
esac