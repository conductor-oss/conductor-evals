# conductor-evals — Agent Guide

This file is for coding agents working on this codebase. Read this before making changes.

## What This Project Does

An eval framework that runs AI test cases across multiple LLM models in parallel, orchestrated by Conductor. Users define eval cases as JSON, pick models, and get scored results with full execution history.

## How to Run It

```bash
# Install deps
pip install -e .

# Conductor server must be running (default: localhost:8080)
# Config: config/orkes-config.json

# Register task/workflow definitions (once, or after changing definitions)
python3 scripts/register.py

# Start workers (keep running in background)
python3 main.py

# Run evals
python3 scripts/run_suite.py --suite math-basics --models claude-haiku --wait
python3 scripts/run_suite.py --suite math-basics --models claude-haiku --dry-run --wait  # no LLM calls

# Compare two runs
python3 scripts/compare_runs.py <workflow-id-A> <workflow-id-B>
```

## Architecture

Two Conductor workflows:

**`eval_suite`** (top-level): `prepare_fork_inputs` → `FORK_JOIN_DYNAMIC` (N parallel sub-workflows) → `JOIN` → `aggregate_results`

**`eval_case_run`** (per case×model): `SWITCH(agent_type)` → agent execution → `normalize_agent_output` (inline JS) → `SWITCH(scoring_method)` → scorer → `record_result`

The cartesian product of (eval_cases × models) determines N. Each pair runs as an independent sub-workflow in parallel.

### What runs where

| Component | Runs on | How |
|-----------|---------|-----|
| `direct_llm` agent calls | Conductor server | Built-in `LLM_CHAT_COMPLETE` system task |
| `tool_use_agent` calls | Conductor server | Built-in `LLM_CHAT_COMPLETE` with tools |
| `llm_judge` scoring calls | Conductor server | Built-in `LLM_CHAT_COMPLETE` |
| `claude_code_agent` calls | Worker process | Custom `execute_agent` task → `claude` CLI |
| `score_text_match` | Worker process | Custom task |
| `score_tool_trace` | Worker process | Custom task |
| `parse_judge_output` | Worker process | Custom task |
| `prepare_fork_inputs` | Worker process | Custom task |
| `record_result` | Worker process | Custom task |
| `aggregate_results` | Worker process | Custom task |
| `normalize_agent_output` | Conductor server | Inline GraalJS task |

API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) must be set on the **Conductor server**, not in the worker env. The server handles all LLM API calls for `direct_llm`, `tool_use_agent`, and `llm_judge`.

## File Map

```
main.py                              Worker entry point — imports all worker modules, starts TaskHandler
config/orkes-config.json             Conductor server URL + auth (keyId/keySecret)

workflows/eval_suite.json            Top-level workflow definition (v2, 7200s timeout)
workflows/eval_case_run.json         Per-case sub-workflow definition (v1, 600s timeout)
tasks/*.json                         Conductor task definitions (7 files)

workers/fork_preparer.py             prepare_fork_inputs: builds cases×models → dynamicTasks
workers/agent_executor.py            execute_agent: only handles claude_code_agent (shells out to claude CLI)
workers/scorers.py                   score_text_match, parse_judge_output, score_tool_trace
workers/aggregator.py                record_result (normalize one result), aggregate_results (per-model stats)

providers/claude_code_provider.py    ClaudeCodeProvider: subprocess call to `claude` CLI, 300s timeout

scripts/helpers.py                   Shared: load_config(), get_execution(), extract_results()
scripts/run_suite.py                 CLI: --suite, --models, --wait, --output (text/markdown/json/csv), --dry-run
scripts/compare_runs.py              CLI: compare two workflow executions side-by-side
scripts/register.py                  Push tasks/*.json and workflows/*.json to Conductor server
scripts/inject_system_prompt.py      Batch-update system_prompt field in eval case JSON files

evals/<suite-name>/*.json            Eval case definitions — one JSON file per test case
```

## Data Flow

### Workflow output shape (`eval_suite`)

```json
{
  "run_id": "run_abc123",
  "summary": {
    "<model_id>": {
      "avg_score": 0.75,
      "pass_rate": 0.75,
      "passed_cases": 3,
      "total_cases": 4
    }
  },
  "results": [
    {
      "case_id": "add_simple",
      "model_id": "<model_id>",
      "provider": "anthropic",
      "run_id": "run_abc123",
      "score": 1.0,
      "passed": true,
      "response_preview": "70",
      "latency_ms": 450,
      "token_usage": { "input_tokens": 20, "output_tokens": 5 },
      "scoring_details": { "score": 1.0, "passed": true, "details": "Contains '70': True" }
    }
  ]
}
```

### Normalized agent output (from `normalize_agent_output` inline task)

Every agent type gets normalized to this shape before scoring:

```json
{
  "response": "the model's text response",
  "tool_calls": [{ "tool_name": "grep_search", "args": { "pattern": "calculate_tax" } }],
  "token_usage": { "input_tokens": 100, "output_tokens": 50 },
  "latency_ms": 450
}
```

## Patterns to Follow

### Adding a new worker task

1. Create the function in the appropriate `workers/*.py` file with `@worker_task(task_definition_name='your_task')` decorator
2. Create `tasks/your_task.json` with the task definition (name, retryCount, timeoutSeconds, inputKeys, outputKeys)
3. The worker module must be imported in `main.py` — add `import workers.your_module` and add the module path to `import_modules` list
4. Wire it into the relevant workflow JSON in `workflows/`
5. Run `python3 scripts/register.py` to push the new task definition

