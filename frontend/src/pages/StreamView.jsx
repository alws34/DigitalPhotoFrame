import { useState, useEffect, useRef } from 'react';
import { Expand, Maximize, Play, Pause } from 'lucide-react';

export default function StreamView() {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const containerRef = useRef(null);

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
          <button onClick={() => setIsPlaying(!isPlaying)} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {isPlaying ? <Pause size={18} /> : <Play size={18} />}
            {isPlaying ? 'Pause Stream' : 'Resume'}
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
        {isPlaying ? (
          <img 
            src="/api/stream?width=1920&height=1080" 
            alt="Live Stream" 
            style={{ 
              maxWidth: '100%', 
              maxHeight: '100%', 
              objectFit: 'contain' 
            }}
          />
        ) : (
          <div style={{ color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
            <Pause size={48} opacity={0.5} />
            <p>Stream Paused</p>
          </div>
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
