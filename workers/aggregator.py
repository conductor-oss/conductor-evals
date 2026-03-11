import logging
from conductor.client.worker.worker_task import worker_task

logger = logging.getLogger(__name__)


@worker_task(task_definition_name="record_result")
def record_result(
    case_id: str,
    model: dict,
    run_id: str,
    agent_output: dict,
    scoring_method: str = "",
    text_match_result: dict = None,
    llm_judge_result: dict = None,
    tool_trace_result: dict = None,
) -> dict:
    # Pick the scorer result based on which SWITCH branch ran
    scoring_details = text_match_result or llm_judge_result or tool_trace_result or {}
    score = scoring_details.get("score", 0.0) if scoring_details else 0.0
    passed = scoring_details.get("passed", False) if scoring_details else False

    return {
        "case_id": case_id,
        "model_id": model.get("model_id", "unknown"),
        "provider": model.get("provider", "unknown"),
        "run_id": run_id,
        "score": score,
        "passed": passed,
        "response_preview": (agent_output.get("response", "") or "")[:500],
        "latency_ms": agent_output.get("latency_ms", 0),
        "token_usage": agent_output.get("token_usage", {}),
        "scoring_details": scoring_details,
        "tool_calls": agent_output.get("tool_calls", []),
    }


@worker_task(task_definition_name="aggregate_results")
def aggregate_results(
    results: dict, suite_name: str, models: object, run_id: str
) -> dict:
    # results comes from JOIN — it's a dict of taskRefName → sub-workflow output
    all_results = []
    failed_cases = 0
    for ref_name, output in (results or {}).items():
        if isinstance(output, dict) and "result" in output:
            all_results.append(output["result"])
        elif isinstance(output, dict) and "case_id" in output:
            all_results.append(output)
        else:
            failed_cases += 1
            logger.warning("Skipping failed sub-workflow output for %s", ref_name)

    # Per-model aggregation
    model_scores = {}
    for r in all_results:
        mid = r.get("model_id", "unknown")
        if mid not in model_scores:
            model_scores[mid] = {"scores": [], "passed": 0, "total": 0}
        score = r.get("score", 0.0)
        model_scores[mid]["scores"].append(score)
        model_scores[mid]["total"] += 1
        if r.get("passed", False):
            model_scores[mid]["passed"] += 1

    summary = {}
    for mid, data in model_scores.items():
        scores = data["scores"]
        summary[mid] = {
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
            "pass_rate": data["passed"] / data["total"] if data["total"] else 0.0,
            "total_cases": data["total"],
            "passed_cases": data["passed"],
        }

    return {
        "suite_name": suite_name,
        "run_id": run_id,
        "summary": summary,
        "results": all_results,
        "total_cases": len(all_results),
        "failed_cases": failed_cases,
    }
