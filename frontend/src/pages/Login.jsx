import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import { Image as ImageIcon, Lock, Eye, EyeOff, Loader2 } from 'lucide-react';

export default function Login() {
  const [identity, setIdentity]       = useState('');
  const [password, setPassword]       = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError]             = useState('');
  const [loading, setLoading]         = useState(false);
  const { login }   = useAuth();
  const navigate    = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!identity.trim()) {
      setError('Please enter your email or username.');
      return;
    }
    if (!password) {
      setError('Please enter your password.');
      return;
    }
    setLoading(true);
    try {
      setError('');
      await login({ username: identity, password });
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.error || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
    }}>
      <div className="glass fade-in" style={{ padding: 40, width: 380, maxWidth: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{
            display: 'inline-flex',
            padding: '1rem',
            borderRadius: '50%',
            background: 'rgba(100, 108, 255, 0.1)',
            marginBottom: '1rem'
          }}>
            <ImageIcon size={48} color="var(--primary)" />
          </div>
          <h1 style={{ margin: 0, fontSize: '1.5rem' }}>Digital Photo Frame</h1>
          <p style={{ color: 'var(--text-muted)', margin: '0.5rem 0 0' }}>Sign in to manage your frame</p>
        </div>

        {error && (
          <div style={{
            background: 'var(--danger)',
            color: 'white',
            padding: '0.75rem',
            borderRadius: '8px',
            marginBottom: '1.5rem',
            fontSize: '0.9rem',
            textAlign: 'center'
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <label htmlFor="login-identity" style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Email or Username
            </label>
            <input
              id="login-identity"
              type="text"
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              style={{ width: '100%' }}
              autoFocus
            />
          </div>

          <div style={{ position: 'relative' }}>
            <label htmlFor="login-password" style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Password
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ width: '100%', paddingRight: '2.5rem' }}
              />
              <button
                type="button"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '0.5rem',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  padding: '4px',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  minWidth: 'auto',
                  minHeight: 'auto'
                }}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="primary"
            disabled={loading}
            style={{ marginTop: '1rem', padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}
          >
            {loading ? <Loader2 size={18} className="spin" /> : <Lock size={18} />}
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <div style={{ marginTop: '2rem', textAlign: 'center', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
          <div style={{ marginBottom: '1rem' }}>
            <Link to="/reset-password" style={{ color: 'var(--text-muted)', textDecoration: 'none' }}>Forgot password?</Link>
          </div>
          Don&#39;t have an account? <Link to="/signup" style={{ color: 'var(--primary)', fontWeight: 500, textDecoration: 'none' }}>Sign up</Link>
        </div>
      </div>

      <style>{`
        .spin { animation: loginSpin 1s linear infinite; }
        @keyframes loginSpin { 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
