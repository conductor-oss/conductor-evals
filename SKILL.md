# Conductor Evals - Agent Skill Guide

This document describes how AI agents can use the Conductor Evals CLI to manage and run AI evaluations.

## Prerequisites

- Python package installed: `pip install -e .` (from the project root)
- Conductor server running (default: `http://localhost:8080`)
- Workers running: `conductor-eval workers` (in a background process or separate terminal)
- At least one LLM provider API key set (e.g., `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`)

## Conductor Server Connection

Environment variables (take precedence over config file):

| Variable | Required | Description |
|----------|----------|-------------|
| `CONDUCTOR_URL` | Yes | Base URL of the Conductor server (e.g., `http://localhost:8080`) |
| `CONDUCTOR_AUTH_KEY` | Yes | API key ID for authentication |
| `CONDUCTOR_AUTH_SECRET` | No | API key secret (required for Orkes Conductor; omit for open-source) |

**Without auth (open-source Conductor):**

```bash
export CONDUCTOR_URL="https://conductor.example.com"
export CONDUCTOR_AUTH_KEY="my-api-key"
```

**With auth (Orkes Conductor):**

```bash
export CONDUCTOR_URL="https://play.orkes.io"
export CONDUCTOR_AUTH_KEY="your-key-id"
export CONDUCTOR_AUTH_SECRET="your-key-secret"
```

If env vars are not set, falls back to `config/orkes-config.json` (first cluster entry).

## CLI Overview

All commands use the `conductor-eval` entry point:

```
conductor-eval <command> [options]
```

## Commands

### Discover available suites and models

```bash
# List all eval suites with case counts
conductor-eval suites

# List cases in a specific suite (shows id, agent_type, scoring_method)
conductor-eval cases <suite_name>

# List available model presets
conductor-eval models
```

### Run an eval suite

```bash
# Run and wait for results (most common usage)
conductor-eval run <suite> --models <model> [<model> ...] --wait

# Run with multiple models for comparison
conductor-eval run math-basics --models claude-sonnet gpt-4o --wait

# Dry run (no LLM calls, tests the pipeline)
conductor-eval run math-basics --models claude-haiku --dry-run --wait

# Get JSON output (best for programmatic use)
conductor-eval run math-basics --models claude-sonnet --wait -o json

# Filter by tags
conductor-eval run math-basics --models claude-sonnet --tags arithmetic --wait

# CI mode: fail if pass rate below threshold
conductor-eval run math-basics --models claude-sonnet --wait --threshold 0.9
```

**Model format:** Use preset names (e.g., `claude-sonnet`, `gpt-4o`) or `provider:model_id` (e.g., `anthropic:claude-haiku-4-5-20251001`).

### Monitor and manage runs

```bash
# List recent runs (default: last 20)
conductor-eval runs

# List runs for a specific suite
conductor-eval runs --suite math-basics

# Show more results
conductor-eval runs --limit 50

# Check status of a specific run (shows progress if still running)
conductor-eval status <workflow_id>

# Get results in JSON
conductor-eval status <workflow_id> -o json

# Cancel a running eval
conductor-eval cancel <workflow_id>
```

### Compare two runs

```bash
# Compare results side-by-side
conductor-eval compare <workflow_id_a> <workflow_id_b>

# JSON output
conductor-eval compare <workflow_id_a> <workflow_id_b> -o json

# Fail if regression exceeds threshold
conductor-eval compare <workflow_id_a> <workflow_id_b> --regression-threshold 0.05
```

### Start infrastructure

```bash
# Start workers (auto-registers workflows with Conductor)
conductor-eval workers

# Start the web UI server on port 3939
conductor-eval server
```

## Writing Eval Cases

Eval cases are JSON files in `evals/<suite_name>/`. Drop a `.json` file in a suite directory to add a case.

### Required fields

| Field | Description |
|-------|-------------|
| `id` | Unique case identifier |
| `prompt` | The prompt sent to the model |
| `agent_type` | `direct_llm`, `tool_use_agent`, or `claude_code_agent` |
| `scoring_method` | `text_match`, `llm_judge`, or `tool_trace` |

### Text match example

```json
{
  "id": "add_simple",
  "agent_type": "direct_llm",
  "scoring_method": "text_match",
  "prompt": "What is 23 + 47? Reply with just the number.",
  "expected": { "value": "70" },
  "match_mode": "contains"
}
```

Match modes: `exact`, `contains`, `regex`, `contains_all`, `contains_any`

### LLM judge example

```json
{
  "id": "ethical_dilemma",
  "agent_type": "direct_llm",
  "scoring_method": "llm_judge",
  "prompt": "Should a hospital deploy an AI system with 85% accuracy?",
  "rubric": "Score 1-5: identifies tradeoffs, considers patient impact"
}
```

### Tool trace example

```json
{
  "id": "file_search",
  "agent_type": "tool_use_agent",
  "scoring_method": "tool_trace",
  "prompt": "Find the definition of 'calculate_tax'.",
  "tools": [{ "name": "grep_search", "description": "Search files", "input_schema": { "type": "object", "properties": { "pattern": { "type": "string" } }, "required": ["pattern"] } }],
  "tool_responses": { "grep_search": { "default": { "matches": [] }, "when": [{ "args_contain": { "pattern": "calculate_tax" }, "response": { "matches": [{ "file": "src/billing.py", "line": 42 }] } }] } },
  "expected_trace": [{ "tool_name": "grep_search", "args_contain": { "pattern": "calculate_tax" } }]
}
```

### Optional fields

| Field | Description |
|-------|-------------|
| `system_prompt` | System prompt for the model |
| `tags` | String array for filtering (`--tags`, `--exclude-tags`) |
| `skip` | Set to `true` to exclude from runs |
| `timeout_seconds` | Per-case timeout hint |
| `max_tool_turns` | Max tool-use iterations (default: 10) |

## Creating a new suite

Create a directory under `evals/` and add JSON case files:

```bash
mkdir -p evals/my-suite
# Add case files as .json
```

The suite will appear in `conductor-eval suites` automatically.

## Available model presets

| Preset | Provider | Model ID |
|--------|----------|----------|
| `claude-sonnet` | anthropic | claude-sonnet-4-20250514 |
| `claude-opus` | anthropic | claude-opus-4-20250514 |
| `claude-haiku` | anthropic | claude-haiku-4-5-20251001 |
| `gpt-4o` | openai | gpt-4o |
| `gpt-4o-mini` | openai | gpt-4o-mini |
| `gpt-5` | openai | gpt-5 |
| `gemini-2.5-pro` | google_gemini | gemini-2.5-pro |
| `gemini-2.5-flash` | google_gemini | gemini-2.5-flash |
| `gemini-2.5-flash-lite` | google_gemini | gemini-2.5-flash-lite |

Custom models: use `provider:model_id` format (e.g., `openai:o3-mini`).

## Key directories

| Path | Purpose |
|------|---------|
| `evals/` | Eval suite directories containing case JSON files |
| `config/model-presets.json` | Model preset definitions |
| `config/orkes-config.json` | Conductor server connection config |
| `workflows/` | Conductor workflow definitions (auto-registered) |
| `workers/` | Custom worker implementations |

## Typical agent workflow

1. `conductor-eval suites` -- discover available suites
2. `conductor-eval cases <suite>` -- inspect what's being tested
3. `conductor-eval models` -- check available models
4. `conductor-eval run <suite> --models <model1> <model2> --wait` -- run the eval
5. `conductor-eval status <id>` -- check results if not using `--wait`
6. `conductor-eval compare <run_a> <run_b>` -- compare across runs
