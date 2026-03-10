import { Router } from 'express';
import fs from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { getEvalsDir, loadConfig } from '../config.js';
import { resolveModels } from '../models.js';
import {
  startWorkflow,
  cancelWorkflow,
  getExecution,
  searchWorkflows,
  extractResults,
  executionToRun,
  searchResultToRun,
} from '../conductor.js';

const router = Router();

// GET /api/runs
router.get('/', async (req, res) => {
  try {
    const { suite_id, limit } = req.query;
    const cfg = loadConfig();
    let query = "workflowType IN (eval_suite)";
    if (suite_id) {
      query += ` AND correlationId IN (${suite_id})`;
    }
    const size = limit ? Number(limit) : 50;
    const data = await searchWorkflows(cfg, query, 0, size);
    const runs = (data.results || []).map(searchResultToRun);
    res.json(runs);
  } catch (err) {
    console.error('Error listing runs:', err);
    res.status(502).json({ error: `Failed to query Conductor: ${(err as Error).message}` });
  }
});

// POST /api/runs
router.post('/', async (req, res) => {
  try {
    const { suite_id, models: modelNames, options } = req.body;

    if (!suite_id || !modelNames || !Array.isArray(modelNames) || modelNames.length === 0) {
      res.status(400).json({ error: 'suite_id and models[] are required' });
      return;
    }

    let models;
    try {
      models = resolveModels(modelNames);
    } catch (err) {
      res.status(400).json({ error: (err as Error).message });
      return;
    }

    const suiteDir = path.join(getEvalsDir(), suite_id);
    if (!fs.existsSync(suiteDir)) {
      res.status(404).json({ error: `Suite directory not found: ${suite_id}` });
      return;
    }

    const jsonFiles = fs.readdirSync(suiteDir).filter((f) => f.endsWith('.json')).sort();
    const evalCases: Record<string, unknown>[] = [];

    for (const f of jsonFiles) {
      try {
        const raw = fs.readFileSync(path.join(suiteDir, f), 'utf-8');
        const caseData = JSON.parse(raw);
        if (!caseData.id) caseData.id = f.replace(/\.json$/, '');
        if (caseData.skip) continue;
        evalCases.push(caseData);
      } catch {
        // Skip invalid JSON
      }
    }

    if (evalCases.length === 0) {
      res.status(400).json({ error: 'No valid eval cases found in suite' });
      return;
    }

    const runId = `run_${uuidv4().replace(/-/g, '').slice(0, 12)}`;
    const workflowInput = {
      suite_name: suite_id,
      eval_cases: evalCases,
      run_id: runId,
      models,
      options: { dry_run: options?.dry_run || false, ...options },
    };

    const cfg = loadConfig();
    const workflowId = await startWorkflow(cfg, workflowInput, suite_id);

    res.status(201).json({
      run_id: runId,
      workflow_id: workflowId,
      suite_id,
      models: modelNames,
      status: 'RUNNING',
    });
  } catch (err) {
    console.error('Error starting run:', err);
    res.status(500).json({ error: (err as Error).message });
  }
});

// GET /api/runs/:id
router.get('/:id', async (req, res) => {
  const cfg = loadConfig();
  // Try as workflow_id first
  try {
    const execution = await getExecution(cfg, req.params.id);
    res.json(executionToRun(execution));
    return;
  } catch {
    // Fall through to search
  }
  // Search by run_id in workflow input
  try {
    const data = await searchWorkflows(cfg, "workflowType IN (eval_suite)", 0, 100);
    for (const r of data.results || []) {
      const input = (r.input || {}) as Record<string, unknown>;
      if (input.run_id === req.params.id) {
        res.json(searchResultToRun(r));
        return;
      }
    }
  } catch (err) {
    console.error(`Error searching for run ${req.params.id}:`, err);
  }
  res.status(404).json({ error: 'Run not found' });
});

// GET /api/runs/:id/status
router.get('/:id/status', async (req, res) => {
  const cfg = loadConfig();
  let execution: Record<string, unknown> | null = null;

  try {
    execution = await getExecution(cfg, req.params.id);
  } catch {
    // Try search fallback
    try {
      const data = await searchWorkflows(cfg, "workflowType IN (eval_suite)", 0, 100);
      for (const r of data.results || []) {
        const input = (r.input || {}) as Record<string, unknown>;
        if (input.run_id === req.params.id) {
          const wfId = r.workflowId as string;
          if (wfId) execution = await getExecution(cfg, wfId);
          break;
        }
      }
    } catch {
      // give up
    }
  }

  if (!execution) {
    res.status(404).json({ error: 'Run not found' });
    return;
  }

  const output = (execution.output || {}) as Record<string, unknown>;
  const results = (output.results || []) as unknown[];
  res.json({
    id: ((execution.input || {}) as Record<string, unknown>).run_id || execution.workflowId || '',
    status: execution.status || 'UNKNOWN',
    summary: output.summary || {},
    error: execution.reasonForIncompletion || null,
    result_count: results.length,
  });
});

// GET /api/runs/:id/results
router.get('/:id/results', async (req, res) => {
  const cfg = loadConfig();
  let execution: Record<string, unknown> | null = null;

  try {
    execution = await getExecution(cfg, req.params.id);
  } catch {
    try {
      const data = await searchWorkflows(cfg, "workflowType IN (eval_suite)", 0, 100);
      for (const r of data.results || []) {
        const input = (r.input || {}) as Record<string, unknown>;
        if (input.run_id === req.params.id) {
          const wfId = r.workflowId as string;
          if (wfId) execution = await getExecution(cfg, wfId);
          break;
        }
      }
    } catch {
      // give up
    }
  }

  if (!execution) {
    res.status(404).json({ error: 'Run not found' });
    return;
  }

  const data = extractResults(execution);
  const resultsList = Object.values(data.results).map((r) => {
    const rec = r as Record<string, unknown>;
    return {
      run_id: data.run_id,
      case_id: rec.case_id || '',
      model_id: rec.model_id || '',
      provider: rec.provider || '',
      score: rec.score || 0,
      passed: rec.passed ? 1 : 0,
      response_preview: rec.response_preview || '',
      latency_ms: rec.latency_ms || 0,
      token_usage: JSON.stringify(rec.token_usage || {}),
      scoring_details: JSON.stringify(rec.scoring_details || {}),
      tool_calls: JSON.stringify(rec.tool_calls || []),
      sub_workflow_id: rec.sub_workflow_id || '',
    };
  });
  res.json(resultsList);
});

// POST /api/runs/:id/cancel
router.post('/:id/cancel', async (req, res) => {
  try {
    const cfg = loadConfig();
    let workflowId = req.params.id;

    // Verify it exists, or search for it
    try {
      await getExecution(cfg, req.params.id);
    } catch {
      const data = await searchWorkflows(cfg, "workflowType IN (eval_suite)", 0, 100);
      for (const r of data.results || []) {
        const input = (r.input || {}) as Record<string, unknown>;
        if (input.run_id === req.params.id) {
          workflowId = (r.workflowId as string) || req.params.id;
          break;
        }
      }
    }

    await cancelWorkflow(cfg, workflowId);
    res.json({ cancelled: true });
  } catch (err) {
    res.status(500).json({ error: (err as Error).message });
  }
});

export default router;
