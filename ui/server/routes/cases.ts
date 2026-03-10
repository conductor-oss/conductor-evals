import { Router, Request } from 'express';
import fs from 'fs';
import path from 'path';
import { getEvalsDir } from '../config.js';
import { validateCase } from '../validation.js';

interface SuiteParams { sid: string; cid: string; [key: string]: string; }

const router = Router({ mergeParams: true });

// GET /api/suites/:sid/cases
router.get('/', (req: Request<SuiteParams>, res) => {
  const suiteDir = path.join(getEvalsDir(), req.params.sid);
  if (!fs.existsSync(suiteDir)) {
    res.status(404).json({ error: 'Suite not found' });
    return;
  }

  const jsonFiles = fs.readdirSync(suiteDir).filter((f) => f.endsWith('.json')).sort();
  const cases = [];
  for (const f of jsonFiles) {
    try {
      const raw = fs.readFileSync(path.join(suiteDir, f), 'utf-8');
      const caseData = JSON.parse(raw);
      cases.push({
        id: caseData.id || f.replace(/\.json$/, ''),
        suite_id: req.params.sid,
        prompt: caseData.prompt || '',
        agent_type: caseData.agent_type || '',
        scoring_method: caseData.scoring_method || '',
        full_json: raw,
      });
    } catch {
      // Skip invalid JSON
    }
  }
  res.json(cases);
});

// POST /api/suites/:sid/cases
router.post('/', (req: Request<SuiteParams>, res) => {
  const { sid } = req.params;
  const caseData = req.body;

  if (!caseData.id) {
    res.status(400).json({ error: 'id is required' });
    return;
  }

  const errors = validateCase(caseData, caseData.id);
  if (errors.length > 0) {
    res.status(400).json({ error: 'Validation failed', details: errors });
    return;
  }

  const suiteDir = path.join(getEvalsDir(), sid);
  if (!fs.existsSync(suiteDir)) {
    res.status(404).json({ error: 'Suite not found' });
    return;
  }

  const filePath = path.join(suiteDir, `${caseData.id}.json`);
  if (fs.existsSync(filePath)) {
    res.status(409).json({ error: `Case '${caseData.id}' already exists in suite '${sid}'` });
    return;
  }

  const jsonStr = JSON.stringify(caseData, null, 2) + '\n';
  fs.writeFileSync(filePath, jsonStr);

  res.status(201).json({
    id: caseData.id,
    suite_id: sid,
    prompt: caseData.prompt || '',
    agent_type: caseData.agent_type || '',
    scoring_method: caseData.scoring_method || '',
    full_json: jsonStr,
  });
});

// GET /api/suites/:sid/cases/:cid
router.get('/:cid', (req: Request<SuiteParams>, res) => {
  const filePath = path.join(getEvalsDir(), req.params.sid, `${req.params.cid}.json`);
  if (!fs.existsSync(filePath)) {
    res.status(404).json({ error: 'Case not found' });
    return;
  }
  const raw = fs.readFileSync(filePath, 'utf-8');
  const caseData = JSON.parse(raw);
  res.json({
    id: caseData.id || req.params.cid,
    suite_id: req.params.sid,
    prompt: caseData.prompt || '',
    agent_type: caseData.agent_type || '',
    scoring_method: caseData.scoring_method || '',
    full_json: raw,
  });
});

// PUT /api/suites/:sid/cases/:cid
router.put('/:cid', (req: Request<SuiteParams>, res) => {
  const { sid, cid } = req.params;
  const caseData = req.body;
  caseData.id = cid;

  const errors = validateCase(caseData, cid);
  if (errors.length > 0) {
    res.status(400).json({ error: 'Validation failed', details: errors });
    return;
  }

  const filePath = path.join(getEvalsDir(), sid, `${cid}.json`);
  if (!fs.existsSync(filePath)) {
    res.status(404).json({ error: 'Case not found' });
    return;
  }

  const jsonStr = JSON.stringify(caseData, null, 2) + '\n';
  fs.writeFileSync(filePath, jsonStr);

  res.json({
    id: cid,
    suite_id: sid,
    prompt: caseData.prompt || '',
    agent_type: caseData.agent_type || '',
    scoring_method: caseData.scoring_method || '',
    full_json: jsonStr,
  });
});

// DELETE /api/suites/:sid/cases/:cid
router.delete('/:cid', (req: Request<SuiteParams>, res) => {
  const { sid, cid } = req.params;
  const filePath = path.join(getEvalsDir(), sid, `${cid}.json`);
  if (!fs.existsSync(filePath)) {
    res.status(404).json({ error: 'Case not found' });
    return;
  }
  fs.unlinkSync(filePath);
  res.json({ deleted: true });
});

export default router;
