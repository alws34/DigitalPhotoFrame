const OPTIONS = [0, 90, 180, 270];

export default function OrientationButtons({ value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {OPTIONS.map((deg) => {
        const selected = value === deg;
        return (
          <button
            key={deg}
            onClick={() => onChange(deg)}
            style={{
              padding: '5px 0',
              width: 52,
              borderRadius: 8,
              border: selected ? '1px solid var(--accent)' : '1px solid var(--glass-border)',
              background: selected ? 'var(--accent-glow)' : 'transparent',
              color: selected ? 'var(--accent-hover)' : 'var(--text-secondary)',
              fontWeight: selected ? 600 : 400,
              fontSize: '0.85rem',
              cursor: 'pointer',
              transition: 'all var(--transition)',
              textAlign: 'center',
            }}
          >
            {deg}°
          </button>
        );
      })}
    </div>
  );
}
