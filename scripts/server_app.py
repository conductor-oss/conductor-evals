"""
Conductor Evals — Python backend (FastAPI).

Serves the REST API and the built React frontend.
Conductor is the single source of truth for execution data.
Suites and cases are read directly from JSON files on disk (evals/*/).

Usage:
    python server.py
"""

import json
import logging
import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("server")

BASE_DIR = Path(os.environ.get("BASE_DIR", Path(__file__).parent.parent))
EVALS_DIR = BASE_DIR / "evals"
CONFIG_FILE = BASE_DIR / "config" / "orkes-config.json"
MODEL_PRESETS_FILE = BASE_DIR / "config" / "model-presets.json"
APP_DIR = Path(__file__).parent.parent
CLIENT_DIST = Path(os.environ.get("CLIENT_DIST", APP_DIR / "ui" / "dist" / "client"))

PORT = int(os.environ.get("PORT", "3939"))
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "TERMINATED"}

# ---------------------------------------------------------------------------
# Configuration & Auth
# ---------------------------------------------------------------------------


class TokenManager:
    """Manages JWT token lifecycle for Orkes Conductor authentication."""

    EXPIRY_BUFFER = 5 * 60  # refresh 5 min before expiry
    DEFAULT_TTL = 24 * 60 * 60  # assume 24h token lifetime

    def __init__(self, conductor_url: str, key_id: str, key_secret: str):
        self._url = conductor_url
        self._key_id = key_id
        self._key_secret = key_secret
        self._token: str | None = None
        self._expires_at: float = 0

    async def get_token(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        return await self._refresh()

    async def _refresh(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._url}/api/token",
                json={"keyId": self._key_id, "keySecret": self._key_secret},
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to obtain auth token: {resp.status_code} {resp.text}"
            )
        self._token = resp.json()["token"]
        self._expires_at = time.time() + self.DEFAULT_TTL - self.EXPIRY_BUFFER
        return self._token


class ConductorConfig:
    def __init__(
        self, url: str, key_id: str | None = None, key_secret: str | None = None
    ):
        self.url = url
        self._token_manager = (
            TokenManager(url, key_id, key_secret) if key_id and key_secret else None
        )
        self._static_key = key_id if key_id and not key_secret else None

    async def get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token_manager:
            headers["X-Authorization"] = await self._token_manager.get_token()
        elif self._static_key:
            headers["X-Authorization"] = self._static_key
        return headers


def load_conductor_config() -> ConductorConfig:
    env_url = os.environ.get("CONDUCTOR_URL")
    env_key = os.environ.get("CONDUCTOR_AUTH_KEY")
    env_secret = os.environ.get("CONDUCTOR_AUTH_SECRET")

    if env_url and env_key:
        url = env_url.rstrip("/").removesuffix("/api")
        return ConductorConfig(url, env_key, env_secret)

    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text())
        cluster = config["clusters"][0]
        url = cluster["url"].rstrip("/").removesuffix("/api")
        return ConductorConfig(url, cluster.get("keyId"), cluster.get("keySecret"))

    raise RuntimeError(
        f"Config not found. Set CONDUCTOR_URL + CONDUCTOR_AUTH_KEY env vars, "
        f"or create {CONFIG_FILE}"
    )


conductor_cfg: ConductorConfig | None = None


def get_conductor_cfg() -> ConductorConfig:
    global conductor_cfg
    if conductor_cfg is None:
        conductor_cfg = load_conductor_config()
    return conductor_cfg


# ---------------------------------------------------------------------------
# Conductor API Client
# ---------------------------------------------------------------------------


async def conductor_get_execution(cfg: ConductorConfig, workflow_id: str) -> dict:
    headers = await cfg.get_headers()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{cfg.url}/api/workflow/{workflow_id}", headers=headers
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch execution {workflow_id}: {resp.status_code}"
        )
    return resp.json()


async def conductor_start_workflow(
    cfg: ConductorConfig,
    workflow_input: dict,
    correlation_id: str | None = None,
) -> str:
    headers = await cfg.get_headers()
    body: dict[str, Any] = {"name": "eval_suite", "version": 2, "input": workflow_input}
    if correlation_id:
        body["correlationId"] = correlation_id
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{cfg.url}/api/workflow", headers=headers, json=body)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to start workflow: {resp.status_code} {resp.text}")
    return resp.text.strip().strip('"')


