"""Register task definitions and workflows with the Conductor server.

AI provider setup (for LLM_CHAT_COMPLETE system tasks):
  Conductor OSS auto-registers providers when API key env vars are set on the server:
    - ANTHROPIC_API_KEY for Anthropic (Claude)
    - OPENAI_API_KEY for OpenAI (GPT)
  Also requires: conductor.integrations.ai.enabled=true in server properties.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "config" / "orkes-config.json"
TASKS_DIR = BASE_DIR / "tasks"
WORKFLOWS_DIR = BASE_DIR / "workflows"

REQUEST_TIMEOUT = 30


class _TokenManager:
    """Manages JWT token lifecycle for Orkes Conductor authentication."""

    _EXPIRY_BUFFER_S = 5 * 60
    _DEFAULT_TTL_S = 24 * 60 * 60

    def __init__(self, conductor_url: str, key_id: str, key_secret: str):
        self._conductor_url = conductor_url
        self._key_id = key_id
        self._key_secret = key_secret
        self._token: str | None = None
        self._expires_at: float = 0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        return self._refresh()

    def _refresh(self) -> str:
        resp = requests.post(
            f"{self._conductor_url}/api/token",
            json={"keyId": self._key_id, "keySecret": self._key_secret},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to obtain Conductor auth token: {resp.status_code} {resp.text}"
            )
        self._token = resp.json()["token"]
        self._expires_at = time.time() + self._DEFAULT_TTL_S - self._EXPIRY_BUFFER_S
        return self._token


def load_config() -> dict:
    # Check environment variables first
    env_url = os.environ.get("CONDUCTOR_URL")
    env_key = os.environ.get("CONDUCTOR_AUTH_KEY")
    env_secret = os.environ.get("CONDUCTOR_AUTH_SECRET")

    if env_url and env_key:
        url = env_url.rstrip("/").removesuffix("/api")
        key_id = env_key
        key_secret = env_secret
    else:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        cluster = config["clusters"][0]
        url = cluster["url"].rstrip("/").removesuffix("/api")
        key_id = cluster["keyId"]
        key_secret = cluster.get("keySecret")

    if key_secret:
        mgr = _TokenManager(url, key_id, key_secret)
        get_headers = lambda: {  # noqa: E731
            "Content-Type": "application/json",
            "X-Authorization": mgr.get_token(),
        }
    else:
        static = {
            "Content-Type": "application/json",
            "X-Authorization": key_id,
        }
        get_headers = lambda: static  # noqa: E731

    return {
        "url": url,
        "get_headers": get_headers,
        "headers": get_headers(),
    }


def check_ai_providers(cfg: dict):
    """Check if AI providers are available on the Conductor server."""
    providers_to_check = ["anthropic", "openai"]
    for provider in providers_to_check:
        try:
            resp = requests.get(
                f"{cfg['url']}/api/model/{provider}",
                headers=cfg["get_headers"](),
            )
            if resp.status_code == 200:
                models = resp.json()
                print(f"  {provider}: available ({len(models)} models)")
            else:
                print(f"  {provider}: not available (ensure {provider.upper()}_API_KEY is set on the server)")
        except Exception:
            print(f"  {provider}: could not check availability")


def register_tasks(cfg: dict):
    task_files = sorted(TASKS_DIR.glob("*.json"))
    if not task_files:
        print("No task definitions found.")
        return

    tasks = []
    for f in task_files:
        with open(f) as fh:
            tasks.append(json.load(fh))
        print(f"  Loaded task: {f.name}")

    resp = requests.post(
        f"{cfg['url']}/api/metadata/taskdefs",
        headers=cfg["get_headers"](),
        json=tasks,
    )
    if resp.status_code in (200, 204):
        print(f"Registered {len(tasks)} task definitions.")
    else:
        print(f"Failed to register tasks: {resp.status_code} {resp.text}")
        sys.exit(1)


def register_workflows(cfg: dict):
    workflow_files = sorted(WORKFLOWS_DIR.glob("*.json"))
    if not workflow_files:
        print("No workflow definitions found.")
        return

    for f in workflow_files:
        with open(f) as fh:
            wf = json.load(fh)
        print(f"  Registering workflow: {wf['name']} v{wf.get('version', 1)}")

        resp = requests.put(
            f"{cfg['url']}/api/metadata/workflow",
            headers=cfg["get_headers"](),
            json=[wf],
        )
        if resp.status_code in (200, 204):
            print(f"  Registered: {wf['name']}")
        else:
            print(f"  Failed: {resp.status_code} {resp.text}")
            sys.exit(1)


def main():
    cfg = load_config()
    print(f"Conductor server: {cfg['url']}")
    print()

    print("Checking AI provider availability...")
    check_ai_providers(cfg)
    print()

    print("Registering task definitions...")
    register_tasks(cfg)
    print()

    print("Registering workflows...")
    register_workflows(cfg)
    print()

    print("Done.")


if __name__ == "__main__":
    main()
