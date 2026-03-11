"""Compare two eval suite runs using Conductor execution history."""

import argparse
import json
import sys

from scripts.helpers import load_config, get_execution, extract_results


def format_comparison_text(data_a, data_b, model_deltas, case_rows):
    """Format comparison as plain text."""
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
        lines.append(f"{model:<30} {a_avg:>10.3f} {b_avg:>10.3f} {sign}{delta:>9.3f}")

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

    return "\n".join(lines)


def format_comparison_json(data_a, data_b, model_deltas, case_rows):
    """Format comparison as JSON."""
    output = {
        "run_a": {"run_id": data_a["run_id"], "status": data_a["status"]},
        "run_b": {"run_id": data_b["run_id"], "status": data_b["status"]},
        "model_comparison": [
            {"model": m, "run_a_avg": a, "run_b_avg": b, "delta": d}
            for m, a, b, d in model_deltas
        ],
        "case_comparison": [
            {"case_id": c, "model": m, "run_a_score": sa, "run_b_score": sb, "delta": d}
            for c, m, sa, sb, d in case_rows
        ],
    }
    return json.dumps(output, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Compare two eval suite runs")
    parser.add_argument("run_a", help="Workflow ID of run A")
    parser.add_argument("run_b", help="Workflow ID of run B")
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=0.0,
        help="Max allowed avg_score drop per model (default: 0.0, any drop is flagged)",
    )
    parser.add_argument(
        "--output",
        "-o",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    cfg = load_config()

    print("Fetching executions...")
    exec_a = get_execution(cfg, args.run_a)
    exec_b = get_execution(cfg, args.run_b)

    data_a = extract_results(exec_a)
    data_b = extract_results(exec_b)

    # Build model comparison data
    all_models = sorted(
        set(list(data_a["summary"].keys()) + list(data_b["summary"].keys()))
    )
    model_deltas = []
    for model in all_models:
        a_avg = data_a["summary"].get(model, {}).get("avg_score", 0.0)
        b_avg = data_b["summary"].get(model, {}).get("avg_score", 0.0)
        delta = b_avg - a_avg
        model_deltas.append((model, a_avg, b_avg, delta))

    # Build case comparison data
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
        delta = s_b - s_a
        case_rows.append((case_id, model, s_a, s_b, delta))

    # Output
    if args.output == "json":
        print(format_comparison_json(data_a, data_b, model_deltas, case_rows))
    else:
        print(f"\n{format_comparison_text(data_a, data_b, model_deltas, case_rows)}")

    # Regression detection
    regressions = []
    for model, a_avg, b_avg, delta in model_deltas:
        if delta < -args.regression_threshold:
            regressions.append((model, delta))

    if regressions:
        print(f"\nREGRESSION DETECTED (threshold: {args.regression_threshold:.3f})")
        for model, delta in regressions:
            print(f"  {model}: {delta:+.3f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
