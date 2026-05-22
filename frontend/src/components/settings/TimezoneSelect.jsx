import { useRef, useState } from "react";

export default function TimezoneSelect({ value, choices, onChange }) {
  const [query, setQuery] = useState(value ?? "");
  const [open, setOpen] = useState(false);
  const skipBlur = useRef(false);
  // Track the last committed value prop so we can detect external updates.
  // Stored as state so we can trigger a re-render with the new query.
  const [committedValue, setCommittedValue] = useState(value ?? "");

  // Derived-state pattern (React docs recommended way): when the prop changes
  // from outside, sync query without an effect.
  if (value !== committedValue) {
    setCommittedValue(value ?? "");
    setQuery(value ?? "");
  }

  const filtered = query.trim()
    ? choices.filter((c) => c.toLowerCase().includes(query.toLowerCase())).slice(0, 80)
    : choices.slice(0, 80);

  function select(choice) {
    onChange(choice);
    setQuery(choice);
    setOpen(false);
  }

  function handleBlur() {
    if (skipBlur.current) { skipBlur.current = false; return; }
    // Restore to last valid value if query doesn't match
    if (!choices.includes(query)) setQuery(value ?? "");
    setOpen(false);
  }

  return (
    <div style={{ position: "relative", flex: 1 }}>
      <input
        type="text"
        value={query}
        placeholder="Search timezone…"
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={handleBlur}
        style={{ width: "100%" }}
      />
      {open && filtered.length > 0 && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0, zIndex: 200,
          background: "var(--surface, #1e1e2e)", border: "1px solid var(--glass-border, #444)",
          borderRadius: 6, maxHeight: 220, overflowY: "auto", boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
        }}>
          {filtered.map((c) => (
            <div
              key={c}
              onMouseDown={() => { skipBlur.current = true; select(c); }}
              style={{
                padding: "6px 12px", cursor: "pointer", fontSize: "0.9em",
                background: c === value ? "var(--accent, #6366f1)" : "transparent",
                color: c === value ? "#fff" : "inherit",
              }}
              onMouseEnter={(e) => { if (c !== value) e.currentTarget.style.background = "rgba(255,255,255,0.07)"; }}
              onMouseLeave={(e) => { if (c !== value) e.currentTarget.style.background = "transparent"; }}
            >
              {c}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
