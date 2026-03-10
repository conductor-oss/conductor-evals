import json
import subprocess
import time


class ClaudeCodeProvider:
    """Provider that shells out to the Claude Code CLI."""

    def __init__(self, model_id: str, params: dict | None = None):
        self.model_id = model_id
        self.params = params or {}

    def call(self, prompt: str, system_prompt: str | None = None) -> dict:
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])
        if self.model_id:
            cmd.extend(["--model", self.model_id])

        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        latency_ms = int((time.time() - start) * 1000)

        if result.returncode != 0:
            return {
                "response": f"[claude code error: {result.stderr.strip()}]",
                "tool_calls": [],
                "token_usage": {"input_tokens": 0, "output_tokens": 0},
                "latency_ms": latency_ms,
            }

        try:
            output = json.loads(result.stdout)
            return {
                "response": output.get("result", result.stdout),
                "tool_calls": output.get("tool_calls", []),
                "token_usage": output.get("usage", {"input_tokens": 0, "output_tokens": 0}),
                "latency_ms": latency_ms,
            }
        except json.JSONDecodeError:
            return {
                "response": result.stdout.strip(),
                "tool_calls": [],
                "token_usage": {"input_tokens": 0, "output_tokens": 0},
                "latency_ms": latency_ms,
            }
