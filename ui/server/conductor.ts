import { loadConfig, type ConductorConfig } from './config.js';

const REQUEST_TIMEOUT = 30_000;

async function fetchWithTimeout(url: string, options: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function getExecution(cfg: ConductorConfig, workflowId: string): Promise<Record<string, unknown>> {
  const headers = await cfg.getHeaders();
  const resp = await fetchWithTimeout(`${cfg.url}/api/workflow/${workflowId}`, {
    headers,
  });
  if (!resp.ok) {
    throw new Error(`Failed to fetch execution ${workflowId}: ${resp.status}`);
  }
  return resp.json() as Promise<Record<string, unknown>>;
}

export async function searchWorkflows(
  cfg: ConductorConfig,
  query: string,
  start = 0,
  size = 100,
): Promise<{ totalHits: number; results: Record<string, unknown>[] }> {
  const headers = await cfg.getHeaders();
  const params = new URLSearchParams({ query, start: String(start), size: String(size) });
  const resp = await fetchWithTimeout(`${cfg.url}/api/workflow/search?${params}`, { headers });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Search failed: ${resp.status} ${body}`);
  }
  return resp.json() as Promise<{ totalHits: number; results: Record<string, unknown>[] }>;
}

/**
 * Build a map from (case_id, model_id) -> subWorkflowId by walking the
 * parent execution's task list looking for SUB_WORKFLOW tasks.
 */
function extractSubWorkflowIds(execution: Record<string, unknown>): Map<string, string> {
  const map = new Map<string, string>();
  const tasks = (execution.tasks || []) as Record<string, unknown>[];

  for (const task of tasks) {
    const taskType = task.taskType as string || '';
    const subWorkflowId = task.subWorkflowId as string || '';
    if (taskType !== 'SUB_WORKFLOW' || !subWorkflowId) continue;

    const inputData = (task.inputData || {}) as Record<string, unknown>;
    const workflowInput = (inputData.workflowInput || {}) as Record<string, unknown>;
    const evalCase = (workflowInput.eval_case || {}) as Record<string, unknown>;
    const model = (workflowInput.model || {}) as Record<string, unknown>;

    const caseId = evalCase.id as string || '';
    const modelId = model.model_id as string || '';

    if (caseId) {
      map.set(`${caseId}::${modelId}`, subWorkflowId);
    }
  }

  return map;
}

export function extractResults(execution: Record<string, unknown>): {
  run_id: string;
  status: string;
  summary: Record<string, unknown>;
  results: Record<string, unknown>;
} {
  const output = (execution.output || {}) as Record<string, unknown>;
  const results = (output.results || []) as Record<string, unknown>[];
  const summary = (output.summary || {}) as Record<string, unknown>;

  const subWorkflowIds = extractSubWorkflowIds(execution);

  const resultsMap: Record<string, unknown> = {};
  for (const r of results) {
    if (r && typeof r === 'object') {
      const rec = r as Record<string, unknown>;
      const caseId = rec.case_id as string || '?';
      const modelId = rec.model_id as string || '';
      const key = `${caseId}::${modelId}`;
      rec.sub_workflow_id = subWorkflowIds.get(key) || '';
      resultsMap[key] = rec;
    }
  }

  return {
    run_id: (output.run_id as string) || (execution.workflowId as string) || '',
    status: (execution.status as string) || 'UNKNOWN',
    summary,
    results: resultsMap,
  };
}

export async function startWorkflow(
  cfg: ConductorConfig,
  workflowInput: Record<string, unknown>,
  correlationId?: string,
): Promise<string> {
  const headers = await cfg.getHeaders();
  const body: Record<string, unknown> = {
    name: 'eval_suite',
    version: 2,
    input: workflowInput,
  };
  if (correlationId) {
    body.correlationId = correlationId;
  }
  const resp = await fetchWithTimeout(`${cfg.url}/api/workflow`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Failed to start workflow: ${resp.status} ${text}`);
  }

  const workflowId = (await resp.text()).trim().replace(/"/g, '');
  return workflowId;
}

export async function cancelWorkflow(cfg: ConductorConfig, workflowId: string): Promise<void> {
  const headers = await cfg.getHeaders();
  const resp = await fetchWithTimeout(`${cfg.url}/api/workflow/${workflowId}`, {
    method: 'DELETE',
    headers,
  });
  if (!resp.ok) {
    throw new Error(`Failed to cancel workflow ${workflowId}: ${resp.status}`);
  }
}

/**
 * Map a Conductor execution to a run object shape for the API.
 */
export function executionToRun(execution: Record<string, unknown>): Record<string, unknown> {
  const input = (execution.input || {}) as Record<string, unknown>;
  const modelsRaw = (input.models || []) as Record<string, unknown>[];
  const modelNames = modelsRaw.map((m) =>
    typeof m === 'object' && m ? (m.model_id as string || JSON.stringify(m)) : String(m)
  );
  return {
    id: (input.run_id as string) || (execution.workflowId as string) || '',
    workflow_id: (execution.workflowId as string) || '',
    suite_id: (input.suite_name as string) || (execution.correlationId as string) || '',
    models: JSON.stringify(modelNames),
    status: (execution.status as string) || 'UNKNOWN',
    started_at: execution.createTime,
    completed_at: execution.endTime,
    options: JSON.stringify((input.options || {}) as object),
    summary: JSON.stringify(((execution.output || {}) as Record<string, unknown>).summary || {}),
    error: execution.reasonForIncompletion || null,
  };
}

/**
 * Map a Conductor search result (lightweight, may lack full input) to a run object.
 * Note: search results return input/output as Java map toString strings,
 * not parsed JSON objects. We extract what we can from top-level fields.
 */
export function searchResultToRun(result: Record<string, unknown>): Record<string, unknown> {
  // input may be a string (Java toString) or an object — handle both
  const rawInput = result.input;
  const input = (typeof rawInput === 'object' && rawInput !== null ? rawInput : {}) as Record<string, unknown>;
  const modelsRaw = (input.models || []) as Record<string, unknown>[];
  const modelNames = modelsRaw.map((m) =>
    typeof m === 'object' && m ? (m.model_id as string || JSON.stringify(m)) : String(m)
  );
  return {
    id: (input.run_id as string) || (result.workflowId as string) || '',
    workflow_id: (result.workflowId as string) || '',
    suite_id: (input.suite_name as string) || (result.correlationId as string) || '',
    models: modelNames.length > 0 ? JSON.stringify(modelNames) : '[]',
    status: (result.status as string) || 'UNKNOWN',
    started_at: result.startTime,
    completed_at: result.endTime,
    options: JSON.stringify((input.options || {}) as object),
    summary: '{}',
    error: result.reasonForIncompletion || null,
  };
}
