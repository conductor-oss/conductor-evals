"""CLI to trigger an eval suite run."""

import argparse
import csv
import io
import json
import logging
import random
import sys
import time
import uuid
from pathlib import Path

import requests

from scripts.helpers import load_config, get_execution, extract_results

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
EVALS_DIR = BASE_DIR / "evals"
MODEL_PRESETS_FILE = BASE_DIR / "config" / "model-presets.json"

POLL_INTERVAL = 5
POLL_TIMEOUT = 7200
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "TERMINATED"}

REQUIRED_FIELDS = {"id", "prompt", "agent_type", "scoring_method"}
SCORING_FIELDS = {
    "text_match": {"expected", "match_mode"},
    "llm_judge": set(),
    "tool_trace": {"expected_trace"},
}


def validate_case(case: dict, filename: str) -> list[str]:
    """Validate an eval case has required fields. Returns list of error messages."""
    errors = []
    missing = REQUIRED_FIELDS - set(case.keys())
    if missing:
        errors.append(f"{filename}: missing required fields: {missing}")

    scoring = case.get("scoring_method", "")
    if scoring in SCORING_FIELDS:
        missing_scoring = SCORING_FIELDS[scoring] - set(case.keys())
        if missing_scoring:
            errors.append(
                f"{filename}: scoring_method '{scoring}' requires fields: {missing_scoring}"
            )
    elif scoring:
        errors.append(f"{filename}: unknown scoring_method '{scoring}'")

    return errors


def load_eval_cases_from_dir(suite_dir: Path) -> list[dict]:
    """Load eval cases from JSON files in a directory, sorted by filename."""
    json_files = sorted(suite_dir.glob("*.json"))
    if not json_files:
        print(f"Error: No JSON files found in {suite_dir}")
        sys.exit(1)

    eval_cases = []
    for json_file in json_files:
        try:
            with open(json_file) as f:
                case = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {json_file}: {e}")
            sys.exit(1)

        if "id" not in case:
            case["id"] = json_file.stem

        if case.get("skip"):
            logger.info("Skipping case %s (skip=true)", case.get("id", json_file.stem))
            continue

        eval_cases.append(case)

    return eval_cases


