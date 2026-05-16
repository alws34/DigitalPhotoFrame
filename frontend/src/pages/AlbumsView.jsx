import { useState, useEffect, useRef, useCallback } from 'react';
import { Loader2, RefreshCw, Trash2, Plus, BookImage, FolderOpen, Check, X, ChevronDown } from 'lucide-react';

// ---------------------------------------------------------------------------
// Mock data — used as fallback when API is not yet implemented
// ---------------------------------------------------------------------------
const MOCK_SOURCES = [
  {
    id: 'local_1',
    source_type: 'local',
    name: 'Local Folder',
    enabled: true,
    is_authenticated: true,
    last_synced_at: null,
  },
];

const MOCK_ALBUMS = [
  {
    id: 'local_1:local_images',
    source_id: 'local_1',
    name: 'local_images',
    media_count: 42,
    last_synced_at: null,
    sync_in_progress: false,
  },
];

const MOCK_ACTIVE = { album_id: 'all', name: 'Local Images' };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const SOURCE_ICONS = {
  google_photos: '📷',
  immich: '🖥️',
  local: '📁',
};

function sourceIcon(type) {
  return SOURCE_ICONS[type] ?? '📷';
}

function formatDate(ts) {
  if (!ts) return 'Never';
  return new Date(typeof ts === 'number' ? ts * 1000 : ts).toLocaleString();
}

