import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import { UserPlus, Image as ImageIcon, Eye, EyeOff, Loader2 } from 'lucide-react';

export default function Signup() {
  const [email, setEmail]             = useState('');
  const [username, setUsername]       = useState('');
  const [password, setPassword]       = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError]             = useState('');
  const [success, setSuccess]         = useState('');
  const [loading, setLoading]         = useState(false);
  const redirectTimerRef              = useRef(null);

  const { signup }  = useAuth();
  const navigate    = useNavigate();

  // Clean up any pending redirect timer on unmount.
  useEffect(() => () => clearTimeout(redirectTimerRef.current), []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      setError('');
      setSuccess('');
      setLoading(true);

      await signup({ email, username, password });

      setSuccess('Account created successfully! Redirecting to login…');
      redirectTimerRef.current = setTimeout(() => navigate('/login'), 2000);

    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create account. Please check your details.');
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
      background: 'linear-gradient(135deg, #121212 0%, #1e1e1e 100%)',
      padding: '2rem'
    }}>
      <div className="glass-panel fade-in" style={{ padding: '2.5rem', width: '100%', maxWidth: '450px' }}>
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
          <h1 style={{ margin: 0, fontSize: '1.5rem' }}>Create Account</h1>
          <p style={{ color: 'var(--text-muted)', margin: '0.5rem 0 0' }}>Sign up to manage your photo frame</p>
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

        {success && (
          <div style={{
            background: 'rgba(100, 108, 255, 0.2)',
            color: 'var(--primary)',
            border: '1px solid var(--primary)',
            padding: '0.75rem',
            borderRadius: '8px',
            marginBottom: '1.5rem',
            fontSize: '0.9rem',
            textAlign: 'center'
          }}>
            {success}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <label htmlFor="signup-email" style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Email Address
            </label>
            <input
              id="signup-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{ width: '100%' }}
              required
              autoFocus
            />
          </div>

          <div>
            <label htmlFor="signup-username" style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Username
            </label>
            <input
              id="signup-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={{ width: '100%' }}
              required
              minLength={3}
              pattern="[a-zA-Z0-9_]+"
              title="Only letters, numbers, and underscores allowed"
            />
          </div>

          <div>
            <label htmlFor="signup-password" style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Password
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="signup-password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ width: '100%', paddingRight: '2.5rem' }}
                required
                minLength={8}
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
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Must be at least 8 characters
            </div>
          </div>

          <button
            type="submit"
            className="primary"
            disabled={loading || !!success}
            style={{ marginTop: '1rem', padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}
          >
            {loading ? <Loader2 size={18} className="spin" /> : <UserPlus size={18} />}
            {loading ? 'Creating…' : 'Sign Up'}
          </button>
        </form>

        <div style={{ marginTop: '2rem', textAlign: 'center', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
          Already have an account? <Link to="/login" style={{ color: 'var(--primary)', fontWeight: 500, textDecoration: 'none' }}>Sign in instead</Link>
        </div>
      </div>

      <style>{`
        .spin { animation: signupSpin 1s linear infinite; }
        @keyframes signupSpin { 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
