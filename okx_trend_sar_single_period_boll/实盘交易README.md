# OKX 实盘交易系统

## 🎯 系统概述

基于 **SAR + Bollinger Bands** 策略的自动化交易系统，支持OKX交易所实盘/模拟盘交易。

---

## 📦 文件清单

### 核心文件

| 文件名 | 说明 |
|--------|------|
| `okx_config.py` | OKX API配置（API密钥、交易模式） |
| `okx_trader.py` | OKX交易接口封装（下单、查询、平仓） |
| `live_trading.py` | 实盘交易主程序（基础版） |
| `live_trading_advanced.py` | 实盘交易主程序（增强版，推荐） |
| `trade_logger.py` | 交易日志记录系统 |
| `check_config.py` | 配置检查工具 |
| `start_live_trading.sh` | 快速启动脚本 |

### 策略相关

| 文件名 | 说明 |
|--------|------|
| `trend_sar_single_period_boll_strategy.py` | 策略核心实现 |
| `strategy_configs.py` | 策略参数配置 |
| `volatility_calculator.py` | 波动率计算器 |
| `ema_calculator.py` | EMA计算器 |

### 文档

| 文件名 | 说明 |
|--------|------|
| `实盘交易使用说明.md` | 详细使用说明 |
| `实盘交易README.md` | 本文件 |

---

## 🚀 快速开始（3步）

### 第 1 步：配置 API 密钥

编辑 `okx_config.py`：

```python
OKX_API_CONFIG = {
    'api_key': '你的API_KEY',
    'secret': '你的SECRET_KEY',
    'password': '你的PASSPHRASE',
    'enableRateLimit': True,
}
```

### 第 2 步：检查配置

```bash
python3 check_config.py
```

确保所有配置检查通过。

### 第 3 步：启动交易

```bash
# 方式1: 使用启动脚本（推荐）
chmod +x start_live_trading.sh
./start_live_trading.sh

# 方式2: 直接运行
python3 live_trading_advanced.py
```

---

## 📊 运行模式对比

| 模式 | mode | test_mode | 是否下单 | 用途 |
|------|------|-----------|----------|------|
| 测试模式 | paper | True | ❌ | 验证策略逻辑 |
| 模拟盘 | paper | False | ✅ (沙盒) | 测试交易流程 |
| 实盘 | live | False | ✅ (真实) | 正式交易 |

### 配置示例

**测试模式**（推荐第一次运行）:
```python
TRADING_CONFIG = {
    'mode': 'paper',
    'test_mode': True,
}
```

**模拟盘模式**（充分测试后）:
```python
TRADING_CONFIG = {
    'mode': 'paper',
    'test_mode': False,
}
```

**实盘模式**（确认无误后）:
```python
TRADING_CONFIG = {
    'mode': 'live',
    'test_mode': False,
}
```

---

## 🔧 策略配置

编辑 `strategy_configs.py`:

```python
config = {
    'long_coin': 'BTC',               # 交易币种
    'timeframe': '30m',               # 时间周期
    'initial_capital': 100000,        # 初始资金
    'position_size_percentage': 100,  # 仓位比例（100=全仓）
    
    # SAR参数
    'sar_start': 0.005,
    'sar_increment': 0.005,
    'sar_maximum': 0.04,
    
    # 止盈止损
    'fixed_take_profit_pct': 0.5,    # 固定止盈 0.5%
    'max_loss_pct': 0,                # 最大亏损（0=禁用）
}
```

---

## 📈 运行示例

### 启动程序

```bash
$ python3 live_trading_advanced.py

================================================================================
🚀 OKX 实盘交易系统 - 增强版
🎯 策略: SAR + Bollinger Bands
================================================================================

📊 策略配置:
  币种: BTC
  周期: 30m
  SAR: start=0.005, inc=0.005, max=0.04
  止盈: 0.5%
  止损: 0%

💡 模式: 模拟盘
🧪 测试: 是（只打印）

================================================================================
🤖 增强版实盘交易机器人已初始化
================================================================================
📊 交易对: BTC-USDT-SWAP
⏰ 时间周期: 30m
🧪 测试模式: 是
================================================================================

🔥 开始预热策略...
📅 预热时间范围: 2025-08-14 -> 2025-10-13
📊 获取到 87360 条历史数据
✅ 策略预热完成！

💰 账户余额: $10,000.00 USDT
   可用余额: $10,000.00 USDT
⏰ 更新间隔: 60 秒
🔄 开始监控市场...

[12:34:56] K线: 12:34 | 价格: $62,345.67 | 持仓: 空仓
```

