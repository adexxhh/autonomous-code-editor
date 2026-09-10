import time
from locust import HttpUser, task, between

class AgentUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def run_agent_and_stream(self):
        # 1. Trigger agent job via POST /agent/run (Returns 202 Accepted)
        payload = {"prompt": "Search for FastAPI SSE streaming performance"}
        self.client.post("/agent/run", json=payload)
        
        # 2. Hold GET /stream connection open to receive SSE events
        with self.client.get("/stream", stream=True, name="/stream (SSE Open)") as response:
            start_time = time.time()
            for line in response.iter_lines():
                # Hold SSE stream open for up to 5 seconds per simulation step
                if time.time() - start_time > 5:
                    break
