"""Unified CLI for the conductor-evals system.

Usage:
    conductor-eval <command> [options]

Commands:
    workers                Start Conductor task workers (auto-registers workflows)
    server                 Start the web UI server

    suites                 List all eval suites
    cases <suite>          List cases in a suite
    models                 List available model presets

    run <suite>            Run an eval suite
    runs [--suite <suite>] List past runs
    status <run_id>        Show run status and results
    cancel <run_id>        Cancel a running eval
    compare <a> <b>        Compare two runs
"""

import argparse
import csv
import io
import json
import random
import sys
import time
import uuid
from pathlib import Path

import requests

from scripts.helpers import load_config, get_execution, extract_results

BASE_DIR = Path(__file__).parent.parent
EVALS_DIR = BASE_DIR / "evals"
MODEL_PRESETS_FILE = BASE_DIR / "config" / "model-presets.json"

POLL_INTERVAL = 5
POLL_TIMEOUT = 7200
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "TERMINATED"}
REQUEST_TIMEOUT = 30

REQUIRED_FIELDS = {"id", "prompt", "agent_type", "scoring_method"}
SCORING_FIELDS = {
    "text_match": {"expected", "match_mode"},
    "llm_judge": set(),
    "tool_trace": {"expected_trace"},
}


def _load_model_presets() -> dict:
    try:
        with open(MODEL_PRESETS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Model presets file not found: {MODEL_PRESETS_FILE}")
        sys.exit(1)


def validate_case(case: dict, filename: str) -> list[str]:
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
            continue
        eval_cases.append(case)
    return eval_cases


def resolve_models(model_names: list[str], presets: dict) -> list[dict]:
    models = []
    for m in model_names:
        if m in presets:
            models.append(presets[m])
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
            print(f"Available presets: {', '.join(presets.keys())}")
            sys.exit(1)
    return models


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_workers(args):
    """Start Conductor task workers."""
    from scripts.workers_main import main as workers_main

    workers_main()


def cmd_server(args):
    """Start the web UI server."""
    from scripts.server_app import main as server_main

    server_main()


def cmd_suites(args):
    """List all eval suites."""
    if not EVALS_DIR.exists():
        print("No evals directory found.")
        return
    suites = []
    for d in sorted(EVALS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        cases = list(d.glob("*.json"))
        suites.append((d.name, len(cases)))
    if not suites:
        print("No suites found.")
        return
    name_col = max(len("Suite"), max(len(s[0]) for s in suites))
    print(f"{'Suite':<{name_col}}  {'Cases':>5}")
    print(f"{'-' * name_col}  {'-' * 5}")
    for name, count in suites:
        print(f"{name:<{name_col}}  {count:>5}")


def cmd_cases(args):
    """List cases in a suite."""
    suite_dir = EVALS_DIR / args.suite
    if not suite_dir.exists():
        print(f"Suite not found: {args.suite}")
        sys.exit(1)
    cases = []
    for f in sorted(suite_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            cases.append(
                {
                    "id": data.get("id", f.stem),
                    "agent_type": data.get("agent_type", ""),
                    "scoring": data.get("scoring_method", ""),
                    "skip": data.get("skip", False),
                }
            )
        except json.JSONDecodeError:
            cases.append(
                {"id": f.stem, "agent_type": "?", "scoring": "?", "skip": False}
            )
    if not cases:
        print("No cases found.")
        return
    id_col = max(len("Case"), max(len(c["id"]) for c in cases))
    at_col = max(len("Agent Type"), max(len(c["agent_type"]) for c in cases))
    sc_col = max(len("Scoring"), max(len(c["scoring"]) for c in cases))
    print(f"{'Case':<{id_col}}  {'Agent Type':<{at_col}}  {'Scoring':<{sc_col}}  Skip")
    print(f"{'-' * id_col}  {'-' * at_col}  {'-' * sc_col}  ----")
    for c in cases:
        skip = "yes" if c["skip"] else ""
        print(
            f"{c['id']:<{id_col}}  {c['agent_type']:<{at_col}}  {c['scoring']:<{sc_col}}  {skip}"
        )


def cmd_models(args):
    """List available model presets."""
    presets = _load_model_presets()
    id_col = max(len("Preset"), max(len(k) for k in presets))
    prov_col = max(len("Provider"), max(len(v["provider"]) for v in presets.values()))
    mod_col = max(len("Model ID"), max(len(v["model_id"]) for v in presets.values()))
    print(f"{'Preset':<{id_col}}  {'Provider':<{prov_col}}  {'Model ID':<{mod_col}}")
    print(f"{'-' * id_col}  {'-' * prov_col}  {'-' * mod_col}")
    for name, cfg in presets.items():
        print(
            f"{name:<{id_col}}  {cfg['provider']:<{prov_col}}  {cfg['model_id']:<{mod_col}}"
        )


def cmd_run(args):
    """Run an eval suite."""
    presets = _load_model_presets()
    cfg = load_config()
    run_id = args.run_id or f"run_{uuid.uuid4().hex[:12]}"

    # Resolve suite path
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

    # Validate
    all_errors = []
    for case in eval_cases:
        all_errors.extend(validate_case(case, case.get("id", "unknown")))
    if all_errors:
        print("Validation errors:")
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
    if args.sample and args.sample < len(eval_cases):
        random.shuffle(eval_cases)
        eval_cases = eval_cases[: args.sample]

    if not eval_cases:
        print("Error: No eval cases remaining after filtering")
        sys.exit(1)

    models = resolve_models(args.models, presets)

    workflow_input = {
        "suite_name": suite_name,
        "eval_cases": eval_cases,
        "run_id": run_id,
        "models": models,
        "options": {"dry_run": args.dry_run},
    }

    filtered_count = total_loaded - len(eval_cases)
    print(f"Starting eval suite: {suite_name}")
    print(f"Run ID: {run_id}")
    if filtered_count > 0:
        print(f"Eval cases: {len(eval_cases)} ({filtered_count} filtered out)")
    else:
        print(f"Eval cases: {len(eval_cases)}")
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
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to Conductor at {cfg['url']}. Is the server running?")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"Request timed out connecting to Conductor at {cfg['url']}")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"Failed to start workflow: {resp.status_code} {resp.text}")
        sys.exit(1)

    workflow_id = resp.text.strip().strip('"')
    print(f"Workflow started: {workflow_id}")
    print(f"Monitor: {cfg['url']}/execution/{workflow_id}")

    if args.wait:
        print("\nWaiting for completion", end="", flush=True)
        execution = _poll_workflow(cfg, workflow_id)
        data = extract_results(execution)
        print()
        print(_format_results(data, suite_name, args.output))

        if args.threshold is not None:
            summary = data.get("summary", {})
            if summary:
                total_passed = sum(s.get("passed_cases", 0) for s in summary.values())
                total_cases = sum(s.get("total_cases", 0) for s in summary.values())
                rate = total_passed / total_cases if total_cases else 0.0
                if rate < args.threshold:
                    print(f"\nThreshold FAILED: {rate:.1%} < {args.threshold:.1%}")
                    sys.exit(1)
                else:
                    print(f"\nThreshold passed: {rate:.1%} >= {args.threshold:.1%}")


def cmd_runs(args):
    """List past runs."""
    cfg = load_config()
    query = "workflowType IN (eval_suite)"
    if args.suite:
        query += f" AND correlationId IN ({args.suite})"

    try:
        resp = requests.get(
            f"{cfg['url']}/api/workflow/search",
            headers=cfg["get_headers"](),
            params={"query": query, "start": 0, "size": args.limit},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to Conductor at {cfg['url']}.")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"Search failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    results = resp.json().get("results", [])
    if not results:
        print("No runs found.")
        return

    if args.output == "json":
        rows = []
        for r in results:
            rows.append(
                {
                    "workflow_id": r.get("workflowId", ""),
                    "suite": r.get("correlationId", ""),
                    "status": r.get("status", ""),
                    "started": r.get("startTime", ""),
                }
            )
        print(json.dumps(rows, indent=2))
        return

    wf_col = max(len("Workflow ID"), max(len(r.get("workflowId", "")) for r in results))
    suite_col = max(len("Suite"), max(len(r.get("correlationId", "")) for r in results))
    print(f"{'Workflow ID':<{wf_col}}  {'Suite':<{suite_col}}  {'Status':<12}  Started")
    print(f"{'-' * wf_col}  {'-' * suite_col}  {'-' * 12}  -------")
    for r in results:
        print(
            f"{r.get('workflowId', ''):<{wf_col}}  {r.get('correlationId', ''):<{suite_col}}  {r.get('status', ''):<12}  {r.get('startTime', '')}"
        )


def cmd_status(args):
    """Show run status and results."""
    cfg = load_config()
    execution = get_execution(cfg, args.run_id)
    status = execution.get("status", "UNKNOWN")
    wf_input = execution.get("input", {})
    suite_name = wf_input.get("suite_name", "")
    models = [
        m.get("model_id", str(m)) if isinstance(m, dict) else str(m)
        for m in wf_input.get("models", [])
    ]

    print(f"Run:    {args.run_id}")
    print(f"Suite:  {suite_name}")
    print(f"Models: {models}")
    print(f"Status: {status}")

    if status in TERMINAL_STATUSES:
        data = extract_results(execution)
        print()
        print(_format_results(data, suite_name, args.output))
    else:
        # Show progress
        tasks = execution.get("tasks", [])
        if tasks:
            completed = sum(1 for t in tasks if t.get("status") in TERMINAL_STATUSES)
            print(f"Progress: {completed}/{len(tasks)} tasks complete")
        if execution.get("reasonForIncompletion"):
            print(f"Error: {execution['reasonForIncompletion']}")


def cmd_cancel(args):
    """Cancel a running eval."""
    cfg = load_config()
    try:
        resp = requests.delete(
            f"{cfg['url']}/api/workflow/{args.run_id}",
            headers=cfg["get_headers"](),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to Conductor at {cfg['url']}.")
        sys.exit(1)

    if resp.status_code == 200:
        print(f"Cancelled: {args.run_id}")
    else:
        print(f"Failed to cancel: {resp.status_code} {resp.text}")
        sys.exit(1)


def cmd_compare(args):
    """Compare two runs."""
    cfg = load_config()

    print("Fetching executions...")
    exec_a = get_execution(cfg, args.run_a)
    exec_b = get_execution(cfg, args.run_b)

    data_a = extract_results(exec_a)
    data_b = extract_results(exec_b)

    all_models = sorted(
        set(list(data_a["summary"].keys()) + list(data_b["summary"].keys()))
    )
    model_deltas = []
    for model in all_models:
        a_avg = data_a["summary"].get(model, {}).get("avg_score", 0.0)
        b_avg = data_b["summary"].get(model, {}).get("avg_score", 0.0)
        model_deltas.append((model, a_avg, b_avg, b_avg - a_avg))

    all_cases = sorted(
        set(list(data_a["results"].keys()) + list(data_b["results"].keys()))
    )
    case_rows = []
    for case_id in all_cases:
        r_a = data_a["results"].get(case_id, {})
        r_b = data_b["results"].get(case_id, {})
        model = r_a.get("model_id", r_b.get("model_id", "?"))
        s_a = r_a.get("score", 0.0)
        s_b = r_b.get("score", 0.0)
        case_rows.append((case_id, model, s_a, s_b, s_b - s_a))

    if args.output == "json":
        output = {
            "run_a": {"run_id": data_a["run_id"], "status": data_a["status"]},
            "run_b": {"run_id": data_b["run_id"], "status": data_b["status"]},
            "model_comparison": [
                {"model": m, "run_a_avg": a, "run_b_avg": b, "delta": d}
                for m, a, b, d in model_deltas
            ],
            "case_comparison": [
                {
                    "case_id": c,
                    "model": m,
                    "run_a_score": sa,
                    "run_b_score": sb,
                    "delta": d,
                }
                for c, m, sa, sb, d in case_rows
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        lines = []
        lines.append(f"{'=' * 70}")
        lines.append(f"Run A: {data_a['run_id']} ({data_a['status']})")
        lines.append(f"Run B: {data_b['run_id']} ({data_b['status']})")
        lines.append(f"{'=' * 70}")
        lines.append("")
        lines.append(f"{'Model':<30} {'Run A Avg':>10} {'Run B Avg':>10} {'Delta':>10}")
        lines.append(f"{'-' * 30} {'-' * 10} {'-' * 10} {'-' * 10}")
        for model, a_avg, b_avg, delta in model_deltas:
            sign = "+" if delta > 0 else ""
            lines.append(
                f"{model:<30} {a_avg:>10.3f} {b_avg:>10.3f} {sign}{delta:>9.3f}"
            )
        if case_rows:
            lines.append(
                f"\n{'Case':<25} {'Model':<25} {'Run A':>8} {'Run B':>8} {'Delta':>8}"
            )
            lines.append(f"{'-' * 25} {'-' * 25} {'-' * 8} {'-' * 8} {'-' * 8}")
            for case_id, model, s_a, s_b, delta in case_rows:
                sign = "+" if delta > 0 else ""
                lines.append(
                    f"{case_id:<25} {model:<25} {s_a:>8.3f} {s_b:>8.3f} {sign}{delta:>7.3f}"
                )
        print("\n".join(lines))

    # Regression detection
    regressions = [
        (m, d) for m, _a, _b, d in model_deltas if d < -args.regression_threshold
    ]
    if regressions:
        print(f"\nREGRESSION DETECTED (threshold: {args.regression_threshold:.3f})")
        for model, delta in regressions:
            print(f"  {model}: {delta:+.3f}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poll_workflow(cfg: dict, workflow_id: str) -> dict:
    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        execution = get_execution(cfg, workflow_id)
        status = execution.get("status", "UNKNOWN")
        if status in TERMINAL_STATUSES:
            print()
            return execution
        tasks = execution.get("tasks", [])
        if tasks:
            completed = sum(1 for t in tasks if t.get("status") in TERMINAL_STATUSES)
            print(f"\r[{completed}/{len(tasks)} tasks complete]", end="", flush=True)
        else:
            print(".", end="", flush=True)
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    print()
    print(f"Timed out after {POLL_TIMEOUT}s")
    sys.exit(1)


def _format_results(data: dict, suite_name: str, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(
            {
                "run_id": data["run_id"],
                "status": data["status"],
                "summary": data["summary"],
                "results": list(data["results"].values()),
            },
            indent=2,
        )
    if fmt == "csv":
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
    if fmt == "markdown":
        lines = [
            f"# Eval Results: {suite_name}",
            "",
            f"**Run ID:** {data['run_id']} | **Status:** {data['status']}",
            "",
        ]
        summary = data["summary"]
        if summary:
            lines += [
                "## Model Summary",
                "",
                "| Model | Avg Score | Pass Rate | Passed | Total |",
                "|-------|-----------|-----------|--------|-------|",
            ]
            for mid in sorted(summary):
                s = summary[mid]
                lines.append(
                    f"| {mid} | {s.get('avg_score', 0):.3f} | {s.get('pass_rate', 0) * 100:.1f}% | {s.get('passed_cases', 0)} | {s.get('total_cases', 0)} |"
                )
        results = data["results"]
        if results:
            lines += [
                "",
                "## Case Results",
                "",
                "| Case | Model | Score | Passed |",
                "|------|-------|-------|--------|",
            ]
            for cid in sorted(results):
                r = results[cid]
                lines.append(
                    f"| {cid} | {r.get('model_id', '?')} | {r.get('score', 0):.3f} | {'PASS' if r.get('passed') else 'FAIL'} |"
                )
        return "\n".join(lines)

    # Default: text
    lines = [
        f"Suite: {suite_name} | Run: {data['run_id']} | Status: {data['status']}",
        "",
    ]
    summary = data["summary"]
    if summary:
        lines.append("Model Summary")
        model_col = max(len("Model"), max(len(m) for m in summary))
        lines.append(
            f"{'Model':<{model_col}}  {'Avg Score':>9}  {'Pass Rate':>9}  {'Passed':>6}  {'Total':>5}"
        )
        for mid in sorted(summary):
            s = summary[mid]
            lines.append(
                f"{mid:<{model_col}}  {s.get('avg_score', 0):>9.3f}  {s.get('pass_rate', 0) * 100:>8.1f}%  {s.get('passed_cases', 0):>6}  {s.get('total_cases', 0):>5}"
            )
    results = data["results"]
    if results:
        lines.append("")
        lines.append("Case Results")
        case_col = max(len("Case"), max(len(c) for c in results))
        model_ids = sorted({r.get("model_id", "?") for r in results.values()})
        model_col = max(len("Model"), max(len(m) for m in model_ids))
        lines.append(
            f"{'Case':<{case_col}}  {'Model':<{model_col}}  {'Score':>5}  {'Passed':<6}"
        )
        for cid in sorted(results):
            r = results[cid]
            lines.append(
                f"{cid:<{case_col}}  {r.get('model_id', '?'):<{model_col}}  {r.get('score', 0):>5.3f}  {'PASS' if r.get('passed') else 'FAIL':<6}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        prog="conductor-eval", description="Conductor Evals CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # workers
    sub.add_parser("workers", help="Start Conductor task workers (auto-registers)")

    # server
    sub.add_parser("server", help="Start the web UI server")

    # suites
    sub.add_parser("suites", help="List all eval suites")

    # cases
    p_cases = sub.add_parser("cases", help="List cases in a suite")
    p_cases.add_argument("suite", help="Suite name")

    # models
    sub.add_parser("models", help="List available model presets")

    # run
    p_run = sub.add_parser("run", help="Run an eval suite")
    p_run.add_argument("suite", help="Suite name or path")
    p_run.add_argument(
        "--models", required=True, nargs="+", help="Model presets or provider:model_id"
    )
    p_run.add_argument("--run-id", default=None, help="Custom run ID")
    p_run.add_argument("--dry-run", action="store_true", help="Don't call LLMs")
    p_run.add_argument(
        "--wait", action="store_true", help="Wait for completion and show results"
    )
    p_run.add_argument(
        "--output",
        "-o",
        choices=["text", "markdown", "json", "csv"],
        default="text",
        help="Output format (with --wait)",
    )
    p_run.add_argument("--tags", nargs="+", help="Only run cases with these tags")
    p_run.add_argument(
        "--exclude-tags", nargs="+", help="Exclude cases with these tags"
    )
    p_run.add_argument("--sample", type=int, help="Randomly sample N cases")
    p_run.add_argument(
        "--threshold",
        type=float,
        help="Min pass rate (0-1). Exit 1 if below. Requires --wait",
    )

    # runs
    p_runs = sub.add_parser("runs", help="List past runs")
    p_runs.add_argument("--suite", default=None, help="Filter by suite")
    p_runs.add_argument(
        "--limit", type=int, default=20, help="Max results (default: 20)"
    )
    p_runs.add_argument("--output", "-o", choices=["text", "json"], default="text")

    # status
    p_status = sub.add_parser("status", help="Show run status and results")
    p_status.add_argument("run_id", help="Workflow ID")
    p_status.add_argument(
        "--output", "-o", choices=["text", "markdown", "json", "csv"], default="text"
    )

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel a running eval")
    p_cancel.add_argument("run_id", help="Workflow ID")

    # compare
    p_compare = sub.add_parser("compare", help="Compare two runs")
    p_compare.add_argument("run_a", help="Workflow ID of run A")
    p_compare.add_argument("run_b", help="Workflow ID of run B")
    p_compare.add_argument(
        "--regression-threshold", type=float, default=0.0, help="Max allowed score drop"
    )
    p_compare.add_argument("--output", "-o", choices=["text", "json"], default="text")

    args = parser.parse_args()

    commands = {
        "workers": cmd_workers,
        "server": cmd_server,
        "suites": cmd_suites,
        "cases": cmd_cases,
        "models": cmd_models,
        "run": cmd_run,
        "runs": cmd_runs,
        "status": cmd_status,
        "cancel": cmd_cancel,
        "compare": cmd_compare,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
