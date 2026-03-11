import logging
from conductor.client.worker.worker_task import worker_task

logger = logging.getLogger(__name__)


@worker_task(task_definition_name="execute_agent")
def execute_agent(eval_case: dict, model: dict) -> dict:
    """Execute agent for claude_code_agent mode only.

    direct_llm and tool_use_agent are handled by Conductor's built-in
    LLM_CHAT_COMPLETE system task. API keys are configured on the Conductor
    server, not in worker env vars.
    """
    agent_type = eval_case.get("agent_type")

    if agent_type == "claude_code_agent":
        from providers.claude_code_provider import ClaudeCodeProvider

        provider = ClaudeCodeProvider(model_id=model.get("model_id", ""))
        prompt = eval_case["prompt"]
        system_prompt = eval_case.get("system_prompt")
        logger.info(
            "Executing claude_code_agent for case %s with model %s",
            eval_case.get("id", "?"),
            model.get("model_id", "?"),
        )
        return provider.call(prompt, system_prompt)
    else:
        raise ValueError(
            f"Unsupported agent_type for custom worker: {agent_type}. "
            "Use LLM_CHAT_COMPLETE system task for direct_llm and tool_use_agent."
        )
