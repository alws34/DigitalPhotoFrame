import { useState, useEffect, useRef } from 'react';
import { Expand, Maximize, Layers } from 'lucide-react';
import { withCsrf } from '../csrf';

const POLL_INTERVAL_MS = 200; // 5 fps — sufficient for photo frame monitoring

export default function StreamView() {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);
  const [snapshotUrl, setSnapshotUrl] = useState(null);
  const [error, setError] = useState(false);
  const containerRef = useRef(null);
  const intervalRef = useRef(null);

  const fetchSnapshot = async () => {
    try {
      const res = await fetch('/api/stream/snapshot');
      if (!res.ok) { setError(true); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setSnapshotUrl(prev => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
      setError(false);
    } catch {
      setError(true);
    }
  };

  useEffect(() => {
    intervalRef.current = setInterval(fetchSnapshot, POLL_INTERVAL_MS);
    return () => {
      clearInterval(intervalRef.current);
      setSnapshotUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
    };
  }, []);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  return (
    <div style={{ padding: '2rem', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <header style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '2rem', fontWeight: 600 }}>Live View</h1>
          <p style={{ margin: '0.5rem 0 0', color: 'var(--text-muted)' }}>Real-time stream from your digital photo frame</p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={async () => {
              const next = !showOverlay;
              setShowOverlay(next);
              try {
                const res = await fetch('/api/settings', { credentials: 'include' });
                const current = await res.json();
                await fetch('/api/settings', withCsrf({
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ ...current, stream: { ...(current.stream ?? {}), show_overlay: next } }),
                }));
              // eslint-disable-next-line no-empty
              } catch {}
            }}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', opacity: showOverlay ? 1 : 0.5 }}
            title={showOverlay ? 'Hide overlay' : 'Show overlay'}
          >
            <Layers size={18} />
            Overlay {showOverlay ? 'On' : 'Off'}
          </button>
        </div>
      </header>

      <div
        ref={containerRef}
        className="glass-panel fade-in"
        style={{
          flex: 1,
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: isFullscreen ? '#000' : 'var(--surface-color)',
          borderRadius: isFullscreen ? '0' : '16px',
          border: isFullscreen ? 'none' : '1px solid var(--border-color)',
          animationDelay: '0.2s'
        }}
      >
        {snapshotUrl ? (
          <img
            src={snapshotUrl}
            alt="Live Stream"
            style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
          />
        ) : error ? (
          <div style={{ color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
            <p>Stream unavailable — frame server may be starting up</p>
          </div>
        ) : (
          <div style={{ color: 'var(--text-muted)' }}>Connecting…</div>
        )}

        <button
          onClick={toggleFullscreen}
          className="glass-panel"
          style={{
            position: 'absolute',
            bottom: '1rem',
            right: '1rem',
            padding: '0.75rem',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: 'none',
            background: 'var(--glass-bg)',
            color: 'white',
            opacity: 0.7,
            transition: 'opacity 0.2s',
          }}
          onMouseEnter={(e) => e.currentTarget.style.opacity = 1}
          onMouseLeave={(e) => e.currentTarget.style.opacity = 0.7}
          title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
        >
          {isFullscreen ? <Expand size={20} /> : <Maximize size={20} />}
        </button>
      </div>
    </div>
  );
}
