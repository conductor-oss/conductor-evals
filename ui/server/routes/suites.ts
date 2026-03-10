import { Router } from 'express';
import fs from 'fs';
import path from 'path';
import { getEvalsDir } from '../config.js';

const router = Router();

function readSuitesFromDisk() {
  const evalsDir = getEvalsDir();
  if (!fs.existsSync(evalsDir)) return [];

  const entries = fs.readdirSync(evalsDir, { withFileTypes: true });
  return entries
    .filter((e) => e.isDirectory())
    .map((e) => {
      const suiteDir = path.join(evalsDir, e.name);
      const cases = fs.readdirSync(suiteDir).filter((f) => f.endsWith('.json'));
      return {
        id: e.name,
        name: e.name.split(/[-_]/).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
        description: '',
        case_count: cases.length,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

// GET /api/suites
router.get('/', (_req, res) => {
  res.json(readSuitesFromDisk());
});

// POST /api/suites
router.post('/', (req, res) => {
  const { id, name, description } = req.body;
  if (!id || !name) {
    res.status(400).json({ error: 'id and name are required' });
    return;
  }

  const suiteDir = path.join(getEvalsDir(), id);
  if (fs.existsSync(suiteDir)) {
    res.status(409).json({ error: `Suite directory already exists: ${id}` });
    return;
  }

  fs.mkdirSync(suiteDir, { recursive: true });
  res.status(201).json({ id, name, description: description || '', case_count: 0 });
});

// GET /api/suites/:id
router.get('/:id', (req, res) => {
  const suiteDir = path.join(getEvalsDir(), req.params.id);
  if (!fs.existsSync(suiteDir)) {
    res.status(404).json({ error: 'Suite not found' });
    return;
  }

  const sid = req.params.id;
  const displayName = sid.split(/[-_]/).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  const jsonFiles = fs.readdirSync(suiteDir).filter((f) => f.endsWith('.json')).sort();

  const cases = [];
  for (const f of jsonFiles) {
    try {
      const raw = fs.readFileSync(path.join(suiteDir, f), 'utf-8');
      const caseData = JSON.parse(raw);
      const caseId = caseData.id || f.replace(/\.json$/, '');
      cases.push({
        id: caseId,
        suite_id: sid,
        prompt: caseData.prompt || '',
        agent_type: caseData.agent_type || '',
        scoring_method: caseData.scoring_method || '',
        full_json: raw,
      });
    } catch {
      // Skip invalid JSON
    }
  }

  res.json({ id: sid, name: displayName, description: '', cases, case_count: cases.length });
});

// PUT /api/suites/:id
router.put('/:id', (req, res) => {
  const suiteDir = path.join(getEvalsDir(), req.params.id);
  if (!fs.existsSync(suiteDir)) {
    res.status(404).json({ error: 'Suite not found' });
    return;
  }

  const sid = req.params.id;
  const displayName = req.body.name || sid.split(/[-_]/).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  res.json({ id: sid, name: displayName, description: req.body.description || '' });
});

// DELETE /api/suites/:id
router.delete('/:id', (req, res) => {
  const suiteDir = path.join(getEvalsDir(), req.params.id);
  if (!fs.existsSync(suiteDir)) {
    res.status(404).json({ error: 'Suite not found' });
    return;
  }
  fs.rmSync(suiteDir, { recursive: true });
  res.json({ deleted: true });
});

export default router;
