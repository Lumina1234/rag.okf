import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  Building,
  FolderOpen,
  Shield,
  FileCheck,
  Plus,
  Trash2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  History
} from 'lucide-react';
import OrgSidebar from '../components/OrgSidebar';
import { orgAPI, auditAPI, rolesAPI } from '../lib/orgApi';
import { useAuth } from '../context/AuthContext';

export default function OrgAdmin() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const orgId = localStorage.getItem('activeOrgId');
  const orgType = localStorage.getItem('activeOrgType') || 'business';
  const orgName = localStorage.getItem('activeOrgName') || 'Organization';
  const orgSlug = localStorage.getItem('activeOrgSlug') || 'org';

  const [activeTab, setActiveTab] = useState('members');
  const [members, setMembers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [roleTemplates, setRoleTemplates] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // New department form
  const [deptName, setDeptName] = useState('');
  const [deptType, setDeptType] = useState('');

  // New member form
  const [newUserId, setNewUserId] = useState('');
  const [newRoleId, setNewRoleId] = useState('');
  const [newDeptId, setNewDeptId] = useState('');

  // New workspace form
  const [wsName, setWsName] = useState('');
  const [wsType, setWsType] = useState(orgType === 'education' ? 'student' : 'business');

  const loadData = async () => {
    if (!orgId) {
      navigate('/org-selection');
      return;
    }
    setLoading(true);
    try {
      const [memRes, deptRes, wsRes, roleRes, auditRes] = await Promise.all([
        orgAPI.listMembers(orgId).catch(() => ({ data: [] })),
        orgAPI.listDepartments(orgId).catch(() => ({ data: [] })),
        orgAPI.listWorkspaces(orgId).catch(() => ({ data: [] })),
        rolesAPI.listTemplates().catch(() => ({ data: [] })),
        auditAPI.getLogs(orgId, 50).catch(() => ({ data: [] })),
      ]);
      setMembers(memRes.data);
      setDepartments(deptRes.data);
      setWorkspaces(wsRes.data);
      setRoleTemplates(roleRes.data.filter(r => r.portal_type === orgType));
      setAuditLogs(auditRes.data);
    } catch (e) {
      setError('Failed to load organization data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [orgId]);

  const handleCreateDepartment = async (e) => {
    e.preventDefault();
    if (!deptName.trim()) return;
    try {
      await orgAPI.createDepartment(orgId, { name: deptName, dept_type: deptType || undefined });
      setSuccess(`Department '${deptName}' created successfully.`);
      setDeptName('');
      setDeptType('');
      loadData();
    } catch (e) {
      setError('Failed to create department: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!newUserId || !newRoleId) return;
    try {
      await orgAPI.addMember(orgId, {
        user_id: parseInt(newUserId),
        role_id: parseInt(newRoleId),
        department_id: newDeptId ? parseInt(newDeptId) : undefined,
      });
      setSuccess(`Member added successfully.`);
      setNewUserId('');
      loadData();
    } catch (e) {
      setError('Failed to add member: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleRemoveMember = async (userId) => {
    if (!window.confirm('Are you sure you want to remove this member?')) return;
    try {
      await orgAPI.removeMember(orgId, userId);
      setSuccess('Member removed.');
      loadData();
    } catch (e) {
      setError('Failed to remove member.');
    }
  };

  const handleCreateWorkspace = async (e) => {
    e.preventDefault();
    if (!wsName.trim()) return;
    try {
      await orgAPI.createWorkspace(orgId, { name: wsName, workspace_type: wsType });
      setSuccess(`Workspace '${wsName}' created.`);
      setWsName('');
      loadData();
    } catch (e) {
      setError('Failed to create workspace.');
    }
  };

  return (
    <div className="app-shell">
      <OrgSidebar portalType={orgType} orgName={orgName} orgSlug={orgSlug} />

      <main className="main-content" style={{ padding: '32px' }}>
        <div style={{ marginBottom: '24px' }}>
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0 }}>Organization Administration</h1>
          <p className="text-muted" style={{ margin: '4px 0 0 0', fontSize: '14px' }}>
            Governance controls, department hierarchy, user roles and security audit logs.
          </p>
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

        {/* Tabs */}
        <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '24px' }}>
          {[
            { id: 'members', label: 'Members', icon: Users },
            { id: 'departments', label: 'Departments', icon: Building },
            { id: 'workspaces', label: 'Workspaces', icon: FolderOpen },
            { id: 'roles', label: 'Role Profiles', icon: Shield },
            { id: 'audit', label: 'Audit Trail', icon: History },
          ].map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id); setError(null); setSuccess(null); }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 16px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === tab.id ? '2px solid var(--primary-color)' : '2px solid transparent',
                  color: activeTab === tab.id ? 'var(--primary-color)' : 'var(--text-muted)',
                  fontWeight: activeTab === tab.id ? 600 : 400,
                  fontSize: '14px',
                  cursor: 'pointer',
                }}
              >
                <Icon size={16} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab 1: Members */}
        {activeTab === 'members' && (
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Organization Members ({members.length})</h2>
              {members.length === 0 ? (
                <p className="text-muted" style={{ fontSize: '14px' }}>No members yet.</p>
              ) : (
                <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '8px' }}>User ID</th>
                      <th style={{ padding: '8px' }}>Role ID</th>
                      <th style={{ padding: '8px' }}>Department</th>
                      <th style={{ padding: '8px' }}>Status</th>
                      <th style={{ padding: '8px' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {members.map((m) => (
                      <tr key={m.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        <td style={{ padding: '10px 8px' }}>User #{m.user_id}</td>
                        <td style={{ padding: '10px 8px' }}>Role #{m.org_role_id || 'None'}</td>
                        <td style={{ padding: '10px 8px' }}>{m.department_id ? `Dept #${m.department_id}` : 'General'}</td>
                        <td style={{ padding: '10px 8px' }}>
                          <span className="badge" style={{ background: m.is_active ? 'rgba(74, 222, 128, 0.1)' : 'rgba(239, 68, 68, 0.1)', color: m.is_active ? '#4ade80' : '#f87171' }}>
                            {m.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td style={{ padding: '10px 8px' }}>
                          {m.is_active && (
                            <button
                              onClick={() => handleRemoveMember(m.user_id)}
                              className="btn btn-ghost btn-sm"
                              style={{ color: '#f87171' }}
                            >
                              <Trash2 size={13} />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Add Member Form */}
            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)', height: 'fit-content' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Add Organization Member</h2>
              <form onSubmit={handleAddMember}>
                <div style={{ marginBottom: '16px' }}>
                  <label className="input-label" style={{ fontSize: '12px', marginBottom: '6px', display: 'block' }}>User ID</label>
                  <input
                    type="number"
                    value={newUserId}
                    onChange={(e) => setNewUserId(e.target.value)}
                    placeholder="e.g. 2"
                    className="input-field"
                    style={{ width: '100%' }}
                    required
                  />
                </div>
                <div style={{ marginBottom: '16px' }}>
                  <label className="input-label" style={{ fontSize: '12px', marginBottom: '6px', display: 'block' }}>Role Profile</label>
                  <select
                    value={newRoleId}
                    onChange={(e) => setNewRoleId(e.target.value)}
                    className="input-field"
                    style={{ width: '100%' }}
                    required
                  >
                    <option value="">Select Role</option>
                    {roleTemplates.map((r) => (
                      <option key={r.id} value={r.id}>{r.display_name} ({r.role_name})</option>
                    ))}
                  </select>
                </div>
                <div style={{ marginBottom: '20px' }}>
                  <label className="input-label" style={{ fontSize: '12px', marginBottom: '6px', display: 'block' }}>Department (Optional)</label>
                  <select
                    value={newDeptId}
                    onChange={(e) => setNewDeptId(e.target.value)}
                    className="input-field"
                    style={{ width: '100%' }}
                  >
                    <option value="">None / Institution Wide</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                </div>
                <button type="submit" className="btn btn-primary w-full">
                  <Plus size={14} /> Add Member
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Tab 2: Departments */}
        {activeTab === 'departments' && (
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Department Hierarchy ({departments.length})</h2>
              {departments.length === 0 ? (
                <p className="text-muted" style={{ fontSize: '14px' }}>No departments created yet.</p>
              ) : (
                <div style={{ display: 'grid', gap: '8px' }}>
                  {departments.map((d) => (
                    <div
                      key={d.id}
                      style={{
                        padding: '12px 16px',
                        background: 'rgba(255, 255, 255, 0.03)',
                        borderRadius: '8px',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '14px' }}>{d.name}</div>
                        <div className="text-muted" style={{ fontSize: '12px' }}>{d.dept_type || 'General Unit'}</div>
                      </div>
                      <span className="badge" style={{ background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8' }}>
                        ID #{d.id}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)', height: 'fit-content' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Create Department</h2>
              <form onSubmit={handleCreateDepartment}>
                <div style={{ marginBottom: '16px' }}>
                  <label className="input-label" style={{ fontSize: '12px', marginBottom: '6px', display: 'block' }}>Department Name</label>
                  <input
                    type="text"
                    value={deptName}
                    onChange={(e) => setDeptName(e.target.value)}
                    placeholder={orgType === 'education' ? 'e.g. AI & DS Department' : 'e.g. Finance'}
                    className="input-field"
                    style={{ width: '100%' }}
                    required
                  />
                </div>
                <div style={{ marginBottom: '20px' }}>
                  <label className="input-label" style={{ fontSize: '12px', marginBottom: '6px', display: 'block' }}>Unit Type</label>
                  <input
                    type="text"
                    value={deptType}
                    onChange={(e) => setDeptType(e.target.value)}
                    placeholder="e.g. Academic, Administrative, Branch"
                    className="input-field"
                    style={{ width: '100%' }}
                  />
                </div>
                <button type="submit" className="btn btn-primary w-full">
                  <Plus size={14} /> Create Department
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Tab 3: Workspaces */}
        {activeTab === 'workspaces' && (
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Organization Workspaces ({workspaces.length})</h2>
              {workspaces.length === 0 ? (
                <p className="text-muted" style={{ fontSize: '14px' }}>No workspaces bound to this organization.</p>
              ) : (
                <div style={{ display: 'grid', gap: '8px' }}>
                  {workspaces.map((ws) => (
                    <div
                      key={ws.id}
                      style={{
                        padding: '12px 16px',
                        background: 'rgba(255, 255, 255, 0.03)',
                        borderRadius: '8px',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '14px' }}>{ws.name}</div>
                        <div className="text-muted" style={{ fontSize: '12px' }}>Type: {ws.workspace_type}</div>
                      </div>
                      <span className="badge" style={{ background: 'rgba(168, 85, 247, 0.1)', color: '#c084fc' }}>
                        WS #{ws.id}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)', height: 'fit-content' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Create Org Workspace</h2>
              <form onSubmit={handleCreateWorkspace}>
                <div style={{ marginBottom: '16px' }}>
                  <label className="input-label" style={{ fontSize: '12px', marginBottom: '6px', display: 'block' }}>Workspace Name</label>
                  <input
                    type="text"
                    value={wsName}
                    onChange={(e) => setWsName(e.target.value)}
                    placeholder="e.g. 5th Sem AI Notes"
                    className="input-field"
                    style={{ width: '100%' }}
                    required
                  />
                </div>
                <div style={{ marginBottom: '20px' }}>
                  <label className="input-label" style={{ fontSize: '12px', marginBottom: '6px', display: 'block' }}>Type</label>
                  <select
                    value={wsType}
                    onChange={(e) => setWsType(e.target.value)}
                    className="input-field"
                    style={{ width: '100%' }}
                  >
                    <option value="student">Student / Education</option>
                    <option value="business">Business / Corporate</option>
                  </select>
                </div>
                <button type="submit" className="btn btn-primary w-full">
                  <Plus size={14} /> Create Workspace
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Tab 4: Roles */}
        {activeTab === 'roles' && (
          <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>
              {orgType === 'education' ? 'Education Role Profiles' : 'Business Role Profiles'}
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
              {roleTemplates.map((r) => (
                <div
                  key={r.id}
                  style={{
                    padding: '16px',
                    background: 'rgba(255, 255, 255, 0.02)',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '15px', color: 'var(--primary-color)' }}>{r.display_name}</div>
                  <div className="text-muted" style={{ fontSize: '12px', marginBottom: '8px' }}>Identifier: {r.role_name}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {r.permissions?.map((p) => (
                      <span key={p} className="badge" style={{ fontSize: '11px', background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-muted)' }}>
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 5: Audit Trail */}
        {activeTab === 'audit' && (
          <div style={{ background: 'var(--bg-card)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Security Audit Trail ({auditLogs.length} events)</h2>
            {auditLogs.length === 0 ? (
              <p className="text-muted" style={{ fontSize: '14px' }}>No audit events logged yet.</p>
            ) : (
              <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '8px' }}>Timestamp</th>
                    <th style={{ padding: '8px' }}>Action</th>
                    <th style={{ padding: '8px' }}>Resource Type</th>
                    <th style={{ padding: '8px' }}>Resource ID</th>
                    <th style={{ padding: '8px' }}>User ID</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.map((log) => (
                    <tr key={log.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                      <td style={{ padding: '8px', color: 'var(--text-muted)', fontSize: '12px' }}>{log.created_at}</td>
                      <td style={{ padding: '8px', fontWeight: 600 }}>{log.action}</td>
                      <td style={{ padding: '8px' }}>{log.resource_type || '—'}</td>
                      <td style={{ padding: '8px' }}>{log.resource_id || '—'}</td>
                      <td style={{ padding: '8px' }}>{log.user_id ? `User #${log.user_id}` : 'System'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
