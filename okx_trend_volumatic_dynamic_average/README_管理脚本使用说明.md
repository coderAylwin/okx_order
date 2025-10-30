# VIDYA策略交易程序管理脚本使用说明

## 概述
`manage_vidya_trading.sh` 是专为VIDYA策略设计的交易程序管理脚本，提供了完整的程序生命周期管理功能。

## 快速开始

### 1. 给脚本添加执行权限
```bash
chmod +x manage_vidya_trading.sh
```

### 2. 启动VIDYA交易程序
```bash
./manage_vidya_trading.sh start
```

### 3. 查看程序状态
```bash
./manage_vidya_trading.sh status
```

### 4. 查看实时日志
```bash
./manage_vidya_trading.sh logs today
```

## 详细功能说明

### 📋 基本操作

#### 启动程序
```bash
./manage_vidya_trading.sh start
```
- 后台启动VIDYA交易程序
- 自动创建日志目录
- 保存进程ID到PID文件
- 检查启动是否成功

#### 停止程序
```bash
./manage_vidya_trading.sh stop
```
- 优雅关闭程序（先发送SIGTERM信号）
- 等待8秒后如果仍在运行则强制关闭
- 清理PID文件

#### 重启程序
```bash
./manage_vidya_trading.sh restart
```
- 等同于先stop再start
- 确保完全重新加载配置

#### 查看状态
```bash
./manage_vidya_trading.sh status
```
显示详细的程序运行状态：
- ✅ 运行状态
- 🆔 进程ID
- 📅 启动时间
- ⏱️ 运行时长
- 💾 内存使用量
- 📊 日志信息

### 📊 日志管理

#### 查看今日实时日志
```bash
./manage_vidya_trading.sh logs today
# 或者简写
./manage_vidya_trading.sh logs
```

#### 查看昨日日志
```bash
./manage_vidya_trading.sh logs yesterday
```

#### 查看错误日志
```bash
./manage_vidya_trading.sh logs error
```
筛选包含以下关键词的日志：
- error
- exception
- fail
- traceback
- ❌

#### 查看成功交易记录
```bash
./manage_vidya_trading.sh logs success
```
筛选包含以下关键词的日志：
- 开仓成功
- 平仓成功
- ✅.*成交
- ✅.*盈利

#### 查看日志统计
```bash
./manage_vidya_trading.sh logs stats
```
显示：
- 📄 总行数
- ⚠️ 错误数量
- ✅ 成功数量
- 💰 开仓次数
- 🎯 平仓次数
- 📅 最后更新时间
- 📊 文件大小

#### 列出所有日志文件
```bash
./manage_vidya_trading.sh logs list
```

### 🖥️ 高级功能

#### 实时监控模式
```bash
./manage_vidya_trading.sh monitor
```
功能：
- 每5秒自动刷新程序状态
- 显示最近10行日志
- 按Ctrl+C退出监控模式

#### 环境检测
```bash
./manage_vidya_trading.sh test
```
检测项目：
- ✅ Python环境
- ✅ 工作目录
- ✅ 主程序文件
- ✅ 日志目录
- ✅ 配置文件

## 日志系统

### 日志文件命名规则
```
logs/vidya_trading_bot_YYYYMMDD.log
```
例如：`logs/vidya_trading_bot_20251028.log`

### 日志轮转
- 每天自动创建新的日志文件
- 历史日志文件会保留
- 可通过 `logs list` 查看所有日志文件

## 故障排除

### 程序无法启动
1. 检查Python环境：
```bash
./manage_vidya_trading.sh test
```

2. 查看启动错误：
```bash
./manage_vidya_trading.sh logs error
```

3. 检查配置文件：
- `okx_config.py` - OKX API配置
- `strategy_configs.py` - 策略参数配置

### 程序运行异常
1. 查看实时日志：
```bash
./manage_vidya_trading.sh logs today
```

2. 查看错误信息：
```bash
./manage_vidya_trading.sh logs error
```

3. 重启程序：
```bash
./manage_vidya_trading.sh restart
```

### 日志文件过大
历史日志文件可以手动删除：
```bash
# 删除7天前的日志
find logs/ -name "vidya_trading_bot_*.log" -mtime +7 -delete
```

## 常用运维命令

### 启动并监控
```bash
./manage_vidya_trading.sh start && ./manage_vidya_trading.sh monitor
```

### 查看交易情况
```bash
# 查看成功交易
./manage_vidya_trading.sh logs success

# 查看统计信息
./manage_vidya_trading.sh logs stats
```

### 故障诊断
```bash
# 快速检查状态和错误
./manage_vidya_trading.sh status
./manage_vidya_trading.sh logs error
```

## 注意事项

1. **权限要求**：脚本需要执行权限
2. **路径配置**：脚本中的路径已配置为当前VIDYA策略目录
3. **PID文件**：程序运行时会创建 `vidya_trading_bot.pid` 文件
4. **日志目录**：首次运行会自动创建 `logs/` 目录
5. **优雅关闭**：使用 `stop` 命令会先尝试优雅关闭，8秒后强制关闭

## 脚本文件结构
```
okx_trend_volumatic_dynamic_average/
├── manage_vidya_trading.sh          # 主管理脚本
├── live_trading_VIDYA.py           # VIDYA交易程序
├── logs/                           # 日志目录（自动创建）
│   └── vidya_trading_bot_YYYYMMDD.log
├── vidya_trading_bot.pid           # PID文件（运行时创建）
└── README_管理脚本使用说明.md       # 本说明文件
```

---

## 技术支持

如果遇到问题，请：
1. 首先运行 `./manage_vidya_trading.sh test` 检查环境
2. 查看错误日志 `./manage_vidya_trading.sh logs error`
3. 检查配置文件是否正确配置API密钥和参数
