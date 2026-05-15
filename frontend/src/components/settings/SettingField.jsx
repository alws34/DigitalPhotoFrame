import React, { useState } from "react";
import ClockKnob from "./ClockKnob";

export default function SettingField({ fieldKey, fieldPath, value, schema, onChange, depth = 0, extras = {} }) {
  const [showPassword, setShowPassword] = useState(false);
  const ftype = schema?.type ?? null;

  const rawLabel = (schema?.label ?? fieldKey)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  const label = schema?.restart_required ? `${rawLabel} ⚠` : rawLabel;

  const labelEl = (
    <span style={{
      color: "var(--text-secondary)", fontSize: "0.85em", minWidth: 180,
      display: "flex", alignItems: "center", gap: 4,
    }}>
      {label}
    </span>
  );

  const row = (input) => (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "6px 0", paddingLeft: depth * 16,
    }}>
      {labelEl}
      <div style={{ flex: 1 }}>{input}</div>
    </div>
  );

  if (ftype === "password") {
    return row(
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <input
          type={showPassword ? "text" : "password"}
          value={value ?? ""}
          onChange={(e) => onChange(fieldPath, e.target.value)}
          style={{ flex: 1 }}
        />
        <button onClick={() => setShowPassword((p) => !p)} style={{ padding: "2px 8px", fontSize: "0.8em" }}>
          {showPassword ? "Hide" : "Show"}
        </button>
      </div>
    );
  }

  if (ftype === "enum" || ftype === "color") {
    const choices = schema?.choices ?? [];
    return row(
      <select value={value ?? ""} onChange={(e) => onChange(fieldPath, e.target.value)}>
        {choices.map((c) => <option key={c} value={c}>{c}</option>)}
        {value != null && !choices.includes(String(value)) && (
          <option value={String(value)}>{String(value)}</option>
        )}
      </select>
    );
  }

  if (ftype === "numeric_string") {
    return row(
      <input
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(fieldPath, e.target.value)}
        style={{ maxWidth: 160 }}
      />
    );
  }

  if (schema?.ui === "clock") {
    return row(
      <ClockKnob value={value} onChange={(h) => onChange(fieldPath, h)} />
    );
  }

  if (schema?.ui === "album_select") {
    const albums = Array.isArray(extras?.albums) ? extras.albums : [];
    return row(
      <select value={value ?? "all"} onChange={(e) => onChange(fieldPath, e.target.value)}>
        <option value="all">Local Images</option>
        {albums.map((a) => (
          <option key={a.id} value={a.id}>{a.name}</option>
        ))}
      </select>
    );
  }

  if (typeof value === "boolean" || ftype === "bool") {
    return row(
      <label className="toggle">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(fieldPath, e.target.checked)}
        />
        <span className="toggle-track" />
      </label>
    );
  }

  if (typeof value === "number" || ftype === "int" || ftype === "float") {
    const isFloat = ftype === "float" || (!Number.isInteger(value) && ftype !== "int");
    const step = schema?.step ?? (isFloat ? 0.01 : 1);
    const min = schema?.min;
    const max = schema?.max;
    return row(
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {min !== undefined && max !== undefined && (
          <input
            type="range"
            min={min} max={max} step={step}
            value={value ?? 0}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") { onChange(fieldPath, min ?? 0); return; }
              const v = isFloat ? parseFloat(raw) : parseInt(raw, 10);
              if (!isNaN(v)) onChange(fieldPath, v);
            }}
            style={{ flex: 1 }}
          />
        )}
        <input
          type="number"
          value={value ?? 0}
          step={step}
          min={min} max={max}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") { onChange(fieldPath, min ?? 0); return; }
            const v = isFloat ? parseFloat(raw) : parseInt(raw, 10);
            if (!isNaN(v)) onChange(fieldPath, v);
          }}
          style={{ maxWidth: 100 }}
        />
      </div>
    );
  }

  if (typeof value === "string") {
    return row(
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(fieldPath, e.target.value)}
      />
    );
  }

  if (Array.isArray(value)) {
    const isSimple = value.every((v) => typeof v !== "object");
    if (!isSimple) return null;  // hide complex arrays (e.g. schedules) — managed elsewhere
    return row(
      <input
        type="text"
        value={value.join(", ")}
        onChange={(e) =>
          onChange(fieldPath, e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
            .map((s) => (isNaN(Number(s)) ? s : Number(s))))
        }
      />
    );
  }

  return null;
}
