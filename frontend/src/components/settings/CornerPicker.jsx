import React from "react";

// Renders a 2x2 grid of corner buttons.
// value: "top-left" | "top-right" | "bottom-left" | "bottom-right"
// onChange: (value) => void

const CORNERS = [
  { value: "top-left",     label: "↖", row: 0, col: 0 },
  { value: "top-right",    label: "↗", row: 0, col: 1 },
  { value: "bottom-left",  label: "↙", row: 1, col: 0 },
  { value: "bottom-right", label: "↘", row: 1, col: 1 },
];

export default function CornerPicker({ value, onChange }) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: "6px",
      width: "fit-content",
    }}>
      {CORNERS.map(c => {
        const selected = value === c.value;
        return (
          <button
            key={c.value}
            onClick={() => onChange(c.value)}
            title={c.value}
            style={{
              width: 44,
              height: 44,
              borderRadius: 8,
              border: selected
                ? "2px solid var(--accent)"
                : "1px solid rgba(255,255,255,0.12)",
              background: selected
                ? "var(--accent-glow)"
                : "rgba(255,255,255,0.05)",
              color: selected ? "var(--accent)" : "rgba(255,255,255,0.6)",
              fontSize: 20,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "all var(--transition)",
              boxShadow: selected ? "0 0 8px var(--accent-glow)" : "none",
            }}
          >
            {c.label}
          </button>
        );
      })}
    </div>
  );
}
