import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getSuite, deleteCase, createCase, deleteSuite, startRun } from '../api.js';
import CaseForm from '../components/CaseForm.js';
import ModelSelector from '../components/ModelSelector.js';

export default function SuiteDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [suite, setSuite] = useState<any>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showRun, setShowRun] = useState(false);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [error, setError] = useState('');

  const load = () => {
    if (id) getSuite(id).then(setSuite).catch((e) => setError(e.message));
  };

  useEffect(() => { load(); }, [id]);

  const handleDeleteCase = async (caseId: string) => {
    if (!confirm(`Delete case "${caseId}"?`)) return;
    try {
      await deleteCase(id!, caseId);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleDeleteSuite = async () => {
    if (!confirm(`Delete suite "${id}" and all its cases?`)) return;
    try {
      await deleteSuite(id!);
      navigate('/');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleAddCase = async (data: any) => {
    try {
      await createCase(id!, data);
      setShowAdd(false);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleRunSuite = async () => {
    if (selectedModels.length === 0) return;
    try {
      const result = await startRun({ suite_id: id!, models: selectedModels });
      navigate(`/runs/${result.run_id}`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!suite) return <p>Loading...</p>;

  const cases = suite.cases || [];
  const recentRuns = suite.recent_runs || [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Link to="/" style={{ fontSize: 13, color: '#666' }}>Dashboard</Link>
          <span style={{ margin: '0 8px', color: '#666' }}>/</span>
          <h1 style={{ fontSize: 24, display: 'inline' }}>{suite.name}</h1>
          <span style={{ marginLeft: 8, fontSize: 13, color: '#666' }}>{suite.id}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => setShowRun(!showRun)}
            style={{ padding: '8px 16px', borderRadius: 6, border: 'none', background: '#1a1a2e', color: '#fff', cursor: 'pointer' }}
          >
            Run Suite
          </button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #ddd', background: '#fff', cursor: 'pointer' }}
          >
            Add Case
          </button>
          <button
            onClick={handleDeleteSuite}
            style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #dc3545', background: '#fff', color: '#dc3545', cursor: 'pointer' }}
          >
            Delete
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, background: '#f8d7da', color: '#721c24', borderRadius: 6, marginBottom: 16 }}>
          {error}
          <button onClick={() => setError('')} style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer' }}>x</button>
        </div>
      )}

      {showRun && (
        <div style={{ background: '#fff', padding: 16, borderRadius: 8, border: '1px solid #ddd', marginBottom: 16 }}>
          <h3 style={{ marginBottom: 12 }}>Run Suite</h3>
          <ModelSelector selected={selectedModels} onChange={setSelectedModels} />
          <button
            onClick={handleRunSuite}
            disabled={selectedModels.length === 0}
            style={{
              marginTop: 12, padding: '8px 24px', borderRadius: 6, border: 'none',
              background: selectedModels.length > 0 ? '#1a1a2e' : '#ccc', color: '#fff',
              cursor: selectedModels.length > 0 ? 'pointer' : 'default', fontWeight: 600,
            }}
          >
            Start
          </button>
        </div>
      )}

      {showAdd && (
        <div style={{ background: '#fff', padding: 16, borderRadius: 8, border: '1px solid #ddd', marginBottom: 16 }}>
          <h3 style={{ marginBottom: 12 }}>New Case</h3>
          <CaseForm onSubmit={handleAddCase} onCancel={() => setShowAdd(false)} />
        </div>
      )}

      {/* Cases Table */}
      <h2 style={{ fontSize: 18, marginBottom: 12 }}>Cases ({cases.length})</h2>
      {cases.length === 0 ? (
        <p style={{ color: '#666' }}>No cases. Add one above or drop JSON files into evals/{id}/</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8, marginBottom: 32 }}>
          <thead>
            <tr>
              {['ID', 'Agent Type', 'Scoring', 'Prompt', 'Actions'].map((h) => (
                <th key={h} style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '2px solid #ddd', fontSize: 13 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cases.map((c: any) => (
              <tr key={c.id}>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>
                  <Link to={`/suites/${id}/cases/${c.id}`} style={{ color: '#1a1a2e', fontWeight: 600 }}>
                    {c.id}
                  </Link>
                </td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{c.agent_type}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{c.scoring_method}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13, maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.prompt}
                </td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13, display: 'flex', gap: 12 }}>
                  <Link
                    to={`/suites/${id}/cases/${c.id}`}
                    style={{ color: '#1a73e8', textDecoration: 'none', fontSize: 13 }}
                  >
                    Edit
                  </Link>
                  <button
                    onClick={() => handleDeleteCase(c.id)}
                    style={{ background: 'none', border: 'none', color: '#dc3545', cursor: 'pointer', fontSize: 13 }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Recent Runs */}
      {recentRuns.length > 0 && (
        <>
          <h2 style={{ fontSize: 18, marginBottom: 12 }}>Recent Runs</h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8 }}>
            <thead>
              <tr>
                {['Run ID', 'Models', 'Status', 'Started'].map((h) => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '2px solid #ddd', fontSize: 13 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recentRuns.map((r: any) => (
                <tr key={r.id}>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>
                    <Link to={`/runs/${r.id}`} style={{ color: '#1a1a2e' }}>{r.id}</Link>
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{r.models}</td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>
                    <span style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: 12, fontWeight: 600,
                      background: r.status === 'COMPLETED' ? '#d4edda' : r.status === 'RUNNING' ? '#cce5ff' : '#f8d7da',
                      color: r.status === 'COMPLETED' ? '#155724' : r.status === 'RUNNING' ? '#004085' : '#721c24',
                    }}>
                      {r.status}
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{r.started_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
