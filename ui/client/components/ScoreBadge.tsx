import React from 'react';

interface Props {
  score: number;
  passed?: boolean;
}

export default function ScoreBadge({ score, passed }: Props) {
  const bg = passed ? '#d4edda' : score > 0 ? '#fff3cd' : '#f8d7da';
  const color = passed ? '#155724' : score > 0 ? '#856404' : '#721c24';

  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 4,
      background: bg,
      color,
      fontWeight: 600,
      fontSize: 13,
    }}>
      {score.toFixed(3)} {passed !== undefined && (passed ? 'PASS' : 'FAIL')}
    </span>
  );
}
