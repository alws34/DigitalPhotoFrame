import { Outlet, NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { MonitorPlay, Aperture, Settings, LogOut, User } from 'lucide-react';

export default function DashboardLayout() {
  const { user, logout } = useAuth();

  const navItems = [
    { path: '/stream', icon: <MonitorPlay size={20} />, label: 'Live Stream' },
    { path: '/gallery', icon: <Aperture size={20} />, label: 'Gallery' },
    { path: '/settings', icon: <Settings size={20} />, label: 'Settings' },
  ];

  return (
    <div className="app-container">
      <aside className="sidebar fade-in">
        <div style={{ marginBottom: '2rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ padding: '0.5rem', borderRadius: '8px', background: 'var(--primary)', color: 'white' }}>
            <MonitorPlay size={24} />
          </div>
          <h2 style={{ margin: 0, fontSize: '1.25rem', letterSpacing: '-0.5px' }}>PhotoFrame</h2>
        </div>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flex: 1 }}>
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.75rem 1rem',
                borderRadius: '8px',
                color: isActive ? 'white' : 'var(--text-muted)',
                backgroundColor: isActive ? 'var(--primary)' : 'transparent',
                transition: 'all 0.2s ease'
              })}
            >
              {item.icon}
              <span style={{ fontWeight: 500 }}>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div style={{ 
          marginTop: 'auto', 
          paddingTop: '1rem', 
          borderTop: '1px solid var(--border-color)',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--text-muted)' }}>
            <div style={{ background: 'var(--surface-hover)', padding: '0.5rem', borderRadius: '50%' }}>
              <User size={16} />
            </div>
            <div style={{ fontSize: '0.9rem' }}>
              <div style={{ color: 'white', fontWeight: 500 }}>{user?.username}</div>
              <div style={{ fontSize: '0.8rem' }}>{user?.role}</div>
            </div>
          </div>
          
          <button 
            onClick={logout} 
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              gap: '0.5rem', 
              width: '100%',
              background: 'transparent',
              border: '1px solid var(--border-color)',
              color: 'var(--text-color)'
            }}
          >
            <LogOut size={16} /> Sign Out
          </button>
        </div>
      </aside>

      <main className="main-content fade-in" style={{ animationDelay: '0.1s' }}>
        <Outlet />
      </main>
    </div>
  );
}
