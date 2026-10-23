# Autonomous Code Editor

A Python code-repair toolkit that combines targeted Tree-sitter edits, model-generated function replacements and test feedback.

The repair CLI produces reviewable patches in disposable Git worktrees. The repository also includes a FastAPI task service demonstrating queued LangGraph workflows, task-scoped events and cancellation.

## Code-repair workflow

~~~mermaid
flowchart LR
  Task[Task and source context] --> Model[Configured model provider]
  Model --> Candidate[Function replacement]
  Candidate --> AST[Tree-sitter and Python validation]
  AST --> Worktree[Disposable Git worktree]
  Worktree --> Tests[Verification command]
  Tests -->|Pass| Diff[Reviewable patch]
  Tests -->|Fail, within attempt limit| Model
~~~

- Select a unique top-level Python function and replace its byte range.
- Preserve surrounding code, decorators and Unicode content.
- Validate syntax and repository paths before verification.
- Run a developer-supplied test command in a detached worktree.
- Feed verification failures into a bounded repair loop.
- Return the patch, test output and attempt history for review.

The repair CLI leaves the original checkout unchanged. Verification executes code with the runtime's privileges; use an isolated environment for untrusted repositories or generated code.

## Install

~~~sh
python -m venv .venv
# Activate the environment, then:
pip install -r requirements.txt
~~~

## Preview a targeted edit

~~~sh
python ast_editor.py --repo /path/to/repo --file example.py --function add --replacement candidate.txt
~~~

candidate.txt contains the complete replacement function. The command validates the edit and displays its diff.

## Run a model-assisted repair

Start from a clean, committed repository and configure an OpenAI-compatible model gateway:

~~~sh
python repair_agent.py --repo /path/to/repo --file example.py --function add --task "Fix addition" --base-url http://localhost:11434/v1 --model your-local-model --output result.json --allow-local-execution --verify python -m pytest -q
~~~

REPAIR_API_KEY supplies an optional gateway credential. The default repair budget is three attempts, configurable up to five. Context and feedback limits bound the information passed between attempts.

The result includes the base revision, proposed replacements, verification output and a successful diff when a candidate passes the supplied checks.

## Asynchronous workflow service

FastAPI, Redis/ARQ and LangGraph provide an asynchronous search-workflow example:

1. POST /agent/run submits a task and returns task_id and task_token.
2. The worker executes the workflow and publishes task-scoped events.
3. Clients receive SSE updates or retrieve the latest task state.
4. Clients can request cooperative cancellation.

Status and cancellation use X-Task-Token. SSE connections use task_id and token query parameters. Treat task tokens as access credentials.

~~~sh
docker compose up --build
~~~

For a single-process local demo, set AGENT_DEMO_MODE=1 and REDIS_HOST=localhost, then:

~~~sh
uvicorn main:app --host 127.0.0.1 --port 8000
~~~

The search workflow service is a separate entry point from the code-repair CLI.

## Validation

~~~sh
python -m pytest -q
python -m scripts.demo_scenario
~~~

The local suite passes 12 tests covering AST edits, path handling, worktree verification, repair feedback, task access and provider failures. Linux CI additionally verifies queued completion, cancellation and task-scoped events against Redis.

[CI results](https://github.com/adexxhh/autonomous-code-editor/actions/runs/39961303101) ? [Recorded job evidence](docs/evidence/github-actions.json)

[Model-repair probes](benchmarks/README.md) exercise three disclosed tasks with a local model. Their reports retain proposals, test results and diffs for each attempt. Use these as integration checks; representative repair performance requires a broader dataset.

## Demo

![Code editor terminal walkthrough](assets/demo.gif)

[PNG](assets/demo.png) ? [Command transcript](assets/demo-transcript.json)

Regenerate the walkthrough with requirements-demo.txt and python scripts/render_demo.py.

## Development

[Engineering guide](OWNERSHIP.md) ? [GPU repair notebook](benchmarks/colab_model_repairs.ipynb) ? [Continuation notes](HANDOFF.md)
