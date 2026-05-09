import React, { useState } from "react";
import SettingField from "./SettingField";

export default function SettingsSection({ data, onChange, depth = 0 }) {
  const [collapsed, setCollapsed] = useState({});

  const toggle = (key) =>
    setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {Object.entries(data).map(([key, value]) => {
        if (value !== null && typeof value === "object" && !Array.isArray(value)) {
          const isCollapsed = collapsed[key] ?? false;
          const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
          return (
            <div
              key={key}
              style={{
                border: "1px solid var(--glass-border)",
                borderRadius: 10,
                marginTop: 6,
                overflow: "hidden",
                paddingLeft: depth * 8,
              }}
            >
              <button
                onClick={() => toggle(key)}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 14px",
                  background: "rgba(255,255,255,0.04)",
                  border: "none",
                  borderRadius: 0,
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <span style={{ fontWeight: 500 }}>{label}</span>
                <span>{isCollapsed ? "▶" : "▼"}</span>
              </button>
              {!isCollapsed && (
                <div style={{ padding: "8px 14px" }}>
                  <SettingsSection
                    data={value}
                    onChange={(subKey, subVal) =>
                      onChange(key, { ...value, [subKey]: subVal })
                    }
                    depth={depth + 1}
                  />
                </div>
              )}
            </div>
          );
        }

        return (
          <SettingField
            key={key}
            fieldKey={key}
            value={value}
            onChange={onChange}
            depth={depth}
          />
        );
      })}
    </div>
  );
}
