#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid 聪明钱仓位监控服务

功能：
1. 每5分钟轮询一次，监控指定地址的交易活动
2. 检测到新成交(fills)后，获取当前仓位并与上次对比
3. 聚合fills信息，生成变动描述
4. 将仓位变动推送到飞书群
5. 仓位快照保存到数据库（hl_position_snapshot）

运行方式：
  pip install hyperliquid-python-sdk requests pymysql
  python hyperliquid_monitor.py

添加地址：
  在 ADDRESS_CONFIG 中添加 {"address": "0x...", "label": "别名"}

添加监控币种：
  在 WATCH_COINS 中添加币种名称（如 "ETH", "BTC"）
  设为空列表 [] 则监控所有币种

建表SQL：
  CREATE TABLE `hl_position_snapshot` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `address` VARCHAR(64) NOT NULL,
    `account_value` DECIMAL(20,6) DEFAULT NULL,
    `total_margin_used` DECIMAL(20,6) DEFAULT NULL,
    `positions` JSON DEFAULT NULL,
    `snapshot_time` BIGINT DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_address_created` (`address`, `created_at` DESC)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

import sys
import time
import json
import pymysql
import requests
import logging
import traceback
from datetime import datetime, timezone, timedelta
from hyperliquid.info import Info
from hyperliquid.utils import constants

# ===================== 配置区 =====================

# 地址配置：地址 + 别名
ADDRESS_CONFIG = [
    {"address": "0x634fe24f2f7396f5d967ec3936df04f49a3e6951", "label": "聪明钱A"},
    {"address": "0x687feda45b6847763f5bf5c01a2f6c1a3d727f5c", "label": "聪明钱B"},
    {"address": "0xa5b0edf6b55128e0ddae8e51ac538c3188401d41", "label": "聪明钱C"},
    {"address": "0x6c8512516ce5669d35113a11ca8b8de322fd84f6", "label": "聪明钱D"},
    {"address": "0x71dfc07de32c2ebf1c4801f4b1c9e40b76d4a23d", "label": "聪明钱E"},
    {"address": "0x35d1151ef1aab579cbb3109e69fa82f94ff5acb1", "label": "聪明钱F"},
    # {"address": "0xabc...", "label": "聪明钱B"},
]

# 监控币种（只关注这些币种的仓位变动，其他忽略）
# 设为空列表 [] 则监控所有币种
# 注意：API返回的币种可能有前缀如 "xyz:GOLD"，这里只需要写 "GOLD" 即可
WATCH_COINS = ["BTC", "ETH", "SOL"]

# 飞书Webhook地址
LARK_WEBHOOK = "https://open.larksuite.com/open-apis/bot/v2/hook/39ed67d4-8214-4b8b-bf1a-e17f3acdca9f"

# 轮询间隔（秒）
POLL_INTERVAL = 300  # 5分钟

# 仓位变化阈值（size变化绝对值超过此值才算变动）
CHANGE_THRESHOLD = 0.001

# 数据库配置
DB_CONFIG = {
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',
    'port': 3306,
    'user': 'payment_pro',
    'password': 'nS4kO7tG1jH7cI6oR4b',
    'database': 'quantify'
}

# 北京时区
BEIJING_TZ = timezone(timedelta(hours=8))

# ===================== 日志配置 =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ===================== 初始化 =====================
info = Info(constants.MAINNET_API_URL, skip_ws=True)

# 每个地址的上次 fills 最新时间戳（ms）
last_fill_times = {}
for cfg in ADDRESS_CONFIG:
    last_fill_times[cfg['address']] = int(time.time() * 1000) - POLL_INTERVAL * 1000

# 地址别名映射
address_labels = {cfg['address']: cfg['label'] for cfg in ADDRESS_CONFIG}


# ===================== 工具函数 =====================

def format_usd(value):
    """格式化 USD 金额"""
    value = float(value)
    if abs(value) >= 100000000:
        return f"{value / 100000000:.2f} 亿U"
    elif abs(value) >= 10000:
        return f"{value / 10000:.2f} 万U"
    else:
        return f"{value:,.2f} U"


def get_display_coin(coin):
    """
    获取币种显示名称
    处理 xyz:GOLD 这类前缀格式，返回 GOLD
    """
    return coin.split(":")[-1] if ":" in coin else coin


def is_watched_coin(coin):
    """判断币种是否在监控列表中"""
    if not WATCH_COINS:
        return True  # 空列表表示监控全部
    display_coin = get_display_coin(coin)
    return display_coin in WATCH_COINS


# ===================== 数据库操作 =====================

def init_db():
    """初始化数据库，自动创建表（如果不存在）"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `hl_position_snapshot` (
                `id` BIGINT NOT NULL AUTO_INCREMENT,
                `address` VARCHAR(64) NOT NULL,
                `account_value` DECIMAL(20,6) DEFAULT NULL,
                `total_margin_used` DECIMAL(20,6) DEFAULT NULL,
                `positions` JSON DEFAULT NULL,
                `snapshot_time` BIGINT DEFAULT NULL,
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (`id`),
                INDEX `idx_address_created` (`address`, `created_at` DESC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        conn.commit()
        logging.info("✅ 数据库表 hl_position_snapshot 已就绪")
    except Exception as e:
        logging.error(f"初始化数据库失败: {e}")
        logging.error(traceback.format_exc())
    finally:
        if conn:
            conn.close()


def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database'],
        charset='utf8mb4'
    )


def save_snapshot(address, account_value, total_margin_used, positions, snapshot_time):
    """
    保存仓位快照到数据库
    
    Args:
        address: 钱包地址
        account_value: 账户价值
        total_margin_used: 已用保证金
        positions: 过滤后的仓位列表
        snapshot_time: API返回的时间戳(ms)
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
        INSERT INTO hl_position_snapshot 
        (address, account_value, total_margin_used, positions, snapshot_time, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        now = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(sql, (
            address,
            account_value,
            total_margin_used,
            json.dumps(positions, ensure_ascii=False),
            snapshot_time,
            now
        ))
        conn.commit()
        label = address_labels.get(address, address[:10])
        logging.info(f"✅ [{label}] 仓位快照保存成功")
    except Exception as e:
        logging.error(f"保存仓位快照失败: {e}")
        logging.error(traceback.format_exc())
    finally:
        if conn:
            conn.close()


def get_latest_snapshot(address):
    """
    获取地址最新的仓位快照
    
    Returns:
        dict: 包含 account_value, total_margin_used, positions, snapshot_time
        None: 如果没有历史记录
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
        SELECT account_value, total_margin_used, positions, snapshot_time
        FROM hl_position_snapshot
        WHERE address = %s
        ORDER BY created_at DESC
        LIMIT 1
        """
        cursor.execute(sql, (address,))
        result = cursor.fetchone()
        if result:
            return {
                'account_value': float(result[0]) if result[0] else 0,
                'total_margin_used': float(result[1]) if result[1] else 0,
                'positions': json.loads(result[2]) if result[2] else [],
                'snapshot_time': result[3]
            }
        return None
    except Exception as e:
        logging.error(f"查询仓位快照失败: {e}")
        logging.error(traceback.format_exc())
        return None
    finally:
        if conn:
            conn.close()


# ===================== 仓位处理 =====================

def simplify_positions(user_state):
    """
    从 clearinghouseState 提取简化后的仓位列表
    只保留 WATCH_COINS 中的币种
    
    Args:
        user_state: clearinghouseState API 返回的完整数据
    
    Returns:
        list: 简化后的仓位列表
    """
    positions = []
    asset_positions = user_state.get("assetPositions", [])
    
    for item in asset_positions:
        pos = item.get("position", {})
        if not pos:
            continue
        
        coin = pos.get("coin", "")
        if not coin:
            continue
        
        # 过滤币种
        if not is_watched_coin(coin):
            continue
        
        leverage = pos.get("leverage", {})
        
        positions.append({
            "coin": coin,
            "display_coin": get_display_coin(coin),
            "szi": float(pos.get("szi", 0)),
            "entry_px": pos.get("entryPx", "0"),
            "position_value": pos.get("positionValue", "0"),
            "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
            "return_on_equity": pos.get("returnOnEquity", "0"),
            "liquidation_px": pos.get("liquidationPx", "0"),
            "margin_used": pos.get("marginUsed", "0"),
            "leverage_type": leverage.get("type", ""),
            "leverage_value": leverage.get("value", 0),
            "max_leverage": pos.get("maxLeverage", 0),
        })
    
    return positions


def positions_to_dict(positions):
    """将仓位列表转为 {coin: position} 字典，方便对比"""
    return {p['coin']: p for p in positions}


# ===================== Fills 聚合 =====================

def aggregate_fills(fills):
    """
    按 coin + dir 聚合 fills 信息
    
    Args:
        fills: userFillsByTime 返回的原始 fills 列表
    
    Returns:
        dict: {coin: {dirs: {dir: {total_sz, avg_px, total_closed_pnl, total_fee, count}}, total_count}}
    """
    agg = {}
    
    for fill in fills:
        coin = fill.get("coin", "")
        if not coin:
            continue
        
        # 过滤币种
        if not is_watched_coin(coin):
            continue
        
        sz = float(fill.get("sz", 0))
        px = float(fill.get("px", 0))
        closed_pnl = float(fill.get("closedPnl", 0))
        fee = float(fill.get("fee", 0))
        direction = fill.get("dir", "Unknown")
        
        if coin not in agg:
            agg[coin] = {
                'display_coin': get_display_coin(coin),
                'dirs': {},
                'total_count': 0
            }
        
        agg[coin]['total_count'] += 1
        
        if direction not in agg[coin]['dirs']:
            agg[coin]['dirs'][direction] = {
                'total_sz': 0,
                'total_px_sz': 0,
                'total_closed_pnl': 0,
                'total_fee': 0,
                'count': 0
            }
        
        d = agg[coin]['dirs'][direction]
        d['total_sz'] += sz
        d['total_px_sz'] += px * sz
        d['total_closed_pnl'] += closed_pnl
        d['total_fee'] += fee
        d['count'] += 1
    
    # 计算加权均价
    for coin in agg:
        for dir_name in agg[coin]['dirs']:
            d = agg[coin]['dirs'][dir_name]
            if d['total_sz'] > 0:
                d['avg_px'] = d['total_px_sz'] / d['total_sz']
            else:
                d['avg_px'] = 0
            del d['total_px_sz']
    
    return agg


def format_fills_summary(fills_agg_coin):
    """
    格式化单个币种的 fills 聚合信息
    
    Args:
        fills_agg_coin: aggregate_fills 中某个 coin 的聚合数据
    
    Returns:
        str: 格式化的 fills 描述
    """
    parts = []
    for dir_name, d in fills_agg_coin['dirs'].items():
        part = f"{dir_name}: {d['count']}笔, 均价={d['avg_px']:.2f}, 量={d['total_sz']:.4f}"
        if d['total_closed_pnl'] != 0:
            part += f", 已实现PnL={d['total_closed_pnl']:+.2f}"
        part += f", 手续费={d['total_fee']:.2f}"
        parts.append(part)
    return " | ".join(parts)


# ===================== 仓位对比 =====================

def detect_changes(prev_positions, curr_positions, fills_agg):
    """
    对比前后仓位，生成变动描述列表
    
    Args:
        prev_positions: 上一次仓位 dict {coin: position}
        curr_positions: 当前仓位 dict {coin: position}
        fills_agg: fills 聚合数据 {coin: {...}}
    
    Returns:
        list: 变动描述列表
    """
    changes = []
    all_coins = set(prev_positions.keys()) | set(curr_positions.keys())
    
    for coin in sorted(all_coins):
        prev = prev_positions.get(coin)
        curr = curr_positions.get(coin)
        display_coin = get_display_coin(coin)
        fill_info = fills_agg.get(coin)
        
        if prev is None and curr is not None:
            # ====== 新开仓 ======
            direction = "多" if curr['szi'] > 0 else "空"
            line = f"🆕 开{direction} {display_coin}:"
            line += f" size={curr['szi']:+.4f}"
            line += f", 开仓价={curr['entry_px']}"
            line += f", 杠杆={curr['leverage_value']}x({curr['leverage_type']})"
            line += f"\n     仓位价值={format_usd(curr['position_value'])}"
            line += f", 爆仓价={curr['liquidation_px']}"
            if fill_info:
                line += f"\n     📝 {format_fills_summary(fill_info)}"
            changes.append(line)
        
        elif prev is not None and curr is None:
            # ====== 全部平仓 ======
            direction = "多" if prev['szi'] > 0 else "空"
            line = f"🔚 平{direction} {display_coin}:"
            line += f" 原size={prev['szi']:.4f}"
            if fill_info:
                # 汇总所有 dir 的 closedPnl
                total_pnl = sum(d['total_closed_pnl'] for d in fill_info['dirs'].values())
                total_fee = sum(d['total_fee'] for d in fill_info['dirs'].values())
                line += f", 已实现PnL={total_pnl:+.2f} USDC"
                line += f", 手续费={total_fee:.2f}"
                line += f"\n     📝 {format_fills_summary(fill_info)}"
            changes.append(line)
        
        elif prev is not None and curr is not None:
            # ====== 仓位变化 ======
            sub_changes = []
            
            # 1. szi 变化
            delta_szi = curr['szi'] - prev['szi']
            if abs(delta_szi) > CHANGE_THRESHOLD:
                # 判断操作类型
                if prev['szi'] > 0 and curr['szi'] < 0:
                    action = "🔄 反手做空"
                elif prev['szi'] < 0 and curr['szi'] > 0:
                    action = "🔄 反手做多"
                elif abs(curr['szi']) > abs(prev['szi']):
                    direction = "多" if curr['szi'] > 0 else "空"
                    action = f"📈 加仓({direction})"
                else:
                    direction = "多" if curr['szi'] > 0 else "空"
                    action = f"📉 减仓({direction})"
                
                line = f"{action} {display_coin}:"
                line += f" {prev['szi']:.4f} → {curr['szi']:.4f} (delta={delta_szi:+.4f})"
                line += f"\n     开仓价: {prev['entry_px']} → {curr['entry_px']}"
                line += f", 仓位价值={format_usd(curr['position_value'])}"
                
                if fill_info:
                    total_pnl = sum(d['total_closed_pnl'] for d in fill_info['dirs'].values())
                    if total_pnl != 0:
                        line += f", 已实现PnL={total_pnl:+.2f}"
                    line += f"\n     📝 {format_fills_summary(fill_info)}"
                
                sub_changes.append(line)
            
            # 2. 爆仓价变化（仅在 szi 未变化时单独显示）
            if abs(delta_szi) <= CHANGE_THRESHOLD and prev['liquidation_px'] != curr['liquidation_px']:
                sub_changes.append(
                    f"  ⚠️ {display_coin} 爆仓价变化: {prev['liquidation_px']} → {curr['liquidation_px']}"
                )
            
            # 3. 杠杆变化（仅在 szi 未变化时单独显示）
            if abs(delta_szi) <= CHANGE_THRESHOLD:
                if prev['leverage_value'] != curr['leverage_value'] or prev['leverage_type'] != curr['leverage_type']:
                    sub_changes.append(
                        f"  🔧 {display_coin} 杠杆变化: "
                        f"{prev['leverage_value']}x({prev['leverage_type']}) → "
                        f"{curr['leverage_value']}x({curr['leverage_type']})"
                    )
            
            changes.extend(sub_changes)
    
    return changes


# ===================== 飞书推送 =====================

def send_lark_message(content):
    """发送飞书消息"""
    payload = {
        "msg_type": "text",
        "content": {"text": content}
    }
    try:
        resp = requests.post(LARK_WEBHOOK, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get('code') == 0:
            logging.info("✅ 飞书消息推送成功")
        else:
            logging.warning(f"⚠️ 飞书推送返回异常: {result}")
    except requests.exceptions.RequestException as e:
        logging.error(f"飞书推送失败（网络错误）: {e}")
    except Exception as e:
        logging.error(f"飞书推送失败: {e}")
        logging.error(traceback.format_exc())


# ===================== 主循环 =====================

def check_once():
    """执行一轮检查，返回是否有变动"""
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
    logging.info(f"[{now_str}] 开始新一轮检查...")
    
    all_changes = []  # 本轮所有变动，聚合推送
    
    for cfg in ADDRESS_CONFIG:
        address = cfg['address']
        label = cfg['label']
        
        try:
            # 1. 获取最近的 fills
            start_time = last_fill_times.get(address, int(time.time() * 1000) - POLL_INTERVAL * 1000)
            
            fills = info.user_fills_by_time(address, start_time)
            
            if not isinstance(fills, list):
                fills = []
            
            if not fills:
                logging.debug(f"[{label}] 无新成交，跳过")
                continue
            
            # 更新 last_fill_time 为最新一条的时间戳 +1（避免重复）
            latest_time = max(f.get("time", 0) for f in fills)
            if latest_time > last_fill_times.get(address, 0):
                last_fill_times[address] = latest_time + 1
            
            logging.info(f"[{label}] 发现 {len(fills)} 条新成交，检查仓位...")
            
            # 2. 聚合 fills（按 coin + dir 分组）
            fills_agg = aggregate_fills(fills)
            
            if fills_agg:
                for coin, agg_data in fills_agg.items():
                    dc = agg_data['display_coin']
                    for dir_name, d in agg_data['dirs'].items():
                        logging.info(f"  [{label}] {dc} {dir_name}: {d['count']}笔, 量={d['total_sz']:.4f}, 均价={d['avg_px']:.2f}")
            
            # 3. 获取当前仓位
            state = info.user_state(address)
            curr_positions_list = simplify_positions(state)
            curr_positions_dict = positions_to_dict(curr_positions_list)
            
            # 账户信息
            margin_summary = state.get("marginSummary", {}) or state.get("crossMarginSummary", {})
            account_value = float(margin_summary.get("accountValue", 0))
            total_margin_used = float(margin_summary.get("totalMarginUsed", 0))
            snapshot_time = state.get("time", 0)
            
            # 4. 获取上一次快照并对比
            prev_snapshot = get_latest_snapshot(address)
            
            if prev_snapshot is None:
                # 第一次运行，只保存不推送
                save_snapshot(address, account_value, total_margin_used, curr_positions_list, snapshot_time)
                logging.info(f"[{label}] 初始仓位已保存（首次运行，不推送）")
                
                # 日志打印当前仓位
                for p in curr_positions_list:
                    direction = "多" if p['szi'] > 0 else "空"
                    logging.info(f"  [{label}] {p['display_coin']}: {direction} size={p['szi']:.4f}, "
                                 f"entry={p['entry_px']}, leverage={p['leverage_value']}x")
                continue
            
            prev_positions_dict = positions_to_dict(prev_snapshot['positions'])
            
            # 5. 对比变动
            changes = detect_changes(prev_positions_dict, curr_positions_dict, fills_agg)
            
            if changes:
                # 有变动 → 保存新快照
                save_snapshot(address, account_value, total_margin_used, curr_positions_list, snapshot_time)
                
                # 构建变动描述
                addr_short = f"{address[:6]}...{address[-4:]}"
                account_info = f"💰 账户价值: {format_usd(account_value)}, 已用保证金: {format_usd(total_margin_used)}"
                
                # 当前持仓概览
                pos_summary_parts = []
                for p in curr_positions_list:
                    direction = "多" if p['szi'] > 0 else "空"
                    pnl_sign = "+" if p['unrealized_pnl'] >= 0 else ""
                    roe = float(p['return_on_equity']) * 100
                    roe_sign = "+" if roe >= 0 else ""
                    pos_summary_parts.append(
                        f"  • {p['display_coin']} {direction} size={p['szi']:.4f} "
                        f"entry={p['entry_px']} "
                        f"uPnL={pnl_sign}{p['unrealized_pnl']:.2f}({roe_sign}{roe:.2f}%)"
                    )
                
                pos_summary = "\n".join(pos_summary_parts) if pos_summary_parts else "  （无持仓）"
                
                change_text = "\n".join(f"  {c}" for c in changes)
                
                coinglass_url = f"https://www.coinglass.com/zh/hyperliquid/{address}"
                change_block = (
                    f"📍 {label} ({addr_short})\n"
                    f"{account_info}\n"
                    f"\n"
                    f"📋 变动明细:\n"
                    f"{change_text}\n"
                    f"\n"
                    f"📊 当前持仓:\n"
                    f"{pos_summary}\n"
                    f"\n"
                    f"🔗 {coinglass_url}"
                )
                all_changes.append(change_block)
                
                logging.info(f"[{label}] 检测到 {len(changes)} 个变动")
                for c in changes:
                    logging.info(f"  {c}")
            else:
                # 有 fills 但仓位无变化（可能是监控币种之外的交易）
                # 仍然保存快照以更新时间
                save_snapshot(address, account_value, total_margin_used, curr_positions_list, snapshot_time)
                logging.info(f"[{label}] 有成交但监控仓位无变化，已更新快照")
        
        except Exception as e:
            logging.error(f"[{label}] 查询异常: {e}")
            logging.error(traceback.format_exc())
    
    # 6. 聚合推送
    if all_changes:
        beijing_now = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M')
        message = (
            f"🔔 Hyperliquid 仓位变动\n"
            f"⏰ {beijing_now}\n"
            f"\n"
            + "\n\n".join(all_changes)
        )
        send_lark_message(message)
        return True
    
    logging.info("本轮检查完成，无仓位变动")
    return False


def main_loop():
    """主监控循环"""
    logging.info("=" * 60)
    logging.info("Hyperliquid 聪明钱仓位监控服务启动")
    logging.info(f"监控地址数: {len(ADDRESS_CONFIG)}")
    for cfg in ADDRESS_CONFIG:
        logging.info(f"  - {cfg['label']}: {cfg['address'][:10]}...")
    logging.info(f"监控币种: {WATCH_COINS if WATCH_COINS else '全部'}")
    logging.info(f"轮询间隔: {POLL_INTERVAL}秒")
    logging.info(f"仓位变化阈值: {CHANGE_THRESHOLD}")
    logging.info(f"飞书Webhook: {LARK_WEBHOOK[:50]}...")
    logging.info("=" * 60)
    
    # 自动建表
    init_db()
    
    while True:
        try:
            check_once()
        except Exception as e:
            logging.error(f"本轮检查异常: {e}")
            logging.error(traceback.format_exc())
        
        logging.info(f"等待 {POLL_INTERVAL} 秒后进行下一轮检查...")
        time.sleep(POLL_INTERVAL)


# ===================== 入口 =====================
if __name__ == "__main__":
    # 支持 --once 参数，执行一次后退出（用于测试）
    if '--once' in sys.argv:
        logging.info("单次执行模式")
        check_once()
        logging.info("执行完成，退出")
    else:
        try:
            main_loop()
        except KeyboardInterrupt:
            logging.info("服务已停止")
        except Exception as e:
            logging.error(f"服务异常退出: {e}")
            logging.error(traceback.format_exc())

