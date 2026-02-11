# 文件名: webhook_server.py
# 建议放在 /opt/arkham-webhook/ 目录下

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import json
from datetime import datetime
import logging
from pathlib import Path

# ===================== 配置区域 =====================
LOG_FILE = "/home/ubuntu/okx_order/arkham/arkham-webhook.log"
PORT = 8001                          # 内部监听端口（Nginx 会代理到这里）
ALLOWED_IPS = []                     # 如果 Arkham 有固定 IP，可在这里限制（可选）
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
    event_type = payload.get("type", "unknown")
    tx_hash = payload.get("data", {}).get("hash", "no-hash")

    logger.info(f"[{timestamp}] Received event: {event_type} | tx: {tx_hash}")

    # 保存原始 payload（带时间戳）
    try:
        filename = PAYLOAD_DIR / f"payload_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved payload to {filename}")
    except Exception as e:
        logger.error(f"Failed to save payload: {e}")

    # 在这里写你自己的处理逻辑，例如：
    # send_to_telegram(payload)
    # save_to_database(payload)
    # trigger_another_service(payload)
    # ...

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