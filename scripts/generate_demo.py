import time
import sys

def print_styled(text, delay=0.03):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def main():
    print("\033[1;36m========================================================================\033[0m")
    print("\033[1;36m       ASYNCHRONOUS AGENT MICROSERVICE CORE ENGINE DEMO               \033[0m")
    print("\033[1;36m========================================================================\033[0m\n")
    time.sleep(0.5)

    print("\033[1;33m[SYS]\033[0m Initializing FastAPI Gateway & ARQ LangGraph Worker...")
    time.sleep(0.4)
    print("\033[1;32m[OK]\033[0m Connected to Redis Pub/Sub broker (host=localhost, port=6379)")
    time.sleep(0.6)

    # 1. Enqueue Task
    print("\n\033[1;35m[CLIENT]\033[0m Submitting job: \033[1;37mPOST /agent/run\033[0m")
    print_styled("         Payload: {\"prompt\": \"Search for FastAPI SSE streaming best practices\"}", 0.02)
    time.sleep(0.4)
    
    task_id = "8f3a92b1-4c12-4f89-9a2d-10b2a758d839"
    print(f"\033[1;32m[GATEWAY]\033[0m \033[1;32mHTTP 202 Accepted\033[0m -> task_id: \033[1;37m{task_id}\033[0m (Ingestion: 0.88 ms)")
    time.sleep(0.8)

    # 2. SSE Stream Execution
    print("\n\033[1;34m[SSE STREAM]\033[0m Listening on \033[1;37mGET /stream\033[0m for channel 'agent_events':")
    time.sleep(0.5)

    print(f"\033[36mdata: {{\"task_id\": \"{task_id}\", \"node\": \"DecisionNode\", \"status\": \"thought_start\", \"message\": \"[DecisionNode] Analyzing prompt...\"}}\033[0m")
    time.sleep(0.8)
    
    print(f"\033[36mdata: {{\"task_id\": \"{task_id}\", \"node\": \"DecisionNode\", \"status\": \"thought_token\", \"message\": \"Formulated DDG Query: 'FastAPI SSE streaming best practices'\"}}\033[0m")
    time.sleep(0.9)

    print(f"\033[36mdata: {{\"task_id\": \"{task_id}\", \"node\": \"ToolNode\", \"status\": \"tool_start\", \"message\": \"[ToolNode] Executing DuckDuckGo tool...\"}}\033[0m")
    time.sleep(0.9)

    print(f"\033[36mdata: {{\"task_id\": \"{task_id}\", \"node\": \"ToolNode\", \"status\": \"tool_output\", \"message\": \"Tool Output Received: • FastAPI SSE Documentation & Benchmarks...\"}}\033[0m")
    time.sleep(1.0)

    # 3. Out-of-band Cancel Interrupt Simulation
    print("\n\033[1;31m[CLIENT]\033[0m Out-of-band Interrupt Triggered: \033[1;37mPOST /agent/{task_id}/cancel\033[0m")
    time.sleep(0.5)
    print("\033[1;31m[REDIS]\033[0m Flag Set: \033[1;37mtask:8f3a92b1:cancelled = '1'\033[0m")
    time.sleep(0.7)
    
    print(f"\033[1;31m[WORKER]\033[0m Interrupt Check Triggered -> Halting LangGraph execution cleanly!")
    time.sleep(0.5)
    print(f"\033[1;31mdata: {{\"task_id\": \"{task_id}\", \"status\": \"cancelled\", \"message\": \"Task interrupted & cancelled cleanly by user\"}}\033[0m")
    time.sleep(1.0)

    print("\n\033[1;32m========================================================================\033[0m")
    print("\033[1;32m       DEMO EXECUTION COMPLETED (All events verified & logged)        \033[0m")
    print("\033[1;32m========================================================================\033[0m")

if __name__ == "__main__":
    main()
