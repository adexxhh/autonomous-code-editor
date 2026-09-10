import pytest
import uuid
import fakeredis.aioredis
from pydantic import ValidationError
from worker import run_agent_pipeline, SearchToolInput, AgentOutput

@pytest.fixture
def mock_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)

@pytest.mark.asyncio
async def test_eval_case1_ambiguous_prompt_with_symbols(mock_redis):
    """
    Test Case 1: Ambiguous prompt with leading/trailing whitespace & special punctuation.
    Inputs: "  ??? search for FastAPI SSE best practices !!! "
    """
    task_id = str(uuid.uuid4())
    prompt = "  ??? search for FastAPI SSE best practices !!! "
    
    result: AgentOutput = await run_agent_pipeline(task_id, prompt, redis_client=mock_redis)

    # 1. Assert correct tool schema selection & validation via Pydantic
    assert isinstance(result.tool_input, SearchToolInput)
    assert len(result.tool_input.query) > 0
    assert result.tool_input.query == "FastAPI SSE best practices"
    
    # 2. Assert step count does not exceed 4 execution steps
    assert result.steps_count <= 4

    # 3. Assert structured JSON matches AgentOutput schema without schema hallucinations
    assert isinstance(result, AgentOutput)
    validated = AgentOutput.model_validate(result.model_dump())
    assert validated.status == "completed"

@pytest.mark.asyncio
async def test_eval_case2_multi_intent_code_snippet(mock_redis):
    """
    Test Case 2: Multi-intent prompt containing embedded code snippet.
    Input: "How to fix async def stream(): yield 123 in FastAPI?"
    """
    task_id = str(uuid.uuid4())
    prompt = "How to fix async def stream(): yield 123 in FastAPI?"
    
    result: AgentOutput = await run_agent_pipeline(task_id, prompt, redis_client=mock_redis)

    # 1. Assert tool schema choice via Pydantic
    assert isinstance(result.tool_input, SearchToolInput)
    assert "async def stream()" in result.tool_input.query

    # 2. Assert max 4 execution steps
    assert result.steps_count <= 4

    # 3. Assert JSON matches schema without hallucinations
    assert isinstance(result, AgentOutput)
    validated = AgentOutput.model_validate(result.model_dump())
    assert validated.task_id == task_id

@pytest.mark.asyncio
async def test_eval_case3_minimal_single_word(mock_redis):
    """
    Test Case 3: Minimal single-word prompt edge case.
    Input: "Redis"
    """
    task_id = str(uuid.uuid4())
    prompt = "Redis"
    
    result: AgentOutput = await run_agent_pipeline(task_id, prompt, redis_client=mock_redis)

    # 1. Assert tool schema choice via Pydantic
    assert isinstance(result.tool_input, SearchToolInput)
    assert result.tool_input.query == "Redis"

    # 2. Assert max 4 execution steps
    assert result.steps_count <= 4

    # 3. Assert JSON matches schema without hallucinations
    assert isinstance(result, AgentOutput)
    AgentOutput.model_validate(result.model_dump())

@pytest.mark.asyncio
async def test_eval_case4_special_sql_json_characters(mock_redis):
    """
    Test Case 4: Edge-case prompt containing JSON/SQL-like characters.
    Input: "{ 'query': 'DB connection string & select * from users;' }"
    """
    task_id = str(uuid.uuid4())
    prompt = "{ 'query': 'DB connection string & select * from users;' }"
    
    result: AgentOutput = await run_agent_pipeline(task_id, prompt, redis_client=mock_redis)

    # 1. Assert tool schema choice via Pydantic
    assert isinstance(result.tool_input, SearchToolInput)
    assert "DB connection string" in result.tool_input.query

    # 2. Assert max 4 execution steps
    assert result.steps_count <= 4

    # 3. Assert JSON matches schema without hallucinations
    assert isinstance(result, AgentOutput)
    AgentOutput.model_validate(result.model_dump())

@pytest.mark.asyncio
async def test_eval_case5_empty_whitespace_fallback(mock_redis):
    """
    Test Case 5: Empty / whitespace-only fallback edge case.
    Input: "   "
    """
    task_id = str(uuid.uuid4())
    prompt = "   "
    
    result: AgentOutput = await run_agent_pipeline(task_id, prompt, redis_client=mock_redis)

    # 1. Assert fallback query chooses valid SearchToolInput schema
    assert isinstance(result.tool_input, SearchToolInput)
    assert result.tool_input.query == "FastAPI sse-starlette redis pubsub"

    # 2. Assert max 4 execution steps
    assert result.steps_count <= 4

    # 3. Assert JSON matches schema without hallucinations
    assert isinstance(result, AgentOutput)
    validated = AgentOutput.model_validate(result.model_dump())
    assert validated.steps_count <= 4
