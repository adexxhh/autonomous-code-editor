"""Opt-in checks against a disposable real Redis server (no public search calls)."""
import asyncio,json,os,uuid
import pytest
import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import Worker
from worker import run_agent_task

@pytest.mark.asyncio
@pytest.mark.skipif(os.name=="nt",reason="ARQ worker lifecycle requires POSIX signals; run on Linux")
@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"),reason="Disposable Redis server not configured")
async def test_real_queue_completion_cancellation_and_scoped_events():
    url=os.environ["TEST_REDIS_URL"]
    client=redis.from_url(url,decode_responses=True)
    pool=await create_pool(RedisSettings.from_dsn(url))
    prefix="integration-"+uuid.uuid4().hex
    queue=prefix+":queue";normal=prefix+"-normal";cancelled=prefix+"-cancelled"
    pubsub=client.pubsub()
    runner=None
    try:
        await client.ping()
        await pubsub.subscribe(f"agent_events:{normal}",f"agent_events:{cancelled}")
        await client.set(f"task:{cancelled}:cancelled","1",ex=60)
        jobs=[await pool.enqueue_job("run_agent_task",task,"search Redis task verification",
               _queue_name=queue,_job_id=task) for task in [normal,cancelled]]
        runner=Worker(functions=[run_agent_task],redis_pool=pool,queue_name=queue,burst=True,
            ctx={"redis_client":client},handle_signals=False,poll_delay=.05,max_jobs=2,
            health_check_key=prefix+":health",keep_result=60)
        await asyncio.wait_for(runner.async_run(),timeout=20)
        assert runner.jobs_complete==2 and runner.jobs_failed==0
        for job in jobs:assert await job.result(timeout=2) is None
        last={task:json.loads(await client.get(f"task:{task}:last_event")) for task in [normal,cancelled]}
        assert last[normal]["status"]=="completed"
        assert last[cancelled]["status"]=="cancelled"
        seen={}
        async with asyncio.timeout(5):
            while len(seen)<2:
                message=await pubsub.get_message(ignore_subscribe_messages=True,timeout=1)
                if message and message["type"]=="message":
                    event=json.loads(message["data"])
                    assert message["channel"]==f"agent_events:{event['task_id']}"
                    if event["status"] in {"completed","cancelled"}:seen[event["task_id"]]=event["status"]
        assert seen=={normal:"completed",cancelled:"cancelled"}
    finally:
        await pubsub.aclose()
        # Only this test's random namespace; never FLUSHDB/FLUSHALL.
        for task in [normal,cancelled]:
            await client.delete(f"task:{task}:last_event",f"task:{task}:cancelled",f"arq:result:{task}",f"arq:job:{task}")
        await client.delete(queue,prefix+":health")
        if runner:await runner.close()
        else:await pool.aclose()
        await client.aclose()
