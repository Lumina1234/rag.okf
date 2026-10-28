import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Lock, User, Sparkles } from 'lucide-react';

const Login = () => {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const { login, register } = useAuth();
  const navigate = useNavigate();

  const formatAuthError = (err) => {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => item?.msg || item?.message || JSON.stringify(item))
        .join('; ');
    }
    if (detail && typeof detail === 'object') {
      return JSON.stringify(detail);
    }
    return err?.message || 'Authentication failed';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isRegister) {
        const payload = { username, password, full_name: fullName };
        if (email.trim()) payload.email = email.trim();
        await register(payload);
      } else {
        await login(username, password);
      }
      navigate('/');
    } catch (err) {
      console.error('Auth error:', err);
      setError(formatAuthError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-bg-orb orb1"></div>
      <div className="login-bg-orb orb2"></div>

      <div className="login-card fade-in">
        <div className="login-logo">
          <div className="login-logo-icon">⚡</div>
          <div className="login-logo-text">
            <h1>Enterprise AI RAG</h1>
            <p>100% Offline Local Intelligence</p>
          </div>
        </div>

        <div className="login-tabs">
          <button 
            className={`login-tab ${!isRegister ? 'active' : ''}`}
            onClick={() => { setIsRegister(false); setError(null); }}
          >
            Sign In
          </button>
          <button 
            className={`login-tab ${isRegister ? 'active' : ''}`}
            onClick={() => { setIsRegister(true); setError(null); }}
          >
            Register Account
          </button>
        </div>

        {error && (
          <div className="card mb-16" style={{ background: 'var(--danger-dim)', borderColor: 'var(--danger)', color: 'var(--danger)', fontSize: '13px', padding: '10px 14px' }}>
            ⚠️ {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="input-group">
            <label className="input-label">Username or Email</label>
            <input 
              type="text" 
              className="input" 
              placeholder="Enter username or Gmail email" 
              value={username}
              onChange={e => setUsername(e.target.value)}
              required 
            />
          </div>

          {isRegister && (
            <>
              <div className="input-group">
                <label className="input-label">Full Name</label>
                <input 
                  type="text" 
                  className="input" 
                  placeholder="John Doe" 
                  value={fullName}
                  onChange={e => setFullName(e.target.value)}
                />
              </div>

              <div className="input-group">
                <label className="input-label">Email (Gmail recommended)</label>
                <input 
                  type="email" 
                  className="input" 
                  placeholder="yourname@gmail.com" 
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                />
              </div>
            </>
          )}

          <div className="input-group">
            <label className="input-label">Password</label>
            <input 
              type="password" 
              className="input" 
              placeholder="••••••••" 
              value={password}
              onChange={e => setPassword(e.target.value)}
              required 
            />
          </div>

          <button type="submit" className="btn btn-primary w-full btn-lg" style={{ marginTop: '8px' }} disabled={loading}>
            {loading ? <div className="spinner"></div> : <Sparkles size={16} />}
            <span>{isRegister ? 'Create Account' : 'Sign In'}</span>
          </button>
        </form>

        <div style={{ marginTop: '24px', textAlign: 'center', fontSize: '11px', color: 'var(--text-muted)' }}>
          🔒 Encrypted SQLite • Local JWT RBAC • No Cloud Telemetry
        </div>
      </div>
    </div>
  );
};

export default Login;
