import React, { useCallback, useEffect, useRef, useState } from "react";
import SettingsSection from "../components/settings/SettingsSection";

const HIDDEN_KEYS = new Set(["about"]);

function setNestedValue(obj, path, value) {
  const [head, ...rest] = path.split(".");
  if (rest.length === 0) return { ...obj, [head]: value };
  return { ...obj, [head]: setNestedValue(obj[head] ?? {}, rest.join("."), value) };
}

function collectChangedPaths(original, updated, prefix = "") {
  const paths = new Set();
  for (const key of Object.keys(updated)) {
    const path = prefix ? `${prefix}.${key}` : key;
    const orig = original?.[key];
    const upd = updated[key];
    if (upd !== null && typeof upd === "object" && !Array.isArray(upd)) {
      const sub = collectChangedPaths(orig, upd, path);
      sub.forEach((p) => paths.add(p));
    } else if (orig !== upd) {
      paths.add(path);
    }
  }
  return paths;
}

function gatherRestartPaths(schema, prefix = "") {
  const paths = new Set();
  for (const [key, val] of Object.entries(schema)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (val && typeof val === "object") {
      if ("type" in val) {
        if (val.restart_required) paths.add(path);
      } else {
        const sub = gatherRestartPaths(val, path);
        sub.forEach((p) => paths.add(p));
      }
    }
  }
  return paths;
}

export default function SettingsView() {
  const [settings, setSettings] = useState(null);
  const [schema, setSchema] = useState({});
  const [activeTab, setActiveTab] = useState(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [showRestartModal, setShowRestartModal] = useState(false);
  const originalRef = useRef(null);
  const pendingRef = useRef(null);

  const [albums, setAlbums] = useState([]);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch("/api/settings", { credentials: "include" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setSettings(data);
      originalRef.current = data;
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  }, []);

  useEffect(() => { fetchSettings(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetch("/api/albums", { credentials: "include" })
      .then((r) => r.json())
      .then(setAlbums)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (settings && !activeTab) {
      setActiveTab(Object.keys(settings).find((k) => !HIDDEN_KEYS.has(k)));
    }
  }, [settings, activeTab]);

  useEffect(() => {
    fetch("/api/settings/schema")
      .then((r) => r.json())
      .then(setSchema)
      .catch(() => {});
  }, []);

  useEffect(() => {
    const es = new EventSource("/api/settings/events", { withCredentials: true });
    es.onmessage = (e) => {
      if (e.data === "settings_updated" && !pendingRef.current) fetchSettings();
    };
    return () => es.close();
  }, [fetchSettings]);

  const handleChange = useCallback((path, value) => {
    setSettings((prev) => {
      const next = setNestedValue(prev, path, value);
      pendingRef.current = next;
      return next;
    });
    setStatus("Unsaved changes");
  }, []);

  const handleSave = async () => {
    const snapshot = pendingRef.current;
    if (!snapshot) return;
    setSaving(true);
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(snapshot),
      });
      if (!res.ok) throw new Error(await res.text());

      const changed = collectChangedPaths(originalRef.current, snapshot);
      const restartPaths = gatherRestartPaths(schema);
      const needsRestart = [...changed].some((p) => restartPaths.has(p));

      originalRef.current = snapshot;
      if (pendingRef.current === snapshot) pendingRef.current = null;
      setStatus("Saved");
      setTimeout(() => setStatus(""), 2000);
      if (needsRestart) setShowRestartModal(true);
    } catch (e) {
      setStatus(`Save failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRestart = async () => {
    setShowRestartModal(false);
    try {
      await fetch("/api/maintenance/restart", { method: "POST", credentials: "include" });
      setStatus("Restarting…");
    } catch (e) {
      setStatus(`Restart failed: ${e.message}`);
    }
  };

  if (!settings) {
    return <div style={{ padding: 40, color: "var(--text-secondary)" }}>Loading settings…</div>;
  }

  const tabs = Object.keys(settings).filter((k) => !HIDDEN_KEYS.has(k));

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 24, gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: "1.4em", fontWeight: 600 }}>Settings</h1>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {status && (
            <span style={{
              color: status.startsWith("Error") || status.startsWith("Save failed")
                ? "var(--danger)" : "var(--accent)",
              fontSize: "0.85em"
            }}>
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
              padding: "6px 16px", borderRadius: 20,
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
        <div className="glass" style={{ flex: 1, overflowY: "auto", padding: 20 }}>
          {typeof settings[activeTab] === "object" && !Array.isArray(settings[activeTab]) && (
            <SettingsSection
              data={settings[activeTab]}
              pathPrefix={activeTab}
              schema={schema[activeTab] ?? {}}
              onChange={handleChange}
              extras={{ albums }}
            />
          )}
        </div>
      )}

      {showRestartModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
        }}>
          <div className="glass" style={{ padding: 32, maxWidth: 420, borderRadius: 16, textAlign: "center" }}>
            <h2 style={{ marginBottom: 12 }}>Restart Required</h2>
            <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>
              Some changes require a restart to take effect.
            </p>
            <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
              <button className="primary" onClick={handleRestart}>Restart Now</button>
              <button onClick={() => setShowRestartModal(false)}>Later</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
