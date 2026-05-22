import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useNavigate, Link } from 'react-router-dom';
import { Key, Eye, EyeOff, ArrowLeft, Loader2 } from 'lucide-react';

export default function ResetPassword() {
  const [email, setEmail]             = useState('');
  const [password, setPassword]       = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState('');
  const [success, setSuccess]         = useState('');
  const redirectTimerRef              = useRef(null);
  const navigate                      = useNavigate();

  // Clean up any pending redirect timer on unmount.
  useEffect(() => () => clearTimeout(redirectTimerRef.current), []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const res = await axios.post('/api/auth/reset-password', { email, password });
      setSuccess(res.data.message || 'Password reset successfully!');
      redirectTimerRef.current = setTimeout(() => navigate('/login'), 3000);
    } catch (err) {
      if (err.response?.status === 401) {
        setError('Password reset requires being logged in. Please sign in first, then change your password from Settings.');
      } else {
        setError(err.response?.data?.error || 'Failed to reset password.');
      }
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
        <div style={{ marginBottom: '1.5rem' }}>
          <Link to="/login" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', textDecoration: 'none', fontSize: '0.9rem' }}>
            <ArrowLeft size={16} /> Back to Login
          </Link>
        </div>

        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{
            display: 'inline-flex',
            padding: '1rem',
            borderRadius: '50%',
            background: 'rgba(100, 108, 255, 0.1)',
            marginBottom: '1rem'
          }}>
            <Key size={48} color="var(--primary)" />
          </div>
          <h1 style={{ margin: 0, fontSize: '1.5rem' }}>Reset Password</h1>
          <p style={{ color: 'var(--text-muted)', margin: '0.5rem 0 0' }}>You must be logged in to reset a password</p>
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
            <label htmlFor="reset-email" style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Email Address
            </label>
            <input
              id="reset-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{ width: '100%' }}
              required
              placeholder="your@email.com"
            />
          </div>

          <div>
            <label htmlFor="reset-password" style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              New Password
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="reset-password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ width: '100%', paddingRight: '2.5rem' }}
                required
                minLength={8}
                placeholder="••••••••"
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
            disabled={loading || !!success}
            style={{ marginTop: '1rem', padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}
          >
            {loading ? <Loader2 size={18} className="spin" /> : <Key size={18} />}
            {loading ? 'Resetting…' : 'Reset Password'}
          </button>
        </form>
      </div>

      <style>{`
        .spin { animation: resetSpin 1s linear infinite; }
        @keyframes resetSpin { 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
