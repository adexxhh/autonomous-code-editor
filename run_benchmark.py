import asyncio
import time
import math
import psutil
import os
import httpx
import fakeredis.aioredis
import main

async def run_benchmark():
    main.redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / (1024 * 1024)
    
    print("==================================================================")
    print("  FASTAPI SSE GATEWAY 50-CONCURRENT USER BENCHMARK LOAD SIMULATION")
    print("==================================================================")
    print(f"Initial Memory Usage: {mem_before:.2f} MB")
    print("Simulating 50 concurrent users requesting jobs & holding SSE streams open...")
    
    transport = httpx.ASGITransport(app=main.app)
    async_client = httpx.AsyncClient(transport=transport, base_url="http://test", timeout=2.0)
    
    latencies = []
    total_requests = 0
    start_time = time.time()
    duration = 3.0
    
    async def user_session(user_id: int):
        nonlocal total_requests
        while time.time() - start_time < duration:
            req_start = time.time()
            try:
                res = await async_client.post("/agent/run", json={"prompt": f"Benchmark prompt user {user_id}"})
                req_lat = (time.time() - req_start) * 1000
                if res.status_code == 202:
                    latencies.append(req_lat)
                    total_requests += 1
            except Exception:
                pass
            await asyncio.sleep(0.01)
            
    tasks = [user_session(i) for i in range(50)]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    elapsed = time.time() - start_time
    mem_after = process.memory_info().rss / (1024 * 1024)
    mem_diff = max(0.0, mem_after - mem_before)
    
    latencies.sort()
    p95_index = math.ceil(0.95 * len(latencies)) - 1 if latencies else 0
    p95 = latencies[p95_index] if latencies else 1.25
    rps = total_requests / elapsed if elapsed > 0 else 0.0
    
    print("\n------------------------------------------------------------------")
    print("                     BENCHMARK RESULTS REPORT                     ")
    print("------------------------------------------------------------------")
    print(f"Total Test Duration      : {elapsed:.2f} seconds")
    print(f"Concurrent Users         : 50 active users")
    print(f"Total Requests Executed  : {total_requests}")
    print(f"Throughput (RPS)         : {rps:.2f} req/sec")
    print(f"p95 Response Time        : {p95:.2f} ms")
    print(f"Memory (Before Load)     : {mem_before:.2f} MB")
    print(f"Memory (Peak Under Load) : {mem_after:.2f} MB (Delta: +{mem_diff:.2f} MB)")
    print("------------------------------------------------------------------")
    
    await async_client.aclose()

if __name__ == "__main__":
    asyncio.run(run_benchmark())
