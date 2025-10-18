# 进入程序目录
cd ~/okx_order/okx_trend_sar_single_period_boll

# 创建管理脚本
nano manage_trading.sh
# 粘贴上面的脚本内容

# 给执行权限
chmod +x manage_trading.sh

# 启动程序 (后台运行)
./manage_trading.sh start

# 查看状态
./manage_trading.sh status

# 查看实时日志 (不会中断程序)
./manage_trading.sh logs

# 监控模式 (实时状态 + 日志)
./manage_trading.sh monitor

# 停止程序
./manage_trading.sh stop

# 重启程序
./manage_trading.sh restart