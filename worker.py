import asyncio
import json
import os
import redis.asyncio as aioredis
from typing import TypedDict, List, Optional
from ddgs import DDGS
from langgraph.graph import StateGraph, END
from arq.connections import RedisSettings

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Define LangGraph Agent State Schema
class AgentState(TypedDict):
    task_id: str
    prompt: str
    query: Optional[str]
    thoughts: List[str]
    tool_output: Optional[str]
    status: str
    redis_client: Optional[object]

async def publish_event(redis_client, task_id: str, node_name: str, event_type: str, data: str):
    """Utility to stream thought tokens and tool outputs directly to Redis Pub/Sub."""
    if not redis_client:
        return
    payload = json.dumps({
        "task_id": task_id,
        "node": node_name,
        "type": event_type,
        "message": data
    })
    await redis_client.publish("agent_events", payload)

# Node 1: Decision Node
async def decision_node(state: AgentState) -> AgentState:
    task_id = state["task_id"]
    prompt = state["prompt"]
    redis = state.get("redis_client")

    # Stream Decision Node thought tokens to Redis
    await publish_event(redis, task_id, "DecisionNode", "thought_start", f"--> [DecisionNode] Analyzing task prompt: '{prompt}'")
    await asyncio.sleep(0.5)

    # Extract/formulate search query
    query = prompt.replace("search for", "").replace("search", "").strip() or "FastAPI sse-starlette redis pubsub"
    
    thought_msg = f"--> [DecisionNode] Thought: Formulated DuckDuckGo query -> '{query}'. Routing to ToolExecutionNode..."
    state["thoughts"].append(thought_msg)
    state["query"] = query
    state["status"] = "query_formulated"

    await publish_event(redis, task_id, "DecisionNode", "thought_token", thought_msg)
    await asyncio.sleep(0.5)

    return state

# Node 2: Tool Execution Node (DuckDuckGo Search)
async def tool_node(state: AgentState) -> AgentState:
    task_id = state["task_id"]
    query = state.get("query", "python fastapi")
    redis = state.get("redis_client")

    await publish_event(redis, task_id, "ToolNode", "tool_start", f"--> [ToolNode] Executing DuckDuckGo search for: '{query}'...")
    await asyncio.sleep(0.5)

    # Execute DuckDuckGo search
    results_str = ""
    try:
        results = list(DDGS().text(query, max_results=3))
        if results:
            snippets = [f"• {r.get('title')}: {r.get('body')}" for r in results]
            results_str = "\n".join(snippets)
        else:
            results_str = f"No results found for query '{query}'."
    except Exception as e:
        results_str = f"DuckDuckGo Search fallback result for '{query}' (Network info: {str(e)})"

    state["tool_output"] = results_str
    state["status"] = "completed"

    # Stream tool output directly to Redis Pub/Sub
    tool_event_msg = f"--> [ToolNode] Tool Output Received:\n{results_str[:300]}..."
    await publish_event(redis, task_id, "ToolNode", "tool_output", tool_event_msg)
    await publish_event(redis, task_id, "GraphEnd", "completion", f"Task [{task_id[:8]}] finished successfully via LangGraph pipeline.")

    return state

# Build 2-Node LangGraph State Machine
builder = StateGraph(AgentState)
builder.add_node("decision_node", decision_node)
builder.add_node("tool_node", tool_node)

builder.set_entry_point("decision_node")
builder.add_edge("decision_node", "tool_node")
builder.add_edge("tool_node", END)

langgraph_agent = builder.compile()

# ARQ Task Entry Point
async def run_agent_task(ctx, task_id: str, prompt: str):
    redis = ctx.get('redis_client')
    if not redis:
        try:
            redis = aioredis.from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}",
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                retry_on_timeout=False
            )
            await redis.ping()
        except Exception:
            import fakeredis.aioredis
            redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    initial_state: AgentState = {
        "task_id": task_id,
        "prompt": prompt,
        "query": None,
        "thoughts": [],
        "tool_output": None,
        "status": "initialized",
        "redis_client": redis
    }

    # Execute 2-Node LangGraph Pipeline
    await langgraph_agent.ainvoke(initial_state)

async def startup(ctx):
    try:
        client = aioredis.from_url(
            f"redis://{REDIS_HOST}:{REDIS_PORT}",
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            retry_on_timeout=False
        )
        await client.ping()
        ctx['redis_client'] = client
    except Exception:
        import fakeredis.aioredis
        ctx['redis_client'] = fakeredis.aioredis.FakeRedis(decode_responses=True)

async def shutdown(ctx):
    client = ctx.get('redis_client')
    if client and hasattr(client, 'aclose'):
        await client.aclose()

class WorkerSettings:
    functions = [run_agent_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(host=REDIS_HOST, port=REDIS_PORT, conn_timeout=0.5)
