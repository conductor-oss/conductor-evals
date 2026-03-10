import React, { useEffect, useState } from 'react';
import { getModels } from '../api.js';

interface Props {
  selected: string[];
  onChange: (models: string[]) => void;
}

export default function ModelSelector({ selected, onChange }: Props) {
  const [presets, setPresets] = useState<Record<string, any>>({});
  const [providers, setProviders] = useState<string[]>([]);
  const [customInput, setCustomInput] = useState('');

  useEffect(() => {
    getModels()
      .then((data) => {
        setPresets(data.presets);
        setProviders(data.providers);
      })
      .catch(console.error);
  }, []);

  const toggle = (name: string) => {
    if (selected.includes(name)) {
      onChange(selected.filter((m) => m !== name));
    } else {
      onChange([...selected, name]);
    }
  };

  const addCustomModel = () => {
    const value = customInput.trim();
    if (!value || selected.includes(value)) return;
    if (!value.includes(':')) return;
    onChange([...selected, value]);
    setCustomInput('');
  };

  const isCustom = (name: string) => !(name in presets);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {Object.entries(presets).map(([name, config]) => (
          <button
            key={name}
            onClick={() => toggle(name)}
            style={{
              padding: '6px 12px',
              borderRadius: 6,
              border: selected.includes(name) ? '2px solid #1a1a2e' : '2px solid #ddd',
              background: selected.includes(name) ? '#1a1a2e' : '#fff',
              color: selected.includes(name) ? '#fff' : '#333',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {name}
            <span style={{ fontSize: 11, opacity: 0.7, marginLeft: 4 }}>
              ({(config as any).provider})
            </span>
          </button>
        ))}
        {selected.filter(isCustom).map((name) => (
          <button
            key={name}
            onClick={() => toggle(name)}
            style={{
              padding: '6px 12px',
              borderRadius: 6,
              border: '2px solid #1a1a2e',
              background: '#1a1a2e',
              color: '#fff',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {name}
            <span
              style={{ marginLeft: 6, fontSize: 11, opacity: 0.7 }}
              title="Remove custom model"
            >
              x
            </span>
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <input
          type="text"
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') addCustomModel(); }}
          placeholder="provider:model_id"
          list="provider-hints"
          style={{
            padding: '6px 10px',
            borderRadius: 6,
            border: '1px solid #ddd',
            fontSize: 13,
            width: 260,
          }}
        />
        <datalist id="provider-hints">
          {providers.map((p) => (
            <option key={p} value={`${p}:`} />
          ))}
        </datalist>
        <button
          onClick={addCustomModel}
          disabled={!customInput.includes(':')}
          style={{
            padding: '6px 12px',
            borderRadius: 6,
            border: '1px solid #ddd',
            background: customInput.includes(':') ? '#1a1a2e' : '#eee',
            color: customInput.includes(':') ? '#fff' : '#999',
            cursor: customInput.includes(':') ? 'pointer' : 'default',
            fontSize: 13,
          }}
        >
          Add
        </button>
      </div>
    </div>
  );
}
