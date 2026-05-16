import { useEffect } from 'react';

export default function FrameView() {
  useEffect(() => {
    let timer;
    const hide = () => { document.body.style.cursor = 'none'; };
    const show = () => {
      document.body.style.cursor = 'default';
      clearTimeout(timer);
      timer = setTimeout(hide, 3000);
    };
    document.addEventListener('mousemove', show);
    hide();
    return () => {
      document.removeEventListener('mousemove', show);
      clearTimeout(timer);
      document.body.style.cursor = 'default';
    };
  }, []);

  return (
    <div style={{
      width: '100vw',
      height: '100vh',
      background: '#000',
      overflow: 'hidden',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    }}>
      <img
        src="/api/stream"
        alt=""
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
        }}
      />
    </div>
  );
}