Worker functions receive inputs as keyword arguments matching the `inputParameters` in the workflow JSON. They return a dict that becomes the task's output.

### Adding a new scoring method

1. Add scorer function in `workers/scorers.py` with `@worker_task` decorator
2. Add task definition JSON in `tasks/`
3. Add a new case in the `route_scorer` SWITCH in `workflows/eval_case_run.json`
4. Wire scorer output into `record_result` inputParameters (add a new `*_result` parameter)
5. Update `record_result` in `workers/aggregator.py` to pick up the new result key

Scorer functions must return `{"score": float, "passed": bool, ...}`. Score is 0.0-1.0.

### Adding a new agent type

1. If it needs a custom worker: add handler in `workers/agent_executor.py`, or create a new worker
2. Add a new case in the `route_agent` SWITCH in `workflows/eval_case_run.json`
3. Wire the new task's output reference into `normalize_agent_output`'s inputParameters
4. Update the inline JS expression in `normalize_agent_output` to handle the new output shape

If the agent type can use Conductor's `LLM_CHAT_COMPLETE` system task, prefer that over a custom worker.

### Adding a new model preset

Add to the `MODEL_PRESETS` dict in `scripts/run_suite.py`:

```python
"preset-name": {
    "provider": "anthropic",          # must match a Conductor AI provider
    "model_id": "model-id-string",
    "params": {"max_tokens": 4096, "temperature": 0.0},
},
```

### Adding eval cases

Drop a `.json` file in `evals/<suite-name>/`. Create the directory for a new suite. No registration step — cases are loaded client-side by `run_suite.py` at runtime.

Required fields: `id`, `agent_type`, `scoring_method`, `prompt`.

**text_match** cases also need: `expected` (`{"value": "..."}` or `{"values": [...]}`) and `match_mode` (exact/contains/regex/contains_all/contains_any).

**llm_judge** cases also need: `rubric`. Optional: `judge_model` (default: claude-sonnet-4-20250514), `judge_provider` (default: anthropic).

**tool_trace** cases also need: `tools` (array of tool definitions with `inputSchema`), `expected_trace` (array of `{"tool_name", "args_contain"}`), `strict_order` (bool).

Optional fields on any case: `name`, `description`, `system_prompt`, `tags`, `timeout_seconds`, `max_tool_turns`.

### Adding a new output format to run_suite.py

1. Add a `format_yourformat(data, suite_name)` function in `scripts/run_suite.py`
2. Add it to the `FORMATTERS` dict
3. Add the choice to the `--output` argparse argument

The `data` dict has keys: `run_id`, `status`, `summary` (dict of model_id → stats), `results` (dict of case_id → result). This comes from `extract_results()` in `scripts/helpers.py`.

### Modifying shared helpers

`scripts/helpers.py` is imported by both `run_suite.py` and `compare_runs.py`. Changes here affect both scripts. The three functions:

- `load_config()` — reads `config/orkes-config.json`, returns `{"url", "headers"}`
- `get_execution(cfg, workflow_id)` — `GET /api/workflow/{id}`, returns execution dict
- `extract_results(execution)` — pulls `output.summary` and `output.results` from execution, returns normalized dict

Note: `scripts/register.py` has its own `load_config()` copy (not imported from helpers) because it predates the refactor and doesn't need the other helpers.

## Conductor Specifics

- Workflow/task definitions are JSON, stored in `workflows/` and `tasks/`. They must be registered with the server via `scripts/register.py` before use.
- `FORK_JOIN_DYNAMIC` requires `dynamicTasks` (array of task descriptors) and `dynamicTasksInputs` (dict of refName → input). The `prepare_fork_inputs` worker builds these.
- `SWITCH` tasks use `evaluatorType: "value-param"` for simple value matching against `expression`.
- `INLINE` tasks run JavaScript (GraalJS) on the Conductor server. The `normalize_agent_output` task is the only one — it unifies output from three agent types.
- Task reference names must be unique within a workflow. They're used in `${refName.output}` expressions.
- `LLM_CHAT_COMPLETE` is a Conductor system task type — no worker needed. It calls LLM APIs directly from the server using configured AI providers.

## Testing Changes

```bash
# Dry run (no LLM calls) — fast way to test workflow changes
python3 scripts/run_suite.py --suite math-basics --models claude-haiku --dry-run --wait

# Verify all output formats
python3 scripts/run_suite.py --suite math-basics --models claude-haiku --dry-run --wait --output text
python3 scripts/run_suite.py --suite math-basics --models claude-haiku --dry-run --wait --output markdown
python3 scripts/run_suite.py --suite math-basics --models claude-haiku --dry-run --wait --output json
python3 scripts/run_suite.py --suite math-basics --models claude-haiku --dry-run --wait --output csv

# Verify compare still works
python3 scripts/compare_runs.py <id-A> <id-B>

# Syntax check all Python files
python3 -c "import ast; [ast.parse(open(f).read()) for f in __import__('glob').glob('**/*.py', recursive=True)]"
```

Workers must be restarted (`main.py`) after changing worker code. Workflow/task definitions must be re-registered (`scripts/register.py`) after changing JSON definitions.
