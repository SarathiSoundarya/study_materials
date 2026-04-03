import asyncio, hmac, hashlib, json, time, logging
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException, logger
from fastapi.responses import JSONResponse, PlainTextResponse
from cachetools import TTLCache
from pydantic import BaseModel, Field

# =========================
# CONFIG
# =========================
SECRET = "dev-shared-secret"
MAX_QUEUE_SIZE = 100
WORKER_CONCURRENCY = 5
MAX_RETRIES = 3
BASE_BACKOFF = 250  # ms
IDEM_TTL = 3600

# =========================
# SETUP
# =========================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = FastAPI(title="Webhook Queue System")

queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
dead_letter_queue = []
seen_ids = TTLCache(maxsize=1000, ttl=IDEM_TTL)

metrics = {
    "accepted": 0,
    "rejected": 0,
    "enqueued": 0,
    "dequeued": 0,
    "processed_ok": 0,
    "processed_failed": 0,
    "dead_letter": 0,
    "inflight": 0,
    "queue_size_peak": 0,
    "last_error": ""
}

# =========================
# MODEL
# =========================
class WebhookPayload(BaseModel):
    event_id: str
    event_type: str
    data: Dict[str, Any]
    ts: int = Field(default_factory=lambda: int(time.time()))

# =========================
# SECURITY
# =========================
def verify_signature(payload: bytes, signature_header: str) -> None:
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=400, detail="Invalid signature format")

    signature = signature_header.split("=", 1)[1]
    computed = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

# =========================
# IDEMPOTENCY
# =========================
def ensure_idempotent(event_id: str):
    if event_id in seen_ids:
        raise HTTPException(status_code=409, detail="Duplicate request")
    seen_ids[event_id] = True

# =========================
# PROCESSING LOGIC
# =========================
async def process_task(task: dict):
    # Simulate failure for testing
    if task["event_type"] == "fail":
        raise Exception("Simulated failure")

    await asyncio.sleep(0.5)  # simulate work

# =========================
# WORKER
# =========================
async def worker(worker_id: int):
    while True:
        task = await queue.get()
        metrics["dequeued"] += 1
        metrics["inflight"] += 1

        retries = 0

        while retries <= MAX_RETRIES:
            try:
                await process_task(task)
                metrics["processed_ok"] += 1
                break

            except Exception as e:
                retries += 1
                metrics["last_error"] = str(e)

                if retries > MAX_RETRIES:
                    dead_letter_queue.append(task)
                    metrics["dead_letter"] += 1
                    metrics["processed_failed"] += 1
                    break

                backoff = (BASE_BACKOFF * (2 ** (retries - 1))) / 1000
                await asyncio.sleep(backoff)

        metrics["inflight"] -= 1
        queue.task_done()

# =========================
# STARTUP
# =========================
@app.on_event("startup")
async def startup():
    for i in range(WORKER_CONCURRENCY):
        asyncio.create_task(worker(i))
    logger.info(f"Started {WORKER_CONCURRENCY} workers")
#this will start the worker tasks in the background when the FastAPI app starts. Each worker will continuously listen for new tasks in the queue and process them as they come in.

# =========================
# WEBHOOK ENDPOINT
# =========================
@app.post("/webhook")
async def webhook(request: Request):
    payload_bytes = await request.body()

    # Signature
    signature = request.headers.get("X-Signature")
    logger.info(f"Received webhook with signature: {signature} and payload: {payload_bytes.decode()}")
    verify_signature(payload_bytes, signature)

    # Parse
    payload_dict = json.loads(payload_bytes)
    payload = WebhookPayload(**payload_dict)

    # Idempotency
    ensure_idempotent(payload.event_id)

    metrics["accepted"] += 1

    # Queue full check
    if queue.full():
        metrics["rejected"] += 1
        raise HTTPException(status_code=429, detail="Queue full")

    await queue.put(payload_dict)
    metrics["enqueued"] += 1

    metrics["queue_size_peak"] = max(metrics["queue_size_peak"], queue.qsize())

    return JSONResponse({"status": "accepted"})

# =========================
# DEBUG ENDPOINTS
# =========================
@app.get("/metrics")
async def get_metrics():
    return metrics

@app.get("/dead-letter")
async def get_dead_letter():
    return {"dead_letter_queue": dead_letter_queue}

@app.get("/health")
async def health():
    return PlainTextResponse("OK")



# Client
#   ↓
# Webhook endpoint
#   ↓
# [Signature check]
#   ↓
# [Validation]
#   ↓
# [Idempotency check]
#   ↓
# [Queue full?]
#   ↓
# Enqueue → Respond 200 ✅
#   ↓
# ──────── Background ────────
#   ↓
# Worker picks task
#   ↓
# Process task
#   ↓
#    ├── Success → processed_ok
#    └── Failure
#          ↓
#       Retry (backoff)
#          ↓
#       Max retries?
#          ├── No → retry
#          └── Yes → dead_letter

# Exactly — you’ve got the right intuition 👍

# Once the webhook returns, process_task cannot send anything back to the client.
# So its job is to perform side effects in the background.


# What you learned about webhooks (short & crisp)
# A webhook = event-driven POST request sent by another system
# You don’t call it, you just expose an endpoint and receive it
# It should be:
# 🔒 Secure → signature verification (HMAC)
# 🔁 Idempotent → avoid duplicate processing
# ⚡ Fast → respond quickly (don’t block)
# Heavy work is NOT done in the request, but in background (queue + workers)
# 🎯 What webhooks are mainly used for
# Payments (e.g., payment success)
# Notifications (user signup, events)
# Integrations between systems
# Triggering async workflows

# 👉 In short:

# “Notify another system instantly when something happens”, so when we make payment, webhook is called and then database is updated, email is sent etc. It’s a way to connect different systems in real-time without polling.


#What happens if DB update / email fails?

# In your system:

# 👉 It’s handled by retry + backoff + dead-letter queue
#What is Dead Letter Queue?

#   A dead-letter queue is a place where failed tasks go after max retries. It allows you to inspect and handle failures later without losing data.


#Webhook = the /webhook API endpoint that receives events, validates them, and hands them off for async processing Real-world mapping. In your program, the webhook is the /webhook endpoint that receives external events and pushes them into your system.

# Imagine:

# Stripe sends payment success → calls your /webhook
# Your webhook:
# verifies it's Stripe
# queues the task
# Worker:
# updates DB
# sends email