async def conductor_cancel_workflow(cfg: ConductorConfig, workflow_id: str):
    headers = await cfg.get_headers()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(
            f"{cfg.url}/api/workflow/{workflow_id}", headers=headers
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to cancel workflow {workflow_id}: {resp.status_code}"
        )


async def conductor_search_workflows(
    cfg: ConductorConfig,
    query: str,
    start: int = 0,
    size: int = 100,
) -> dict:
    """Search workflow executions. Returns {totalHits, results[]}."""
    headers = await cfg.get_headers()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{cfg.url}/api/workflow/search",
            headers=headers,
            params={"query": query, "start": start, "size": size},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Search failed: {resp.status_code} {resp.text}")
    return resp.json()


def extract_sub_workflow_ids(execution: dict) -> dict[str, str]:
    """Map (case_id::model_id) -> subWorkflowId from execution tasks."""
    mapping: dict[str, str] = {}
    for task in execution.get("tasks", []):
        if task.get("taskType") != "SUB_WORKFLOW" or not task.get("subWorkflowId"):
            continue
        wi = task.get("inputData", {}).get("workflowInput", {})
        case_id = wi.get("eval_case", {}).get("id", "")
        model_id = wi.get("model", {}).get("model_id", "")
        if case_id:
            mapping[f"{case_id}::{model_id}"] = task["subWorkflowId"]
    return mapping


def extract_results(execution: dict) -> dict:
    output = execution.get("output") or {}
    results = output.get("results") or []
    summary = output.get("summary") or {}
    sub_ids = extract_sub_workflow_ids(execution)

    results_map: dict[str, dict] = {}
    for r in results:
        if not isinstance(r, dict):
            continue
        case_id = r.get("case_id", "?")
        model_id = r.get("model_id", "")
        key = f"{case_id}::{model_id}"
        r["sub_workflow_id"] = sub_ids.get(key, "")
        results_map[key] = r

    return {
        "run_id": output.get("run_id", execution.get("workflowId", "")),
        "status": execution.get("status", "UNKNOWN"),
        "summary": summary,
        "results": results_map,
    }


