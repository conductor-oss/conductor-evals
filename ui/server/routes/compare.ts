import { Router } from 'express';
import { loadConfig } from '../config.js';
import { getExecution, extractResults, executionToRun } from '../conductor.js';

const router = Router();

// GET /api/compare?a=X&b=Y
router.get('/', async (req, res) => {
  const { a, b } = req.query;

  if (!a || !b) {
    res.status(400).json({ error: 'Both query params a and b (run IDs) are required' });
    return;
  }

  try {
    const cfg = loadConfig();
    const [execA, execB] = await Promise.all([
      getExecution(cfg, a as string),
      getExecution(cfg, b as string),
    ]);

    const dataA = extractResults(execA);
    const dataB = extractResults(execB);

    const summaryA = dataA.summary as Record<string, Record<string, unknown>>;
    const summaryB = dataB.summary as Record<string, Record<string, unknown>>;

    const allModels = [...new Set([...Object.keys(summaryA), ...Object.keys(summaryB)])].sort();
    const modelComparison = allModels.map((model) => {
      const aAvg = (summaryA[model]?.avg_score as number) ?? 0;
      const bAvg = (summaryB[model]?.avg_score as number) ?? 0;
      return {
        model,
        run_a_avg: aAvg,
        run_b_avg: bAvg,
        delta: bAvg - aAvg,
        run_a_pass_rate: (summaryA[model]?.pass_rate as number) ?? 0,
        run_b_pass_rate: (summaryB[model]?.pass_rate as number) ?? 0,
      };
    });

    const resultsA = Object.values(dataA.results) as Record<string, unknown>[];
    const resultsB = Object.values(dataB.results) as Record<string, unknown>[];
    const caseMapA = new Map(resultsA.map((r) => [`${r.case_id}|${r.model_id}`, r]));
    const caseMapB = new Map(resultsB.map((r) => [`${r.case_id}|${r.model_id}`, r]));

    const allKeys = [...new Set([...caseMapA.keys(), ...caseMapB.keys()])].sort();
    const caseComparison = allKeys.map((key) => {
      const rA = caseMapA.get(key) || {};
      const rB = caseMapB.get(key) || {};
      const [caseId, modelId] = key.split('|');
      return {
        case_id: caseId,
        model_id: modelId,
        run_a_score: (rA as Record<string, unknown>).score ?? 0,
        run_b_score: (rB as Record<string, unknown>).score ?? 0,
        delta: ((rB as Record<string, unknown>).score as number ?? 0) - ((rA as Record<string, unknown>).score as number ?? 0),
        run_a_passed: (rA as Record<string, unknown>).passed ? 1 : 0,
        run_b_passed: (rB as Record<string, unknown>).passed ? 1 : 0,
      };
    });

    const runA = executionToRun(execA);
    const runB = executionToRun(execB);
    res.json({
      run_a: { id: runA.id, suite_id: runA.suite_id, status: runA.status, started_at: runA.started_at },
      run_b: { id: runB.id, suite_id: runB.suite_id, status: runB.status, started_at: runB.started_at },
      model_comparison: modelComparison,
      case_comparison: caseComparison,
    });
  } catch (err) {
    res.status(404).json({ error: `One or both runs not found: ${(err as Error).message}` });
  }
});

export default router;
