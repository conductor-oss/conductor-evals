import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE_DIR = process.env.BASE_DIR || path.resolve(__dirname, '..', '..');
const CONFIG_FILE = path.join(BASE_DIR, 'config', 'orkes-config.json');

export interface ConductorConfig {
  url: string;
  getHeaders: () => Promise<Record<string, string>>;
}

/**
 * Manages JWT token lifecycle for Orkes Conductor authentication.
 * Exchanges keyId + keySecret for a short-lived token via POST /api/token,
 * caches it, and refreshes automatically when expired.
 */
class TokenManager {
  private token: string | null = null;
  private tokenExpiresAt = 0;

  // Refresh 5 minutes before actual expiry to avoid edge-case failures
  private static readonly EXPIRY_BUFFER_MS = 5 * 60 * 1000;
  // Default token lifetime assumption: 24 hours
  private static readonly DEFAULT_TTL_MS = 24 * 60 * 60 * 1000;

  constructor(
    private readonly conductorUrl: string,
    private readonly keyId: string,
    private readonly keySecret: string,
  ) {}

  async getToken(): Promise<string> {
    if (this.token && Date.now() < this.tokenExpiresAt) {
      return this.token;
    }
    return this.refreshToken();
  }

  private async refreshToken(): Promise<string> {
    const resp = await fetch(`${this.conductorUrl}/api/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyId: this.keyId, keySecret: this.keySecret }),
    });

    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(
        `Failed to obtain Conductor auth token: ${resp.status} ${body}`
      );
    }

    const data = (await resp.json()) as { token: string };
    this.token = data.token;
    this.tokenExpiresAt =
      Date.now() + TokenManager.DEFAULT_TTL_MS - TokenManager.EXPIRY_BUFFER_MS;
    return this.token;
  }
}

/**
 * Build a getHeaders function from credentials.
 *
 * - If both keyId and keySecret are provided, uses TokenManager to exchange
 *   them for a JWT (Orkes Conductor auth flow).
 * - If only keyId is provided (no secret), uses it directly as the
 *   X-Authorization value (open-source Conductor / static token).
 */
function makeGetHeaders(
  conductorUrl: string,
  keyId: string,
  keySecret?: string,
): () => Promise<Record<string, string>> {
  if (keySecret) {
    const tokenManager = new TokenManager(conductorUrl, keyId, keySecret);
    return async () => {
      const token = await tokenManager.getToken();
      return {
        'Content-Type': 'application/json',
        'X-Authorization': token,
      };
    };
  }

  // No secret — use keyId directly (backwards compatible)
  const staticHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Authorization': keyId,
  };
  return async () => staticHeaders;
}

export function loadConfig(): ConductorConfig {
  // Check environment variables first
  const envUrl = process.env.CONDUCTOR_URL;
  const envKey = process.env.CONDUCTOR_AUTH_KEY;
  const envSecret = process.env.CONDUCTOR_AUTH_SECRET;

  if (envUrl && envKey) {
    const url = envUrl.replace(/\/+$/, '').replace(/\/api$/, '');
    return {
      url,
      getHeaders: makeGetHeaders(url, envKey, envSecret),
    };
  }

  // Fall back to config file
  if (!fs.existsSync(CONFIG_FILE)) {
    throw new Error(
      `Config file not found: ${CONFIG_FILE}. ` +
      'Set CONDUCTOR_URL and CONDUCTOR_AUTH_KEY env vars, ' +
      'or create the config file from config/orkes-config.example.json'
    );
  }

  const config = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
  const cluster = config.clusters[0];
  const url = (cluster.url as string).replace(/\/+$/, '').replace(/\/api$/, '');
  return {
    url,
    getHeaders: makeGetHeaders(url, cluster.keyId, cluster.keySecret),
  };
}

export function getBaseDir(): string {
  return BASE_DIR;
}

export function getEvalsDir(): string {
  return path.join(BASE_DIR, 'evals');
}
