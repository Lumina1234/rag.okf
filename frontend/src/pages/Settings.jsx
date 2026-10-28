import React, { useState, useEffect } from 'react';
import { Cpu, Server, HardDrive, RefreshCw, CheckCircle, AlertTriangle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { systemAPI } from '../lib/api';

const Settings = () => {
  const { user } = useAuth();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const res = await systemAPI.status();
      setStatus(res.data);
    } catch (err) {
      console.error('Failed to load system status:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-area fade-in">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>System Settings & Health</h1>
          <p>Local AI models, vector database configurations, and environment status</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={loadStatus}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          <span>Refresh Status</span>
        </button>
      </div>

      {/* Model Configuration */}
      <div className="settings-section">
        <div className="settings-section-title flex items-center gap-8">
          <Cpu size={16} className="text-accent" />
          <span>LLM Engine & Embeddings</span>
        </div>

        <div className="card">
          <div className="settings-row">
            <div>
              <div className="settings-label">Default LLM Model</div>
              <div className="settings-sub">Running via local Ollama service</div>
            </div>
            <span className="tag" style={{ fontSize: '12px' }}>{status?.default_llm || 'gemma4:12b'}</span>
          </div>

          <div className="settings-row">
            <div>
              <div className="settings-label">Embedding Model</div>
              <div className="settings-sub">Dense vector encoder for semantic search</div>
            </div>
            <span className="tag" style={{ fontSize: '12px' }}>{status?.embedding_model || 'BAAI/bge-m3'}</span>
          </div>

          <div className="settings-row">
            <div>
              <div className="settings-label">Available Ollama Models</div>
              <div className="settings-sub">Installed on local host machine</div>
            </div>
            <div className="flex gap-6 flex-wrap">
              {status?.available_models?.length > 0 ? (
                status.available_models.map((m, idx) => (
                  <span key={idx} className="status-badge ready">{m}</span>
                ))
              ) : (
                <span className="text-muted text-sm">No models detected or Ollama offline</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* System Health */}
      <div className="settings-section">
        <div className="settings-section-title flex items-center gap-8">
          <Server size={16} className="text-accent" />
          <span>Local Environment Health</span>
        </div>

        <div className="card">
          <div className="settings-row">
            <div>
              <div className="settings-label">Ollama Host Connection</div>
              <div className="settings-sub">http://localhost:11434</div>
            </div>
            <span className={`status-badge ${status?.ollama_online ? 'ready' : 'failed'}`}>
              {status?.ollama_online ? <CheckCircle size={12} /> : <AlertTriangle size={12} />}
              {status?.ollama_online ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>

          <div className="settings-row">
            <div>
              <div className="settings-label">Database & Vector Index</div>
              <div className="settings-sub">SQLite + Local FAISS Vector Store</div>
            </div>
            <span className="status-badge ready">READY</span>
          </div>

          <div className="settings-row">
            <div>
              <div className="settings-label">Total Documents Indexed</div>
              <div className="settings-sub">Across all workspaces</div>
            </div>
            <span className="font-bold">{status?.total_documents || 0} files</span>
          </div>
        </div>
      </div>

      {/* User Info */}
      <div className="settings-section">
        <div className="settings-section-title flex items-center gap-8">
          <HardDrive size={16} className="text-accent" />
          <span>Current Account</span>
        </div>

        <div className="card">
          <div className="settings-row">
            <div className="settings-label">Username</div>
            <span>{user?.username}</span>
          </div>
          <div className="settings-row">
            <div className="settings-label">Role</div>
            <span className="tag">{user?.role?.toUpperCase()}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
