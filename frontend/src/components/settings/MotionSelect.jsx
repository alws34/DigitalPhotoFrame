const OPTIONS = [
  { value: 'subtle',    label: 'Subtle',    detail: '150ms' },
  { value: 'cinematic', label: 'Cinematic', detail: '350ms' },
];

export default function MotionSelect({ value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {OPTIONS.map(o => {
        const selected = value === o.value;
        return (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            style={{
              padding: '5px 14px',
              borderRadius: 20,
              border: selected ? '1px solid var(--accent)' : '1px solid var(--glass-border)',
              background: selected ? 'var(--accent-glow)' : 'transparent',
              color: selected ? 'var(--accent-hover)' : 'var(--text-secondary)',
              fontWeight: selected ? 600 : 400,
              fontSize: '0.82rem',
              cursor: 'pointer',
              transition: 'all var(--transition)',
            }}
          >
            {o.label} <span style={{ opacity: 0.6, fontSize: '0.75em' }}>({o.detail})</span>
          </button>
        );
      })}
    </div>
  );
}