def _epoch_ms_to_iso(epoch_ms) -> str | None:
    """Convert epoch milliseconds to ISO 8601 string, or return as-is if already a string."""
    if epoch_ms is None:
        return None
    if isinstance(epoch_ms, str):
        return epoch_ms
    try:
        from datetime import datetime, timezone

        return (
            datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (TypeError, ValueError, OSError):
        return str(epoch_ms)


def _execution_to_run(execution: dict) -> dict:
    """Map a Conductor workflow execution to a run object for the API."""
    wf_input = execution.get("input") or {}
    models_raw = wf_input.get("models", [])
    model_names = [
        m.get("model_id", str(m)) if isinstance(m, dict) else str(m) for m in models_raw
    ]
    output = execution.get("output") or {}
    return {
        "id": wf_input.get("run_id", execution.get("workflowId", "")),
        "workflow_id": execution.get("workflowId", ""),
        "suite_id": wf_input.get("suite_name", execution.get("correlationId", "")),
        "models": json.dumps(model_names),
        "status": execution.get("status", "UNKNOWN"),
        "started_at": _epoch_ms_to_iso(execution.get("createTime")),
        "completed_at": _epoch_ms_to_iso(execution.get("endTime")),
        "options": json.dumps(wf_input.get("options", {})),
        "summary": json.dumps(output.get("summary") or {}),
        "error": execution.get("reasonForIncompletion"),
    }


def _search_result_to_run(result: dict) -> dict:
    """Map a Conductor search result (lightweight) to a run object.

    Note: search results return input/output as Java map toString strings,
    not parsed JSON objects. We extract what we can from top-level fields.
    """
    # input may be a string (Java toString) or a dict — handle both
    wf_input = result.get("input", {})
    if isinstance(wf_input, str):
        # Can't reliably parse Java map syntax; use top-level fields instead
        wf_input = {}
    models_raw = wf_input.get("models", [])
    model_names = [
        m.get("model_id", str(m)) if isinstance(m, dict) else str(m) for m in models_raw
    ]
    return {
        "id": wf_input.get("run_id", result.get("workflowId", "")),
        "workflow_id": result.get("workflowId", ""),
        "suite_id": wf_input.get("suite_name", result.get("correlationId", "")),
        "models": json.dumps(model_names) if model_names else "[]",
        "status": result.get("status", "UNKNOWN"),
        "started_at": result.get("startTime"),
        "completed_at": result.get("endTime"),
        "options": json.dumps(wf_input.get("options", {})),
        "summary": "{}",
        "error": result.get("reasonForIncompletion"),
    }


# ---------------------------------------------------------------------------
# Model Resolution
# ---------------------------------------------------------------------------

_model_presets_cache: dict | None = None


def load_model_presets() -> dict:
    global _model_presets_cache
    if _model_presets_cache is None:
        _model_presets_cache = json.loads(MODEL_PRESETS_FILE.read_text())
    return _model_presets_cache


DEFAULT_PARAMS = {"max_tokens": 4096, "temperature": 0}


def resolve_models(models: list) -> list[dict]:
    presets = load_model_presets()
    resolved = []
    for m in models:
        if isinstance(m, dict) and m.get("provider") and m.get("model_id"):
            resolved.append(
                {
                    "provider": m["provider"],
                    "model_id": m["model_id"],
                    "params": m.get("params", DEFAULT_PARAMS),
                }
            )
        elif isinstance(m, str):
            if m in presets:
                resolved.append(presets[m])
            elif ":" in m:
                provider, model_id = m.split(":", 1)
                resolved.append(
                    {
                        "provider": provider,
                        "model_id": model_id,
                        "params": DEFAULT_PARAMS,
                    }
                )
            else:
                raise ValueError(
                    f"Unknown model: {m}. Use a preset name, provider:model_id format, or a full config object."
                )
        else:
            raise ValueError(f"Invalid model spec: {m}")
    return resolved


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"id", "prompt", "agent_type", "scoring_method"}
SCORING_FIELDS = {
    "text_match": {"expected", "match_mode"},
    "llm_judge": set(),
    "tool_trace": {"expected_trace"},
}


def validate_case(case_data: dict, filename: str) -> list[str]:
    errors = []
    keys = set(case_data.keys())
    missing = REQUIRED_FIELDS - keys
    if missing:
        errors.append(f"{filename}: missing required fields: {', '.join(missing)}")
    scoring = case_data.get("scoring_method", "")
    if scoring in SCORING_FIELDS:
        missing_scoring = SCORING_FIELDS[scoring] - keys
        if missing_scoring:
            errors.append(
                f"{filename}: scoring_method '{scoring}' requires fields: {', '.join(missing_scoring)}"
            )
    elif scoring:
        errors.append(f"{filename}: unknown scoring_method '{scoring}'")
    return errors


# ---------------------------------------------------------------------------
# Disk helpers for suites & cases
# ---------------------------------------------------------------------------


