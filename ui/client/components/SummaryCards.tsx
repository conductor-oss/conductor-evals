import React from 'react';

interface ModelSummary {
  avg_score: number;
  pass_rate: number;
  passed_cases: number;
  total_cases: number;
}

interface Props {
  summary: Record<string, ModelSummary>;
}

export default function SummaryCards({ summary }: Props) {
  const models = Object.entries(summary).sort(([a], [b]) => a.localeCompare(b));

  if (models.length === 0) {
    return <p style={{ color: '#666' }}>No summary data available yet.</p>;
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
      {models.map(([modelId, stats]) => (
        <div key={modelId} style={{
          background: '#fff',
          border: '1px solid #e0e0e0',
          borderRadius: 8,
          padding: 16,
        }}>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 12 }}>{modelId}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <div style={{ fontSize: 11, color: '#666' }}>Avg Score</div>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{stats.avg_score?.toFixed(3) ?? '—'}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#666' }}>Pass Rate</div>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{stats.pass_rate?.toFixed(1) ?? '—'}%</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#666' }}>Passed</div>
              <div style={{ fontSize: 16 }}>{stats.passed_cases ?? 0}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: '#666' }}>Total</div>
              <div style={{ fontSize: 16 }}>{stats.total_cases ?? 0}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
