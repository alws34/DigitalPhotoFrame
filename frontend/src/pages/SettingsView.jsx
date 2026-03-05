import { useState, useEffect } from 'react';
import axios from 'axios';
import { Save, Loader2, MonitorSmartphone, Key } from 'lucide-react';

export default function SettingsView() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const res = await axios.get('/api/settings/');
      setSettings(res.data);
    } catch (err) {
      console.error('Failed to fetch settings', err);
      setMessage('Failed to load settings: ' + (err.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (path, value) => {
    setSettings(prev => {
      const newSettings = { ...prev };
      
      // Handle nested paths like "ui.show_weather"
      const keys = path.split('.');
      let current = newSettings;
      
      for (let i = 0; i < keys.length - 1; i++) {
        if (!current[keys[i]]) current[keys[i]] = {};
        current = current[keys[i]];
      }
      
      current[keys[keys.length - 1]] = value;
      return newSettings;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage('');
    
    try {
      await axios.post('/api/settings/', settings);
      setMessage('Settings saved successfully!');
      setTimeout(() => setMessage(''), 3000);
    } catch (err) {
      console.error('Failed to save settings', err);
      setMessage('Failed to save settings: ' + (err.response?.data?.error || err.message));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem', color: 'var(--text-muted)' }}>
        <Loader2 size={32} className="spin" />
      </div>
    );
  }

  if (!settings) return <div style={{ padding: '2rem' }}>{message || 'Failed to load settings.'}</div>;

  return (
    <div style={{ padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>
      <header style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '2rem', fontWeight: 600 }}>Settings</h1>
          <p style={{ margin: '0.5rem 0 0', color: 'var(--text-muted)' }}>Configure your photo frame experience</p>
        </div>
        
        <button 
          onClick={handleSave} 
          className="primary"
          disabled={saving}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          {saving ? <Loader2 size={18} className="spin" /> : <Save size={18} />}
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </header>

      {message && (
        <div className="fade-in" style={{ 
          padding: '1rem', 
          marginBottom: '2rem', 
          borderRadius: '8px',
          backgroundColor: message.includes('Failed') ? 'rgba(255, 77, 79, 0.1)' : 'rgba(100, 108, 255, 0.1)',
          color: message.includes('Failed') ? 'var(--danger)' : 'var(--primary)',
          border: `1px solid ${message.includes('Failed') ? 'var(--danger)' : 'var(--primary)'}`
        }}>
          {message}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
        
        {/* System Settings Section */}
        <section className="glass-panel fade-in" style={{ padding: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
            <MonitorSmartphone size={24} color="var(--primary)" />
            <h2 style={{ margin: 0, fontSize: '1.25rem' }}>System</h2>
          </div>
          
          <div style={{ display: 'grid', gap: '1.5rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label><strong style={{ display: 'block' }}>Service Name</strong></label>
              <input 
                type="text" 
                value={settings.system?.service_name || 'PhotoFrame_App'}
                onChange={(e) => handleChange('system.service_name', e.target.value)}
                style={{ width: '100%' }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label><strong style={{ display: 'block' }}>Image Directory</strong></label>
              <input 
                type="text" 
                value={settings.system?.image_dir || 'Images'}
                onChange={(e) => handleChange('system.image_dir', e.target.value)}
                style={{ width: '100%' }}
              />
            </div>
          </div>
        </section>

        {/* Display Settings Section */}
        <section className="glass-panel fade-in" style={{ padding: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
            <MonitorSmartphone size={24} color="var(--primary)" />
            <h2 style={{ margin: 0, fontSize: '1.25rem' }}>Display & UI</h2>
          </div>
          
          <div style={{ display: 'grid', gap: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
              <div>
                <strong style={{ display: 'block' }}>Contrast Text (Negative Colors)</strong>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Improve text visibility on any background</span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input 
                  type="checkbox" 
                  checked={settings.ui?.contrast_text || false}
                  onChange={(e) => handleChange('ui.contrast_text', e.target.checked)}
                  style={{ width: '24px', height: '24px', cursor: 'pointer' }}
                />
              </label>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
              <div>
                <strong style={{ display: 'block' }}>Show Weather</strong>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Display current weather conditions</span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input 
                  type="checkbox" 
                  checked={settings.ui?.show_weather || false}
                  onChange={(e) => handleChange('ui.show_weather', e.target.checked)}
                  style={{ width: '24px', height: '24px', cursor: 'pointer' }}
                />
              </label>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
              <div>
                <strong style={{ display: 'block' }}>Clock Format</strong>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Use 24-hour time format</span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input 
                  type="checkbox" 
                  checked={settings.ui?.is_24h || false}
                  onChange={(e) => handleChange('ui.is_24h', e.target.checked)}
                  style={{ width: '24px', height: '24px', cursor: 'pointer' }}
                />
              </label>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
              <div>
                <strong style={{ display: 'block' }}>Show Caption</strong>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Display image captions if available</span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input 
                  type="checkbox" 
                  checked={settings.ui?.show_caption || false}
                  onChange={(e) => handleChange('ui.show_caption', e.target.checked)}
                  style={{ width: '24px', height: '24px', cursor: 'pointer' }}
                />
              </label>
            </div>
          </div>
        </section>

        {/* Playback Section */}
        <section className="glass-panel fade-in" style={{ padding: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
            <MonitorSmartphone size={24} color="var(--primary)" />
            <h2 style={{ margin: 0, fontSize: '1.25rem' }}>Playback</h2>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label><strong style={{ display: 'block' }}>Slide Duration (seconds)</strong></label>
              <input 
                type="number" 
                min="1" 
                max="3600"
                value={settings.playback?.delay_between_images || 30}
                onChange={(e) => handleChange('playback.delay_between_images', parseInt(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label><strong style={{ display: 'block' }}>Transition Duration (seconds)</strong></label>
              <input 
                type="number" 
                min="1" 
                max="60"
                value={settings.playback?.animation_duration || 10}
                onChange={(e) => handleChange('playback.animation_duration', parseInt(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label><strong style={{ display: 'block' }}>Animation FPS</strong></label>
              <input 
                type="number" 
                min="1" 
                max="60"
                value={settings.playback?.animation_fps || 30}
                onChange={(e) => handleChange('playback.animation_fps', parseInt(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>
          </div>
        </section>

        {/* Effects Section */}
        <section className="glass-panel fade-in" style={{ padding: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
            <MonitorSmartphone size={24} color="var(--primary)" />
            <h2 style={{ margin: 0, fontSize: '1.25rem' }}>Visual Effects</h2>
          </div>
          <div style={{ display: 'grid', gap: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
              <div>
                <strong style={{ display: 'block' }}>Translucent Background</strong>
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Allow blur effects behind overlays</span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input 
                  type="checkbox" 
                  checked={settings.effects?.allow_translucent_background || false}
                  onChange={(e) => handleChange('effects.allow_translucent_background', e.target.checked)}
                  style={{ width: '24px', height: '24px', cursor: 'pointer' }}
                />
              </label>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label><strong style={{ display: 'block' }}>Background Opacity (0.0 - 1.0)</strong></label>
              <input 
                type="range" 
                min="0" 
                max="1" 
                step="0.05"
                value={settings.effects?.background_opacity || 0.4}
                onChange={(e) => handleChange('effects.background_opacity', parseFloat(e.target.value))}
                style={{ width: '100%' }}
              />
              <span style={{ textAlign: 'right', fontSize: '0.8rem' }}>{settings.effects?.background_opacity || 0.4}</span>
            </div>
          </div>
        </section>

        {/* API Keys Section */}
        <section className="glass-panel fade-in" style={{ padding: '2rem', animationDelay: '0.1s' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
            <Key size={24} color="var(--primary)" />
            <h2 style={{ margin: 0, fontSize: '1.25rem' }}>API Keys</h2>
          </div>
          
          <div style={{ display: 'grid', gap: '1.5rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label><strong style={{ display: 'block' }}>AccuWeather API Key</strong></label>
              <input 
                type="password" 
                placeholder="Enter API Key"
                value={settings.weather_api_key || ''}
                onChange={(e) => handleChange('weather_api_key', e.target.value)}
                style={{ width: '100%' }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label><strong style={{ display: 'block' }}>AccuWeather Location Key</strong></label>
              <input 
                type="text" 
                placeholder="e.g. 215854"
                value={settings.location_key || ''}
                onChange={(e) => handleChange('location_key', e.target.value)}
                style={{ width: '100%' }}
              />
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
