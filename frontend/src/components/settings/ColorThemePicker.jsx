const THEMES = [
  { value: 'indigo',  label: 'Indigo',  gradient: 'linear-gradient(135deg, #6366f1, #8b5cf6)' },
  { value: 'sky',     label: 'Sky',     gradient: 'linear-gradient(135deg, #0ea5e9, #38bdf8)' },
  { value: 'emerald', label: 'Emerald', gradient: 'linear-gradient(135deg, #059669, #10b981)' },
  { value: 'rose',    label: 'Rose',    gradient: 'linear-gradient(135deg, #e11d48, #f43f5e)' },
];

export default function ColorThemePicker({ value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
      {THEMES.map(t => {
        const selected = value === t.value;
        return (
          <button
            key={t.value}
            type="button"
            title={t.label}
            aria-label={`Select ${t.label} theme`}
            aria-pressed={selected}
            onClick={() => onChange(t.value)}
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: t.gradient,
              border: selected ? '2px solid #fff' : '2px solid transparent',
              outline: selected ? '2px solid var(--accent)' : 'none',
              outlineOffset: 2,
              padding: 0,
              cursor: 'pointer',
              boxShadow: selected ? '0 0 10px var(--accent-glow)' : 'none',
              transition: 'box-shadow var(--transition), outline var(--transition)',
            }}
          />
        );
      })}
      <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginLeft: 4 }}>
        {THEMES.find(t => t.value === value)?.label ?? value}
      </span>
    </div>
  );
}
