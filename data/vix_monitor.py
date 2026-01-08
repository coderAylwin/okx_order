import yfinance as yf
import time
import datetime
import pytz  # 用于时区处理

# VIX 符号
vix = yf.Ticker("^VIX")

# 时区设置
ny_tz = pytz.timezone('America/New_York')  # 自动处理夏令时/冬令时
local_tz = datetime.datetime.now().astimezone().tzinfo  # 本地时区（用于显示本地时间）

print("VIX 数据监控已启动（yfinance，免费近实时），每 5 分钟更新一次（按 Ctrl+C 停止）\n")

while True:
    try:
        now_utc = datetime.datetime.now(pytz.UTC)
        now_ny = now_utc.astimezone(ny_tz)  # 当前美东时间（自动夏令时）
        now_local = datetime.datetime.now()

        # 判断交易时段（周一到周五）
        weekday = now_ny.weekday()  # 0=周一, 6=周日
        time_ny = now_ny.time()

        in_regular = (weekday < 5) and (datetime.time(9, 30) <= time_ny <= datetime.time(16, 0))
        in_pre_market = (weekday < 5) and (datetime.time(4, 0) <= time_ny < datetime.time(9, 30))
        in_after_hours = (weekday < 5) and (datetime.time(16, 0) < time_ny <= datetime.time(20, 0))
        is_holiday_or_weekend = weekday >= 5 or not (in_pre_market or in_regular or in_after_hours)

        # 获取当前价格信息
        info = vix.info
        current_price = info.get('regularMarketPrice') or info.get('previousClose')
        previous_close = info.get('regularMarketPreviousClose')
        change = info.get('regularMarketChange')
        change_percent = info.get('regularMarketChangePercent')

        print(f"本地时间 : {now_local.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"美东时间 : {now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}  ({'夏令时' if now_ny.dst() else '冬令时'})")
        
        if in_regular:
            print("   当前状态：正常交易时段（9:30-16:00 ET）")
        elif in_pre_market:
            print("   当前状态：盘前交易（4:00-9:30 ET） → 当前价格更新，但5分钟K线暂无新数据")
        elif in_after_hours:
            print("   当前状态：盘后交易（16:00-20:00 ET） → 当前价格更新，但5分钟K线暂无新数据")
        else:
            print("   当前状态：非交易时间（休市/周末/节假日）")

        print(f"   VIX 当前价格    : {current_price}")
        print(f"   前日收盘        : {previous_close}")
        if change is not None and change_percent is not None:
            print(f"   今日变化        : {change:+.2f} ({change_percent:+.2f}%)")
        print("-" * 60)

        # 获取最近5分钟K线
        hist = vix.history(period="5d", interval="5m")
        recent_hist = hist.tail(10)

        if not recent_hist.empty:
            print("最近 10 条 5 分钟 K 线（美东时间 ET）：")
            for index, row in recent_hist.iterrows():
                # 将时间转换为美东时间并格式化
                ts_ny = index.tz_convert(ny_tz)
                ts_str = ts_ny.strftime("%Y-%m-%d %H:%M:%S %Z")
                print(f"   {ts_str} | 开: {row['Open']:.2f} 高: {row['High']:.2f} 低: {row['Low']:.2f} 收: {row['Close']:.2f} 成交量: {int(row['Volume'])}")
        else:
            print("   暂无5分钟K线数据（可能还未开盘）")

        print("\n")

    except Exception as e:
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 请求出错: {e}\n")
        time.sleep(60)

    # 每5分钟更新一次
    time.sleep(300)