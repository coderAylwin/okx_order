# 给脚本权限
chmod +x manage_okx_advanced.sh

# 启动程序（自动创建带日期的日志）
./manage_okx_advanced.sh start

# 查看今日实时日志
./manage_okx_advanced.sh logs today

# 查看昨日日志
./manage_okx_advanced.sh logs yesterday

# 列出所有日志文件
./manage_okx_advanced.sh logs list

# 清理旧日志
./manage_okx_advanced.sh cleanup

# 查看状态（会显示日志路径）
./manage_okx_advanced.sh status