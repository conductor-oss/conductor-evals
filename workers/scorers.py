import json
import logging
import re
from conductor.client.worker.worker_task import worker_task

logger = logging.getLogger(__name__)


@worker_task(task_definition_name="score_text_match")
def score_text_match(agent_output: str, expected: dict, match_mode: str) -> dict:
    agent_output = str(agent_output or "")
    expected = expected or {}
    match_mode = match_mode or "contains"

    if match_mode == "exact":
        passed = agent_output.strip() == expected.get("value", "").strip()
        score = 1.0 if passed else 0.0
        details = "Exact match" if passed else f"Expected: {expected.get('value')!r}"

    elif match_mode == "contains":
        value = expected.get("value", "")
        passed = value in agent_output
        score = 1.0 if passed else 0.0
        details = f"Contains '{value}': {passed}"

    elif match_mode == "regex":
        pattern = expected.get("pattern", "")
        passed = bool(re.search(pattern, agent_output))
        score = 1.0 if passed else 0.0
        details = f"Regex '{pattern}': {passed}"

    elif match_mode == "contains_all":
        values = expected.get("values", [])
        matched = [v for v in values if v in agent_output]
        score = len(matched) / len(values) if values else 1.0
        passed = score == 1.0
        details = f"Matched {len(matched)}/{len(values)}: {matched}"

    elif match_mode == "contains_any":
        values = expected.get("values", [])
        matched = [v for v in values if v in agent_output]
        passed = len(matched) > 0
        score = 1.0 if passed else 0.0
        details = f"Matched any: {matched}"

    else:
        passed = False
        score = 0.0
        details = f"Unknown match_mode: {match_mode}"

    return {"score": score, "passed": passed, "details": details}


@worker_task(task_definition_name="parse_judge_output")
def parse_judge_output(judge_result: str) -> dict:
    """Parse the JSON output from the LLM_CHAT_COMPLETE judge system task.

    The LLM_CHAT_COMPLETE task with jsonOutput=true returns the result as a string.
    This worker parses it and normalizes the 1-5 score to 0.0-1.0.
    """
    if not judge_result:
        logger.warning("No judge output received")
        return {
            "score": 0.0,
            "raw_score": 0,
            "passed": False,
            "reasoning": "No judge output",
        }

    try:
        result = (
            json.loads(judge_result) if isinstance(judge_result, str) else judge_result
        )
        raw_score = result.get("score", 1)
        reasoning = result.get("reasoning", "")
    except (json.JSONDecodeError, TypeError):
        match = re.search(r'"score"\s*:\s*(\d+)', str(judge_result))
        raw_score = int(match.group(1)) if match else 1
        reasoning = str(judge_result)

    normalized_score = (raw_score - 1) / 4.0  # 1-5 → 0.0-1.0
    normalized_score = max(0.0, min(1.0, normalized_score))
    passed = normalized_score >= 0.5  # score >= 3 out of 5

    return {
        "score": normalized_score,
        "raw_score": raw_score,
        "passed": passed,
        "reasoning": reasoning,
    }


@worker_task(task_definition_name="score_tool_trace")
def score_tool_trace(
    tool_calls: object, expected_trace: object, strict_order: bool = True
) -> dict:
    if not expected_trace:
        return {
            "score": 1.0,
            "passed": True,
            "missing": [],
            "extra": [],
            "details": "No trace expected",
        }

    tool_calls = tool_calls if isinstance(tool_calls, list) else []
    actual_calls = [
        {"tool_name": tc["tool_name"], "args": tc.get("args", {})} for tc in tool_calls
    ]
    missing = []
    matched = []

    if strict_order:
        actual_idx = 0
        for exp in expected_trace:
            found = False
            while actual_idx < len(actual_calls):
                if _trace_matches(actual_calls[actual_idx], exp):
                    matched.append(exp)
                    actual_idx += 1
                    found = True
                    break
                actual_idx += 1
            if not found:
                missing.append(exp)
    else:
        remaining = list(actual_calls)
        for exp in expected_trace:
            found = False
            for i, actual in enumerate(remaining):
                if _trace_matches(actual, exp):
                    matched.append(exp)
                    remaining.pop(i)
                    found = True
                    break
            if not found:
                missing.append(exp)

    expected_names = {e["tool_name"] for e in expected_trace}
    extra = [tc for tc in actual_calls if tc["tool_name"] not in expected_names]

    score = len(matched) / len(expected_trace) if expected_trace else 1.0
    passed = score == 1.0

    return {
        "score": score,
        "passed": passed,
        "missing": missing,
        "extra": extra,
        "details": f"Matched {len(matched)}/{len(expected_trace)} expected calls",
    }


def _trace_matches(actual: dict, expected: dict) -> bool:
    if actual["tool_name"] != expected["tool_name"]:
        return False
    args_contain = expected.get("args_contain", {})
    for key, value in args_contain.items():
        if key not in actual["args"]:
            return False
        if str(value) not in str(actual["args"][key]):
            return False
    return True
