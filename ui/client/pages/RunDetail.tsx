import React, { useEffect, useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getRun, getRunStatus, getRunResults, cancelRun, getConfig } from '../api.js';
import SummaryCards from '../components/SummaryCards.js';
import ResultsTable from '../components/ResultsTable.js';

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'TERMINATED']);

export default function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<any>(null);
  const [results, setResults] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [conductorUrl, setConductorUrl] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadFull = () => {
    if (!id) return;
    getRun(id).then(setRun).catch((e) => setError(e.message));
    getRunResults(id).then(setResults).catch(() => {});
  };

  useEffect(() => {
    getConfig().then((cfg) => setConductorUrl(cfg.conductor_url)).catch(() => {});
  }, []);

  useEffect(() => {
    loadFull();

    // Poll for status updates
    pollRef.current = setInterval(async () => {
      if (!id) return;
      try {
        const status = await getRunStatus(id);
        setRun((prev: any) => prev ? { ...prev, status: status.status, summary: JSON.stringify(status.summary), error: status.error } : prev);
        if (status.result_count > results.length) {
          getRunResults(id).then(setResults).catch(() => {});
        }
        if (TERMINAL.has(status.status)) {
          if (pollRef.current) clearInterval(pollRef.current);
          loadFull(); // Final load
        }
      } catch { /* ignore transient errors */ }
    }, 3000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [id]);

  const handleCancel = async () => {
    if (!id || !confirm('Cancel this run?')) return;
    try {
      await cancelRun(id);
      loadFull();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!run) return <p>Loading...</p>;

  const summary = (() => {
    try { return JSON.parse(run.summary || '{}'); } catch { return {}; }
  })();

  const isTerminal = TERMINAL.has(run.status);

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link to="/runs" style={{ fontSize: 13, color: '#666' }}>Runs</Link>
        <span style={{ margin: '0 8px', color: '#666' }}>/</span>
        <h1 style={{ fontSize: 24, display: 'inline' }}>{run.id}</h1>
      </div>

      {error && (
        <div style={{ padding: 12, background: '#f8d7da', color: '#721c24', borderRadius: 6, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* Run metadata */}
      <div style={{ background: '#fff', padding: 16, borderRadius: 8, border: '1px solid #e0e0e0', marginBottom: 24, display: 'flex', gap: 32, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 11, color: '#666' }}>Status</div>
          <span style={{
            padding: '2px 8px', borderRadius: 4, fontSize: 14, fontWeight: 600,
            background: run.status === 'COMPLETED' ? '#d4edda' : run.status === 'RUNNING' ? '#cce5ff' : run.status === 'FAILED' ? '#f8d7da' : '#eee',
            color: run.status === 'COMPLETED' ? '#155724' : run.status === 'RUNNING' ? '#004085' : run.status === 'FAILED' ? '#721c24' : '#333',
          }}>
            {run.status}
          </span>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#666' }}>Suite</div>
          <Link to={`/suites/${run.suite_id}`} style={{ color: '#1a1a2e', fontWeight: 600 }}>{run.suite_id}</Link>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#666' }}>Models</div>
          <span style={{ fontSize: 14 }}>{run.models}</span>
        </div>
        <div>
          <div style={{ fontSize: 11, color: '#666' }}>Started</div>
          <span style={{ fontSize: 14 }}>{run.started_at}</span>
        </div>
        {run.workflow_id && (
          <div>
            <div style={{ fontSize: 11, color: '#666' }}>Workflow</div>
            {conductorUrl ? (
              <a
                href={`${conductorUrl}/execution/${run.workflow_id}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ fontSize: 12, fontFamily: 'monospace', color: '#1a73e8' }}
              >
                {run.workflow_id}
              </a>
            ) : (
              <span style={{ fontSize: 12, fontFamily: 'monospace' }}>{run.workflow_id}</span>
            )}
          </div>
        )}
        {!isTerminal && (
          <button
            onClick={handleCancel}
            style={{ padding: '6px 16px', borderRadius: 6, border: '1px solid #dc3545', background: '#fff', color: '#dc3545', cursor: 'pointer', marginLeft: 'auto' }}
          >
            Cancel Run
          </button>
        )}
      </div>

      {run.error && (
        <div style={{ padding: 12, background: '#f8d7da', color: '#721c24', borderRadius: 6, marginBottom: 16 }}>
          <strong>Error:</strong> {run.error}
        </div>
      )}

      {/* Summary Cards */}
      <h2 style={{ fontSize: 18, marginBottom: 12 }}>Model Summary</h2>
      <div style={{ marginBottom: 24 }}>
        <SummaryCards summary={summary} />
      </div>

      {/* Results Table */}
      <h2 style={{ fontSize: 18, marginBottom: 12 }}>
        Results ({results.length})
        {!isTerminal && <span style={{ fontSize: 13, color: '#666', fontWeight: 400, marginLeft: 8 }}>updating...</span>}
      </h2>
      {results.length > 0 ? (
        <ResultsTable results={results} conductorUrl={conductorUrl || undefined} workflowId={run.workflow_id || undefined} />
      ) : (
        <p style={{ color: '#666' }}>{isTerminal ? 'No results recorded.' : 'Waiting for results...'}</p>
      )}
    </div>
  );
}
