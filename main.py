import asyncio
import os
import uuid
import json
from fastapi import FastAPI, Body, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from arq import create_pool
from arq.connections import RedisSettings
import redis.asyncio as aioredis
from sse_starlette.sse import EventSourceResponse

app = FastAPI()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

redis_client = None
arq_pool = None

async def get_redis_client():
    try:
        client = aioredis.from_url(
            f"redis://{REDIS_HOST}:{REDIS_PORT}",
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            retry_on_timeout=False
        )
        await client.ping()
        print(f"Connected to live Redis at {REDIS_HOST}:{REDIS_PORT}")
        return client
    except Exception:
        print("Live Redis server not reachable, using in-memory FakeRedis for local dev/testing.")
        import fakeredis.aioredis
        return fakeredis.aioredis.FakeRedis(decode_responses=True)

@app.on_event("startup")
async def startup_event():
    global redis_client, arq_pool
    redis_client = await get_redis_client()
    try:
        arq_pool = await create_pool(RedisSettings(host=REDIS_HOST, port=REDIS_PORT, conn_timeout=0.5))
    except Exception:
        print("ARQ Redis pool initialization bypassed (using async background task runner).")

@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html>
<head><title>Autonomous Agent Task Worker</title></head>
<body style="font-family:sans-serif; padding:2rem; max-width:800px; margin:0 auto;">
    <h2>Autonomous Code Editor Task Dispatcher</h2>
    <form onsubmit="runAgent(event)">
        <input type="text" id="prompt" placeholder="Enter prompt (e.g. Refactor main.py)..." required style="padding:0.6rem; width:70%;">
        <button type="submit" style="padding:0.6rem 1.2rem;">Run Agent Task</button>
    </form>
    
    <h3>Task Queue & Worker Status (HTTP 202 Stream):</h3>
    <div id="log" style="background:#1e1e1e; color:#00ff66; font-family:monospace; padding:1rem; border-radius:6px; min-height:200px;"></div>

    <script>
        const evtSource = new EventSource('/stream');
        evtSource.onmessage = e => {
            const log = document.getElementById('log');
            log.innerHTML += '<div>' + e.data + '</div>';
            log.scrollTop = log.scrollHeight;
        };

        async function runAgent(e) {
            e.preventDefault();
            const input = document.getElementById('prompt');
            const res = await fetch('/agent/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({prompt: input.value})
            });
            const data = await res.json();
            document.getElementById('log').innerHTML += '<div style="color:#e6db74;">--> HTTP ' + res.status + ' Accepted: Task Enqueued ' + JSON.stringify(data) + '</div>';
            input.value = '';
        }
    </script>
</body>
</html>"""

@app.post("/agent/run", status_code=status.HTTP_202_ACCEPTED)
async def run_agent(payload: dict = Body(...)):
    """
    Submits an agent task to the heavy compute worker queue.
    Returns HTTP 202 Accepted immediately without blocking the web server thread.
    """
    prompt = payload.get("prompt", "Default task")
    task_id = str(uuid.uuid4())
    
    if arq_pool:
        await arq_pool.enqueue_job('run_agent_task', task_id, prompt)
    else:
        # Fallback in-process async execution for environments without external ARQ worker running
        from worker import run_agent_task
        asyncio.create_task(run_agent_task({'redis_client': redis_client}, task_id, prompt))
        
    return {
        "status": "queued",
        "task_id": task_id,
        "message": f"Task enqueued for processing: {prompt}"
    }

async def event_generator(request: Request):
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("agent_events")
    try:
        while True:
            # 1. CLIENT DISCONNECT CHECK:
            # Periodically poll request.is_disconnected() to detect if browser closed connection
            if await request.is_disconnected():
                print("Client disconnected from /stream. Cleaning up SSE stream generator...")
                break
                
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                yield {"data": message["data"]}
                
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        print("SSE stream coroutine cancelled due to client disconnect.")
    finally:
        # 2. CLEANUP ON DISCONNECT: Unsubscribe Pub/Sub channel to prevent memory/socket leaks
        await pubsub.unsubscribe("agent_events")
        print("Unsubscribed from 'agent_events' Redis channel.")

@app.get("/stream")
async def stream(request: Request):
    return EventSourceResponse(event_generator(request))
