import fs from 'fs';
import path from 'path';
import { getBaseDir } from './config.js';

export interface ModelPreset {
  provider: string;
  model_id: string;
  params: Record<string, unknown>;
}

let cachedPresets: Record<string, ModelPreset> | null = null;

export function loadModelPresets(): Record<string, ModelPreset> {
  if (cachedPresets) return cachedPresets;
  const presetsFile = path.join(getBaseDir(), 'config', 'model-presets.json');
  cachedPresets = JSON.parse(fs.readFileSync(presetsFile, 'utf-8'));
  return cachedPresets!;
}

const DEFAULT_PARAMS = { max_tokens: 4096, temperature: 0 };

export function resolveModels(models: (string | ModelPreset)[]): ModelPreset[] {
  const presets = loadModelPresets();
  return models.map((m) => {
    if (typeof m === 'object' && m.provider && m.model_id) {
      return { provider: m.provider, model_id: m.model_id, params: m.params || DEFAULT_PARAMS };
    }
    const name = m as string;
    if (presets[name]) return presets[name];
    // Try provider:model_id format
    if (name.includes(':')) {
      const [provider, ...rest] = name.split(':');
      const model_id = rest.join(':');
      return { provider, model_id, params: DEFAULT_PARAMS };
    }
    throw new Error(`Unknown model: ${name}. Use a preset name, provider:model_id format, or a full config object.`);
  });
}
