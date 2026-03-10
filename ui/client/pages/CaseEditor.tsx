import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getCase, updateCase } from '../api.js';
import CaseForm from '../components/CaseForm.js';

export default function CaseEditor() {
  const { sid, cid } = useParams<{ sid: string; cid: string }>();
  const navigate = useNavigate();
  const [caseData, setCaseData] = useState<any>(null);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (sid && cid) {
      getCase(sid, cid).then((c) => {
        // Parse full_json to get the actual case data
        const parsed = c.full_json ? JSON.parse(c.full_json) : c;
        setCaseData(parsed);
      }).catch((e) => setError(e.message));
    }
  }, [sid, cid]);

  const handleSubmit = async (data: any) => {
    try {
      await updateCase(sid!, cid!, data);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!caseData) return <p>Loading...</p>;

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link to="/" style={{ fontSize: 13, color: '#666' }}>Dashboard</Link>
        <span style={{ margin: '0 8px', color: '#666' }}>/</span>
        <Link to={`/suites/${sid}`} style={{ fontSize: 13, color: '#666' }}>{sid}</Link>
        <span style={{ margin: '0 8px', color: '#666' }}>/</span>
        <h1 style={{ fontSize: 24, display: 'inline' }}>{cid}</h1>
      </div>

      {error && (
        <div style={{ padding: 12, background: '#f8d7da', color: '#721c24', borderRadius: 6, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {saved && (
        <div style={{ padding: 12, background: '#d4edda', color: '#155724', borderRadius: 6, marginBottom: 16 }}>
          Case saved successfully.
        </div>
      )}

      <div style={{ background: '#fff', padding: 24, borderRadius: 8, border: '1px solid #e0e0e0' }}>
        <CaseForm
          initial={caseData}
          onSubmit={handleSubmit}
          onCancel={() => navigate(`/suites/${sid}`)}
        />
      </div>
    </div>
  );
}
