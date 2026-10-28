import React, { useEffect, useMemo, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Shield, History, Clock3, MessageSquareText, Download, Search, ArrowUpDown, RotateCcw } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { systemAPI } from '../lib/api';

const AdminHistory = () => {
  const { user } = useAuth();
  const [history, setHistory] = useState({ login_history: [], conversation_history: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortDirection, setSortDirection] = useState('newest');
  const [selectedThreadKey, setSelectedThreadKey] = useState('');

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await systemAPI.adminHistory();
      setHistory(res.data);
    } catch (err) {
      console.error('Failed to load admin history:', err);
      setError(err.response?.data?.detail || 'Unable to load admin history');
    } finally {
      setLoading(false);
    }
  };

  const loginHistory = useMemo(() => history.login_history || [], [history]);
  const conversationHistory = useMemo(() => history.conversation_history || [], [history]);

  const filteredLoginHistory = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return loginHistory.filter((item) => {
      const matchesTerm = !term || [item.username, item.action, item.resource, item.role, JSON.stringify(item.details || {})]
        .join(' ')
        .toLowerCase()
        .includes(term);

      const created = new Date(item.created_at);
      const matchesFrom = !dateFrom || created >= new Date(dateFrom);
      const matchesTo = !dateTo || created <= new Date(`${dateTo}T23:59:59`);
      return matchesTerm && matchesFrom && matchesTo;
    });
  }, [loginHistory, searchTerm, dateFrom, dateTo]);

  const filteredConversationHistory = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return conversationHistory.filter((item) => {
      const matchesTerm = !term || [item.username, item.workspace_name, item.role, item.content, item.user_role]
        .join(' ')
        .toLowerCase()
        .includes(term);

      const created = new Date(item.created_at);
      const matchesFrom = !dateFrom || created >= new Date(dateFrom);
      const matchesTo = !dateTo || created <= new Date(`${dateTo}T23:59:59`);
      return matchesTerm && matchesFrom && matchesTo;
    });
  }, [conversationHistory, searchTerm, dateFrom, dateTo]);

  const sortedLoginHistory = useMemo(() => {
    return [...filteredLoginHistory].sort((a, b) => {
      const delta = new Date(a.created_at) - new Date(b.created_at);
      return sortDirection === 'newest' ? -delta : delta;
    });
  }, [filteredLoginHistory, sortDirection]);

  const sortedConversationHistory = useMemo(() => {
    return [...filteredConversationHistory].sort((a, b) => {
      const delta = new Date(a.created_at) - new Date(b.created_at);
      return sortDirection === 'newest' ? -delta : delta;
    });
  }, [filteredConversationHistory, sortDirection]);

  const selectedThreadLabel = useMemo(() => {
    if (!selectedThreadKey) return '';
    const [workspaceId, userId] = selectedThreadKey.split('|');
    const threadItems = conversationHistory.filter((item) => String(item.workspace_id) === workspaceId && String(item.user_id) === userId);
    if (threadItems.length === 0) return 'Selected thread';
    return `${threadItems[0].workspace_name} • ${threadItems[0].username}`;
  }, [selectedThreadKey, conversationHistory]);

  const selectedThreadHistory = useMemo(() => {
    if (!selectedThreadKey) return [];
    const [workspaceId, userId] = selectedThreadKey.split('|');
    return conversationHistory
      .filter((item) => String(item.workspace_id) === workspaceId && String(item.user_id) === userId)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  }, [selectedThreadKey, conversationHistory]);

  const exportCsv = () => {
    const rows = [
      ...sortedLoginHistory.map((item) => ({
        type: 'login',
        username: item.username || '',
        role: item.role || '',
        workspace: '',
        action: item.action || '',
        content: item.details ? JSON.stringify(item.details) : '',
        created_at: item.created_at,
      })),
      ...sortedConversationHistory.map((item) => ({
        type: 'conversation',
        username: item.username || '',
        role: item.role || '',
        workspace: item.workspace_name || '',
        action: item.role || '',
        content: item.content || '',
        created_at: item.created_at,
      })),
    ];

    const header = ['type', 'username', 'role', 'workspace', 'action', 'content', 'created_at'];
    const csv = [header.join(',')]
      .concat(rows.map((row) => header.map((key) => `"${String(row[key] ?? '').replace(/"/g, '""')}"`).join(',')))
      .join('\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'admin-history.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const exportSelectedThreadCsv = () => {
    if (!selectedThreadHistory.length) return;
    const header = ['workspace', 'username', 'role', 'content', 'created_at'];
    const csv = [header.join(',')]
      .concat(selectedThreadHistory.map((item) => header.map((key) => {
        const value = key === 'workspace' ? item.workspace_name : key === 'username' ? item.username : key === 'role' ? item.role : key === 'content' ? item.content : item.created_at;
        return `"${String(value ?? '').replace(/"/g, '""')}"`;
      }).join(',')))
      .join('\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `thread-${selectedThreadKey.replace(/[^a-z0-9-_]/gi, '-')}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const clearFilters = () => {
    setSearchTerm('');
    setDateFrom('');
    setDateTo('');
  };

  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="page-area fade-in">
      <div className="page-header flex items-center justify-between">
        <div>
          <h1>Admin Conversation & Login History</h1>
          <p>Review all Telegram/RAG conversations and the web login audit trail from one secure admin view.</p>
        </div>
        <div className="flex gap-8 flex-wrap items-center">
          <button className="btn btn-secondary btn-sm" onClick={loadHistory}>
            <History size={14} />
            <span>Refresh</span>
          </button>
          <button className="btn btn-primary btn-sm" onClick={exportCsv}>
            <Download size={14} />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="settings-section-title flex items-center gap-8">
          <Search size={16} className="text-accent" />
          <span>Filter History</span>
        </div>
        <div className="grid grid-4" style={{ gap: '12px' }}>
          <div className="input-group">
            <label className="input-label">Search by username or message</label>
            <input className="input" placeholder="Type a username or term" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
          </div>
          <div className="input-group">
            <label className="input-label">From date</label>
            <input type="date" className="input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div className="input-group">
            <label className="input-label">To date</label>
            <input type="date" className="input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div className="input-group">
            <label className="input-label">Sort</label>
            <select className="input" value={sortDirection} onChange={(e) => setSortDirection(e.target.value)}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </div>
        </div>
        <div className="flex gap-8 mt-12">
          <button className="btn btn-ghost btn-sm" onClick={clearFilters}>
            <RotateCcw size={14} />
            <span>Clear Filters</span>
          </button>
          <button className="btn btn-secondary btn-sm" onClick={exportSelectedThreadCsv} disabled={!selectedThreadHistory.length}>
            <Download size={14} />
            <span>Export Selected Thread</span>
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="card">Loading admin history…</div>
      ) : (
        <div className="grid grid-2" style={{ gap: '16px' }}>
          <div className="card">
            <div className="settings-section-title flex items-center gap-8">
              <Shield size={16} className="text-accent" />
              <span>Login History</span>
            </div>
            <div style={{ maxHeight: '420px', overflowY: 'auto' }}>
              {sortedLoginHistory.length === 0 ? (
                <div className="text-muted">No matching login events found.</div>
              ) : (
                sortedLoginHistory.map((item) => (
                  <div key={item.id} className="history-row" style={{ padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
                    <div className="font-bold">{item.username || 'Unknown user'} • {item.role || 'user'}</div>
                    <div className="text-sm text-muted">{item.action} • {item.resource || 'user'}</div>
                    <div className="text-sm">{item.details ? JSON.stringify(item.details) : '-'}</div>
                    <div className="text-sm text-muted"><Clock3 size={12} /> {new Date(item.created_at).toLocaleString()}</div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="card">
            <div className="settings-section-title flex items-center gap-8">
              <MessageSquareText size={16} className="text-accent" />
              <span>Conversation History</span>
            </div>
            <div className="text-sm text-muted" style={{ marginBottom: '8px' }}>
              {selectedThreadLabel ? `Selected thread: ${selectedThreadLabel}` : 'Select any conversation card to export that conversation thread'}
            </div>
            <div style={{ maxHeight: '420px', overflowY: 'auto' }}>
              {sortedConversationHistory.length === 0 ? (
                <div className="text-muted">No matching conversations found.</div>
              ) : (
                sortedConversationHistory.map((item) => {
                  const threadKey = `${item.workspace_id}|${item.user_id}`;
                  const isSelected = selectedThreadKey === threadKey;
                  return (
                    <div key={item.id} className="history-row" style={{ padding: '12px 0', borderBottom: '1px solid var(--border)' }}>
                      <div className="flex items-center justify-between gap-8">
                        <div className="font-bold">{item.workspace_name} • {item.username} ({item.user_role || item.role})</div>
                        <button className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setSelectedThreadKey(threadKey)}>
                          {isSelected ? 'Selected Thread' : 'Select Thread'}
                        </button>
                      </div>
                      <div className="text-sm text-muted">{item.role} • <Clock3 size={12} /> {new Date(item.created_at).toLocaleString()}</div>
                      <div className="text-sm" style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>
                      {item.sources?.length > 0 && (
                        <div className="text-sm text-muted">Sources: {item.sources.length}</div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminHistory;
