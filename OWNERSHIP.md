# Engineering changes and project ownership

## A defensible description
"I implemented a deterministic Tree-sitter Python function editor with validation and disposable Git-worktree verification. Separately, I built a FastAPI/Redis background search workflow with task-scoped event streaming, cooperative cancellation and explicit failure handling."

An editor primitive plus orchestration infrastructure is useful engineering. A bounded model-proposal/verification loop is now implemented in repair_agent.py. It still needs a configured real model, representative task evaluation and a stronger execution boundary before autonomous deployment.

## Trace both components
**Editor:** ast_editor.replace_function encodes UTF-8, parses a tree, finds exactly one top-level function, substitutes its byte span and reparses. preview resolves the path and produces a diff. evaluate_in_worktree creates a detached checkout, applies the candidate, optionally invokes a trusted verification command and always removes the worktree.

**Service:** POST /agent/run validates input and generates a task ID and capability token. In Redis mode ARQ queues work; in explicit demo mode an asyncio task runs in the same process. worker.py runs a fixed decision/search graph. Events are published to one channel per task and the last event is saved as a key. Status/cancel/SSE require the task token.

repair_agent.py connects a configured HTTP model gateway to the editor and worktree verifier. Candidate JSON is validated; actual test failure feedback drives bounded retries. It outputs a reviewable diff and never automatically changes the original checkout. Model quality was not evaluated on this host.

## Before and after
| Earlier issue | Repair | Engineering consequence |
|---|---|---|
| Repository name/resume implied AST edits, but only a search graph existed | Added a real tested Tree-sitter editor | There is now an implementation you can inspect and demonstrate |
| Claimed Git rollback without code | Disposable worktree verification with success/failure tests | Failed candidates leave the original committed checkout untouched |
| Synchronous DDGS call inside async node | Move blocking call to a thread, await with timeout | Other event-loop work can proceed while the provider is blocked |
| Search exceptions produced plausible fake output | Return and publish failed status | Operational failure is visible |
| Every client received the same global event channel | Separate task channel plus random capability | One task's token does not grant another task's output/cancellation |
| Redis failure silently activated local emulation | Explicit AGENT_DEMO_MODE; otherwise fail startup | Deployment failure is no longer mistaken for a functioning distributed system |
| No status after missed Pub/Sub messages | Last-event snapshot | Reconnect can recover last known state; intermediate events still are not replayed |
| Benchmark claimed 50 SSE users but opened no streams | Explicitly label mock-queue, in-process dispatch | Reported numbers no longer pretend to measure completed-job/network throughput |

## Concepts to master
**AST and bytes:** Python string indexes count Unicode code points; Tree-sitter positions count bytes. Explain the caf? fixture and why using character offsets would corrupt edits. Understand decorated functions, ambiguous names, nested scopes and why the current primitive supports only top-level Python functions.

**Safety:** parsing proves syntax, not behavioural correctness. Passing a test does not establish complete semantic equivalence. Git isolation protects a checkout; it does not restrict network, filesystem, subprocesses or secrets. Verification commands execute with the caller's privileges.

**Git:** understand commits, detached HEAD, worktrees, clean checkout requirements and try/finally cleanup. Know why uncommitted source changes are rejected rather than silently ignored.

**Async execution:** an async function can still block. asyncio.to_thread moves blocking work but cancelling the await does not forcibly stop the worker thread. Cooperative cancellation is checked at defined points.

**Queue versus event bus:** ARQ is for task dispatch; Pub/Sub broadcasts transient events. A connection that misses a Pub/Sub message cannot replay it from Pub/Sub itself. The snapshot key stores only the newest event.

**Authorization:** UUIDs identify tasks; random bearer capabilities authorize access. Tokens in URLs can leak through logs. This is not an account system, tenancy model, rate limiter or externally hardened service.

**Metrics:** HTTP 202 means accepted/queued, not completed. Differentiate dispatch latency, queue wait, tool latency, completed jobs/sec, stream fanout and error rate. p95 is a percentile of a clearly specified population.

**Token accounting:** tokenizer, prompt, file context, patch format, retries and model output all affect actual cost. The demo's 23-to-9 token comparison is output payload on one tiny fixture only. It cannot establish a general percentage saving.

## Hands-on ownership checkpoints
- Implement a second edit selector for a class method; reject ambiguous matching methods.
- Explain and reproduce Unicode preservation.
- Show a syntactically valid but wrong candidate failing the subprocess assertion.
- Add a failing verification command and verify the original Git checkout remains clean.
- Introduce a blocking fake search provider and show another coroutine still makes progress.
- Cancel before a node, then during a running tool; explain the different outcomes.
- Try another task's token and inspect the 403 response.
- Stop Redis in real mode and verify explicit startup failure.
- Benchmark with an actual Redis queue and workers before making end-to-end claims.
- If you add an LLM, specify its edit schema, retries, budgets, test feedback and failure taxonomy.

## Verification and limits
12 CPU tests passed, including actual temporary Git repositories/worktrees and mocked provider behaviour. The recorded demo computes the token numbers rather than printing a preset result.
No representative bug dataset, real model-provider run, OS sandbox, live Redis deployment or network/SSE load benchmark has been validated. The former 45%, 92% and throughput/latency showcase claims have been withdrawn.


## Defend the repair loop
Trace repair() from model context through Candidate validation, AST replacement, worktree test output and retry. Explain why it requires an explicit verification command instead of letting the model choose shell commands. Demonstrate a wrong candidate failing and a second candidate passing using the real failure feedback. Explain attempt bounds, context truncation limits, provider timeouts and the distinction between a test-passing patch and a correct patch. A paid/API model run and a representative repair benchmark remain pending.