// ---------------------------------------------------------------------------
// Google Photos setup guide (inline collapsible)
// ---------------------------------------------------------------------------
function GooglePhotosSetupGuide() {
  const [open, setOpen] = useState(false);
  const steps = [
    { n: 1, title: 'Open Google Cloud Console', body: <>Go to <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>console.cloud.google.com</a> and create a new project (or select an existing one).</> },
    { n: 2, title: 'Enable the Photos Library API', body: <>Navigate to <strong>APIs &amp; Services → Library</strong>, search for <strong>"Photos Library API"</strong>, and click <strong>Enable</strong>.</> },
    { n: 3, title: 'Configure the OAuth consent screen', body: <>Go to <strong>APIs &amp; Services → OAuth consent screen</strong>. Choose <strong>External</strong>, fill in the app name (e.g. "Photo Frame"), add your email as a test user, and save.</> },
    { n: 4, title: 'Create an OAuth 2.0 Client ID', body: <>Go to <strong>APIs &amp; Services → Credentials → Create Credentials → OAuth client ID</strong>. Choose <strong>Web application</strong>. You will paste the Redirect URI shown in the next step.</> },
    { n: 5, title: 'Paste the Client ID and Secret here', body: <>Copy the <strong>Client ID</strong> and <strong>Client Secret</strong> from the credentials page into the fields below, then click Connect to get the Redirect URI.</> },
    { n: 6, title: 'Add the Redirect URI to Google', body: <>After clicking Connect, copy the Redirect URI shown and add it under <strong>Authorized redirect URIs</strong> in your OAuth client, then click <strong>Open Google Authorization</strong>.</> },
  ];
  return (
    <div style={{ marginBottom: '1.25rem' }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.4rem',
          fontSize: '0.83rem', color: 'var(--accent)', background: 'none',
          border: 'none', padding: 0, cursor: 'pointer', marginBottom: open ? '0.75rem' : 0,
        }}
      >
        {open ? '▼' : '▶'} Setup guide — how to get your Client ID &amp; Secret
      </button>
      {open && (
        <ol style={{ margin: 0, paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          {steps.map(({ n, title, body }) => (
            <li key={n} style={{ fontSize: '0.83rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              <strong style={{ color: 'var(--text-primary)' }}>{title}</strong><br />{body}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared modal shell
// ---------------------------------------------------------------------------
const overlayStyle = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
};
const modalStyle = {
  background: 'rgba(20,25,40,0.98)', border: '1px solid var(--glass-border)',
  borderRadius: '16px', padding: '2rem', width: '460px', maxWidth: '90vw',
  boxShadow: 'var(--glass-shadow)',
};

// ---------------------------------------------------------------------------
// Google Photos modal
// ---------------------------------------------------------------------------
function GooglePhotosModal({ onClose, onAdd }) {
  const [name, setName] = useState('Google Photos');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  // step: 'form' | 'authorize'
  const [step, setStep] = useState('form');
  const [authUrl, setAuthUrl] = useState('');
  const [redirectUri, setRedirectUri] = useState('');

  const handleConnect = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr('');
    try {
      // 1. Create source
      const createRes = await fetch('/api/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ type: 'google_photos', name }),
      });
      if (!createRes.ok) throw new Error(await createRes.text());
      const created = await createRes.json();

      // 2. Start OAuth — compute redirect URI from current origin
      const redir = `${window.location.origin}/api/sources/${created.id}/auth/callback`;
      const authRes = await fetch(`/api/sources/${created.id}/auth/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, redirect_uri: redir }),
      });
      if (!authRes.ok) throw new Error(await authRes.text());
      const { redirect_url } = await authRes.json();

      onAdd(created);
      setRedirectUri(redir);
      setAuthUrl(redirect_url);
      setStep('authorize');
    } catch (e) {
      setErr(e.message || 'Failed to start Google Photos auth');
    } finally {
      setBusy(false);
    }
  };

  if (step === 'authorize') {
    return (
      <div style={overlayStyle} onClick={onClose}>
        <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
          <h2 style={{ margin: '0 0 1rem' }}>Authorize Google Photos</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1rem' }}>
            Add this URI to your Google Cloud Console → OAuth 2.0 Client → Authorized redirect URIs:
          </p>
          <div style={{
            background: 'rgba(255,255,255,0.06)', border: '1px solid var(--glass-border)',
            borderRadius: '8px', padding: '0.75rem 1rem', fontFamily: 'monospace',
            fontSize: '0.82rem', wordBreak: 'break-all', marginBottom: '1.5rem',
            display: 'flex', gap: '0.5rem', alignItems: 'center',
          }}>
            <span style={{ flex: 1 }}>{redirectUri}</span>
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(redirectUri)}
              style={{ padding: '0.2rem 0.6rem', fontSize: '0.78rem', flexShrink: 0 }}
            >Copy</button>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
            <button type="button" onClick={onClose}>Close</button>
            <button
              className="primary"
              onClick={() => { window.open(authUrl, '_blank'); onClose(); }}
            >
              Open Google Authorization →
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ margin: '0 0 0.5rem' }}>Connect Google Photos</h2>
        <GooglePhotosSetupGuide />

        <form onSubmit={handleConnect} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {[
            { label: 'Name', value: name, set: setName, type: 'text', placeholder: 'Google Photos' },
            { label: 'Client ID', value: clientId, set: setClientId, type: 'text', placeholder: '…apps.googleusercontent.com' },
            { label: 'Client Secret', value: clientSecret, set: setClientSecret, type: 'password', placeholder: 'GOCSPX-…' },
          ].map(({ label, value, set, type, placeholder }) => (
            <div key={label}>
              <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>{label}</label>
              <input type={type} value={value} onChange={(e) => set(e.target.value)} placeholder={placeholder} required={label !== 'Name'} />
            </div>
          ))}
          {err && <p style={{ color: 'var(--danger)', fontSize: '0.85rem', margin: 0 }}>{err}</p>}
          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className="primary" disabled={busy}>
              {busy ? <Loader2 size={16} className="spin" /> : null}
              {busy ? ' Connecting…' : 'Connect'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Immich modal
// ---------------------------------------------------------------------------
function ImmichModal({ onClose, onAdd }) {
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [name, setName] = useState('My Immich');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr('');
    try {
      const res = await fetch('/api/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          type: 'immich',
          name,
          config: { base_url: baseUrl },
          credentials: { api_key: apiKey },
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const created = await res.json();
      onAdd(created);
      onClose();
    } catch (e) {
      setErr(e.message || 'Failed to add Immich source');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ margin: '0 0 1.5rem' }}>Connect Immich</h2>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Name
            </label>
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              Base URL
            </label>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://immich.example.com"
              required
            />
          </div>
          <div>
            <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.35rem' }}>
              API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="your-api-key"
              required
            />
          </div>
          {err && <p style={{ color: 'var(--danger)', fontSize: '0.85rem', margin: 0 }}>{err}</p>}
          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className="primary" disabled={busy}>
              {busy ? <Loader2 size={16} className="spin" /> : null}
              {busy ? ' Connecting…' : 'Connect'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Browse & Subscribe panel
// ---------------------------------------------------------------------------
function BrowsePanel({ source, subscribedAlbums, onSubscribe, onClose }) {
  const [remoteAlbums, setRemoteAlbums] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState('');
  const [subscribing, setSubscribing] = useState(null);

  const subscribedRemoteIds = new Set(subscribedAlbums.map((a) => a.id.split(':').slice(1).join(':')));

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setLoadErr('');
      try {
        const res = await fetch(`/api/sources/${source.id}/remote-albums`, { credentials: 'include' });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || `HTTP ${res.status}`);
        }
        const data = await res.json();
        if (!cancelled) setRemoteAlbums(data);
      } catch (e) {
        if (!cancelled) setLoadErr(e.message || 'Failed to load albums');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [source.id]);

  const handleSubscribe = async (album) => {
    setSubscribing(album.remote_id);
    try {
      const res = await fetch('/api/albums', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          source_id: source.id,
          remote_id: album.remote_id,
          name: album.name,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const created = await res.json();
      onSubscribe(created);
    } catch (e) {
      console.error('Subscribe failed', e);
      alert('Subscribe failed: ' + e.message);
    } finally {
      setSubscribing(null);
    }
  };

  const panelStyle = {
    marginTop: '1.5rem',
    padding: '1.5rem',
    background: 'var(--glass-bg)',
    border: '1px solid var(--glass-border)',
    borderRadius: '12px',
  };

  return (
    <div style={panelStyle} className="fade-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h3 style={{ margin: 0 }}>{sourceIcon(source.source_type)} Browse Albums — {source.name}</h3>
        <button onClick={onClose} style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}>
          <X size={14} /> Close
        </button>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
          <Loader2 size={24} className="spin" />
        </div>
      ) : loadErr ? (
        <p style={{ color: 'var(--danger)', textAlign: 'center', padding: '1.5rem' }}>{loadErr}</p>
      ) : remoteAlbums.length === 0 ? (
        <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '1.5rem' }}>
          No albums found on this source.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {remoteAlbums.map((album) => {
            const alreadySubscribed = subscribedRemoteIds.has(album.remote_id);
            return (
              <div
                key={album.remote_id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '0.75rem 1rem',
                  background: 'rgba(255,255,255,0.04)',
                  borderRadius: '8px',
                  border: '1px solid var(--glass-border)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 500 }}>{album.name}</div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    {album.media_count ?? '?'} items
                  </div>
                </div>
                {alreadySubscribed ? (
                  <span style={{ fontSize: '0.85rem', color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                    <Check size={14} /> Subscribed
                  </span>
                ) : (
                  <button
                    className="primary"
                    disabled={subscribing === album.remote_id}
                    onClick={() => handleSubscribe(album)}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.9rem' }}
                  >
                    {subscribing === album.remote_id ? <Loader2 size={14} className="spin" /> : <Plus size={14} />}
                    Subscribe
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Source card
// ---------------------------------------------------------------------------
function SourceCard({ source, albums, onSynced, onRemoved, onUnsubscribe, onSubscribed }) {
  const [syncing, setSyncing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [browsing, setBrowsing] = useState(false);

  const sourceAlbums = albums.filter((a) => a.source_id === source.id);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await fetch(`/api/sources/${source.id}/sync`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) throw new Error(await res.text());
      onSynced(source.id);
    } catch (e) {
      console.error('Sync failed', e);
      alert('Sync failed: ' + e.message);
    } finally {
      setSyncing(false);
    }
  };

  const handleRemove = async () => {
    if (!window.confirm(`Remove source "${source.name}" and all its subscribed albums?`)) return;
    setRemoving(true);
    try {
      const res = await fetch(`/api/sources/${source.id}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (!res.ok) throw new Error(await res.text());
      onRemoved(source.id);
    } catch (e) {
      console.error('Remove failed', e);
      alert('Remove failed: ' + e.message);
      setRemoving(false);
    }
  };

  const handleUnsubscribe = async (album) => {
    if (!window.confirm(`Unsubscribe from "${album.name}"? Local files will be removed.`)) return;
    try {
      const res = await fetch(`/api/albums/${encodeURIComponent(album.id)}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (!res.ok) throw new Error(await res.text());
      onUnsubscribe(album.id);
    } catch (e) {
      console.error('Unsubscribe failed', e);
      alert('Unsubscribe failed: ' + e.message);
    }
  };

  const cardStyle = {
    padding: '1.5rem',
    background: 'var(--glass-bg)',
    border: '1px solid var(--glass-border)',
    borderRadius: '12px',
    boxShadow: 'var(--glass-shadow)',
  };

  const badgeStyle = (ok) => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: '0.3rem',
    fontSize: '0.78rem',
    padding: '0.2rem 0.6rem',
    borderRadius: '999px',
    background: ok ? 'rgba(80,200,120,0.15)' : 'rgba(255,90,90,0.15)',
    border: `1px solid ${ok ? 'rgba(80,200,120,0.4)' : 'rgba(255,90,90,0.4)'}`,
    color: ok ? 'rgba(100,220,140,0.9)' : 'var(--danger)',
    fontWeight: 500,
  });

  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <div style={cardStyle} className="fade-in">
        {/* Header row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.5rem' }}>{sourceIcon(source.source_type)}</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: '1rem' }}>{source.name}</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                {source.source_type}
              </div>
            </div>
            <span style={badgeStyle(source.is_authenticated)}>
              {source.is_authenticated ? <Check size={12} /> : <X size={12} />}
              {source.is_authenticated ? 'Connected' : 'Not connected'}
            </span>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              onClick={() => setBrowsing((b) => !b)}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', fontSize: '0.875rem' }}
            >
              <BookImage size={15} />
              {browsing ? 'Hide Albums' : 'Browse Albums'}
            </button>
            <button
              onClick={handleSync}
              disabled={syncing}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', fontSize: '0.875rem' }}
            >
              {syncing ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
              Sync Now
            </button>
            <button
              className="danger"
              onClick={handleRemove}
              disabled={removing}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', fontSize: '0.875rem' }}
            >
              {removing ? <Loader2 size={15} className="spin" /> : <Trash2 size={15} />}
              Remove
            </button>
          </div>
        </div>

        {/* Subscribed albums */}
        {sourceAlbums.length > 0 && (
          <div style={{ marginTop: '1.25rem', borderTop: '1px solid var(--glass-border)', paddingTop: '1.25rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Subscribed Albums
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {sourceAlbums.map((album) => (
                <div
                  key={album.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.65rem 0.9rem',
                    background: 'rgba(255,255,255,0.04)',
                    borderRadius: '8px',
                    border: '1px solid var(--glass-border)',
                    flexWrap: 'wrap',
                    gap: '0.5rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                    {album.sync_in_progress && <Loader2 size={14} className="spin" style={{ color: 'var(--accent)' }} />}
                    <div>
                      <span style={{ fontWeight: 500 }}>{album.name}</span>
                      <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', marginLeft: '0.5rem' }}>
                        {album.media_count ?? 0} items
                      </span>
                    </div>
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      Synced: {formatDate(album.last_synced_at)}
                    </span>
                  </div>
                  <button
                    className="danger"
                    onClick={() => handleUnsubscribe(album)}
                    style={{ fontSize: '0.82rem', padding: '0.3rem 0.7rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                  >
                    <X size={13} /> Unsubscribe
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Browse panel */}
      {browsing && (
        <BrowsePanel
          source={source}
          subscribedAlbums={sourceAlbums}
          onSubscribe={(newAlbum) => {
            onSubscribed(newAlbum);
          }}
          onClose={() => setBrowsing(false)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
const POLL_INTERVAL_MS = 5000;

export default function AlbumsView() {
  const [sources, setSources] = useState([]);
  const [albums, setAlbums] = useState([]);
  const [activeAlbum, setActiveAlbum] = useState(MOCK_ACTIVE);
  const [loading, setLoading] = useState(true);
  const [showImmichModal, setShowImmichModal] = useState(false);
  const [showGoogleModal, setShowGoogleModal] = useState(false);
  const [settingActive, setSettingActive] = useState(false);
  const pollRef = useRef(null);

  // ── Fetch ──────────────────────────────────────────────────────────────
  const fetchSources = useCallback(async () => {
    try {
      const res = await fetch('/api/sources', { credentials: 'include' });
      if (!res.ok) throw new Error('Not OK');
      return await res.json();
    } catch {
      console.warn('GET /api/sources not available yet, using mock data');
      return MOCK_SOURCES;
    }
  }, []);

  const fetchAlbums = useCallback(async () => {
    try {
      const res = await fetch('/api/albums', { credentials: 'include' });
      if (!res.ok) throw new Error('Not OK');
      return await res.json();
    } catch {
      console.warn('GET /api/albums not available yet, using mock data');
      return MOCK_ALBUMS;
    }
  }, []);

  const fetchActive = useCallback(async () => {
    try {
      const res = await fetch('/api/albums/active', { credentials: 'include' });
      if (!res.ok) throw new Error('Not OK');
      return await res.json();
    } catch {
      console.warn('GET /api/albums/active not available yet, using mock data');
      return MOCK_ACTIVE;
    }
  }, []);

  const loadAll = useCallback(async () => {
    const [s, a, active] = await Promise.all([fetchSources(), fetchAlbums(), fetchActive()]);
    setSources(s);
    setAlbums(a);
    setActiveAlbum(active);
    setLoading(false);
  }, [fetchSources, fetchAlbums, fetchActive]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // ── Polling when sync in progress ─────────────────────────────────────
  useEffect(() => {
    const anySync = albums.some((a) => a.sync_in_progress);
    if (anySync) {
      pollRef.current = setInterval(async () => {
        const fresh = await fetchAlbums();
        setAlbums(fresh);
      }, POLL_INTERVAL_MS);
    } else {
      clearInterval(pollRef.current);
    }
    return () => clearInterval(pollRef.current);
  }, [albums, fetchAlbums]);

  // ── Active album selector ──────────────────────────────────────────────
  const handleActiveChange = async (albumId) => {
    setSettingActive(true);
    try {
      const res = await fetch('/api/albums/active', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ album_id: albumId }),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = await res.json();
      setActiveAlbum(updated);
    } catch (e) {
      console.warn('PUT /api/albums/active failed (API not implemented yet):', e.message);
      // Optimistic update when API unavailable
      const found = albums.find((a) => a.id === albumId);
      setActiveAlbum(albumId === 'all' ? { album_id: 'all', name: 'Local Images' } : { album_id: albumId, name: found?.name ?? albumId });
    } finally {
      setSettingActive(false);
    }
  };

  // ── Add Source handlers ────────────────────────────────────────────────

  const handleAddLocal = async () => {
    try {
      const res = await fetch('/api/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ type: 'local', name: 'Local Folder' }),
      });
      if (!res.ok) throw new Error(await res.text());
      const created = await res.json();
      setSources((prev) => [...prev, created]);
    } catch (e) {
      console.warn('POST /api/sources (local) not yet implemented:', e.message);
      alert('Local folder source API is not yet available.');
    }
  };

  // ── Mutation callbacks ────────────────────────────────────────────────
  const handleSourceSynced = (sourceId) => {
    // Mark albums from that source as syncing
    setAlbums((prev) =>
      prev.map((a) => (a.source_id === sourceId ? { ...a, sync_in_progress: true } : a))
    );
  };

  const handleSourceRemoved = (sourceId) => {
    setSources((prev) => prev.filter((s) => s.id !== sourceId));
    setAlbums((prev) => prev.filter((a) => a.source_id !== sourceId));
  };

  const handleUnsubscribe = (albumId) => {
    setAlbums((prev) => prev.filter((a) => a.id !== albumId));
  };

  const handleSubscribed = (newAlbum) => {
    setAlbums((prev) => {
      if (prev.find((a) => a.id === newAlbum.id)) return prev;
      return [...prev, newAlbum];
    });
  };

  const handleImmichAdded = (newSource) => {
    setSources((prev) => [...prev, newSource]);
  };

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div style={{ padding: '2rem', maxWidth: '960px', margin: '0 auto' }}>
      {/* Inline keyframe for spin animation */}
      <style>{`
        .spin { animation: albumsSpin 1s linear infinite; }
        @keyframes albumsSpin { 100% { transform: rotate(360deg); } }
      `}</style>

      <header style={{ marginBottom: '2rem' }}>
        <h1 style={{ margin: 0, fontSize: '2rem', fontWeight: 600 }}>Albums</h1>
        <p style={{ margin: '0.5rem 0 0', color: 'var(--text-secondary)' }}>
          Manage photo sources and subscribed albums
        </p>
      </header>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem', color: 'var(--text-secondary)' }}>
          <Loader2 size={32} className="spin" />
        </div>
      ) : (
        <>
          {/* ── 1. Active Album selector ─────────────────────────────── */}
          <section
            className="glass-panel fade-in"
            style={{ padding: '1.25rem 1.5rem', marginBottom: '2rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}
          >
            <div style={{ fontWeight: 600, fontSize: '0.95rem', minWidth: 'max-content' }}>
              Now Playing
            </div>
            <div style={{ position: 'relative', flex: 1, minWidth: '200px', maxWidth: '360px' }}>
              <select
                value={activeAlbum?.album_id ?? 'all'}
                onChange={(e) => handleActiveChange(e.target.value)}
                disabled={settingActive}
                style={{ paddingRight: '2rem', appearance: 'none' }}
              >
                <option value="all">Local Images</option>
                {albums.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              <ChevronDown
                size={16}
                style={{ position: 'absolute', right: '0.6rem', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'var(--text-secondary)' }}
              />
            </div>
            {settingActive && <Loader2 size={16} className="spin" style={{ color: 'var(--accent)' }} />}
          </section>

          {/* ── 2. Sources list ───────────────────────────────────────── */}
          <section style={{ marginBottom: '2rem' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Sources
            </h2>

            {sources.length === 0 ? (
              <div
                className="glass-panel fade-in"
                style={{ padding: '3rem 2rem', textAlign: 'center', color: 'var(--text-secondary)' }}
              >
                <FolderOpen size={40} style={{ marginBottom: '0.75rem', opacity: 0.4 }} />
                <p>No sources configured. Add one below.</p>
              </div>
            ) : (
              sources.map((source) => (
                <SourceCard
                  key={source.id}
                  source={source}
                  albums={albums}
                  onSynced={handleSourceSynced}
                  onRemoved={handleSourceRemoved}
                  onUnsubscribe={handleUnsubscribe}
                  onSubscribed={handleSubscribed}
                />
              ))
            )}
          </section>

          {/* ── 3. Add Source ─────────────────────────────────────────── */}
          <section className="glass-panel fade-in" style={{ padding: '1.5rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1.25rem' }}>Add Source</h2>
            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
              <button
                className="primary"
                onClick={() => setShowGoogleModal(true)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <Plus size={16} /> 📷 Google Photos
              </button>
              <button
                className="primary"
                onClick={() => setShowImmichModal(true)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <Plus size={16} /> 🖥️ Immich
              </button>
              <button
                onClick={handleAddLocal}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <Plus size={16} /> 📁 Local Folder
              </button>
            </div>
          </section>
        </>
      )}

      {showGoogleModal && (
        <GooglePhotosModal
          onClose={() => setShowGoogleModal(false)}
          onAdd={(src) => { setSources((prev) => [...prev, src]); }}
        />
      )}
      {showImmichModal && (
        <ImmichModal
          onClose={() => setShowImmichModal(false)}
          onAdd={handleImmichAdded}
        />
      )}
    </div>
  );
}
