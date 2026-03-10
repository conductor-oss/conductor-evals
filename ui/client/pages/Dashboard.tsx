import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { getSuites, getRuns, createSuite, triggerSync, startRun } from '../api.js';
import ModelSelector from '../components/ModelSelector.js';

export default function Dashboard() {
  const [suites, setSuites] = useState<any[]>([]);
  const [recentRuns, setRecentRuns] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [quickSuite, setQuickSuite] = useState('');
  const [quickModels, setQuickModels] = useState<string[]>([]);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const load = () => {
    getSuites().then(setSuites).catch(console.error);
    getRuns({ limit: 5 }).then(setRecentRuns).catch(console.error);
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    if (!newId || !newName) return;
    try {
      await createSuite({ id: newId, name: newName });
      setShowCreate(false);
      setNewId('');
      setNewName('');
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleQuickRun = async () => {
    if (!quickSuite || quickModels.length === 0) return;
    try {
      const result = await startRun({ suite_id: quickSuite, models: quickModels });
      navigate(`/runs/${result.run_id}`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24 }}>Dashboard</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => triggerSync().then(load)}
            style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #ddd', background: '#fff', cursor: 'pointer' }}
          >
            Sync Files
          </button>
          <button
            onClick={() => setShowCreate(true)}
            style={{ padding: '8px 16px', borderRadius: 6, border: 'none', background: '#1a1a2e', color: '#fff', cursor: 'pointer' }}
          >
            New Suite
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, background: '#f8d7da', color: '#721c24', borderRadius: 6, marginBottom: 16 }}>
          {error}
          <button onClick={() => setError('')} style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer' }}>x</button>
        </div>
      )}

      {showCreate && (
        <div style={{ background: '#fff', padding: 16, borderRadius: 8, marginBottom: 16, border: '1px solid #ddd' }}>
          <h3 style={{ marginBottom: 12 }}>Create Suite</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              placeholder="suite-id"
              value={newId}
              onChange={(e) => setNewId(e.target.value)}
              style={{ flex: 1, padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6 }}
            />
            <input
              placeholder="Display Name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={{ flex: 1, padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6 }}
            />
            <button onClick={handleCreate} style={{ padding: '8px 16px', borderRadius: 6, border: 'none', background: '#1a1a2e', color: '#fff', cursor: 'pointer' }}>
              Create
            </button>
            <button onClick={() => setShowCreate(false)} style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #ddd', background: '#fff', cursor: 'pointer' }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Suite Cards */}
      <h2 style={{ fontSize: 18, marginBottom: 12 }}>Suites</h2>
      {suites.length === 0 ? (
        <p style={{ color: '#666' }}>No suites found. Create one or add JSON files to evals/.</p>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginBottom: 32 }}>
          {suites.map((s: any) => (
            <Link
              key={s.id}
              to={`/suites/${s.id}`}
              style={{
                textDecoration: 'none',
                color: 'inherit',
                background: '#fff',
                border: '1px solid #e0e0e0',
                borderRadius: 8,
                padding: 16,
                transition: 'box-shadow 0.2s',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 4 }}>{s.name}</div>
              <div style={{ fontSize: 13, color: '#666', marginBottom: 8 }}>{s.id}</div>
              <div style={{ display: 'flex', gap: 16, fontSize: 13, color: '#444' }}>
                <span>{s.case_count} cases</span>
                <span>{s.run_count} runs</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Quick Run */}
      <h2 style={{ fontSize: 18, marginBottom: 12 }}>Quick Run</h2>
      <div style={{ background: '#fff', padding: 16, borderRadius: 8, border: '1px solid #e0e0e0', marginBottom: 32 }}>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>Suite</label>
          <select
            value={quickSuite}
            onChange={(e) => setQuickSuite(e.target.value)}
            style={{ padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, width: '100%' }}
          >
            <option value="">Select a suite...</option>
            {suites.map((s: any) => (
              <option key={s.id} value={s.id}>{s.name} ({s.case_count} cases)</option>
            ))}
          </select>
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>Models</label>
          <ModelSelector selected={quickModels} onChange={setQuickModels} />
        </div>
        <button
          onClick={handleQuickRun}
          disabled={!quickSuite || quickModels.length === 0}
          style={{
            padding: '8px 24px', borderRadius: 6, border: 'none',
            background: quickSuite && quickModels.length > 0 ? '#1a1a2e' : '#ccc',
            color: '#fff', cursor: quickSuite && quickModels.length > 0 ? 'pointer' : 'default',
            fontWeight: 600,
          }}
        >
          Start Run
        </button>
      </div>

      {/* Recent Runs */}
      <h2 style={{ fontSize: 18, marginBottom: 12 }}>Recent Runs</h2>
      {recentRuns.length === 0 ? (
        <p style={{ color: '#666' }}>No runs yet.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8 }}>
          <thead>
            <tr>
              {['Run ID', 'Suite', 'Models', 'Status', 'Started'].map((h) => (
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
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{r.suite_id}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{r.models}</td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>
                  <span style={{
                    padding: '2px 8px', borderRadius: 4, fontSize: 12, fontWeight: 600,
                    background: r.status === 'COMPLETED' ? '#d4edda' : r.status === 'RUNNING' ? '#cce5ff' : r.status === 'FAILED' ? '#f8d7da' : '#eee',
                    color: r.status === 'COMPLETED' ? '#155724' : r.status === 'RUNNING' ? '#004085' : r.status === 'FAILED' ? '#721c24' : '#333',
                  }}>
                    {r.status}
                  </span>
                </td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontSize: 13 }}>{r.started_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
