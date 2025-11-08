#!/bin/bash

# SAR 限价策略管理脚本

SCRIPT_NAME="live_trading_v2.py"
PROJECT_NAME="sar_trading_bot"

# 定位策略目录
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POSSIBLE_DIRS=(
    "$BASE_DIR"
    "$BASE_DIR/okx_trend_sar_v2"
    "$BASE_DIR/../okx_trend_sar_v2"
)
SCRIPT_DIR=""

for dir in "${POSSIBLE_DIRS[@]}"; do
    if [ -f "$dir/$SCRIPT_NAME" ]; then
        SCRIPT_DIR="$dir"
        break
    fi
done

if [ -z "$SCRIPT_DIR" ]; then
    echo "❌ 未找到 $SCRIPT_NAME，请检查脚本位置"
    exit 1
fi

# 路径配置
PID_FILE="$SCRIPT_DIR/${PROJECT_NAME}.pid"
LOG_DIR="$SCRIPT_DIR/logs"
CURRENT_DATE=$(date +%Y%m%d)
LOG_FILE="$LOG_DIR/${PROJECT_NAME}_${CURRENT_DATE}.log"

# 虚拟环境
DEFAULT_VENV="$SCRIPT_DIR/../venv/bin/activate"
if [ -n "$VENV_PATH" ]; then
    VENV_ACTIVATE="$VENV_PATH"
elif [ -f "$DEFAULT_VENV" ]; then
    VENV_ACTIVATE="$DEFAULT_VENV"
else
    VENV_ACTIVATE=""
fi

# Python 命令
PY_CMD=${PY_CMD:-python3}

# 创建日志目录
mkdir -p "$LOG_DIR"

cd "$SCRIPT_DIR" || {
    echo "❌ 无法进入目录: $SCRIPT_DIR"
    exit 1
}

# 日志路径
get_log_file() {
    echo "$LOG_DIR/${PROJECT_NAME}_$(date +%Y%m%d).log"
}

# 检查进程
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            return 0
        else
            rm -f "$PID_FILE"
        fi
    fi
    return 1
}

case "$1" in
    start)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动SAR策略交易程序..."

        if is_running; then
            PID=$(cat "$PID_FILE")
            echo "程序已在运行 (PID: $PID)"
            exit 1
        fi

        echo "📂 工作目录: $SCRIPT_DIR"
        echo "🐍 Python命令: $PY_CMD"
        echo "📄 脚本文件: $SCRIPT_NAME"

        if [ -n "$VENV_ACTIVATE" ]; then
            if [ -f "$VENV_ACTIVATE" ]; then
                # shellcheck disable=SC1090
                source "$VENV_ACTIVATE"
            else
                echo "⚠️  虚拟环境激活脚本不存在: $VENV_ACTIVATE"
            fi
        else
            echo "ℹ️  未配置虚拟环境，直接使用系统Python"
        fi

        nohup $PY_CMD "$SCRIPT_NAME" >> "$(get_log_file)" 2>&1 &
        echo $! > "$PID_FILE"
        PID_VALUE=$(cat "$PID_FILE")
        echo "程序已启动 (PID: $PID_VALUE)"
        echo "日志文件: $(get_log_file)"
        echo "使用 './manage_trading.sh logs' 查看实时日志"
        ;;

    stop)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 停止SAR策略交易程序..."

        if is_running; then
            PID=$(cat "$PID_FILE")
            echo "停止进程: $PID"
            kill $PID
            sleep 5

            if ps -p $PID > /dev/null 2>&1; then
                echo "强制停止进程: $PID"
                kill -9 $PID
            fi

            rm -f "$PID_FILE"
            echo "程序已停止"
        else
            echo "程序未在运行"
            if [ -f "$PID_FILE" ]; then
                rm -f "$PID_FILE"
            fi
        fi
        ;;

    restart)
        echo "重启SAR策略交易程序..."
        $0 stop
        sleep 3
        $0 start
        ;;

    status)
        echo "SAR策略交易程序状态:"
        if is_running; then
            PID=$(cat "$PID_FILE")
            echo "✅ 运行中 (PID: $PID)"
            echo "📅 启动时间: $(ps -p $PID -o lstart=)"
            echo "⏱️  运行时间: $(ps -p $PID -o etime=)"
            echo "📊 今日日志: $(get_log_file)"
            echo "💾 内存使用: $(ps -p $PID -o rss= | awk '{printf \"%.1f MB\\n\", $1/1024}')"
        else
            echo "❌ 未运行"
        fi
        ;;

    logs)
        case "$2" in
            today|"")
                echo "查看今日实时日志 (Ctrl+C 退出):"
                tail -f "$(get_log_file)"
                ;;
            yesterday)
                YESTERDAY=$(date -d "yesterday" +%Y%m%d)
                YESTERDAY_LOG="$LOG_DIR/${PROJECT_NAME}_${YESTERDAY}.log"
                if [ -f "$YESTERDAY_LOG" ]; then
                    echo "查看昨日日志:"
                    tail -100 "$YESTERDAY_LOG"
                else
                    echo "昨天的日志文件不存在: $YESTERDAY_LOG"
                fi
                ;;
            error)
                echo "查看错误日志:"
                grep -i "error\|exception\|fail\|traceback" "$(get_log_file)" | tail -50
                ;;
            stats)
                echo "今日日志统计:"
                LOG_FILE=$(get_log_file)
                if [ -f "$LOG_FILE" ]; then
                    echo "总行数: $(wc -l < "$LOG_FILE")"
                    echo "错误数: $(grep -i "error" "$LOG_FILE" | wc -l)"
                    echo "异常数: $(grep -i "exception" "$LOG_FILE" | wc -l)"
                    echo "最后更新时间: $(stat -c %y "$LOG_FILE")"
                else
                    echo "今日日志文件不存在"
                fi
                ;;
            list)
                echo "可用的日志文件:"
                ls -la "$LOG_DIR"/${PROJECT_NAME}_*.log 2>/dev/null | sort -r || echo "没有找到日志文件"
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
        echo "进入监控模式 (Ctrl+C 退出)"
        echo "每5秒刷新一次状态"
        while true; do
            clear
            echo "=== SAR 策略交易程序监控 ==="
            echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
            echo
            $0 status
            echo
            echo "最近日志:"
            tail -10 "$(get_log_file)" 2>/dev/null || echo "暂无日志"
            echo
            echo "按 Ctrl+C 退出监控"
            sleep 5
        done
        ;;

    *)
        echo "SAR 策略交易程序管理脚本"
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


