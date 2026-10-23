# Actual local model repair probes
Run fixture checks offline: python -m benchmarks.model_repair --check-fixtures --output artifacts/fixture-checks.json (create artifacts first).
On a disposable CUDA runtime with transformers, bitsandbytes, peft, accelerate and project requirements installed:
python -m benchmarks.model_repair --model /path/to/local/Qwen3-8B --allow-local-execution --output repair-probes.json
Three fixed disclosed tasks exercise real model proposals, Tree-sitter edits, worktree test execution and bounded feedback. No solutions are supplied to the model. Reports retain every attempt, errors and diffs.
These tasks are deliberately small integration probes. They cannot substantiate a general repair-success percentage. Git worktrees are not an OS sandbox; generated code runs with the runtime's privileges. Use an ephemeral account-free runtime.
No actual CUDA model run has been completed in this repository yet.
