# 文件名: webhook_server.py
# 建议放在 /opt/arkham-webhook/ 目录下

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import json
import requests
from datetime import datetime
import logging
from pathlib import Path

# ===================== 配置区域 =====================
LOG_FILE = "/home/ubuntu/okx_order/arkham/arkham-webhook.log"
PORT = 8001                          # 内部监听端口（Nginx 会代理到这里）
ALLOWED_IPS = []                     # 如果 Arkham 有固定 IP，可在这里限制（可选）

# 飞书Webhook地址（Arkham链上转账提醒）
LARK_WEBHOOK_URL = "https://open.larksuite.com/open-apis/bot/v2/hook/79a83817-a871-4471-b72f-3742d0a3baa0"

# Arkham Explorer 实体地址前缀
ARKHAM_ENTITY_URL = "https://intel.arkm.com/explorer/entity/"
# ====================================================

app = FastAPI(title="Arkham Webhook Receiver")

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 保存原始 payload 的目录（可选）
PAYLOAD_DIR = Path("/home/ubuntu/okx_order/arkham/payloads")


def format_usd_display(usd_value):
    """格式化USD价值显示"""
    if usd_value >= 100000000:  # 大于1亿
        return f"{usd_value / 100000000:.2f} 亿美元"
    elif usd_value >= 10000:  # 大于1万
        return f"{usd_value / 10000:.2f} 万美元"
    else:
        return f"{usd_value:,.2f} 美元"


def format_amount_display(amount):
    """格式化数量显示"""
    if amount >= 10000:
        return f"{amount:,.2f}"
    else:
        return f"{amount:,.4f}"


# 链名称映射（美化显示）
CHAIN_DISPLAY_MAP = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "tron": "TRX",
    "polygon": "MATIC",
    "avalanche": "AVAX",
    "arbitrum": "ARB",
    "optimism": "OP",
    "base": "BASE",
    "bsc": "BNB",
}


def send_lark_notification(payload):
    """
    解析 Arkham webhook 数据并推送到飞书
    
    Args:
        payload: Arkham webhook 原始数据
    """
    try:
        transfer = payload.get("transfer", {})
        alert_name = payload.get("alertName", "未知告警")
        
        if not transfer:
            logger.warning("payload 中没有 transfer 数据，跳过推送")
            return
        
        # ====== 解析发送方 ======
        from_address_info = transfer.get("fromAddress", {})
        from_entity = from_address_info.get("arkhamEntity", {})
        from_label = from_address_info.get("arkhamLabel", {})
        
        from_entity_name = from_entity.get("name", "未知实体")
        from_entity_id = from_entity.get("id", "")
        from_label_name = from_label.get("name", "")
        from_address = from_address_info.get("address", "未知地址")
        
        # 发送方显示：实体名 + 标签名（如果有）
        if from_label_name:
            from_display = f"{from_entity_name} ({from_label_name})"
        else:
            from_display = from_entity_name
        
        # ====== 解析接收方（取第一个主要接收地址） ======
        to_addresses = transfer.get("toAddresses", [])
        to_entity_name = "未知实体"
        to_entity_id = ""
        to_label_name = ""
        to_address = "未知地址"
        
        # 找到价值最大的接收地址作为主要接收方
        max_value = 0
        for to_addr_info in to_addresses:
            addr_value = to_addr_info.get("value", 0)
            if addr_value > max_value:
                max_value = addr_value
                addr_detail = to_addr_info.get("address", {})
                to_entity = addr_detail.get("arkhamEntity", {})
                to_label = addr_detail.get("arkhamLabel", {})
                to_entity_name = to_entity.get("name", "") if to_entity else ""
                to_entity_id = to_entity.get("id", "") if to_entity else ""
                to_label_name = to_label.get("name", "") if to_label else ""
                to_address = addr_detail.get("address", "未知地址")
        
        # 接收方显示
        if to_entity_name and to_label_name:
            to_display = f"{to_entity_name} ({to_label_name})"
        elif to_entity_name:
            to_display = to_entity_name
        elif to_label_name:
            to_display = to_label_name
        else:
            to_display = f"{to_address[:8]}...{to_address[-6:]}" if len(to_address) > 14 else to_address
        
        # ====== 解析其他信息 ======
        chain = transfer.get("chain", "unknown")
        chain_display = CHAIN_DISPLAY_MAP.get(chain, chain.upper())
        to_value = transfer.get("toValue", transfer.get("unitValue", 0))
        historical_usd = transfer.get("historicalUSD", 0)
        block_timestamp = transfer.get("blockTimestamp", "")
        
        # 格式化时间
        if block_timestamp:
            try:
                dt = datetime.fromisoformat(block_timestamp.replace("Z", "+00:00"))
                time_display = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                time_display = block_timestamp
        else:
            time_display = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # 格式化金额
        amount_display = format_amount_display(to_value)
        usd_display = format_usd_display(historical_usd)
        
        # ====== 构建消息 ======
        content_lines = [
            f"🐋 链上大额转账提醒",
            "",
            f"⏰ 时间: {time_display}",
            "",
            f"📤 发送方: {from_display}",
            f"📥 接收方: {to_display}",
            "",
            f"💰 链: {chain_display}",
            f"📦 数量: {amount_display} {chain_display}",
            f"💵 价值: {usd_display}",
        ]
        
        # 添加 Arkham 实体链接
        content_lines.append("")
        if from_entity_id:
            content_lines.append(f"🔗 发送方: {ARKHAM_ENTITY_URL}{from_entity_id}")
        if to_entity_id:
            content_lines.append(f"🔗 接收方: {ARKHAM_ENTITY_URL}{to_entity_id}")
        
        content_text = "\n".join(content_lines)
        
        # 发送飞书消息
        lark_payload = {
            "msg_type": "text",
            "content": {
                "text": content_text
            }
        }
        
        response = requests.post(LARK_WEBHOOK_URL, json=lark_payload, timeout=5)
        response.raise_for_status()
        
        result = response.json()
        if result.get('code') == 0:
            logger.info(f"✅ 飞书推送成功: {from_entity_name} -> {to_entity_name}, {amount_display} {chain_display}, {usd_display}")
        else:
            logger.warning(f"⚠️ 飞书推送返回异常: {result}")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"飞书推送失败（网络错误）: {e}")
    except Exception as e:
        logger.error(f"飞书推送失败: {e}")
        import traceback
        logger.error(f"异常详情: {traceback.format_exc()}")


@app.post("/webhook/arkham")
async def receive_arkham_webhook(request: Request):
    # 可选：检查来源 IP（如果 Arkham 提供固定 IP 段）
    # client_ip = request.client.host
    # if ALLOWED_IPS and client_ip not in ALLOWED_IPS:
    #     raise HTTPException(status_code=403, detail="IP not allowed")

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raw_body = await request.body()
        logger.error(f"Invalid JSON received: {raw_body.decode(errors='replace')}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 记录基本信息
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    alert_name = payload.get("alertName", "unknown")
    txid = payload.get("transfer", {}).get("txid", "no-hash")

    logger.info(f"[{timestamp}] Received alert: {alert_name} | tx: {txid}")

    # 保存原始 payload（带时间戳）
    try:
        PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = PAYLOAD_DIR / f"payload_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved payload to {filename}")
    except Exception as e:
        logger.error(f"Failed to save payload: {e}")

    # 推送到飞书
    send_lark_notification(payload)

    # Arkham 要求快速返回 200
    return JSONResponse(
        status_code=200,
        content={"status": "received"}
    )

@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "webhook_server:app",
        host="127.0.0.1",
        port=PORT,
        log_level="info",
        workers=2
    )