const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(body.error || `HTTP ${resp.status}`);
  }
  return resp.json();
}

// Suites
export const getSuites = () => request<any[]>('/suites');
export const getSuite = (id: string) => request<any>(`/suites/${id}`);
export const createSuite = (data: { id: string; name: string; description?: string }) =>
  request<any>('/suites', { method: 'POST', body: JSON.stringify(data) });
export const updateSuite = (id: string, data: { name?: string; description?: string }) =>
  request<any>(`/suites/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteSuite = (id: string) =>
  request<any>(`/suites/${id}`, { method: 'DELETE' });

// Cases
export const getCases = (suiteId: string) => request<any[]>(`/suites/${suiteId}/cases`);
export const getCase = (suiteId: string, caseId: string) =>
  request<any>(`/suites/${suiteId}/cases/${caseId}`);
export const createCase = (suiteId: string, data: any) =>
  request<any>(`/suites/${suiteId}/cases`, { method: 'POST', body: JSON.stringify(data) });
export const updateCase = (suiteId: string, caseId: string, data: any) =>
  request<any>(`/suites/${suiteId}/cases/${caseId}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteCase = (suiteId: string, caseId: string) =>
  request<any>(`/suites/${suiteId}/cases/${caseId}`, { method: 'DELETE' });

// Runs
export const getRuns = (params?: { suite_id?: string; limit?: number }) => {
  const qs = new URLSearchParams();
  if (params?.suite_id) qs.set('suite_id', params.suite_id);
  if (params?.limit) qs.set('limit', String(params.limit));
  const query = qs.toString();
  return request<any[]>(`/runs${query ? `?${query}` : ''}`);
};
export const getRun = (id: string) => request<any>(`/runs/${id}`);
export const getRunStatus = (id: string) => request<any>(`/runs/${id}/status`);
export const getRunResults = (id: string) => request<any[]>(`/runs/${id}/results`);
export const startRun = (data: { suite_id: string; models: (string | { provider: string; model_id: string; params?: Record<string, unknown> })[]; options?: any }) =>
  request<any>('/runs', { method: 'POST', body: JSON.stringify(data) });
export const cancelRun = (id: string) =>
  request<any>(`/runs/${id}/cancel`, { method: 'POST' });

// Compare
export const compareRuns = (a: string, b: string) =>
  request<any>(`/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);

// Models
export const getModels = () => request<{ presets: Record<string, any>; providers: string[] }>('/models');

// Config
export const getConfig = () => request<{ conductor_url: string | null }>('/config');

// Sync
export const triggerSync = () => request<any>('/sync', { method: 'POST' });
