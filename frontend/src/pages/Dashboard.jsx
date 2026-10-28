import React, { useState, useEffect } from 'react';
import { LayoutDashboard, FileText, Database, MessageSquare, Briefcase, GraduationCap, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { analyticsAPI } from '../lib/api';

const Dashboard = () => {
  const { activeWorkspace } = useAuth();
  const [stats, setStats] = useState(null);

  useEffect(() => {
    if (activeWorkspace) {
      loadStats();
    }
  }, [activeWorkspace?.id]);

  const loadStats = async () => {
    try {
      const res = await analyticsAPI.dashboard(activeWorkspace.id);
      setStats(res.data);
    } catch (err) {
      console.error('Failed to load dashboard stats:', err);
    }
  };

  const isStudent = activeWorkspace?.workspace_type === 'student';

  return (
    <div className="page-area fade-in">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>Workspace Overview</h1>
          <p>Local AI RAG status & Knowledge Base statistics for <strong>{activeWorkspace?.name || 'Workspace'}</strong></p>
        </div>
        <span className={`status-badge ${isStudent ? 'ready' : 'processing'}`} style={{ padding: '6px 14px', fontSize: '12px' }}>
          {isStudent ? <GraduationCap size={14} /> : <Briefcase size={14} />}
          {isStudent ? 'STUDENT WORKSPACE' : 'ENTERPRISE BUSINESS WORKSPACE'}
        </span>
      </div>

      {/* KPI Cards */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Indexed Documents</div>
          <div className="kpi-value">{stats?.total_documents || 0}</div>
          <div className="kpi-sub">Uploaded & processed</div>
          <div className="kpi-icon">📄</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Vector Embeddings</div>
          <div className="kpi-value">{stats?.total_chunks || 0}</div>
          <div className="kpi-sub">FAISS 1024-dim chunks</div>
          <div className="kpi-icon">🧠</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">AI Conversations</div>
          <div className="kpi-value">{stats?.total_chats || 0}</div>
          <div className="kpi-sub">Local LLM query responses</div>
          <div className="kpi-icon">💬</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Security Mode</div>
          <div className="kpi-value" style={{ fontSize: '20px', color: 'var(--success)' }}>OFFLINE</div>
          <div className="kpi-sub">0% Cloud / 100% Private</div>
          <div className="kpi-icon">🔒</div>
        </div>
      </div>

      {/* Quick Action Grid */}
      <div className="grid-2 mb-24">
        <div className="card">
          <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '8px' }}>
            {isStudent ? '🎓 Student Learning Hub' : '💼 Business Intelligence RAG'}
          </h3>
          <p className="text-muted text-sm mb-16">
            {isStudent 
              ? 'Upload textbooks, PPTs, previous VTU question papers, and research papers to generate MCQs, summaries, and instant explanations.'
              : 'Query contracts, invoices, financial reports, and HR policies directly using natural-language questions.'
            }
          </p>
          <Link to="/chat" className="btn btn-primary">
            <span>Launch AI Chat</span>
            <ArrowRight size={14} />
          </Link>
        </div>

        <div className="card">
          <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '8px' }}>
            📂 Manage Knowledge Base
          </h3>
          <p className="text-muted text-sm mb-16">
            Add new PDF, Word, Excel, CSV, or PowerPoint documents to expand this workspace's local vector index.
          </p>
          <Link to="/documents" className="btn btn-secondary">
            <span>Upload Documents</span>
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>

      {/* Recent Documents Table */}
      <div className="card">
        <h3 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '16px' }}>
          Recent Documents
        </h3>
        {stats?.recent_documents?.length === 0 ? (
          <div className="text-muted text-sm" style={{ padding: '20px 0', textAlign: 'center' }}>
            No documents in this workspace yet. Upload files to get started.
          </div>
        ) : (
          <div className="doc-list">
            {stats?.recent_documents?.map((doc) => (
              <div key={doc.id} className="doc-item">
                <div className="doc-icon">📄</div>
                <div className="doc-info">
                  <div className="doc-name">{doc.original_filename}</div>
                  <div className="doc-meta">
                    <span>{doc.file_type.toUpperCase()}</span>
                    <span>•</span>
                    <span>{doc.chunk_count} chunks</span>
                  </div>
                </div>
                <span className={`status-badge ${doc.status}`}>{doc.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
