import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  GraduationCap, 
  BookOpen, 
  Users, 
  ShieldCheck, 
  FileText, 
  FolderPlus,
  Search,
  ExternalLink,
  ChevronRight,
  School
} from 'lucide-react';
import OrgSidebar from '../components/OrgSidebar';
import { orgAPI } from '../lib/orgApi';
import { useAuth } from '../context/AuthContext';

export default function EduPortal() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const orgId = localStorage.getItem('activeOrgId');
  const orgName = localStorage.getItem('activeOrgName') || 'Education Portal';
  const orgSlug = localStorage.getItem('activeOrgSlug') || 'edu';

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
      <OrgSidebar portalType="education" orgName={orgName} orgSlug={orgSlug} />

      <main className="main-content" style={{ padding: '32px' }}>
        {/* Header */}
        <div style={{ marginBottom: '32px' }}>
          <div className="flex items-center gap-3 mb-2">
            <span style={{ fontSize: '32px' }}>🎓</span>
            <div>
              <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0 }}>{orgName}</h1>
              <p className="text-muted" style={{ margin: 0, fontSize: '14px' }}>
                Education Portal — Universities, Colleges, Departments, Faculty & Students
              </p>
            </div>
          </div>
        </div>

        {/* Quick KPI Cards */}
        <div className="grid grid-cols-4 gap-4 mb-32" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '32px' }}>
          <div className="metric-card" style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <div className="text-muted" style={{ fontSize: '13px', marginBottom: '8px' }}>Departments / Branches</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--primary-color)' }}>{departments.length}</div>
            <div className="text-muted" style={{ fontSize: '12px', marginTop: '4px' }}>Academic Units</div>
          </div>

          <div className="metric-card" style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <div className="text-muted" style={{ fontSize: '13px', marginBottom: '8px' }}>Course Workspaces</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: '#38bdf8' }}>{workspaces.length}</div>
            <div className="text-muted" style={{ fontSize: '12px', marginTop: '4px' }}>Isolated syllabi & repos</div>
          </div>

          <div className="metric-card" style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <div className="text-muted" style={{ fontSize: '13px', marginBottom: '8px' }}>Enrolled Members</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: '#4ade80' }}>{members.length}</div>
            <div className="text-muted" style={{ fontSize: '12px', marginTop: '4px' }}>Students, Faculty & Staff</div>
          </div>

          <div className="metric-card" style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <div className="text-muted" style={{ fontSize: '13px', marginBottom: '8px' }}>Security & ACL</div>
            <div style={{ fontSize: '28px', fontWeight: 700, color: '#a78bfa' }}>Enforced</div>
            <div className="text-muted" style={{ fontSize: '12px', marginTop: '4px' }}>Deny-by-default isolation</div>
          </div>
        </div>

        {/* Roles & Portal Sections */}
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
          {/* Left Column: Workspaces and Academic Units */}
          <div>
            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)', marginBottom: '24px' }}>
              <div className="flex items-center justify-between mb-16">
                <h2 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>Academic Departments</h2>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => navigate('/org/admin')}
                  style={{ fontSize: '12px' }}
                >
                  Manage Departments →
                </button>
              </div>

              {departments.length === 0 ? (
                <p className="text-muted" style={{ fontSize: '14px' }}>No departments created yet. Visit Org Management to add departments like CSE, AI&DS, ECE.</p>
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
                        <span style={{ fontSize: '18px' }}>🏛️</span>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '14px' }}>{d.name}</div>
                          <div className="text-muted" style={{ fontSize: '12px' }}>{d.dept_type || 'Academic Department'}</div>
                        </div>
                      </div>
                      <span className="badge" style={{ fontSize: '11px', background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8' }}>Active</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Educational Workspaces */}
            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <div className="flex items-center justify-between mb-16">
                <h2 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>Course Workspaces</h2>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => navigate('/documents')}
                  style={{ fontSize: '12px' }}
                >
                  <FolderPlus size={14} /> Open Course Materials
                </button>
              </div>

              {workspaces.length === 0 ? (
                <p className="text-muted" style={{ fontSize: '14px' }}>No workspaces linked yet.</p>
              ) : (
                <div style={{ display: 'grid', gap: '10px' }}>
                  {workspaces.map((ws) => (
                    <div
                      key={ws.id}
                      style={{
                        padding: '12px 16px',
                        background: 'rgba(255, 255, 255, 0.03)',
                        borderRadius: '8px',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        cursor: 'pointer',
                      }}
                      onClick={() => navigate('/chat')}
                    >
                      <div className="flex items-center gap-3">
                        <BookOpen size={18} className="text-primary" />
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '14px' }}>{ws.name}</div>
                          <div className="text-muted" style={{ fontSize: '12px' }}>Type: {ws.workspace_type}</div>
                        </div>
                      </div>
                      <ChevronRight size={16} className="text-muted" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Roles & Governance Info */}
          <div>
            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Education Role Templates</h2>
              <div style={{ display: 'grid', gap: '12px', fontSize: '13px' }}>
                <div style={{ borderLeft: '3px solid #38bdf8', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>🏛️ Institution Admin</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Full governance & campus configuration</div>
                </div>
                <div style={{ borderLeft: '3px solid #818cf8', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>🎓 Principal</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Academic oversight & department reporting</div>
                </div>
                <div style={{ borderLeft: '3px solid #a78bfa', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>📋 Head of Department (HOD)</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Department documents & course approvals</div>
                </div>
                <div style={{ borderLeft: '3px solid #34d399', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>👨‍🏫 Faculty</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Upload lectures, assignments & syllabus</div>
                </div>
                <div style={{ borderLeft: '3px solid #fbbf24', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>🧑‍🎓 Student</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Query approved notes (exam papers protected)</div>
                </div>
                <div style={{ borderLeft: '3px solid #f87171', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>🔒 Examination Officer</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Manage highly confidential exam materials</div>
                </div>
                <div style={{ borderLeft: '3px solid #e879f9', paddingLeft: '12px' }}>
                  <div style={{ fontWeight: 600 }}>📚 Librarian</div>
                  <div className="text-muted" style={{ fontSize: '12px' }}>Reference repository & public archives</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
