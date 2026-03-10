import express from 'express';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';

import { loadConfig } from './config.js';
import { loadModelPresets } from './models.js';

import suitesRouter from './routes/suites.js';
import casesRouter from './routes/cases.js';
import runsRouter from './routes/runs.js';
import compareRouter from './routes/compare.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = parseInt(process.env.PORT || '3939', 10);

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// API routes
app.use('/api/suites', suitesRouter);
app.use('/api/suites/:sid/cases', casesRouter);
app.use('/api/runs', runsRouter);
app.use('/api/compare', compareRouter);

// GET /api/models - return available model presets and providers
app.get('/api/models', (_req, res) => {
  res.json({
    presets: loadModelPresets(),
    providers: ['anthropic', 'openai', 'google_gemini'],
  });
});

// GET /api/config - return non-sensitive config for the frontend
app.get('/api/config', (_req, res) => {
  try {
    const cfg = loadConfig();
    res.json({ conductor_url: cfg.url });
  } catch {
    res.json({ conductor_url: null });
  }
});

// POST /api/sync - no-op, kept for backwards compatibility
app.post('/api/sync', (_req, res) => {
  const evalsDir = path.join(process.env.BASE_DIR || path.resolve(__dirname, '..', '..'), 'evals');
  const fs = require('fs');
  let suites = 0;
  let cases = 0;
  if (fs.existsSync(evalsDir)) {
    const entries = fs.readdirSync(evalsDir, { withFileTypes: true });
    for (const e of entries) {
      if (e.isDirectory()) {
        suites++;
        cases += fs.readdirSync(path.join(evalsDir, e.name)).filter((f: string) => f.endsWith('.json')).length;
      }
    }
  }
  res.json({ message: 'Sync complete', suites, cases });
});

// Serve built frontend (production)
const clientDist = path.resolve(__dirname, '..', 'dist', 'client');
app.use(express.static(clientDist));
app.get('*', (_req, res) => {
  res.sendFile(path.join(clientDist, 'index.html'));
});

// Start server
app.listen(PORT, () => {
  console.log(`\nEval UI server running at http://localhost:${PORT}\n`);
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down...');
  process.exit(0);
});

process.on('SIGTERM', () => {
  process.exit(0);
});