def _load_model_presets() -> dict:
    """Load model presets from shared JSON config file."""
    try:
        with open(MODEL_PRESETS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Model presets file not found: {MODEL_PRESETS_FILE}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {MODEL_PRESETS_FILE}: {e}")
        sys.exit(1)


# Preset model configurations (loaded from config/model-presets.json)
MODEL_PRESETS = _load_model_presets()


def poll_workflow(cfg: dict, workflow_id: str) -> dict:
    """Poll workflow until it reaches a terminal status."""
    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        execution = get_execution(cfg, workflow_id)
        status = execution.get("status", "UNKNOWN")
        if status in TERMINAL_STATUSES:
            print()  # newline after dots
            return execution

        # Progress reporting: count completed sub-workflows
        tasks = execution.get("tasks", [])
        if tasks:
            completed = sum(1 for t in tasks if t.get("status") in TERMINAL_STATUSES)
            total = len(tasks)
            print(f"\r[{completed}/{total} tasks complete]", end="", flush=True)
        else:
            print(".", end="", flush=True)

        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    print()
    print(f"Timed out after {POLL_TIMEOUT}s waiting for workflow {workflow_id}")
    sys.exit(1)


def format_text(data: dict, suite_name: str) -> str:
    """Format results as plain text tables."""
    lines = []
    lines.append(
        f"Suite: {suite_name} | Run: {data['run_id']} | Status: {data['status']}"
    )
    lines.append("")

    # Model summary
    summary = data["summary"]
    if summary:
        lines.append("Model Summary")
        model_col = max(len("Model"), max((len(m) for m in summary), default=5))
        header = f"{'Model':<{model_col}}  {'Avg Score':>9}  {'Pass Rate':>9}  {'Passed':>6}  {'Total':>5}"
        lines.append(header)

        for model_id in sorted(summary):
            s = summary[model_id]
            avg = s.get("avg_score", 0.0)
            rate = s.get("pass_rate", 0.0)
            passed = s.get("passed_cases", 0)
            total = s.get("total_cases", 0)
            lines.append(
                f"{model_id:<{model_col}}  {avg:>9.3f}  {rate:>8.1f}%  {passed:>6}  {total:>5}"
            )

    # Case results
    results = data["results"]
    if results:
        lines.append("")
        lines.append("Case Results")
        case_col = max(len("Case"), max((len(c) for c in results), default=4))
        model_ids = sorted({r.get("model_id", "?") for r in results.values()})
        model_col = max(len("Model"), max((len(m) for m in model_ids), default=5))
        header = (
            f"{'Case':<{case_col}}  {'Model':<{model_col}}  {'Score':>5}  {'Passed':<6}"
        )
        lines.append(header)

        for case_id in sorted(results):
            r = results[case_id]
            model = r.get("model_id", "?")
            score = r.get("score", 0.0)
            passed = "PASS" if r.get("passed") else "FAIL"
            lines.append(
                f"{case_id:<{case_col}}  {model:<{model_col}}  {score:>5.3f}  {passed:<6}"
            )

    return "\n".join(lines)


def format_markdown(data: dict, suite_name: str) -> str:
    """Format results as markdown tables."""
    lines = []
    lines.append(f"# Eval Results: {suite_name}")
    lines.append("")
    lines.append(f"**Run ID:** {data['run_id']} | **Status:** {data['status']}")
    lines.append("")

    # Model summary
    summary = data["summary"]
    if summary:
        lines.append("## Model Summary")
        lines.append("")
        lines.append("| Model | Avg Score | Pass Rate | Passed | Total |")
        lines.append("|-------|-----------|-----------|--------|-------|")

        for model_id in sorted(summary):
            s = summary[model_id]
            avg = s.get("avg_score", 0.0)
            rate = s.get("pass_rate", 0.0)
            passed = s.get("passed_cases", 0)
            total = s.get("total_cases", 0)
            lines.append(
                f"| {model_id} | {avg:.3f} | {rate:.1f}% | {passed} | {total} |"
            )

    # Case results
    results = data["results"]
    if results:
        lines.append("")
        lines.append("## Case Results")
        lines.append("")
        lines.append("| Case | Model | Score | Passed |")
        lines.append("|------|-------|-------|--------|")

        for case_id in sorted(results):
            r = results[case_id]
            model = r.get("model_id", "?")
            score = r.get("score", 0.0)
            passed = "PASS" if r.get("passed") else "FAIL"
            lines.append(f"| {case_id} | {model} | {score:.3f} | {passed} |")

    return "\n".join(lines)


def format_json(data: dict) -> str:
    """Format results as JSON."""
    output = {
        "run_id": data["run_id"],
        "status": data["status"],
        "summary": data["summary"],
        "results": list(data["results"].values()),
    }
    return json.dumps(output, indent=2)


def format_csv(data: dict) -> str:
    """Format results as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["case_id", "model_id", "score", "passed", "response_preview"])

    for case_id in sorted(data["results"]):
        r = data["results"][case_id]
        writer.writerow(
            [
                case_id,
                r.get("model_id", ""),
                r.get("score", 0.0),
                r.get("passed", False),
                r.get("response_preview", ""),
            ]
        )

    return buf.getvalue()


FORMATTERS = {
    "text": lambda data, suite: format_text(data, suite),
    "markdown": lambda data, suite: format_markdown(data, suite),
    "json": lambda data, _suite: format_json(data),
    "csv": lambda data, _suite: format_csv(data),
}


def main():
    parser = argparse.ArgumentParser(description="Run an eval suite")
    parser.add_argument(
        "--suite", required=True, help="Eval suite name or path to eval directory"
    )
    parser.add_argument(
        "--models",
        required=True,
        nargs="+",
        help=f"Model presets ({list(MODEL_PRESETS.keys())}) or provider:model_id",
    )
    parser.add_argument(
        "--run-id", default=None, help="Custom run ID (auto-generated if omitted)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't call LLMs, use placeholder responses",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll until workflow completes, then display results",
    )
    parser.add_argument(
        "--output",
        "-o",
        choices=["text", "markdown", "json", "csv"],
        default="text",
        help="Output format when using --wait (default: text)",
    )
    parser.add_argument(
        "--tags", nargs="+", help="Only run cases matching any of these tags"
    )
    parser.add_argument(
        "--exclude-tags", nargs="+", help="Exclude cases matching any of these tags"
    )
    parser.add_argument(
        "--sample", type=int, help="Randomly sample N cases from the suite"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        help="Minimum pass rate (0.0-1.0). Exit non-zero if below. Requires --wait",
    )
    args = parser.parse_args()

    if args.threshold is not None and not args.wait:
        print("Error: --threshold requires --wait")
        sys.exit(1)

    cfg = load_config()
    run_id = args.run_id or f"run_{uuid.uuid4().hex[:12]}"

    # Resolve suite: path or name
    suite_path = Path(args.suite)
    if suite_path.is_dir():
        suite_dir = suite_path
        suite_name = suite_path.name
    else:
        suite_dir = EVALS_DIR / args.suite
        suite_name = args.suite

    if not suite_dir.exists():
        print(f"Error: Eval suite directory not found: {suite_dir}")
        sys.exit(1)

    eval_cases = load_eval_cases_from_dir(suite_dir)

    # Validate cases
    all_errors = []
    for case in eval_cases:
        errors = validate_case(case, case.get("id", "unknown"))
        all_errors.extend(errors)
    if all_errors:
        print("Eval case validation errors:")
        for err in all_errors:
            print(f"  - {err}")
        sys.exit(1)

    # Tag filtering
    total_loaded = len(eval_cases)
    if args.tags:
        eval_cases = [c for c in eval_cases if set(args.tags) & set(c.get("tags", []))]
    if args.exclude_tags:
        eval_cases = [
            c
            for c in eval_cases
            if not (set(args.exclude_tags) & set(c.get("tags", [])))
        ]

    # Random sampling
    if args.sample and args.sample < len(eval_cases):
        random.shuffle(eval_cases)
        eval_cases = eval_cases[: args.sample]

    if not eval_cases:
        print("Error: No eval cases remaining after filtering")
        sys.exit(1)

    models = []
    for m in args.models:
        if m in MODEL_PRESETS:
            models.append(MODEL_PRESETS[m])
        elif ":" in m:
            provider, model_id = m.split(":", 1)
            models.append(
                {
                    "provider": provider,
                    "model_id": model_id,
                    "params": {"max_tokens": 4096, "temperature": 0.0},
                }
            )
        else:
            print(f"Unknown model: {m}. Use a preset name or provider:model_id format.")
            sys.exit(1)

    workflow_input = {
        "suite_name": suite_name,
        "eval_cases": eval_cases,
        "run_id": run_id,
        "models": models,
        "options": {
            "dry_run": args.dry_run,
        },
    }

    filtered_count = total_loaded - len(eval_cases)
    print(f"Starting eval suite: {suite_name}")
    print(f"Run ID: {run_id}")
    if filtered_count > 0:
        print(
            f"Eval cases: {len(eval_cases)} loaded ({total_loaded} total, {filtered_count} filtered out)"
        )
    else:
        print(f"Eval cases: {len(eval_cases)} loaded from {suite_dir}")
    print(f"Models: {[m['model_id'] for m in models]}")
    print()

    try:
        resp = requests.post(
            f"{cfg['url']}/api/workflow",
            headers=cfg["get_headers"](),
            json={
                "name": "eval_suite",
                "version": 2,
                "input": workflow_input,
                "correlationId": suite_name,
            },
            timeout=30,
        )
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to Conductor at {cfg['url']}. Is the server running?")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"Request timed out connecting to Conductor at {cfg['url']}")
        sys.exit(1)

    if resp.status_code == 200:
        workflow_id = resp.text.strip().strip('"')
        print(f"Workflow started: {workflow_id}")
        print(f"Monitor: {cfg['url']}/execution/{workflow_id}")
    else:
        print(f"Failed to start workflow: {resp.status_code} {resp.text}")
        sys.exit(1)

    if args.wait:
        print("\nWaiting for workflow to complete", end="", flush=True)
        execution = poll_workflow(cfg, workflow_id)
        data = extract_results(execution)
        formatter = FORMATTERS[args.output]
        print()
        print(formatter(data, suite_name))

        # Threshold check for CI/CD
        if args.threshold is not None:
            summary = data.get("summary", {})
            if summary:
                total_passed = sum(s.get("passed_cases", 0) for s in summary.values())
                total_cases = sum(s.get("total_cases", 0) for s in summary.values())
                overall_pass_rate = total_passed / total_cases if total_cases else 0.0
                if overall_pass_rate < args.threshold:
                    print(
                        f"\nThreshold check FAILED: pass rate {overall_pass_rate:.1%} < threshold {args.threshold:.1%}"
                    )
                    sys.exit(1)
                else:
                    print(
                        f"\nThreshold check passed: pass rate {overall_pass_rate:.1%} >= threshold {args.threshold:.1%}"
                    )


if __name__ == "__main__":
    main()
