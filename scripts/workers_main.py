"""Start the Conductor task workers for the eval workflow system.

Note: LLM calls for direct_llm, tool_use_agent, and llm_judge scoring are
handled by Conductor's built-in LLM_CHAT_COMPLETE system task. Custom workers
are only needed for: fork_preparer, agent_executor (claude_code only),
scorers (text_match, parse_judge_output, tool_trace), and aggregator.
Eval case loading is handled client-side by run_suite.py.
"""

import json
import logging
import os
import sys
from pathlib import Path

from conductor.client.automator.task_handler import TaskHandler
from conductor.client.configuration.configuration import Configuration

# Import modules so @worker_task decorators register the workers
import workers.fork_preparer  # noqa: F401
import workers.agent_executor  # noqa: F401
import workers.scorers  # noqa: F401
import workers.aggregator  # noqa: F401

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "config" / "orkes-config.json"


def main():
    # Check environment variables first
    env_url = os.environ.get("CONDUCTOR_URL")
    env_key = os.environ.get("CONDUCTOR_AUTH_KEY")
    env_secret = os.environ.get("CONDUCTOR_AUTH_SECRET")

    if env_url and env_key and env_secret:
        server_url = env_url.rstrip("/").removesuffix("/api")
        key_id = env_key
        key_secret = env_secret
    else:
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
        except FileNotFoundError:
            logger.error("Config file not found: %s", CONFIG_FILE)
            logger.error(
                "Set CONDUCTOR_URL, CONDUCTOR_AUTH_KEY, and CONDUCTOR_AUTH_SECRET env vars, "
                "or create the config file from config/orkes-config.example.json"
            )
            sys.exit(1)

        cluster = config["clusters"][0]
        server_url = cluster["url"]
        key_id = cluster.get("keyId")
        key_secret = cluster.get("keySecret")

    configuration = Configuration(
        server_api_url=f"{server_url}/api",
        authentication_settings=None,
        debug=False,
    )

    # If auth keys are provided, set them
    if key_id:
        from conductor.client.configuration.settings.authentication_settings import (
            AuthenticationSettings,
        )

        configuration.authentication_settings = AuthenticationSettings(
            key_id=key_id,
            key_secret=key_secret,
        )

    logger.info("Connecting to Conductor at %s", server_url)

    # Auto-register tasks and workflows on startup
    try:
        from scripts.register import load_config, register_tasks, register_workflows

        cfg = load_config()
        logger.info("Registering task definitions and workflows...")
        register_tasks(cfg)
        register_workflows(cfg)
        logger.info("Registration complete.")
    except Exception as e:
        logger.warning(
            "Auto-registration failed: %s. Continuing with worker startup.", e
        )

    logger.info("Starting workers (scan_for_annotated_workers=True)...")

    task_handler = TaskHandler(
        configuration=configuration,
        scan_for_annotated_workers=True,
        import_modules=[
            "workers.fork_preparer",
            "workers.agent_executor",
            "workers.scorers",
            "workers.aggregator",
        ],
    )
    task_handler.start_processes()

    logger.info("Workers running. Press Ctrl+C to stop.")
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        task_handler.stop_processes()


if __name__ == "__main__":
    main()
