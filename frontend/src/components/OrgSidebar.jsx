import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  GraduationCap,
  Briefcase,
  Users,
  Shield,
  FileText,
  FolderOpen,
  BarChart3,
  LogOut,
  ChevronLeft,
  Building,
  Key
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function OrgSidebar({ portalType, orgName, orgSlug }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const isEdu = portalType === 'education';

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-icon">{isEdu ? '🎓' : '🏢'}</div>
        <div className="brand-text">
          <div className="brand-title">{orgName || (isEdu ? 'Education Portal' : 'Business Portal')}</div>
          <div className="brand-sub">{orgSlug ? `@${orgSlug}` : 'Organization'}</div>
        </div>
      </div>

      <div style={{ padding: '8px 16px', marginBottom: '8px' }}>
        <button
          onClick={() => navigate('/org-selection')}
          className="btn btn-ghost btn-sm w-full"
          style={{ justifyContent: 'flex-start', fontSize: '12px' }}
        >
          <ChevronLeft size={14} /> Switch Organization
        </button>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">Portal</div>
        <NavLink
          to={isEdu ? '/org/education' : '/org/business'}
          end
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <span className="nav-icon">{isEdu ? <GraduationCap size={16} /> : <Briefcase size={16} />}</span>
          <span>{isEdu ? 'Campus Overview' : 'Company Overview'}</span>
        </NavLink>

        <NavLink
          to="/chat"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <span className="nav-icon"><FileText size={16} /></span>
          <span>AI Knowledge Chat</span>
        </NavLink>

        <NavLink
          to="/documents"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <span className="nav-icon"><FolderOpen size={16} /></span>
          <span>Authorized Documents</span>
        </NavLink>

        {!isEdu && (
          <NavLink
            to="/analytics"
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <span className="nav-icon"><BarChart3 size={16} /></span>
            <span>Business Analytics</span>
          </NavLink>
        )}

        <div className="nav-section-label" style={{ marginTop: '16px' }}>Administration</div>
        <NavLink
          to="/org/admin"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <span className="nav-icon"><Users size={16} /></span>
          <span>Org Management</span>
        </NavLink>

        {user?.role === 'admin' && (
          <NavLink
            to="/super-admin"
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <span className="nav-icon"><Shield size={16} /></span>
            <span>Platform Admin</span>
          </NavLink>
        )}

        <NavLink
          to="/"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          style={{ marginTop: '12px' }}
        >
          <span className="nav-icon"><Building size={16} /></span>
          <span>Standard Workspace</span>
        </NavLink>
      </nav>

      <div className="sidebar-footer">
        <div className="flex items-center justify-between">
          <div className="truncate" style={{ fontSize: '12px', fontWeight: 600 }}>
            👤 {user?.username}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={logout} title="Log Out">
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  );
}
