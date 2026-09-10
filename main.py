import asyncio
import uuid
import json
from fastapi import FastAPI, Body, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from arq import create_pool
from arq.connections import RedisSettings
import redis.asyncio as aioredis
from sse_starlette.sse import EventSourceResponse
from config import settings

app = FastAPI(title="Autonomous Code Editor API", version="1.0.0")

redis_client = None
arq_pool = None

async def get_redis_client():
    try:
        client = aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_CONNECT_TIMEOUT,
            retry_on_timeout=False
        )
        await client.ping()
        print(f"Connected to live Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
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
        arq_pool = await create_pool(RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT, conn_timeout=settings.REDIS_CONNECT_TIMEOUT))
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
        <input type="text" id="prompt" placeholder="Enter prompt (e.g. Search for FastAPI SSE)..." required style="padding:0.6rem; width:60%;">
        <button type="submit" style="padding:0.6rem 1.2rem;">Run Agent Task</button>
    </form>
    
    <div id="active-tasks" style="margin-top:1rem;"></div>

    <h3>Task Queue & Worker Status (HTTP 202 Stream):</h3>
    <div id="log" style="background:#1e1e1e; color:#00ff66; font-family:monospace; padding:1rem; border-radius:6px; min-height:220px;"></div>

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
            const taskId = data.task_id;
            
            document.getElementById('log').innerHTML += '<div style="color:#e6db74;">--> HTTP 202 Enqueued: ' + taskId + '</div>';
            
            const tasksDiv = document.getElementById('active-tasks');
            tasksDiv.innerHTML = `<button onclick="cancelTask('${taskId}')" style="background:#ff4d4d; color:white; padding:0.5rem 1rem; border:none; border-radius:4px; cursor:pointer;">Cancel Current Task (${taskId.slice(0,8)})</button>`;
            input.value = '';
        }

        async function cancelTask(taskId) {
            const res = await fetch('/agent/' + taskId + '/cancel', { method: 'POST' });
            const data = await res.json();
            document.getElementById('log').innerHTML += '<div style="color:#ff6666;">--> Cancel Requested: ' + JSON.stringify(data) + '</div>';
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
        from worker import run_agent_task
        asyncio.create_task(run_agent_task({'redis_client': redis_client}, task_id, prompt))
        
    return {
        "status": "queued",
        "task_id": task_id,
        "message": f"Task enqueued for processing: {prompt}"
    }

@app.post("/agent/{task_id}/cancel")
async def cancel_agent_task(task_id: str):
    """
    Registers an is_cancelled flag in Redis for the given task_id.
    The LangGraph worker checks this flag prior to node/tool execution and halts cleanly.
    """
    await redis_client.set(f"task:{task_id}:cancelled", "1", ex=3600)
    return {
        "status": "cancellation_requested",
        "task_id": task_id,
        "message": f"Cancellation request registered for task {task_id}"
    }

async def event_generator(request: Request):
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("agent_events")
    try:
        while True:
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
        await pubsub.unsubscribe("agent_events")
        print("Unsubscribed from 'agent_events' Redis channel.")

@app.get("/stream")
async def stream(request: Request):
    return EventSourceResponse(event_generator(request))
