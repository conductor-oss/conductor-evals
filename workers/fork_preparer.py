import logging
import re
from conductor.client.worker.worker_task import worker_task

logger = logging.getLogger(__name__)


def _sanitize(s: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '_', s)


@worker_task(task_definition_name='prepare_fork_inputs')
def prepare_fork_inputs(eval_cases: object, models: object, run_id: str) -> dict:
    dynamic_tasks = []
    dynamic_tasks_inputs = {}

    for case in eval_cases:
        for model in models:
            case_id = case["id"]
            model_id = _sanitize(model["model_id"])
            ref_name = f"eval_case_run_{case_id}_{model_id}"

            dynamic_tasks.append({
                "name": "eval_case_run",
                "taskReferenceName": ref_name,
                "type": "SUB_WORKFLOW",
                "subWorkflowParam": {
                    "name": "eval_case_run",
                    "version": 1,
                },
            })

            dynamic_tasks_inputs[ref_name] = {
                "eval_case": case,
                "model": model,
                "run_id": run_id,
            }

    logger.info("Prepared %d dynamic tasks for %d cases x %d models",
                len(dynamic_tasks), len(eval_cases), len(models))
    return {
        "dynamicTasks": dynamic_tasks,
        "dynamicTasksInputs": dynamic_tasks_inputs,
    }
