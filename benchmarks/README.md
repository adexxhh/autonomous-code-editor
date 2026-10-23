# Model-assisted repair probes

Run three disclosed Python repair tasks through the model-proposal, AST-edit and worktree-verification loop. The report retains each replacement, verification result, error and diff.

## Check fixtures

Create an artifacts directory, then run:

~~~sh
python -m benchmarks.model_repair --check-fixtures --output artifacts/fixture-checks.json
~~~

This confirms that the starting implementations fail their verification checks.

## Run a local model

Install the project requirements plus transformers, bitsandbytes and accelerate in a disposable CUDA runtime:

~~~sh
python -m benchmarks.model_repair --model /path/to/local/Qwen3-8B --allow-local-execution --output repair-probes.json
~~~

[GPU notebook](colab_model_repairs.ipynb) prepares this run with the source bundle and a pinned model snapshot. Use a runtime without personal Drive mounted or credentials present: proposed Python code executes during verification.

These small tasks check the integration path. Measure representative repair performance with a larger independent task set.
