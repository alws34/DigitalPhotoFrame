import React, { useEffect, useRef, useState, useCallback } from "react";
import SettingsSection from "../components/settings/SettingsSection";

const HIDDEN_KEYS = new Set(["about"]);

export default function SettingsView() {
  const [settings, setSettings] = useState(null);
  const [activeTab, setActiveTab] = useState(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const pendingRef = useRef(null);
  const sseRef = useRef(null);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch("/api/settings", { credentials: "include" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSettings(data);
      if (!activeTab) setActiveTab(Object.keys(data).find((k) => !HIDDEN_KEYS.has(k)));
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }, [activeTab]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchSettings(); }, []);

  useEffect(() => {
    const es = new EventSource("/api/settings/events", { withCredentials: true });
    sseRef.current = es;
    es.onmessage = (e) => {
      if (e.data === "settings_updated") fetchSettings();
    };
    return () => es.close();
  }, [fetchSettings]);

  const handleChange = useCallback((topKey, sectionKey, value) => {
    setSettings((prev) => {
      const next = {
        ...prev,
        [topKey]: { ...prev[topKey], [sectionKey]: value },
      };
      pendingRef.current = next;
      return next;
    });
    setStatus("Unsaved changes");
  }, []);

  const handleSave = async () => {
    if (!pendingRef.current) return;
    setSaving(true);
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pendingRef.current),
      });
      if (!res.ok) throw new Error(await res.text());
      pendingRef.current = null;
      setStatus("Saved");
      setTimeout(() => setStatus(""), 2000);
    } catch (e) {
      setStatus(`Save failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (!settings) {
    return (
      <div style={{ padding: 40, color: "var(--text-secondary)" }}>
        Loading settings…
      </div>
    );
  }

  const tabs = Object.keys(settings).filter((k) => !HIDDEN_KEYS.has(k));

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 24, gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "1.4em", fontWeight: 600 }}>Settings</h1>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {status && (
            <span style={{ color: status.startsWith("Error") || status.startsWith("Save failed") ? "var(--danger)" : "var(--accent)", fontSize: "0.85em" }}>
              {status}
            </span>
          )}
          <button className="primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {tabs.map((key) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: "6px 16px",
              borderRadius: 20,
              border: activeTab === key ? "1px solid var(--accent)" : "1px solid var(--glass-border)",
              background: activeTab === key ? "rgba(90,150,255,0.2)" : "var(--glass-bg)",
              color: activeTab === key ? "var(--accent-hover)" : "var(--text-secondary)",
              fontWeight: activeTab === key ? 600 : 400,
              textTransform: "capitalize",
            }}
          >
            {key.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {activeTab && settings[activeTab] && (
        <div
          className="glass"
          style={{ flex: 1, overflowY: "auto", padding: 20 }}
        >
          {typeof settings[activeTab] === "object" && !Array.isArray(settings[activeTab]) ? (
            <SettingsSection
              data={settings[activeTab]}
              onChange={(sectionKey, value) => handleChange(activeTab, sectionKey, value)}
            />
          ) : (
            <p style={{ color: "var(--text-secondary)" }}>
              {JSON.stringify(settings[activeTab])}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
