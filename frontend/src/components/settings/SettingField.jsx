import React from "react";

export default function SettingField({ fieldKey, value, onChange, depth = 0 }) {
  const label = fieldKey
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  const labelEl = (
    <span style={{ color: "var(--text-secondary)", fontSize: "0.85em", minWidth: 160 }}>
      {label}
    </span>
  );

  const row = (input) => (
    <div
      key={fieldKey}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "6px 0",
        paddingLeft: depth * 16,
      }}
    >
      {labelEl}
      <div style={{ flex: 1 }}>{input}</div>
    </div>
  );

  if (typeof value === "boolean") {
    return row(
      <label className="toggle">
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(fieldKey, e.target.checked)}
        />
        <span className="toggle-track" />
      </label>
    );
  }

  if (typeof value === "number") {
    const isFloat = !Number.isInteger(value);
    return row(
      <input
        type="number"
        value={value}
        step={isFloat ? 0.01 : 1}
        onChange={(e) => {
          const v = isFloat ? parseFloat(e.target.value) : parseInt(e.target.value, 10);
          if (!isNaN(v)) onChange(fieldKey, v);
        }}
        style={{ maxWidth: 160 }}
      />
    );
  }

  if (typeof value === "string") {
    return row(
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(fieldKey, e.target.value)}
      />
    );
  }

  if (Array.isArray(value)) {
    const isSimple = value.every((v) => typeof v !== "object");
    if (isSimple) {
      return row(
        <input
          type="text"
          value={value.join(", ")}
          onChange={(e) =>
            onChange(
              fieldKey,
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
                .map((s) => (isNaN(Number(s)) ? s : Number(s)))
            )
          }
        />
      );
    }
    return row(
      <textarea
        rows={3}
        value={JSON.stringify(value, null, 2)}
        onChange={(e) => {
          try {
            onChange(fieldKey, JSON.parse(e.target.value));
          } catch {
            // ignore invalid JSON while user is typing
          }
        }}
        style={{ fontFamily: "monospace", fontSize: "0.8em" }}
      />
    );
  }

  return null;
}
