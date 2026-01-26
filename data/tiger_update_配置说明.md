# Tiger Update 配置日期范围说明

## 核心问题：为什么配置是12-01至12-05，但数据库中有8月份的数据？

### 关键理解

**配置的日期范围只控制"本次运行"要下载的数据，不会删除已存在的数据！**

---

## 代码逻辑分析

### 1. 配置的作用范围

```python
START_DATE = date(2015, 12, 1)  # 最早日期
END_DATE = date(2025, 12, 5)    # 最晚日期
```

**这些配置的作用**：
- ✅ 控制**本次运行**从哪个日期开始下载
- ✅ 控制**本次运行**下载到哪个日期
- ❌ **不会删除**数据库中已存在的数据
- ❌ **不会限制**查询时能看到的数据范围

### 2. 数据插入逻辑

```python
# 第179行：使用 INSERT IGNORE
INSERT IGNORE INTO {table_name} ...
```

**`INSERT IGNORE` 的含义**：
- 如果数据已存在（基于 `time` 字段的 UNIQUE INDEX），**跳过插入**
- 如果数据不存在，**正常插入**
- **不会删除或覆盖已存在的数据**

### 3. 检查逻辑

```python
# 第151行：检查是否已下载
if check_session_downloaded(table_prefix, current_date):
    print(f"⏩ {target_date_str} 数据库 22:30 已有记录，判定为已下载，跳过。")
    current_date -= timedelta(days=1)
    continue  # 跳过，不下载
```

**检查逻辑的作用**：
- 如果某一天的数据已存在，**跳过下载**
- 如果某一天的数据不存在，**下载数据**

---

## 为什么会有8月份的数据？

### 场景还原

**假设时间线**：

1. **第一次运行（2025年8月）**
   ```python
   END_DATE = date(2025, 8, 31)  # 当时配置是8月31日
   ```
   - 脚本下载了：2025-08-31 → 2025-08-30 → ... → 2015-12-01
   - 数据库中有了8月份的数据

2. **第二次运行（2025年12月）**
   ```python
   END_DATE = date(2025, 12, 5)  # 现在配置是12月5日
   ```
   - 脚本尝试下载：2025-12-05 → 2025-12-04 → ... → 2015-12-01
   - 当遇到8月份时：
     - `check_session_downloaded()` 返回 `True`（8月数据已存在）
     - 脚本**跳过**8月份，继续向前
   - 最终结果：
     - ✅ 新增了：9月、10月、11月、12月的数据
     - ✅ 保留了：8月份的数据（已存在，不会删除）

### 数据库中的数据是"累积的"

```
数据库中的数据 = 所有历史运行下载的数据总和

例如：
- 第1次运行：下载了 8月份数据
- 第2次运行：下载了 12月份数据
- 最终数据库：包含 8月 + 12月 的数据
```

---

## 配置的实际作用

### 当前配置

```python
START_DATE = date(2015, 12, 1)  # 最早日期
END_DATE = date(2025, 12, 5)    # 最晚日期
```

### 本次运行会做什么？

1. **从 2025-12-05 开始向前扫描**
2. **检查每一天是否已有数据**
   - 如果已有数据 → 跳过
   - 如果没有数据 → 下载
3. **一直扫描到 2015-12-01**

### 实际效果

- ✅ 会下载：12-01 到 12-05 之间**缺失**的数据
- ✅ 会跳过：12-01 到 12-05 之间**已有**的数据
- ✅ 会跳过：8月份的数据（因为已存在）
- ❌ **不会删除**：8月份的数据

---

## 验证方法

### 1. 查看数据库中的实际数据范围

```sql
-- 查看2025年的数据范围
SELECT 
    MIN(FROM_UNIXTIME(time)) as earliest_time,
    MAX(FROM_UNIXTIME(time)) as latest_time,
    COUNT(*) as total_records,
    COUNT(DISTINCT DATE(FROM_UNIXTIME(time))) as distinct_days
FROM ml_us_aapl_history_1m_2025;
```

### 2. 查看具体有哪些日期的数据

```sql
-- 查看2025年有哪些日期的数据
SELECT 
    DATE(FROM_UNIXTIME(time)) as date,
    COUNT(*) as records
FROM ml_us_aapl_history_1m_2025
GROUP BY DATE(FROM_UNIXTIME(time))
ORDER BY date DESC
LIMIT 20;
```

### 3. 查看数据的插入时间（create_time）

```sql
-- 查看数据是什么时候插入的
SELECT 
    DATE(FROM_UNIXTIME(time)) as data_date,
    MIN(create_time) as first_inserted,
    MAX(create_time) as last_inserted,
    COUNT(*) as records
FROM ml_us_aapl_history_1m_2025
GROUP BY DATE(FROM_UNIXTIME(time))
ORDER BY data_date DESC
LIMIT 20;
```

---

## 如果想只保留配置范围内的数据

### 方案1：手动删除范围外的数据

```sql
-- 删除2025年8月份的数据（示例）
DELETE FROM ml_us_aapl_history_1m_2025
WHERE time >= UNIX_TIMESTAMP('2025-08-01 00:00:00')
  AND time < UNIX_TIMESTAMP('2025-09-01 00:00:00');
```

### 方案2：修改代码，添加数据清理逻辑

```python
def cleanup_out_of_range_data(table_prefix, start_date, end_date):
    """清理配置范围外的数据"""
    # 获取所有年份
    years = set(range(start_date.year, end_date.year + 1))
    
    for year in years:
        table_name = f"{table_prefix}_{year}"
        
        # 计算该年的开始和结束时间戳
        if year == start_date.year:
            start_ts = int(datetime.combine(start_date, dt_time(0, 0, 0)).timestamp())
        else:
            start_ts = int(datetime.combine(date(year, 1, 1), dt_time(0, 0, 0)).timestamp())
        
        if year == end_date.year:
            end_ts = int(datetime.combine(end_date, dt_time(23, 59, 59)).timestamp())
        else:
            end_ts = int(datetime.combine(date(year, 12, 31), dt_time(23, 59, 59)).timestamp())
        
        # 删除范围外的数据
        delete_query = f"""
        DELETE FROM `{table_name}` 
        WHERE `time` < %s OR `time` > %s
        """
        cursor.execute(delete_query, (start_ts, end_ts))
        deleted = cursor.rowcount
        if deleted > 0:
            print(f"🗑️  清理 {table_name}: 删除了 {deleted} 条范围外的数据")
    
    db_connection.commit()
```

---

## 总结

### 为什么有8月份的数据？

**答案**：因为之前运行过脚本，当时下载了8月份的数据。配置的日期范围只控制**新下载**的数据，不会删除已存在的数据。

### 配置的真正作用

- ✅ **控制本次运行要下载的日期范围**
- ✅ **跳过已有数据的日期**（避免重复下载）
- ❌ **不会删除已存在的数据**
- ❌ **不会限制查询时能看到的数据**

### 如果想清理旧数据

需要手动删除或添加清理逻辑，配置本身不会自动清理。

---

## 建议

1. **如果8月份的数据是之前需要的**：保留即可，不影响使用
2. **如果8月份的数据是误下载的**：手动删除或添加清理逻辑
3. **如果想避免这种情况**：每次运行前先清理范围外的数据

