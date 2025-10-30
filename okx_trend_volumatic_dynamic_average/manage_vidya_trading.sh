#!/bin/bash

# VIDYA策略交易程序管理脚本
SCRIPT_DIR="/Users/Aylwin/okx_order/okx_trend_volumatic_dynamic_average"
SCRIPT_NAME="live_trading_VIDYA.py"
PROJECT_NAME="vidya_trading_bot"

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
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🚀 启动VIDYA交易程序..."
        
        if is_running; then
            PID=$(cat $PID_FILE)
            echo "✅ 程序已在运行 (PID: $PID)"
            exit 1
        fi
        
        # 检查Python环境
        if command -v python3 &> /dev/null; then
            PYTHON_CMD="python3"
        elif command -v python &> /dev/null; then
            PYTHON_CMD="python"
        else
            echo "❌ 错误: 未找到Python环境"
            exit 1
        fi
        
        # 启动程序
        echo "📂 工作目录: $SCRIPT_DIR"
        echo "🐍 Python命令: $PYTHON_CMD"
        echo "📄 脚本文件: $SCRIPT_NAME"
        
        nohup $PYTHON_CMD $SCRIPT_NAME >> $(get_log_file) 2>&1 &
        
        # 保存PID
        echo $! > $PID_FILE
        sleep 2
        
        if is_running; then
            echo "✅ VIDYA程序启动成功 (PID: $(cat $PID_FILE))"
            echo "📁 日志文件: $(get_log_file)"
            echo "💡 使用 './manage_vidya_trading.sh logs' 查看实时日志"
            echo "💡 使用 './manage_vidya_trading.sh status' 查看运行状态"
        else
            echo "❌ 程序启动失败，请查看日志文件"
            tail -20 $(get_log_file)
        fi
        ;;
        
    stop)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🛑 停止VIDYA交易程序..."
        
        if is_running; then
            PID=$(cat $PID_FILE)
            echo "🔄 停止进程: $PID"
            
            # 先尝试正常停止（发送SIGTERM信号）
            kill $PID
            echo "⏳ 等待程序优雅退出..."
            sleep 8
            
            # 如果还在运行，强制停止
            if ps -p $PID > /dev/null 2>&1; then
                echo "⚡ 强制停止进程: $PID"
                kill -9 $PID
                sleep 2
            fi
            
            rm -f $PID_FILE
            echo "✅ VIDYA程序已停止"
        else
            echo "ℹ️  程序未在运行"
            
            # 清理可能存在的旧PID文件
            if [ -f "$PID_FILE" ]; then
                rm -f $PID_FILE
                echo "🧹 已清理旧PID文件"
            fi
        fi
        ;;
        
    restart)
        echo "🔄 重启VIDYA交易程序..."
        $0 stop
        sleep 3
        $0 start
        ;;
        
    status)
        echo "📊 VIDYA交易程序状态:"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        if is_running; then
            PID=$(cat $PID_FILE)
            echo "✅ 运行状态: 正在运行"
            echo "🆔 进程ID: $PID"
            echo "📅 启动时间: $(ps -p $PID -o lstart= 2>/dev/null || echo '未知')"
            echo "⏱️  运行时间: $(ps -p $PID -o etime= 2>/dev/null || echo '未知')"
            echo "💾 内存使用: $(ps -p $PID -o rss= 2>/dev/null | awk '{if($1) printf "%.1f MB\n", $1/1024; else print "未知"}' || echo '未知')"
            echo "📁 当前目录: $SCRIPT_DIR"
            echo "📄 主程序: $SCRIPT_NAME"
            echo "📊 今日日志: $(get_log_file)"
            
            # 检查日志文件大小
            LOG_FILE_PATH=$(get_log_file)
            if [ -f "$LOG_FILE_PATH" ]; then
                LOG_SIZE=$(du -h "$LOG_FILE_PATH" | cut -f1)
                LOG_LINES=$(wc -l < "$LOG_FILE_PATH")
                echo "📋 日志大小: $LOG_SIZE ($LOG_LINES 行)"
            fi
        else
            echo "❌ 运行状态: 未运行"
            echo "📁 程序目录: $SCRIPT_DIR"
            echo "📄 主程序: $SCRIPT_NAME"
        fi
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ;;
        
    logs)
        # 日志查看功能
        case "$2" in
            today|"")
                echo "📊 查看今日实时日志 (Ctrl+C 退出):"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                tail -f $(get_log_file) || echo "❌ 日志文件不存在"
                ;;
            yesterday)
                YESTERDAY=$(date -d "yesterday" +%Y%m%d 2>/dev/null || date -v-1d +%Y%m%d 2>/dev/null)
                YESTERDAY_LOG="$LOG_DIR/${PROJECT_NAME}_${YESTERDAY}.log"
                if [ -f "$YESTERDAY_LOG" ]; then
                    echo "📊 查看昨日日志 (最后100行):"
                    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    tail -100 $YESTERDAY_LOG
                else
                    echo "❌ 昨天的日志文件不存在: $YESTERDAY_LOG"
                fi
                ;;
            error)
                echo "⚠️  查看错误日志 (最近50条):"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                LOG_FILE_PATH=$(get_log_file)
                if [ -f "$LOG_FILE_PATH" ]; then
                    grep -i "error\|exception\|fail\|traceback\|❌" $LOG_FILE_PATH | tail -50 || echo "ℹ️  未找到错误信息"
                else
                    echo "❌ 日志文件不存在"
                fi
                ;;
            success)
                echo "✅ 查看成功交易日志:"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                LOG_FILE_PATH=$(get_log_file)
                if [ -f "$LOG_FILE_PATH" ]; then
                    grep -i "开仓成功\|平仓成功\|✅.*成交\|✅.*盈利" $LOG_FILE_PATH | tail -20 || echo "ℹ️  未找到成功交易记录"
                else
                    echo "❌ 日志文件不存在"
                fi
                ;;
            stats)
                echo "📈 今日日志统计:"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                LOG_FILE_PATH=$(get_log_file)
                if [ -f "$LOG_FILE_PATH" ]; then
                    echo "📄 总行数: $(wc -l < $LOG_FILE_PATH)"
                    echo "⚠️  错误数: $(grep -i "error\|exception\|❌" $LOG_FILE_PATH | wc -l)"
                    echo "✅ 成功数: $(grep -i "成功\|✅" $LOG_FILE_PATH | wc -l)"
                    echo "💰 开仓数: $(grep -i "开.*仓\|OPEN_" $LOG_FILE_PATH | wc -l)"
                    echo "🎯 平仓数: $(grep -i "平仓\|CLOSE\|止盈\|止损" $LOG_FILE_PATH | wc -l)"
                    echo "📅 最后更新: $(stat -f %Sm -t '%Y-%m-%d %H:%M:%S' $LOG_FILE_PATH 2>/dev/null || stat -c %y $LOG_FILE_PATH 2>/dev/null || echo '未知')"
                    echo "📊 文件大小: $(du -h $LOG_FILE_PATH | cut -f1)"
                else
                    echo "❌ 今日日志文件不存在"
                fi
                ;;
            list)
                echo "📁 可用的日志文件:"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                if ls $LOG_DIR/${PROJECT_NAME}_*.log 2>/dev/null; then
                    echo ""
                    echo "📊 文件详情:"
                    ls -lah $LOG_DIR/${PROJECT_NAME}_*.log | sort -k9 -r
                else
                    echo "❌ 没有找到日志文件"
                fi
                ;;
            *)
                echo "📚 日志查看帮助:"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo "用法: $0 logs {today|yesterday|error|success|stats|list}"
                echo "  today     - 查看今日实时日志 (实时滚动)"
                echo "  yesterday - 查看昨日日志 (最后100行)"
                echo "  error     - 查看错误信息 (最近50条)"
                echo "  success   - 查看成功交易记录"
                echo "  stats     - 日志统计信息"
                echo "  list      - 列出所有日志文件"
                ;;
        esac
        ;;
        
    monitor)
        # 监控模式
        echo "🖥️  进入VIDYA监控模式 (Ctrl+C 退出)"
        echo "⏰ 每5秒自动刷新状态"
        echo ""
        while true; do
            clear
            echo "🎯 ═══════════════════════ VIDYA交易程序监控 ═══════════════════════"
            echo "⏰ 监控时间: $(date '+%Y-%m-%d %H:%M:%S')"
            echo ""
            $0 status
            echo ""
            echo "📋 最近日志 (最后10行):"
            echo "─────────────────────────────────────────────────────────────────────"
            tail -10 $(get_log_file) 2>/dev/null | sed 's/^/  /' || echo "  ❌ 暂无日志数据"
            echo "─────────────────────────────────────────────────────────────────────"
            echo "💡 按 Ctrl+C 退出监控模式"
            sleep 5
        done
        ;;
        
    test)
        echo "🧪 VIDYA程序环境测试:"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        # 检查Python环境
        if command -v python3 &> /dev/null; then
            echo "✅ Python3: $(python3 --version)"
        elif command -v python &> /dev/null; then
            echo "✅ Python: $(python --version)"
        else
            echo "❌ Python环境未找到"
        fi
        
        # 检查工作目录
        if [ -d "$SCRIPT_DIR" ]; then
            echo "✅ 工作目录: $SCRIPT_DIR"
        else
            echo "❌ 工作目录不存在: $SCRIPT_DIR"
        fi
        
        # 检查主程序文件
        if [ -f "$SCRIPT_DIR/$SCRIPT_NAME" ]; then
            echo "✅ 主程序文件: $SCRIPT_NAME"
        else
            echo "❌ 主程序文件不存在: $SCRIPT_NAME"
        fi
        
        # 检查日志目录
        if [ -d "$LOG_DIR" ]; then
            echo "✅ 日志目录: $LOG_DIR"
        else
            echo "ℹ️  日志目录不存在，将自动创建: $LOG_DIR"
            mkdir -p "$LOG_DIR"
        fi
        
        # 检查配置文件
        CONFIG_FILES=("okx_config.py" "strategy_configs.py")
        for config_file in "${CONFIG_FILES[@]}"; do
            if [ -f "$SCRIPT_DIR/$config_file" ]; then
                echo "✅ 配置文件: $config_file"
            else
                echo "❌ 配置文件缺失: $config_file"
            fi
        done
        
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ;;
        
    *)
        echo "🎯 VIDYA策略交易程序管理脚本"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "用法: $0 {start|stop|restart|status|logs|monitor|test}"
        echo ""
        echo "📋 基本操作:"
        echo "  start   - 🚀 启动VIDYA程序 (后台运行)"
        echo "  stop    - 🛑 停止VIDYA程序"
        echo "  restart - 🔄 重启VIDYA程序"
        echo "  status  - 📊 查看程序运行状态"
        echo ""
        echo "📊 日志管理:"
        echo "  logs    - 📋 查看日志 (today|yesterday|error|success|stats|list)"
        echo ""
        echo "🖥️  高级功能:"
        echo "  monitor - 📈 进入实时监控模式 (自动刷新)"
        echo "  test    - 🧪 环境和配置检测"
        echo ""
        echo "💡 常用示例:"
        echo "  $0 start          # 启动程序"
        echo "  $0 logs today     # 查看实时日志"  
        echo "  $0 logs error     # 查看错误日志"
        echo "  $0 monitor        # 监控模式"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        exit 1
        ;;
esac
