import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Briefcase, 
  BarChart3, 
  Users, 
  FileText, 
  ShieldCheck, 
  Building2, 
  TrendingUp, 
  ChevronRight,
  FolderPlus
} from 'lucide-react';
import OrgSidebar from '../components/OrgSidebar';
import { orgAPI } from '../lib/orgApi';
import { useAuth } from '../context/AuthContext';

export default function BizPortal() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const orgId = localStorage.getItem('activeOrgId');
  const orgName = localStorage.getItem('activeOrgName') || 'Business Portal';
  const orgSlug = localStorage.getItem('activeOrgSlug') || 'biz';

  const [departments, setDepartments] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!orgId) {
      navigate('/org-selection');
      return;
    }

    Promise.all([
      orgAPI.listDepartments(orgId).catch(() => ({ data: [] })),
      orgAPI.listWorkspaces(orgId).catch(() => ({ data: [] })),
      orgAPI.listMembers(orgId).catch(() => ({ data: [] })),
    ])
      .then(([deptRes, wsRes, memRes]) => {
        setDepartments(deptRes.data);
        setWorkspaces(wsRes.data);
        setMembers(memRes.data);
      })
      .finally(() => setLoading(false));
  }, [orgId, navigate]);

  return (
    <div className="app-shell">
      <OrgSidebar portalType="business" orgName={orgName} orgSlug={orgSlug} />

      <main className="main-content" style={{ padding: '32px' }}>
        {/* Header */}
        <div style={{ marginBottom: '32px' }}>
          <div className="flex items-center gap-3 mb-2">
            <span style={{ fontSize: '32px' }}>🏢</span>
            <div>
              <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0 }}>{orgName}</h1>
              <p className="text-muted" style={{ margin: 0, fontSize: '14px' }}>
                Business Portal — Enterprise Knowledge Intelligence & Executive Analytics
              </p>
            </div>
          </div>
        </div>

        {/* Quick KPI Cards */}
        <div className="grid grid-cols-4 gap-4 mb-32" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '32px' }}>
          <div className="metric-card" style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <div className="text-muted" style={{ fontSize: '13px', marginBottom: '8px' }}>Business Units</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--primary-color)' }}>{departments.length}</div>
            <div className="text-muted" style={{ fontSize: '12px', marginTop: '4px' }}>HR, Finance, Marketing, Sales</div>
          </div>

          <div className="metric-card" style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <div className="text-muted" style={{ fontSize: '13px', marginBottom: '8px' }}>Project Workspaces</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: '#38bdf8' }}>{workspaces.length}</div>
            <div className="text-muted" style={{ fontSize: '12px', marginTop: '4px' }}>Isolated repositories</div>
          </div>

          <div className="metric-card" style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <div className="text-muted" style={{ fontSize: '13px', marginBottom: '8px' }}>Corporate Members</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: '#4ade80' }}>{members.length}</div>
            <div className="text-muted" style={{ fontSize: '12px', marginTop: '4px' }}>Active employees & executives</div>
          </div>

          <div className="metric-card" style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <div className="text-muted" style={{ fontSize: '13px', marginBottom: '8px' }}>Analytics Engine</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: '#34d399' }}>Deterministic</div>
            <div className="text-muted" style={{ fontSize: '12px', marginTop: '4px' }}>Pandas + OKF Governance</div>
          </div>
        </div>

        {/* Roles & Portal Sections */}
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
          {/* Left Column: Workspaces and Analytics */}
          <div>
            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)', marginBottom: '24px' }}>
              <div className="flex items-center justify-between mb-16">
                <h2 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>Corporate Departments</h2>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => navigate('/org/admin')}
                  style={{ fontSize: '12px' }}
                >
                  Manage Teams →
                </button>
              </div>

              {departments.length === 0 ? (
                <p className="text-muted" style={{ fontSize: '14px' }}>No departments created yet. Use Org Management to add teams like HR, Finance, Legal, Marketing.</p>
              ) : (
                <div style={{ display: 'grid', gap: '10px' }}>
                  {departments.map((d) => (
                    <div
                      key={d.id}
                      style={{
                        padding: '12px 16px',
                        background: 'rgba(255, 255, 255, 0.03)',
                        borderRadius: '8px',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div className="flex items-center gap-3">
                        <span style={{ fontSize: '18px' }}>💼</span>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '14px' }}>{d.name}</div>
                          <div className="text-muted" style={{ fontSize: '12px' }}>{d.dept_type || 'Corporate Unit'}</div>
                        </div>
                      </div>
                      <span className="badge" style={{ fontSize: '11px', background: 'rgba(74, 222, 128, 0.1)', color: '#4ade80' }}>Active</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Quick Action Navigation */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div
                style={{
                  background: 'var(--bg-card)',
                  padding: '20px',
                  borderRadius: '12px',
                  border: '1px solid var(--border-color)',
                  cursor: 'pointer',
                }}
                onClick={() => navigate('/analytics')}
              >
                <BarChart3 size={24} style={{ color: '#38bdf8', marginBottom: '8px' }} />
                <div style={{ fontWeight: 600, fontSize: '15px' }}>Business Analytics</div>
                <p className="text-muted" style={{ fontSize: '13px', margin: '4px 0 0 0' }}>
                  Financial, Profitability & Outlier Calculations
                </p>
              </div>

              <div
                style={{
                  background: 'var(--bg-card)',
                  padding: '20px',
                  borderRadius: '12px',
                  border: '1px solid var(--border-color)',
                  cursor: 'pointer',
                }}
                onClick={() => navigate('/chat')}
              >
                <FileText size={24} style={{ color: '#4ade80', marginBottom: '8px' }} />
                <div style={{ fontWeight: 600, fontSize: '15px' }}>Executive AI Chat</div>
                <p className="text-muted" style={{ fontSize: '13px', margin: '4px 0 0 0' }}>
                  RAG Document Retrieval with Deterministic Citations
                </p>
              </div>
            </div>
          </div>

          {/* Right Column: Roles & Governance Info */}
          <div>
            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Business Role Profiles</h2>
              <div style={{ display: 'grid', gap: '12px', fontSize: '13px' }}>
                <div style={{ borderLeft: '3px solid #38bdf8', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>🏛️ Company Admin</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Full company governance & system security</div>
                </div>
                <div style={{ borderLeft: '3px solid #818cf8', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>👔 CEO / Executive</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Cross-department visibility & audit access</div>
                </div>
                <div style={{ borderLeft: '3px solid #f472b6', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>👥 HR Manager</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Member provisioning & employee documents</div>
                </div>
                <div style={{ borderLeft: '3px solid #34d399', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>💰 Finance Manager</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Profitability reports & balance sheets</div>
                </div>
                <div style={{ borderLeft: '3px solid #fb923c', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>📢 Marketing Manager</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Campaign knowledge & public collateral</div>
                </div>
                <div style={{ borderLeft: '3px solid #a78bfa', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>📈 Sales Manager</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Sales pipelines & client documentation</div>
                </div>
                <div style={{ borderLeft: '3px solid #94a3b8', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>💼 Employee</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>General workspace search & knowledge query</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
