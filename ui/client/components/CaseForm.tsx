import React, { useState } from 'react';

interface Props {
  initial?: any;
  onSubmit: (data: any) => void;
  onCancel?: () => void;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  border: '1px solid #ddd',
  borderRadius: 6,
  fontSize: 14,
};

const labelStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  marginBottom: 4,
  display: 'block',
};

export default function CaseForm({ initial, onSubmit, onCancel }: Props) {
  const [mode, setMode] = useState<'form' | 'json'>('form');
  const [rawJson, setRawJson] = useState(initial ? JSON.stringify(initial, null, 2) : '');
  const [id, setId] = useState(initial?.id || '');
  const [prompt, setPrompt] = useState(initial?.prompt || '');
  const [agentType, setAgentType] = useState(initial?.agent_type || 'direct_llm');
  const [scoringMethod, setScoringMethod] = useState(initial?.scoring_method || 'text_match');
  const [expected, setExpected] = useState(initial?.expected ? JSON.stringify(initial.expected) : '');
  const [matchMode, setMatchMode] = useState(initial?.match_mode || 'contains');
  const [tags, setTags] = useState(initial?.tags?.join(', ') || '');
  const [jsonError, setJsonError] = useState('');

  const handleSubmit = () => {
    if (mode === 'json') {
      try {
        const parsed = JSON.parse(rawJson);
        setJsonError('');
        onSubmit(parsed);
      } catch (e) {
        setJsonError((e as Error).message);
      }
      return;
    }

    const data: any = {
      id,
      prompt,
      agent_type: agentType,
      scoring_method: scoringMethod,
    };

    if (tags.trim()) {
      data.tags = tags.split(',').map((t: string) => t.trim()).filter(Boolean);
    }

    if (scoringMethod === 'text_match') {
      data.match_mode = matchMode;
      if (expected.trim()) {
        try { data.expected = JSON.parse(expected); } catch { data.expected = { value: expected }; }
      }
    }

    // Preserve extra fields from initial data
    if (initial) {
      for (const key of Object.keys(initial)) {
        if (!(key in data)) data[key] = initial[key];
      }
    }

    onSubmit(data);
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setMode('form')}
          style={{
            padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
            background: mode === 'form' ? '#1a1a2e' : '#eee',
            color: mode === 'form' ? '#fff' : '#333',
          }}
        >
          Form
        </button>
        <button
          onClick={() => {
            if (mode === 'form') {
              // Sync form data to JSON
              const data: any = { id, prompt, agent_type: agentType, scoring_method: scoringMethod };
              if (tags.trim()) data.tags = tags.split(',').map((t: string) => t.trim()).filter(Boolean);
              if (scoringMethod === 'text_match') {
                data.match_mode = matchMode;
                if (expected.trim()) {
                  try { data.expected = JSON.parse(expected); } catch { data.expected = { value: expected }; }
                }
              }
              if (initial) {
                for (const key of Object.keys(initial)) {
                  if (!(key in data)) data[key] = initial[key];
                }
              }
              setRawJson(JSON.stringify(data, null, 2));
            }
            setMode('json');
          }}
          style={{
            padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
            background: mode === 'json' ? '#1a1a2e' : '#eee',
            color: mode === 'json' ? '#fff' : '#333',
          }}
        >
          Raw JSON
        </button>
      </div>

      {mode === 'json' ? (
        <div>
          <textarea
            value={rawJson}
            onChange={(e) => setRawJson(e.target.value)}
            style={{ ...inputStyle, height: 400, fontFamily: 'monospace', fontSize: 13 }}
          />
          {jsonError && <p style={{ color: 'red', fontSize: 13, marginTop: 4 }}>{jsonError}</p>}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={labelStyle}>ID</label>
            <input style={inputStyle} value={id} onChange={(e) => setId(e.target.value)} disabled={!!initial} />
          </div>
          <div>
            <label style={labelStyle}>Prompt</label>
            <textarea
              style={{ ...inputStyle, height: 120 }}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={labelStyle}>Agent Type</label>
              <select style={inputStyle} value={agentType} onChange={(e) => setAgentType(e.target.value)}>
                <option value="direct_llm">direct_llm</option>
                <option value="tool_use_agent">tool_use_agent</option>
                <option value="claude_code_agent">claude_code_agent</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Scoring Method</label>
              <select style={inputStyle} value={scoringMethod} onChange={(e) => setScoringMethod(e.target.value)}>
                <option value="text_match">text_match</option>
                <option value="llm_judge">llm_judge</option>
                <option value="tool_trace">tool_trace</option>
              </select>
            </div>
          </div>
          {scoringMethod === 'text_match' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={labelStyle}>Expected (JSON or value)</label>
                <input style={inputStyle} value={expected} onChange={(e) => setExpected(e.target.value)} />
              </div>
              <div>
                <label style={labelStyle}>Match Mode</label>
                <select style={inputStyle} value={matchMode} onChange={(e) => setMatchMode(e.target.value)}>
                  <option value="exact">exact</option>
                  <option value="contains">contains</option>
                  <option value="regex">regex</option>
                  <option value="contains_all">contains_all</option>
                  <option value="contains_any">contains_any</option>
                </select>
              </div>
            </div>
          )}
          <div>
            <label style={labelStyle}>Tags (comma-separated)</label>
            <input style={inputStyle} value={tags} onChange={(e) => setTags(e.target.value)} placeholder="math, basic" />
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button
          onClick={handleSubmit}
          style={{
            padding: '8px 24px', borderRadius: 6, border: 'none',
            background: '#1a1a2e', color: '#fff', cursor: 'pointer', fontWeight: 600,
          }}
        >
          Save
        </button>
        {onCancel && (
          <button
            onClick={onCancel}
            style={{
              padding: '8px 24px', borderRadius: 6, border: '1px solid #ddd',
              background: '#fff', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
