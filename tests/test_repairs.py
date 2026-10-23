import asyncio
import subprocess
import sys
import pytest
import fakeredis.aioredis
import main
import worker
from ast_editor import replace_function, resolve_file, evaluate_in_worktree
from httpx import AsyncClient, ASGITransport

def test_targeted_unicode_and_scope():
    source = '# caf?\ndef keep():\n    return 2\n\ndef fix():\n    return 1\n'
    result = replace_function(source, "fix", "def fix():\n    return 3")
    assert "# caf?" in result and "return 2" in result and "return 3" in result
    with pytest.raises(ValueError):
        replace_function(source, "fix", "def other(): pass")

def test_paths_and_invalid_syntax(tmp_path):
    with pytest.raises(ValueError):
        resolve_file(tmp_path, "../escape.py")
    with pytest.raises((ValueError, SyntaxError)):
        replace_function("def x(): pass", "x", "def x(: pass")

def test_worktree_success_and_failure_leave_source_unchanged(tmp_path):
    for args in [["init"], ["config","user.email","test@example.invalid"],["config","user.name","test"]]:
        subprocess.run(["git",*args], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path/"demo.py").write_text("def value():\n    return 1\n")
    subprocess.run(["git","add","."],cwd=tmp_path,check=True)
    subprocess.run(["git","commit","-m","fixture"],cwd=tmp_path,check=True,capture_output=True)
    cmd=[sys.executable,"-c","from demo import value; assert value()==2"]
    good=evaluate_in_worktree(tmp_path,"demo.py","value","def value():\n    return 2",cmd)
    bad=evaluate_in_worktree(tmp_path,"demo.py","value","def value():\n    return 3",cmd)
    assert good["passed"] and not bad["passed"]
    assert "return 1" in (tmp_path/"demo.py").read_text()
    assert not subprocess.run(["git","status","--porcelain"],cwd=tmp_path,capture_output=True,text=True).stdout

@pytest.mark.asyncio
async def test_task_capabilities_and_validation(monkeypatch):
    redis=fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(main,"redis_client",redis)
    class Queue:
        async def enqueue_job(self,*args): pass
    monkeypatch.setattr(main,"arq_pool",Queue())
    async with AsyncClient(transport=ASGITransport(app=main.app),base_url="http://test") as client:
        assert (await client.post("/agent/run",json={"prompt":"   "})).status_code==422
        created=(await client.post("/agent/run",json={"prompt":"Redis"})).json()
        tid=created["task_id"]
        assert (await client.post(f"/agent/{tid}/cancel")).status_code==403
        assert (await client.post(f"/agent/{tid}/cancel",headers={"X-Task-Token":created["task_token"]})).status_code==200
    await redis.aclose()

@pytest.mark.asyncio
async def test_search_failure_not_fabricated(monkeypatch):
    class Broken:
        def text(self,*args,**kwargs): raise OSError("offline")
    monkeypatch.setattr(worker,"DDGS",Broken)
    redis=fakeredis.aioredis.FakeRedis(decode_responses=True)
    result=await worker.run_agent_pipeline("failure","Redis",redis)
    assert result.status=="failed"
    await redis.aclose()

def test_bounded_repair_uses_real_failure_feedback(tmp_path):
    import json
    from repair_agent import repair
    for args in [["init"],["config","user.email","test@example.invalid"],["config","user.name","test"]]:
        subprocess.run(["git",*args],cwd=tmp_path,check=True,capture_output=True)
    (tmp_path/"demo.py").write_text("def value():\n    return 1\n")
    subprocess.run(["git","add","."],cwd=tmp_path,check=True)
    subprocess.run(["git","commit","-m","fixture"],cwd=tmp_path,check=True,capture_output=True)
    class Proposer:
        def __init__(self):self.calls=[]
        def propose(self,context):
            self.calls.append(context)
            value=3 if len(self.calls)==1 else 2
            return json.dumps({"replacement":f"def value():\n    return {value}"})
    provider=Proposer()
    result=repair(tmp_path,"demo.py","value","return 2",provider,
                  [sys.executable,"-c","from demo import value; assert value()==2"])
    assert result["status"]=="verified_candidate"
    assert len(result["attempts"])==2 and "AssertionError" in provider.calls[1]["verification_feedback"]
    assert not result["applied_to_original"]
    assert "return 1" in (tmp_path/"demo.py").read_text()
    assert not subprocess.run(["git","status","--porcelain"],cwd=tmp_path,capture_output=True,text=True).stdout

def test_repair_stops_at_budget_on_bad_model_json(tmp_path):
    from repair_agent import repair
    for args in [["init"],["config","user.email","test@example.invalid"],["config","user.name","test"]]:
        subprocess.run(["git",*args],cwd=tmp_path,check=True,capture_output=True)
    (tmp_path/"demo.py").write_text("def value(): return 1\n")
    subprocess.run(["git","add","."],cwd=tmp_path,check=True)
    subprocess.run(["git","commit","-m","fixture"],cwd=tmp_path,check=True,capture_output=True)
    class Broken:
        def propose(self,context):return "not json"
    result=repair(tmp_path,"demo.py","value","fix",Broken(),[sys.executable,"-c","pass"],max_attempts=2)
    assert result["status"]=="exhausted" and len(result["attempts"])==2