### 收到交易信号

```
================================================================================
🎯 收到交易信号: OPEN_LONG
================================================================================
💰 信号价格: $62,345.67
📝 信号原因: SAR转多开仓...

🟢 执行开多操作...
   投入金额: $10,000.00
   持仓份额: 0.1605
   止损位: $62,100.00
   止盈位: $62,657.00

🧪 【测试模式】模拟开多单: BTC-USDT-SWAP, 数量: 0.1605
✅ 开多单成功！
================================================================================
```

### 查看统计

```
================================================================================
📊 今日交易统计 (2025-10-13)
================================================================================
📈 总交易: 5次
✅ 盈利: 3次
❌ 亏损: 2次
🎯 胜率: 60.0%
💰 累计盈亏: $+125.50
🏆 最大盈利: $+85.30
📉 最大亏损: $-32.10
⚠️  连续亏损: 0次
================================================================================
```

---

## 📝 日志文件

程序会自动创建日志文件：

```
live_trade_logs/
├── trade_log_20251013.txt     # 文本格式日志
├── trade_log_20251013.json    # JSON格式日志（结构化数据）
└── daily_report_20251013.json # 每日报告（交易统计）
```

### 查看日志

```bash
# 实时查看日志
tail -f live_trade_logs/trade_log_$(date +%Y%m%d).txt

# 查看JSON日志
cat live_trade_logs/trade_log_$(date +%Y%m%d).json | jq

# 查看每日报告
cat live_trade_logs/daily_report_$(date +%Y%m%d).json | jq
```

---

## 🛡️ 风险控制

### 内置风险控制

1. **最大持仓限制**: `max_position_value`
2. **最小下单量**: `min_order_size`
3. **API调用重试**: `max_retry`
4. **连续亏损限制**: 默认3次
5. **每日亏损限制**: 可配置

### 手动风险控制

1. **使用小资金**
   ```python
   'initial_capital': 1000  # 只用 1000 USDT
   ```

2. **使用部分仓位**
   ```python
   'position_size_percentage': 50  # 只用50%资金
   ```

3. **设置严格止损**
   ```python
   'max_loss_pct': 2  # 最大亏损2%
   ```

---

## 🔄 持仓同步

程序启动时会自动同步：
- 策略持仓状态
- 交易所实际持仓

**注意**: 运行期间不要手动交易，会导致状态不同步！

---

## 🛑 停止程序

### 正常停止

按 `Ctrl+C`，程序会：
1. 保存交易日志
2. 生成每日报告
3. 关闭数据库连接
4. 优雅退出

### 紧急停止

```bash
# 查找进程
ps aux | grep live_trading

# 强制停止
kill -9 <PID>
```

**注意**: 强制停止可能导致日志丢失！

---

## 📊 监控建议

### 1. 实时监控

- 使用 `tail -f` 实时查看日志
- 定期检查账户余额
- 关注异常信号

### 2. 每日检查

- 查看每日报告
- 分析胜率和盈亏比
- 评估策略表现

### 3. 定期优化

- 根据市场情况调整参数
- 回测验证新参数
- 逐步优化策略

---

## 🔥 高级功能

### 后台运行

```bash
# 使用 nohup 后台运行
nohup python3 live_trading_advanced.py > live_trading.log 2>&1 &

# 查看日志
tail -f live_trading.log
```

### 自动重启（使用 systemd）

创建 `/etc/systemd/system/okx-trading.service`:

```ini
[Unit]
Description=OKX Live Trading Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/Users/Aylwin/trade_okx/trend_sar_single_period_boll
ExecStart=/usr/bin/python3 live_trading_advanced.py
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl start okx-trading
sudo systemctl enable okx-trading  # 开机自启
sudo systemctl status okx-trading  # 查看状态
```

---

## ⚠️ 重要提醒

1. **先测试后实盘**: 务必在测试模式和模拟盘充分测试
2. **小资金起步**: 实盘初期使用小资金
3. **设置止损**: 保护本金最重要
4. **定期检查**: 不要长时间无人监管
5. **保存密钥**: API密钥不要泄露

---

## 🆘 紧急联系

- OKX官方客服: https://www.okx.com/support
- API文档: https://www.okx.com/docs-v5/

---

## 📞 技术支持

如有问题，请检查：
1. 日志文件 (`live_trade_logs/`)
2. 配置文件是否正确
3. 数据库是否有数据
4. API密钥是否有效

---

**祝你交易顺利！🚀**

*免责声明: 量化交易有风险，本系统仅供学习研究，使用造成的损失由使用者自行承担。*

