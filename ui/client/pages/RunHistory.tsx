import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getRuns } from '../api.js';

export default function RunHistory() {
  const [runs, setRuns] = useState<any[]>([]);

  useEffect(() => {
    getRuns({ limit: 50 }).then(setRuns).catch(console.error);
  }, []);

  const statusBadge = (status: string) => {
    const styles: Record<string, { bg: string; color: string }> = {
      COMPLETED: { bg: '#d4edda', color: '#155724' },
      RUNNING: { bg: '#cce5ff', color: '#004085' },
      PENDING: { bg: '#fff3cd', color: '#856404' },
      FAILED: { bg: '#f8d7da', color: '#721c24' },
      TERMINATED: { bg: '#e2e3e5', color: '#383d41' },
    };
    const s = styles[status] || styles.PENDING;
    return (
      <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 12, fontWeight: 600, background: s.bg, color: s.color }}>
        {status}
      </span>
    );
  };

  const parseSummary = (summaryStr: string) => {
    try {
      const summary = JSON.parse(summaryStr || '{}');
      const models = Object.keys(summary);
      if (models.length === 0) return '—';
      const totalPassed = models.reduce((sum, m) => sum + (summary[m]?.passed_cases || 0), 0);
      const totalCases = models.reduce((sum, m) => sum + (summary[m]?.total_cases || 0), 0);
      return totalCases > 0 ? `${totalPassed}/${totalCases} (${((totalPassed / totalCases) * 100).toFixed(0)}%)` : '—';
    } catch {
      return '—';
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24 }}>Run History</h1>

      {runs.length === 0 ? (
        <p style={{ color: '#666' }}>No runs yet. Start one from the Dashboard or a Suite page.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8 }}>
          <thead>
            <tr>
              {['Run ID', 'Suite', 'Models', 'Status', 'Pass Rate', 'Started', 'Duration'].map((h) => (
                <th key={h} style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '2px solid #ddd', fontSize: 13, fontWeight: 600 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map((r: any) => {
              const duration = r.completed_at && r.started_at
                ? `${Math.round((new Date(r.completed_at + 'Z').getTime() - new Date(r.started_at + 'Z').getTime()) / 1000)}s`
                : '—';
              return (
                <tr key={r.id}>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>
                    <Link to={`/runs/${r.id}`} style={{ color: '#1a1a2e', fontWeight: 600 }}>{r.id}</Link>
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>
                    <Link to={`/suites/${r.suite_id}`} style={{ color: '#1a1a2e' }}>{r.suite_id}</Link>
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{r.models}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{statusBadge(r.status)}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{parseSummary(r.summary)}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{r.started_at}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{duration}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
