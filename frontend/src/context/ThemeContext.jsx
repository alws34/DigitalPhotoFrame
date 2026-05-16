import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const ACCENT_TOKENS = {
  indigo:  { '--accent': '#6366f1', '--accent-hover': '#818cf8', '--accent-glow': 'rgba(99,102,241,0.3)' },
  sky:     { '--accent': '#0ea5e9', '--accent-hover': '#38bdf8', '--accent-glow': 'rgba(14,165,233,0.3)' },
  emerald: { '--accent': '#059669', '--accent-hover': '#10b981', '--accent-glow': 'rgba(5,150,105,0.3)' },
  rose:    { '--accent': '#e11d48', '--accent-hover': '#f43f5e', '--accent-glow': 'rgba(225,29,72,0.3)' },
};

const MOTION_TOKENS = {
  subtle:    { '--transition': '0.15s ease-out', '--transition-slow': '0.2s ease-out' },
  cinematic: { '--transition': '0.3s cubic-bezier(0.34,1.56,0.64,1)', '--transition-slow': '0.4s ease' },
};

const DEFAULTS = { accent: 'indigo', motionIntensity: 'subtle', sidebarCollapsed: false };

const ThemeContext = createContext(DEFAULTS);

function applyTokens(accent, motion) {
  const root = document.documentElement;
  const accentMap = ACCENT_TOKENS[accent] ?? ACCENT_TOKENS.indigo;
  const motionMap = MOTION_TOKENS[motion] ?? MOTION_TOKENS.subtle;
  Object.entries({ ...accentMap, ...motionMap }).forEach(([k, v]) => root.style.setProperty(k, v));
}

export function ThemeProvider({ children }) {
  const [accent, setAccent] = useState(DEFAULTS.accent);
  const [motionIntensity, setMotionIntensity] = useState(DEFAULTS.motionIntensity);
  const [sidebarCollapsed, setSidebarCollapsedState] = useState(DEFAULTS.sidebarCollapsed);

  useEffect(() => {
    axios.get('/api/settings', { withCredentials: true })
      .then(res => {
        const ui = res.data?.admin_ui ?? {};
        const a = ui.accent_color ?? DEFAULTS.accent;
        const m = ui.motion_intensity ?? DEFAULTS.motionIntensity;
        const s = ui.sidebar_collapsed ?? DEFAULTS.sidebarCollapsed;
        setAccent(a);
        setMotionIntensity(m);
        setSidebarCollapsedState(s);
        applyTokens(a, m);
      })
      .catch(() => applyTokens(DEFAULTS.accent, DEFAULTS.motionIntensity));
  }, []);

  const saveAdminUiSetting = useCallback(async (key, value) => {
    try {
      const res = await axios.get('/api/settings', { withCredentials: true });
      const current = res.data ?? {};
      const next = { ...current, admin_ui: { ...(current.admin_ui ?? {}), [key]: value } };
      await axios.post('/api/settings', next, { withCredentials: true });
    } catch (e) {
      console.error('Failed to save admin_ui setting', e);
    }
  }, []);

  const setSidebarCollapsed = useCallback((val) => {
    setSidebarCollapsedState(val);
    saveAdminUiSetting('sidebar_collapsed', val);
  }, [saveAdminUiSetting]);

  const handleAccentChange = useCallback((val) => {
    setAccent(val);
    applyTokens(val, motionIntensity);
    saveAdminUiSetting('accent_color', val);
  }, [motionIntensity, saveAdminUiSetting]);

  const handleMotionChange = useCallback((val) => {
    setMotionIntensity(val);
    applyTokens(accent, val);
    saveAdminUiSetting('motion_intensity', val);
  }, [accent, saveAdminUiSetting]);

  return (
    <ThemeContext.Provider value={{
      accent, setAccent: handleAccentChange,
      motionIntensity, setMotionIntensity: handleMotionChange,
      sidebarCollapsed, setSidebarCollapsed,
      saveAdminUiSetting,
    }}>
      {children}
    </ThemeContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
  return useContext(ThemeContext);
}
