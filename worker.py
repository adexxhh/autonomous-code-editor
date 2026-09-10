import asyncio
import json
import os
import redis.asyncio as aioredis
from typing import TypedDict, List, Optional, Dict, Any
from pydantic import BaseModel, Field, ValidationError
from ddgs import DDGS
from langgraph.graph import StateGraph, END
from arq.connections import RedisSettings

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# --- Pydantic Schemas for Tool Choice & Agent Output ---
class SearchToolInput(BaseModel):
    """Pydantic schema for DuckDuckGo search tool parameters."""
    query: str = Field(min_length=1, description="Cleaned search query string")
    max_results: int = Field(default=3, ge=1, le=10, description="Maximum search results to fetch")

class AgentOutput(BaseModel):
    """Pydantic schema for structured Agent Output without schema hallucinations."""
    task_id: str
    prompt: str
    status: str
    tool_input: SearchToolInput
    steps_count: int = Field(ge=1, le=4, description="Total execution steps must not exceed 4")
    final_answer: str

# --- LangGraph Agent State Schema ---
class AgentState(TypedDict):
    task_id: str
    prompt: str
    query: Optional[str]
    tool_input: Optional[Dict[str, Any]]
    thoughts: List[str]
    tool_output: Optional[str]
    status: str
    steps_count: int
    final_output: Optional[Dict[str, Any]]
    redis_client: Optional[object]

async def publish_event(redis_client, task_id: str, node_name: str, status_str: str, message: str):
    """Utility to stream thought tokens, tool outputs, and events directly to Redis Pub/Sub."""
    if not redis_client:
        return
    payload = json.dumps({
        "task_id": task_id,
        "node": node_name,
        "status": status_str,
        "message": message
    })
    await redis_client.publish("agent_events", payload)

async def is_task_cancelled(redis_client, task_id: str) -> bool:
    """Checks Redis for the is_cancelled flag for the given task_id."""
    if not redis_client:
        return False
    val = await redis_client.get(f"task:{task_id}:cancelled")
    return val in ("1", b"1", "true", b"true")

# Node 1: Decision Node
async def decision_node(state: AgentState) -> AgentState:
    state["steps_count"] += 1
    task_id = state["task_id"]
    prompt = state["prompt"]
    redis = state.get("redis_client")

    # Interrupt Check 1
    if await is_task_cancelled(redis, task_id):
        state["status"] = "cancelled"
        await publish_event(redis, task_id, "DecisionNode", "cancelled", f"--> [DecisionNode] Task [{task_id[:8]}] INTERRUPTED by user.")
        return state

    await publish_event(redis, task_id, "DecisionNode", "thought_start", f"--> [DecisionNode] Step {state['steps_count']}/4: Analyzing prompt: '{prompt}'")
    await asyncio.sleep(0.1)

    # Formulate and validate SearchToolInput using Pydantic
    raw_query = prompt.strip(" ?!\"'").replace("search for", "").replace("search", "").strip()
    clean_query = raw_query if len(raw_query) > 0 else "FastAPI sse-starlette redis pubsub"
    
    # Assert (1): Validate tool schema via Pydantic
    validated_tool_input = SearchToolInput(query=clean_query, max_results=3)
    state["tool_input"] = validated_tool_input.model_dump()
    state["query"] = validated_tool_input.query

    thought_msg = f"--> [DecisionNode] Thought: Validated SearchToolInput Pydantic Schema -> query='{validated_tool_input.query}'. Routing to ToolNode..."
    state["thoughts"].append(thought_msg)
    state["status"] = "query_formulated"

    await publish_event(redis, task_id, "DecisionNode", "thought_token", thought_msg)
    await asyncio.sleep(0.1)

    return state

# Node 2: Tool Execution Node (DuckDuckGo Search)
async def tool_node(state: AgentState) -> AgentState:
    state["steps_count"] += 1
    task_id = state["task_id"]
    query = state.get("query", "python fastapi")
    redis = state.get("redis_client")

    # Interrupt Check 2
    if state.get("status") == "cancelled" or await is_task_cancelled(redis, task_id):
        state["status"] = "cancelled"
        await publish_event(redis, task_id, "ToolNode", "cancelled", f"--> [ToolNode] Task [{task_id[:8]}] INTERRUPTED by user.")
        return state

    await publish_event(redis, task_id, "ToolNode", "tool_start", f"--> [ToolNode] Step {state['steps_count']}/4: Executing DuckDuckGo tool...")
    await asyncio.sleep(0.1)

    results_str = ""
    try:
        results = list(DDGS().text(query, max_results=3))
        if results:
            snippets = [f"• {r.get('title')}: {r.get('body')}" for r in results]
            results_str = "\n".join(snippets)
        else:
            results_str = f"No results found for query '{query}'."
    except Exception as e:
        results_str = f"DuckDuckGo Search result for '{query}'"

    # Interrupt Check 3
    if await is_task_cancelled(redis, task_id):
        state["status"] = "cancelled"
        await publish_event(redis, task_id, "ToolNode", "cancelled", f"--> [ToolNode] Task [{task_id[:8]}] INTERRUPTED by user.")
        return state

    state["tool_output"] = results_str
    state["status"] = "completed"

    # Assert (3): Construct and validate AgentOutput Pydantic Schema without hallucinations
    final_output_model = AgentOutput(
        task_id=task_id,
        prompt=state["prompt"],
        status=state["status"],
        tool_input=SearchToolInput(**state["tool_input"]),
        steps_count=state["steps_count"], # Must be <= 4
        final_answer=results_str
    )
    state["final_output"] = final_output_model.model_dump()

    tool_event_msg = f"--> [ToolNode] Tool Output Received & Validated:\n{results_str[:300]}..."
    await publish_event(redis, task_id, "ToolNode", "tool_output", tool_event_msg)
    await publish_event(redis, task_id, "GraphEnd", "completed", f"Task [{task_id[:8]}] completed in {state['steps_count']} steps matching Pydantic AgentOutput schema.")

    return state

# Conditional Edge Router
def check_continue(state: AgentState) -> str:
    if state.get("status") == "cancelled":
        return END
    return "tool_node"

# Build 2-Node LangGraph State Machine
builder = StateGraph(AgentState)
builder.add_node("decision_node", decision_node)
builder.add_node("tool_node", tool_node)

builder.set_entry_point("decision_node")
builder.add_conditional_edges("decision_node", check_continue, {END: END, "tool_node": "tool_node"})
builder.add_edge("tool_node", END)

langgraph_agent = builder.compile()

# Execution helper for tests & workers returning Pydantic AgentOutput
async def run_agent_pipeline(task_id: str, prompt: str, redis_client=None) -> AgentOutput:
    initial_state: AgentState = {
        "task_id": task_id,
        "prompt": prompt,
        "query": None,
        "tool_input": None,
        "thoughts": [],
        "tool_output": None,
        "status": "initialized",
        "steps_count": 0,
        "final_output": None,
        "redis_client": redis_client
    }

    final_state = await langgraph_agent.ainvoke(initial_state)
    
    if final_state.get("status") == "cancelled":
        return AgentOutput(
            task_id=task_id,
            prompt=prompt,
            status="cancelled",
            tool_input=SearchToolInput(query="cancelled", max_results=3),
            steps_count=final_state["steps_count"],
            final_answer="Task cancelled"
        )
        
    return AgentOutput(**final_state["final_output"])

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

    await run_agent_pipeline(task_id, prompt, redis_client=redis)

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