def _read_suites_from_disk() -> list[dict]:
    """Read all suites from the evals directory."""
    suites = []
    if not EVALS_DIR.exists():
        return suites
    for d in sorted(EVALS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        cases = list(d.glob("*.json"))
        suites.append(
            {
                "id": d.name,
                "name": " ".join(
                    w.capitalize() for w in d.name.replace("-", "_").split("_")
                ),
                "description": "",
                "case_count": len(cases),
            }
        )
    return suites


def _read_cases_from_disk(suite_id: str) -> list[dict]:
    """Read all eval cases from a suite directory."""
    suite_dir = EVALS_DIR / suite_id
    if not suite_dir.exists():
        return []
    cases = []
    for f in sorted(suite_dir.glob("*.json")):
        try:
            raw = f.read_text()
            case_data = json.loads(raw)
            if "id" not in case_data:
                case_data["id"] = f.stem
            cases.append(
                {
                    "id": case_data.get("id", f.stem),
                    "suite_id": suite_id,
                    "prompt": case_data.get("prompt", ""),
                    "agent_type": case_data.get("agent_type", ""),
                    "scoring_method": case_data.get("scoring_method", ""),
                    "full_json": raw,
                }
            )
        except (json.JSONDecodeError, OSError):
            pass
    return cases


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Eval UI server running at http://localhost:%d", PORT)
    yield
    logger.info("Shutting down...")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# --- Models ---


@app.get("/api/models")
def api_get_models():
    return {
        "presets": load_model_presets(),
        "providers": ["anthropic", "openai", "google_gemini"],
    }


# --- Config ---


@app.get("/api/config")
def api_get_config():
    try:
        cfg = get_conductor_cfg()
        return {"conductor_url": cfg.url}
    except Exception:
        return {"conductor_url": None}


# --- Sync (no-op, kept for backwards compatibility) ---


@app.post("/api/sync")
def api_sync():
    suites = _read_suites_from_disk()
    total_cases = sum(s["case_count"] for s in suites)
    return {"message": "Sync complete", "suites": len(suites), "cases": total_cases}


# --- Suites ---


@app.get("/api/suites")
async def api_list_suites():
    suites = _read_suites_from_disk()
    # Optionally enrich with run_count from Conductor
    try:
        cfg = get_conductor_cfg()
        for s in suites:
            data = await conductor_search_workflows(
                cfg,
                f"workflowType IN (eval_suite) AND correlationId IN ({s['id']})",
                start=0,
                size=0,
            )
            s["run_count"] = data.get("totalHits", 0)
    except Exception:
        for s in suites:
            s.setdefault("run_count", 0)
    return suites


@app.post("/api/suites", status_code=201)
def api_create_suite(request_body: dict):
    sid = request_body.get("id")
    name = request_body.get("name")
    if not sid or not name:
        raise HTTPException(400, "id and name are required")
    suite_dir = EVALS_DIR / sid
    if suite_dir.exists():
        raise HTTPException(409, f"Suite directory already exists: {sid}")
    suite_dir.mkdir(parents=True)
    return {
        "id": sid,
        "name": name,
        "description": request_body.get("description", ""),
        "case_count": 0,
    }


@app.get("/api/suites/{sid}")
async def api_get_suite(sid: str):
    suite_dir = EVALS_DIR / sid
    if not suite_dir.exists():
        raise HTTPException(404, "Suite not found")
    cases = _read_cases_from_disk(sid)
    display_name = " ".join(w.capitalize() for w in sid.replace("-", "_").split("_"))
    # Fetch recent runs from Conductor
    recent_runs = []
    try:
        cfg = get_conductor_cfg()
        data = await conductor_search_workflows(
            cfg,
            f"workflowType IN (eval_suite) AND correlationId IN ({sid})",
            start=0,
            size=10,
        )
        recent_runs = [_search_result_to_run(r) for r in data.get("results", [])]
    except Exception:
        pass
    return {
        "id": sid,
        "name": display_name,
        "description": "",
        "cases": cases,
        "case_count": len(cases),
        "recent_runs": recent_runs,
    }


@app.put("/api/suites/{sid}")
def api_update_suite(sid: str, request_body: dict):
    suite_dir = EVALS_DIR / sid
    if not suite_dir.exists():
        raise HTTPException(404, "Suite not found")
    # Suite metadata is derived from directory name; nothing persistent to update.
    display_name = request_body.get(
        "name",
        " ".join(w.capitalize() for w in sid.replace("-", "_").split("_")),
    )
    return {
        "id": sid,
        "name": display_name,
        "description": request_body.get("description", ""),
    }


@app.delete("/api/suites/{sid}")
def api_delete_suite(sid: str):
    suite_dir = EVALS_DIR / sid
    if not suite_dir.exists():
        raise HTTPException(404, "Suite not found")
    shutil.rmtree(suite_dir)
    return {"deleted": True}


# --- Cases ---


@app.get("/api/suites/{sid}/cases")
def api_list_cases(sid: str):
    suite_dir = EVALS_DIR / sid
    if not suite_dir.exists():
        raise HTTPException(404, "Suite not found")
    return _read_cases_from_disk(sid)


@app.post("/api/suites/{sid}/cases", status_code=201)
def api_create_case(sid: str, case_data: dict):
    if not case_data.get("id"):
        raise HTTPException(400, "id is required")
    errors = validate_case(case_data, case_data["id"])
    if errors:
        raise HTTPException(
            400, detail={"error": "Validation failed", "details": errors}
        )

    suite_dir = EVALS_DIR / sid
    if not suite_dir.exists():
        raise HTTPException(404, "Suite not found")

    case_file = suite_dir / f"{case_data['id']}.json"
    if case_file.exists():
        raise HTTPException(
            409, f"Case '{case_data['id']}' already exists in suite '{sid}'"
        )

    json_str = json.dumps(case_data, indent=2) + "\n"
    case_file.write_text(json_str)

    return {
        "id": case_data["id"],
        "suite_id": sid,
        "prompt": case_data.get("prompt", ""),
        "agent_type": case_data.get("agent_type", ""),
        "scoring_method": case_data.get("scoring_method", ""),
        "full_json": json_str,
    }


@app.get("/api/suites/{sid}/cases/{cid}")
def api_get_case(sid: str, cid: str):
    case_file = EVALS_DIR / sid / f"{cid}.json"
    if not case_file.exists():
        raise HTTPException(404, "Case not found")
    raw = case_file.read_text()
    case_data = json.loads(raw)
    return {
        "id": case_data.get("id", cid),
        "suite_id": sid,
        "prompt": case_data.get("prompt", ""),
        "agent_type": case_data.get("agent_type", ""),
        "scoring_method": case_data.get("scoring_method", ""),
        "full_json": raw,
    }


@app.put("/api/suites/{sid}/cases/{cid}")
def api_update_case(sid: str, cid: str, case_data: dict):
    case_data["id"] = cid
    errors = validate_case(case_data, cid)
    if errors:
        raise HTTPException(
            400, detail={"error": "Validation failed", "details": errors}
        )

    case_file = EVALS_DIR / sid / f"{cid}.json"
    if not case_file.exists():
        raise HTTPException(404, "Case not found")

    json_str = json.dumps(case_data, indent=2) + "\n"
    case_file.write_text(json_str)

    return {
        "id": cid,
        "suite_id": sid,
        "prompt": case_data.get("prompt", ""),
        "agent_type": case_data.get("agent_type", ""),
        "scoring_method": case_data.get("scoring_method", ""),
        "full_json": json_str,
    }


@app.delete("/api/suites/{sid}/cases/{cid}")
def api_delete_case(sid: str, cid: str):
    case_file = EVALS_DIR / sid / f"{cid}.json"
    if not case_file.exists():
        raise HTTPException(404, "Case not found")
    case_file.unlink()
    return {"deleted": True}


# --- Runs (backed by Conductor) ---


@app.get("/api/runs")
async def api_list_runs(suite_id: str | None = None, limit: int = 50):
    cfg = get_conductor_cfg()
    query = "workflowType IN (eval_suite)"
    if suite_id:
        query += f" AND correlationId IN ({suite_id})"
    try:
        data = await conductor_search_workflows(cfg, query, start=0, size=limit)
    except Exception as e:
        logger.error("Failed to search workflows: %s", e)
        raise HTTPException(502, f"Failed to query Conductor: {e}")
    results = data.get("results", [])
    return [_search_result_to_run(r) for r in results]


@app.post("/api/runs", status_code=201)
async def api_create_run(request_body: dict):
    suite_id = request_body.get("suite_id")
    model_names = request_body.get("models")
    options = request_body.get("options", {})

    if (
        not suite_id
        or not model_names
        or not isinstance(model_names, list)
        or len(model_names) == 0
    ):
        raise HTTPException(400, "suite_id and models[] are required")

    try:
        models = resolve_models(model_names)
    except ValueError as e:
        raise HTTPException(400, str(e))

    suite_dir = EVALS_DIR / suite_id
    if not suite_dir.exists():
        raise HTTPException(404, f"Suite directory not found: {suite_id}")

    eval_cases = []
    for f in sorted(suite_dir.glob("*.json")):
        try:
            case_data = json.loads(f.read_text())
            if "id" not in case_data:
                case_data["id"] = f.stem
            if case_data.get("skip"):
                continue
            eval_cases.append(case_data)
        except (json.JSONDecodeError, OSError):
            pass

    if not eval_cases:
        raise HTTPException(400, "No valid eval cases found in suite")

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    workflow_input = {
        "suite_name": suite_id,
        "eval_cases": eval_cases,
        "run_id": run_id,
        "models": models,
        "options": {"dry_run": options.get("dry_run", False), **options},
    }

    cfg = get_conductor_cfg()
    try:
        workflow_id = await conductor_start_workflow(
            cfg, workflow_input, correlation_id=suite_id
        )
    except Exception as e:
        raise HTTPException(500, str(e))

    return {
        "run_id": workflow_id,
        "workflow_id": workflow_id,
        "suite_id": suite_id,
        "models": model_names,
        "status": "RUNNING",
    }


@app.get("/api/runs/{run_id}")
async def api_get_run(run_id: str):
    cfg = get_conductor_cfg()
    # run_id may be a workflow_id or a logical run_id stored in input
    # Try fetching directly as workflow_id first
    try:
        execution = await conductor_get_execution(cfg, run_id)
        return _execution_to_run(execution)
    except Exception:
        pass
    # Search by run_id in workflow input
    try:
        data = await conductor_search_workflows(
            cfg,
            "workflowType IN (eval_suite)",
            start=0,
            size=100,
        )
        for r in data.get("results", []):
            if r.get("input", {}).get("run_id") == run_id:
                return _search_result_to_run(r)
    except Exception as e:
        logger.error("Failed to search for run %s: %s", run_id, e)
    raise HTTPException(404, "Run not found")


@app.get("/api/runs/{run_id}/status")
async def api_get_run_status(run_id: str):
    cfg = get_conductor_cfg()
    execution = None
    # Try as workflow_id first
    try:
        execution = await conductor_get_execution(cfg, run_id)
    except Exception:
        pass
    # Fallback: search
    if execution is None:
        try:
            data = await conductor_search_workflows(
                cfg,
                "workflowType IN (eval_suite)",
                start=0,
                size=100,
            )
            for r in data.get("results", []):
                if r.get("input", {}).get("run_id") == run_id:
                    wf_id = r.get("workflowId")
                    if wf_id:
                        execution = await conductor_get_execution(cfg, wf_id)
                    break
        except Exception:
            pass
    if execution is None:
        raise HTTPException(404, "Run not found")

    output = execution.get("output", {})
    summary = output.get("summary", {})
    results = output.get("results", [])
    return {
        "id": execution.get("input", {}).get("run_id", execution.get("workflowId", "")),
        "status": execution.get("status", "UNKNOWN"),
        "summary": summary,
        "error": execution.get("reasonForIncompletion"),
        "result_count": len(results) if isinstance(results, list) else 0,
    }


@app.get("/api/runs/{run_id}/results")
async def api_get_run_results(run_id: str):
    cfg = get_conductor_cfg()
    execution = None
    # Try as workflow_id
    try:
        execution = await conductor_get_execution(cfg, run_id)
    except Exception:
        pass
    # Fallback: search
    if execution is None:
        try:
            data = await conductor_search_workflows(
                cfg,
                "workflowType IN (eval_suite)",
                start=0,
                size=100,
            )
            for r in data.get("results", []):
                if r.get("input", {}).get("run_id") == run_id:
                    wf_id = r.get("workflowId")
                    if wf_id:
                        execution = await conductor_get_execution(cfg, wf_id)
                    break
        except Exception:
            pass
    if execution is None:
        raise HTTPException(404, "Run not found")

    result_data = extract_results(execution)
    # Flatten results map into a list
    results_list = []
    for r in result_data["results"].values():
        results_list.append(
            {
                "run_id": result_data["run_id"],
                "case_id": r.get("case_id", ""),
                "model_id": r.get("model_id", ""),
                "provider": r.get("provider", ""),
                "score": r.get("score", 0.0),
                "passed": 1 if r.get("passed") else 0,
                "response_preview": r.get("response_preview", ""),
                "latency_ms": r.get("latency_ms", 0),
                "token_usage": json.dumps(r.get("token_usage", {})),
                "scoring_details": json.dumps(r.get("scoring_details", {})),
                "tool_calls": json.dumps(r.get("tool_calls", [])),
                "sub_workflow_id": r.get("sub_workflow_id", ""),
            }
        )
    return results_list


@app.post("/api/runs/{run_id}/cancel")
async def api_cancel_run(run_id: str):
    cfg = get_conductor_cfg()
    # Resolve workflow_id
    workflow_id = run_id
    try:
        await conductor_get_execution(cfg, run_id)
    except Exception:
        # Search for it
        try:
            data = await conductor_search_workflows(
                cfg,
                "workflowType IN (eval_suite)",
                start=0,
                size=100,
            )
            for r in data.get("results", []):
                if r.get("input", {}).get("run_id") == run_id:
                    workflow_id = r.get("workflowId", run_id)
                    break
        except Exception:
            pass

    try:
        await conductor_cancel_workflow(cfg, workflow_id)
    except Exception as e:
        logger.error("Failed to cancel workflow: %s", e)
        raise HTTPException(500, f"Failed to cancel: {e}")
    return {"cancelled": True}


# --- Compare ---


@app.get("/api/compare")
async def api_compare(a: str, b: str):
    cfg = get_conductor_cfg()
    try:
        exec_a = await conductor_get_execution(cfg, a)
        exec_b = await conductor_get_execution(cfg, b)
    except Exception as e:
        raise HTTPException(404, f"One or both runs not found: {e}")

    data_a = extract_results(exec_a)
    data_b = extract_results(exec_b)

    summary_a = data_a["summary"]
    summary_b = data_b["summary"]

    all_models = sorted(set(list(summary_a.keys()) + list(summary_b.keys())))
    model_comparison = []
    for model in all_models:
        a_avg = summary_a.get(model, {}).get("avg_score", 0)
        b_avg = summary_b.get(model, {}).get("avg_score", 0)
        model_comparison.append(
            {
                "model": model,
                "run_a_avg": a_avg,
                "run_b_avg": b_avg,
                "delta": b_avg - a_avg,
                "run_a_pass_rate": summary_a.get(model, {}).get("pass_rate", 0),
                "run_b_pass_rate": summary_b.get(model, {}).get("pass_rate", 0),
            }
        )

    results_a = data_a["results"]
    results_b = data_b["results"]
    # Normalize keys to case_id|model_id
    case_map_a = {
        f"{r.get('case_id', '')}|{r.get('model_id', '')}": r for r in results_a.values()
    }
    case_map_b = {
        f"{r.get('case_id', '')}|{r.get('model_id', '')}": r for r in results_b.values()
    }
    all_keys = sorted(set(list(case_map_a.keys()) + list(case_map_b.keys())))
    case_comparison = []
    for key in all_keys:
        case_id, model_id = key.split("|", 1)
        ra = case_map_a.get(key, {})
        rb = case_map_b.get(key, {})
        case_comparison.append(
            {
                "case_id": case_id,
                "model_id": model_id,
                "run_a_score": ra.get("score", 0),
                "run_b_score": rb.get("score", 0),
                "delta": (rb.get("score", 0) or 0) - (ra.get("score", 0) or 0),
                "run_a_passed": 1 if ra.get("passed") else 0,
                "run_b_passed": 1 if rb.get("passed") else 0,
            }
        )

    run_a = _execution_to_run(exec_a)
    run_b = _execution_to_run(exec_b)
    return {
        "run_a": {
            "id": run_a["id"],
            "suite_id": run_a["suite_id"],
            "status": run_a["status"],
            "started_at": run_a["started_at"],
        },
        "run_b": {
            "id": run_b["id"],
            "suite_id": run_b["suite_id"],
            "status": run_b["status"],
            "started_at": run_b["started_at"],
        },
        "model_comparison": model_comparison,
        "case_comparison": case_comparison,
    }


# --- Static files (React frontend) ---

if CLIENT_DIST.exists():
    app.mount(
        "/assets", StaticFiles(directory=str(CLIENT_DIST / "assets")), name="assets"
    )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Try to serve the file directly first
        file_path = CLIENT_DIST / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # Otherwise serve index.html (SPA fallback)
        return FileResponse(str(CLIENT_DIST / "index.html"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
