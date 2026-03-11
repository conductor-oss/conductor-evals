"""Shared helpers for eval scripts."""

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "config" / "orkes-config.json"

REQUEST_TIMEOUT = 30


class _TokenManager:
    """Manages JWT token lifecycle for Orkes Conductor authentication.

    Exchanges keyId + keySecret for a short-lived token via POST /api/token,
    caches it, and refreshes automatically when expired.
    """

    _EXPIRY_BUFFER_S = 5 * 60  # refresh 5 min before actual expiry
    _DEFAULT_TTL_S = 24 * 60 * 60  # assume 24h token lifetime

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


def _make_get_headers(conductor_url: str, key_id: str, key_secret: str | None = None):
    """Return a callable that produces auth headers.

    If key_secret is provided, uses TokenManager (Orkes auth flow).
    Otherwise uses key_id directly as X-Authorization (open-source Conductor).
    """
    if key_secret:
        mgr = _TokenManager(conductor_url, key_id, key_secret)

        def _get_headers() -> dict:
            return {
                "Content-Type": "application/json",
                "X-Authorization": mgr.get_token(),
            }

        return _get_headers

    static_headers = {
        "Content-Type": "application/json",
        "X-Authorization": key_id,
    }
    return lambda: static_headers


def load_config() -> dict:
    """Load Conductor connection config.

    The returned dict contains:
      - "url": base URL of the Conductor server
      - "get_headers": callable returning a headers dict (handles token refresh)

    For convenience, a "headers" property is also available but callers should
    prefer get_headers() for long-running processes to benefit from token refresh.
    """
    # Check environment variables first
    env_url = os.environ.get("CONDUCTOR_URL")
    env_key = os.environ.get("CONDUCTOR_AUTH_KEY")
    env_secret = os.environ.get("CONDUCTOR_AUTH_SECRET")

    if env_url and env_key:
        url = env_url.rstrip("/").removesuffix("/api")
        get_headers = _make_get_headers(url, env_key, env_secret)
        return {
            "url": url,
            "get_headers": get_headers,
            "headers": get_headers(),
        }

    # Fall back to config file
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found: {CONFIG_FILE}")
        print(
            "Set CONDUCTOR_URL and CONDUCTOR_AUTH_KEY env vars, "
            "or create the config file from config/orkes-config.example.json"
        )
        sys.exit(1)

    cluster = config["clusters"][0]
    url = cluster["url"].rstrip("/").removesuffix("/api")
    get_headers = _make_get_headers(url, cluster["keyId"], cluster.get("keySecret"))
    return {
        "url": url,
        "get_headers": get_headers,
        "headers": get_headers(),
    }


def get_headers(cfg: dict) -> dict:
    """Get current auth headers from a config dict, with token refresh."""
    return cfg["get_headers"]()


def get_execution(cfg: dict, workflow_id: str) -> dict:
    try:
        resp = requests.get(
            f"{cfg['url']}/api/workflow/{workflow_id}",
            headers=cfg["get_headers"](),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to Conductor at {cfg['url']}. Is the server running?")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"Request timed out connecting to Conductor at {cfg['url']}")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"Failed to fetch execution {workflow_id}: {resp.status_code}")
        sys.exit(1)
    return resp.json()


def extract_results(execution: dict) -> dict:
    """Extract results from a completed eval_suite execution."""
    output = execution.get("output", {})
    results = output.get("results", [])
    summary = output.get("summary", {})
    return {
        "run_id": output.get("run_id", execution.get("workflowId")),
        "status": execution.get("status"),
        "summary": summary,
        "results": {r.get("case_id", "?"): r for r in results if isinstance(r, dict)},
    }
