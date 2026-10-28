import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, 
  MessageSquare, 
  FolderOpen, 
  BarChart3, 
  Settings, 
  LogOut, 
  Plus, 
  Briefcase, 
  GraduationCap,
  ChevronDown,
  Activity,
  Shield,
  FileText
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { workspaceAPI } from '../lib/api';

const Sidebar = ({ systemStatus }) => {
  const { user, workspaces, activeWorkspace, selectWorkspace, refreshWorkspaces, logout } = useAuth();
  const [showWsMenu, setShowWsMenu] = useState(false);
  const [showCreateWsModal, setShowCreateWsModal] = useState(false);
  const [newWsName, setNewWsName] = useState('');
  const [newWsType, setNewWsType] = useState('business');
  const [newWsDesc, setNewWsDesc] = useState('');
  const navigate = useNavigate();

  const handleCreateWorkspace = async (e) => {
    e.preventDefault();
    if (!newWsName.trim()) return;
    try {
      const res = await workspaceAPI.create({
        name: newWsName,
        workspace_type: newWsType,
        description: newWsDesc
      });
      await refreshWorkspaces();
      selectWorkspace(res.data);
      setShowCreateWsModal(false);
      setNewWsName('');
      setNewWsDesc('');
    } catch (err) {
      console.error('Failed to create workspace:', err);
    }
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-icon">⚡</div>
        <div className="brand-text">
          <div className="brand-title">Enterprise RAG</div>
          <div className="brand-sub">100% Offline AI</div>
        </div>
      </div>

      {/* Workspace Selector */}
      <div className="ws-selector" onClick={() => setShowWsMenu(!showWsMenu)}>
        <div className={`ws-badge ${activeWorkspace?.workspace_type || 'business'}`}>
          {activeWorkspace?.workspace_type === 'student' ? <GraduationCap size={16} /> : <Briefcase size={16} />}
        </div>
        <div className="ws-info">
          <div className="ws-name">{activeWorkspace?.name || 'No Workspace'}</div>
          <div className="ws-type">{activeWorkspace?.workspace_type || 'Workspace'}</div>
        </div>
        <ChevronDown size={14} className="text-muted" />
      </div>

      {/* Workspace Dropdown */}
      {showWsMenu && (
        <div className="modal-overlay" onClick={() => setShowWsMenu(false)}>
          <div className="modal fade-in" onClick={e => e.stopPropagation()}>
            <div className="modal-title">Select Workspace</div>
            <div style={{ maxHeight: '200px', overflowY: 'auto', marginBottom: '16px' }}>
              {workspaces.map(ws => (
                <div 
                  key={ws.id} 
                  className={`doc-item ${ws.id === activeWorkspace?.id ? 'active' : ''}`}
                  style={{ cursor: 'pointer', marginBottom: '8px' }}
                  onClick={() => {
                    selectWorkspace(ws);
                    setShowWsMenu(false);
                  }}
                >
                  <div className={`ws-badge ${ws.workspace_type}`}>
                    {ws.workspace_type === 'student' ? <GraduationCap size={16} /> : <Briefcase size={16} />}
                  </div>
                  <div className="ws-info">
                    <div className="ws-name">{ws.name}</div>
                    <div className="ws-type">{ws.workspace_type} • {ws.document_count} docs</div>
                  </div>
                </div>
              ))}
            </div>
            <button className="btn btn-primary w-full" onClick={() => { setShowWsMenu(false); setShowCreateWsModal(true); }}>
              <Plus size={14} /> Create New Workspace
            </button>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="sidebar-nav">
        <div className="nav-section-label">Main</div>
        <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-icon"><LayoutDashboard size={16} /></span>
          <span>Dashboard</span>
        </NavLink>
        <NavLink to="/chat" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-icon"><MessageSquare size={16} /></span>
          <span>AI Workspace Chat</span>
        </NavLink>
        <NavLink to="/documents" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-icon"><FolderOpen size={16} /></span>
          <span>Knowledge Base</span>
        </NavLink>
        <NavLink to="/summarize" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-icon"><FileText size={16} /></span>
          <span>Summarize</span>
        </NavLink>
        
        {activeWorkspace?.workspace_type === 'business' && (
          <NavLink to="/analytics" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><BarChart3 size={16} /></span>
            <span>Business Analytics</span>
          </NavLink>
        )}

        {user?.role === 'admin' && (
          <NavLink to="/admin-history" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><Shield size={16} /></span>
            <span>Admin History</span>
          </NavLink>
        )}

        <div className="nav-section-label" style={{ marginTop: '16px' }}>System</div>
        <NavLink to="/settings" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-icon"><Settings size={16} /></span>
          <span>Settings</span>
        </NavLink>
      </nav>

      {/* Status Pill & User Footer */}
      <div className="sidebar-footer">
        <div className="status-pill mb-12">
          <span className={`status-dot ${systemStatus?.ollama_online ? 'online' : 'offline'}`}></span>
          <span>Ollama: {systemStatus?.ollama_online ? 'Connected' : 'Offline'}</span>
        </div>
        <div className="flex items-center justify-between">
          <div className="truncate" style={{ fontSize: '12px', fontWeight: 600 }}>
            👤 {user?.username}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={logout} title="Log Out">
            <LogOut size={14} />
          </button>
        </div>
      </div>

      {/* Create Workspace Modal */}
      {showCreateWsModal && (
        <div className="modal-overlay" onClick={() => setShowCreateWsModal(false)}>
          <div className="modal slide-up" onClick={e => e.stopPropagation()}>
            <div className="modal-title">Create New Workspace</div>
            <form onSubmit={handleCreateWorkspace}>
              <div className="input-group">
                <label className="input-label">Workspace Name</label>
                <input 
                  type="text" 
                  className="input" 
                  placeholder="e.g. Q3 Financials or DBMS Course"
                  value={newWsName}
                  onChange={e => setNewWsName(e.target.value)}
                  required 
                />
              </div>

              <div className="ws-type-grid">
                <div 
                  className={`ws-type-option ${newWsType === 'business' ? 'selected' : ''}`}
                  onClick={() => setNewWsType('business')}
                >
                  <span className="emoji">💼</span>
                  <div className="label">Business</div>
                  <div className="sublabel">Invoices, Reports, Analytics</div>
                </div>
                <div 
                  className={`ws-type-option ${newWsType === 'student' ? 'selected' : ''}`}
                  onClick={() => setNewWsType('student')}
                >
                  <span className="emoji">🎓</span>
                  <div className="label">Student</div>
                  <div className="sublabel">Notes, Question Papers, MCQs</div>
                </div>
              </div>

              <div className="input-group">
                <label className="input-label">Description (Optional)</label>
                <input 
                  type="text" 
                  className="input" 
                  placeholder="Brief summary of this workspace"
                  value={newWsDesc}
                  onChange={e => setNewWsDesc(e.target.value)}
                />
              </div>

              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowCreateWsModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create Workspace</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  );
};

export default Sidebar;
