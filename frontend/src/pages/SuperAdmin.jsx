import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield,
  Building,
  GraduationCap,
  Briefcase,
  Plus,
  CheckCircle,
  ExternalLink,
  ChevronLeft
} from 'lucide-react';
import { orgAPI } from '../lib/orgApi';
import { useAuth } from '../context/AuthContext';

export default function SuperAdmin() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Form
  const [name, setName] = useState('');
  const [orgType, setOrgType] = useState('education');

  const loadOrgs = () => {
    orgAPI.list()
      .then((res) => setOrgs(res.data))
      .catch((e) => setError('Failed to load organizations.'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadOrgs();
  }, []);

  const handleCreateOrg = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const res = await orgAPI.create({ name, org_type: orgType });
      setSuccess(`Organization '${res.data.name}' (${res.data.org_type}) created successfully!`);
      setName('');
      loadOrgs();
    } catch (e) {
      setError('Failed to create organization: ' + (e.response?.data?.detail || e.message));
    }
  };

  const enterOrg = (org) => {
    localStorage.setItem('activeOrgId', org.id);
    localStorage.setItem('activeOrgType', org.org_type);
    localStorage.setItem('activeOrgName', org.name);
    localStorage.setItem('activeOrgSlug', org.slug);
    if (org.org_type === 'education') {
      navigate('/org/education');
    } else {
      navigate('/org/business');
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-app)', color: 'var(--text-color)', padding: '40px' }}>
      <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
        <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div className="flex items-center gap-3">
              <Shield size={28} className="text-primary" />
              <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0 }}>Platform Super Admin</h1>
            </div>
            <p className="text-muted" style={{ margin: '4px 0 0 0', fontSize: '14px' }}>
              Create and manage educational universities, colleges, and business tenants.
            </p>
          </div>
          <button
            onClick={() => navigate('/')}
            className="btn btn-ghost"
            style={{ fontSize: '13px' }}
          >
            <ChevronLeft size={16} /> Return to App
          </button>
        </div>

        {error && (
          <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px', color: '#fca5a5', fontSize: '13px' }}>
            {error}
          </div>
        )}
        {success && (
          <div style={{ background: 'rgba(74, 222, 128, 0.1)', border: '1px solid #4ade80', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px', color: '#86efac', fontSize: '13px' }}>
            {success}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
          {/* Create Org Form */}
          <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)', height: 'fit-content' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>Provision New Organization</h2>
            <form onSubmit={handleCreateOrg}>
              <div style={{ marginBottom: '16px' }}>
                <label className="input-label" style={{ fontSize: '13px', marginBottom: '6px', display: 'block' }}>Organization Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. VTU University or Acme Corp"
                  className="input-field"
                  style={{ width: '100%' }}
                  required
                />
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label className="input-label" style={{ fontSize: '13px', marginBottom: '6px', display: 'block' }}>Organization Portal Type</label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div
                    onClick={() => setOrgType('education')}
                    style={{
                      padding: '16px',
                      borderRadius: '8px',
                      border: orgType === 'education' ? '2px solid #38bdf8' : '1px solid var(--border-color)',
                      background: orgType === 'education' ? 'rgba(56, 189, 248, 0.05)' : 'transparent',
                      cursor: 'pointer',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '28px', marginBottom: '4px' }}>🎓</div>
                    <div style={{ fontWeight: 600, fontSize: '14px' }}>Education</div>
                    <div className="text-muted" style={{ fontSize: '11px' }}>Colleges & Universities</div>
                  </div>

                  <div
                    onClick={() => setOrgType('business')}
                    style={{
                      padding: '16px',
                      borderRadius: '8px',
                      border: orgType === 'business' ? '2px solid #4ade80' : '1px solid var(--border-color)',
                      background: orgType === 'business' ? 'rgba(74, 222, 128, 0.05)' : 'transparent',
                      cursor: 'pointer',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '28px', marginBottom: '4px' }}>🏢</div>
                    <div style={{ fontWeight: 600, fontSize: '14px' }}>Business</div>
                    <div className="text-muted" style={{ fontSize: '11px' }}>Enterprises & Teams</div>
                  </div>
                </div>
              </div>

              <button type="submit" className="btn btn-primary w-full">
                <Plus size={16} /> Create Organization Tenant
              </button>
            </form>
          </div>

          {/* List of Organizations */}
          <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>Existing Organizations ({orgs.length})</h2>
            {orgs.length === 0 ? (
              <p className="text-muted" style={{ fontSize: '14px' }}>No organizations registered yet.</p>
            ) : (
              <div style={{ display: 'grid', gap: '10px' }}>
                {orgs.map((org) => (
                  <div
                    key={org.id}
                    style={{
                      padding: '14px 16px',
                      background: 'rgba(255, 255, 255, 0.03)',
                      borderRadius: '8px',
                      border: '1px solid var(--border-color)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div className="flex items-center gap-3">
                      <span style={{ fontSize: '22px' }}>{org.org_type === 'education' ? '🎓' : '🏢'}</span>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '14px' }}>{org.name}</div>
                        <div className="text-muted" style={{ fontSize: '12px' }}>@{org.slug} • {org.org_type}</div>
                      </div>
                    </div>
                    <button
                      onClick={() => enterOrg(org)}
                      className="btn btn-ghost btn-sm"
                      style={{ fontSize: '12px', gap: '4px' }}
                    >
                      Enter Portal <ExternalLink size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
