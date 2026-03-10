import React, { useState } from 'react';
import ScoreBadge from './ScoreBadge.js';

interface Result {
  case_id: string;
  model_id: string;
  provider: string;
  score: number;
  passed: number;
  response_preview: string;
  latency_ms: number;
  token_usage: string;
  scoring_details: string;
  tool_calls?: string;
  sub_workflow_id: string;
}

interface Props {
  results: Result[];
  conductorUrl?: string;
  workflowId?: string;
}

export default function ResultsTable({ results, conductorUrl, workflowId }: Props) {
  const [sortKey, setSortKey] = useState<keyof Result>('case_id');
  const [sortAsc, setSortAsc] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const sorted = [...results].sort((a, b) => {
    const va = a[sortKey];
    const vb = b[sortKey];
    const cmp = va < vb ? -1 : va > vb ? 1 : 0;
    return sortAsc ? cmp : -cmp;
  });

  const toggleSort = (key: keyof Result) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(true); }
  };

  const toggleExpand = (idx: number) => {
    const next = new Set(expanded);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    setExpanded(next);
  };

  const headerStyle: React.CSSProperties = {
    padding: '8px 12px', textAlign: 'left', cursor: 'pointer',
    borderBottom: '2px solid #ddd', fontSize: 13, fontWeight: 600,
    userSelect: 'none',
  };

  const cellStyle: React.CSSProperties = {
    padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13,
  };

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8 }}>
      <thead>
        <tr>
          <th style={headerStyle} onClick={() => toggleSort('case_id')}>Case</th>
          <th style={headerStyle} onClick={() => toggleSort('model_id')}>Model</th>
          <th style={headerStyle} onClick={() => toggleSort('score')}>Score</th>
          <th style={headerStyle} onClick={() => toggleSort('latency_ms')}>Latency</th>
          <th style={headerStyle}>Details</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((r, i) => (
          <React.Fragment key={`${r.case_id}-${r.model_id}`}>
            <tr style={{ cursor: 'pointer' }} onClick={() => toggleExpand(i)}>
              <td style={cellStyle}>{r.case_id}</td>
              <td style={cellStyle}>{r.model_id}</td>
              <td style={cellStyle}><ScoreBadge score={r.score} passed={!!r.passed} /></td>
              <td style={cellStyle}>{r.latency_ms}ms</td>
              <td style={cellStyle}>{expanded.has(i) ? 'collapse' : 'expand'}</td>
            </tr>
            {expanded.has(i) && (
              <tr>
                <td colSpan={5} style={{ ...cellStyle, background: '#f9f9f9' }}>
                  <div style={{ padding: 8 }}>
                    <strong>Response:</strong>
                    <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, marginTop: 4 }}>
                      {r.response_preview || '(no preview)'}
                    </pre>
                    <div style={{ marginTop: 8 }}>
                      <strong>Token Usage:</strong> {r.token_usage}
                    </div>
                    <div style={{ marginTop: 4 }}>
                      <strong>Scoring Details:</strong> {r.scoring_details}
                    </div>
                    {(() => {
                      try {
                        const calls = JSON.parse(r.tool_calls || '[]');
                        if (calls.length === 0) return null;
                        return (
                          <div style={{ marginTop: 8 }}>
                            <strong>Tool Calls ({calls.length}):</strong>
                            <div style={{ marginTop: 4 }}>
                              {calls.map((tc: { tool_name: string; args: Record<string, unknown> }, j: number) => (
                                <div key={j} style={{
                                  background: '#fff', border: '1px solid #e0e0e0', borderRadius: 6,
                                  padding: '6px 10px', marginTop: j > 0 ? 6 : 0, fontSize: 12,
                                }}>
                                  <span style={{ fontWeight: 600, color: '#1a1a2e' }}>{tc.tool_name}</span>
                                  <pre style={{
                                    whiteSpace: 'pre-wrap', margin: '4px 0 0', fontSize: 11,
                                    color: '#555', fontFamily: 'monospace',
                                  }}>{JSON.stringify(tc.args, null, 2)}</pre>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      } catch { return null; }
                    })()}
                    {conductorUrl && (r.sub_workflow_id || workflowId) && (
                      <div style={{ marginTop: 8 }}>
                        <a
                          href={`${conductorUrl}/execution/${r.sub_workflow_id || workflowId}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: '#1a73e8', fontSize: 12 }}
                        >
                          View Workflow Execution
                        </a>
                      </div>
                    )}
                  </div>
                </td>
              </tr>
            )}
          </React.Fragment>
        ))}
      </tbody>
    </table>
  );
}
