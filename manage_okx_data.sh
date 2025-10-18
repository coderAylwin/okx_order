#!/bin/bash

SCRIPT_DIR="/home/ubuntu/okx_order"
SCRIPT_NAME="Okx1m_pro.py"
PID_FILE="$SCRIPT_DIR/okx_data.pid"
LOG_DIR="$SCRIPT_DIR/logs"
CURRENT_DATE=$(date +%Y%m%d)
CURRENT_DATETIME=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/okx_data_${CURRENT_DATE}.log"
ARCHIVE_DIR="$LOG_DIR/archive"

# 创建必要的目录
mkdir -p $LOG_DIR $ARCHIVE_DIR

cd $SCRIPT_DIR

get_log_file() {
    echo "$LOG_DIR/okx_data_$(date +%Y%m%d).log"
}

rotate_logs() {
    # 压缩7天前的日志
    find $LOG_DIR -name "okx_data_*.log" -mtime +7 -exec gzip {} \;
    
    # 移动压缩文件到归档目录
    find $LOG_DIR -name "okx_data_*.gz" -exec mv {} $ARCHIVE_DIR/ \;
    
    # 删除30天前的归档文件
    find $ARCHIVE_DIR -name "okx_data_*.gz" -mtime +30 -delete
}

case "$1" in
    start)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动 OKX 数据采集程序..."
        
        # 日志轮转
        rotate_logs
        
        if [ -f "$PID_FILE" ]; then
            PID=$(cat $PID_FILE)
            if ps -p $PID > /dev/null 2>&1; then
                echo "程序已在运行 (PID: $PID)"
                exit 1
            else
                rm -f $PID_FILE
            fi
        fi
        
        source venv/bin/activate
        nohup python $SCRIPT_NAME >> $(get_log_file) 2>&1 &
        echo $! > $PID_FILE
        echo "程序已启动 (PID: $(cat $PID_FILE))"
        echo "日志文件: $(get_log_file)"
        echo "查看实时日志: tail -f $(get_log_file)"
        ;;
        
    stop)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 停止 OKX 数据采集程序..."
        if [ -f "$PID_FILE" ]; then
            PID=$(cat $PID_FILE)
            if ps -p $PID > /dev/null 2>&1; then
                echo "停止进程: $PID"
                kill $PID
                sleep 5
                
                if ps -p $PID > /dev/null 2>&1; then
                    echo "强制停止进程: $PID"
                    kill -9 $PID
                fi
                
                rm -f $PID_FILE
                echo "程序已停止"
            else
                echo "进程不存在，清理PID文件"
                rm -f $PID_FILE
            fi
        else
            echo "PID文件不存在，尝试查找进程..."
            PIDS=$(ps aux | grep "$SCRIPT_NAME" | grep -v grep | awk '{print $2}')
            if [ -n "$PIDS" ]; then
                echo "停止进程: $PIDS"
                kill $PIDS 2>/dev/null
                sleep 3
                kill -9 $PIDS 2>/dev/null
                echo "程序已停止"
            else
                echo "没有找到运行的进程"
            fi
        fi
        ;;
        
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
        
    status)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat $PID_FILE)
            if ps -p $PID > /dev/null 2>&1; then
                echo "程序运行中 (PID: $PID)"
                echo "启动时间: $(ps -p $PID -o lstart=)"
                echo "运行时间: $(ps -p $PID -o etime=)"
                echo "今日日志: $(get_log_file)"
            else
                echo "PID文件存在但进程不存在"
                rm -f $PID_FILE
            fi
        else
            PIDS=$(ps aux | grep "$SCRIPT_NAME" | grep -v grep | awk '{print $2}')
            if [ -n "$PIDS" ]; then
                echo "程序运行中 (PID: $PIDS)"
                echo "今日日志: $(get_log_file)"
            else
                echo "程序未运行"
            fi
        fi
        ;;
        
    logs)
        # 查看日志命令
        case "$2" in
            today)
                tail -f $(get_log_file)
                ;;
            yesterday)
                YESTERDAY=$(date -d "yesterday" +%Y%m%d)
                YESTERDAY_LOG="$LOG_DIR/okx_data_${YESTERDAY}.log"
                if [ -f "$YESTERDAY_LOG" ]; then
                    tail -100 $YESTERDAY_LOG
                else
                    echo "昨天的日志文件不存在: $YESTERDAY_LOG"
                fi
                ;;
            list)
                echo "可用的日志文件:"
                ls -la $LOG_DIR/okx_data_*.log 2>/dev/null || echo "没有找到日志文件"
                ;;
            *)
                echo "用法: $0 logs {today|yesterday|list}"
                ;;
        esac
        ;;
        
    cleanup)
        # 清理旧日志
        echo "清理旧日志文件..."
        rotate_logs
        echo "日志清理完成"
        ;;
        
    *)
        echo "用法: $0 {start|stop|restart|status|logs|cleanup}"
        echo "  start    - 启动程序"
        echo "  stop     - 停止程序"
        echo "  restart  - 重启程序"
        echo "  status   - 查看状态"
        echo "  logs     - 查看日志 (today|yesterday|list)"
        echo "  cleanup  - 清理旧日志"
        exit 1
        ;;
esac