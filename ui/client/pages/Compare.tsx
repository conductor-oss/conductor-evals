import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getRuns, compareRuns } from '../api.js';
import ScoreBadge from '../components/ScoreBadge.js';

export default function Compare() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [runs, setRuns] = useState<any[]>([]);
  const [runA, setRunA] = useState(searchParams.get('a') || '');
  const [runB, setRunB] = useState(searchParams.get('b') || '');
  const [comparison, setComparison] = useState<any>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getRuns({ limit: 50 }).then(setRuns).catch(console.error);
  }, []);

  useEffect(() => {
    if (runA && runB) {
      compareRuns(runA, runB)
        .then(setComparison)
        .catch((e) => setError(e.message));
    }
  }, [runA, runB]);

  const handleCompare = () => {
    if (runA && runB) {
      setSearchParams({ a: runA, b: runB });
      compareRuns(runA, runB)
        .then((c) => { setComparison(c); setError(''); })
        .catch((e) => setError(e.message));
    }
  };

  const deltaColor = (delta: number) => delta > 0 ? '#155724' : delta < 0 ? '#721c24' : '#666';
  const deltaStr = (delta: number) => (delta > 0 ? '+' : '') + delta.toFixed(3);

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24 }}>Compare Runs</h1>

      <div style={{ background: '#fff', padding: 16, borderRadius: 8, border: '1px solid #e0e0e0', marginBottom: 24, display: 'flex', gap: 12, alignItems: 'end' }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>Run A (baseline)</label>
          <select
            value={runA}
            onChange={(e) => setRunA(e.target.value)}
            style={{ width: '100%', padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6 }}
          >
            <option value="">Select...</option>
            {runs.map((r: any) => (
              <option key={r.id} value={r.id}>{r.id} ({r.suite_id} - {r.status})</option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>Run B (comparison)</label>
          <select
            value={runB}
            onChange={(e) => setRunB(e.target.value)}
            style={{ width: '100%', padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6 }}
          >
            <option value="">Select...</option>
            {runs.map((r: any) => (
              <option key={r.id} value={r.id}>{r.id} ({r.suite_id} - {r.status})</option>
            ))}
          </select>
        </div>
        <button
          onClick={handleCompare}
          disabled={!runA || !runB}
          style={{
            padding: '8px 24px', borderRadius: 6, border: 'none',
            background: runA && runB ? '#1a1a2e' : '#ccc', color: '#fff',
            cursor: runA && runB ? 'pointer' : 'default', fontWeight: 600, whiteSpace: 'nowrap',
          }}
        >
          Compare
        </button>
      </div>

      {error && (
        <div style={{ padding: 12, background: '#f8d7da', color: '#721c24', borderRadius: 6, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {comparison && (
        <>
          {/* Model Comparison */}
          <h2 style={{ fontSize: 18, marginBottom: 12 }}>Model Comparison</h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8, marginBottom: 24 }}>
            <thead>
              <tr>
                {['Model', 'Run A Avg', 'Run B Avg', 'Delta', 'Run A Pass%', 'Run B Pass%'].map((h) => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '2px solid #ddd', fontSize: 13, fontWeight: 600 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {comparison.model_comparison.map((m: any) => (
                <tr key={m.model}>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13, fontWeight: 600 }}>{m.model}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{m.run_a_avg.toFixed(3)}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{m.run_b_avg.toFixed(3)}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13, fontWeight: 600, color: deltaColor(m.delta) }}>
                    {deltaStr(m.delta)}
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{m.run_a_pass_rate.toFixed(1)}%</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{m.run_b_pass_rate.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Case Comparison */}
          <h2 style={{ fontSize: 18, marginBottom: 12 }}>Case Comparison</h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8 }}>
            <thead>
              <tr>
                {['Case', 'Model', 'Run A Score', 'Run B Score', 'Delta', 'Run A', 'Run B'].map((h) => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '2px solid #ddd', fontSize: 13, fontWeight: 600 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {comparison.case_comparison.map((c: any, i: number) => (
                <tr key={i}>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{c.case_id}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{c.model_id}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{c.run_a_score.toFixed(3)}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{c.run_b_score.toFixed(3)}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13, fontWeight: 600, color: deltaColor(c.delta) }}>
                    {deltaStr(c.delta)}
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>
                    <ScoreBadge score={c.run_a_score} passed={!!c.run_a_passed} />
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>
                    <ScoreBadge score={c.run_b_score} passed={!!c.run_b_passed} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
