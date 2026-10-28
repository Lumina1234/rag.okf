import React, { useState, useEffect, useRef } from 'react';
import { 
  BarChart3, Sparkles, AlertCircle, FileSpreadsheet, Send, 
  Trash2, Copy, Check, ChevronDown, ChevronUp, Table, Eye,
  Search, Plus, Pin, Clock, MessageSquare, Bot, ArrowRight
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAuth } from '../context/AuthContext';
import { analyticsAPI, documentAPI, chatAPI } from '../lib/api';
import { InlineChart, DataTablePreview } from '../components/AnalyticsComponents';

const Analytics = () => {
  const { activeWorkspace } = useAuth();
  const [dataDocs, setDataDocs] = useState([]);
  const [failedDocs, setFailedDocs] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState('');
  const [inputQuery, setInputQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [copiedId, setCopiedId] = useState(null);

  // Business Analytics Conversation Sessions (Dedicated History)
  const [sessions, setSessions] = useState([
    { id: 1, title: 'New Analysis', messages: [] }
  ]);
  const [activeSessionId, setActiveSessionId] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [historyTab, setHistoryTab] = useState('all'); // 'all' | 'pinned' | 'recent'
  const [pinnedSessions, setPinnedSessions] = useState(new Set());

  const messagesEndRef = useRef(null);

  // Active session
  const activeSession = sessions.find(s => s.id === activeSessionId) || sessions[0] || { id: 1, title: 'New Analysis', messages: [] };
  const messages = activeSession ? activeSession.messages : [];

  // Load datasets and dedicated Business Analytics history whenever workspace changes
  useEffect(() => {
    if (activeWorkspace) {
      loadDataDocuments();
      loadHistory();
    }
  }, [activeWorkspace?.id]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const loadDataDocuments = async () => {
    try {
      const res = await documentAPI.list(activeWorkspace.id);
      const all = res.data.filter(d => ['xlsx', 'xls', 'csv'].includes(d.file_type.toLowerCase()));
      const ready = all.filter(d => d.status === 'ready');
      const failed = all.filter(d => d.status === 'failed');
      setDataDocs(ready);
      setFailedDocs(failed);
      if (ready.length > 0 && !selectedDocId) {
        setSelectedDocId(String(ready[0].id));
      }
    } catch (err) {
      console.error('Failed to load tabular documents:', err);
    }
  };

  const loadHistory = async () => {
    try {
      // Fetch ONLY Business Analytics conversation history
      const res = await chatAPI.history(activeWorkspace.id, 500, 'analytics');
      if (res.data && res.data.length > 0) {
        const grouped = [];
        let cur = null;
        for (const msg of res.data) {
          const msgDt = msg.created_at ? new Date(msg.created_at).getTime() : 0;
          const shouldStartNew = !cur || (msgDt && cur.lastTime && (msgDt - cur.lastTime > 30 * 60 * 1000));
          if (shouldStartNew) {
            const title = msg.role === 'user' ? (msg.content.slice(0, 36).trim() || 'Analysis Session') : 'Analysis Session';
            cur = {
              id: msg.id || Date.now(),
              title: title,
              messages: [msg],
              lastTime: msgDt,
              createdAt: msg.created_at,
            };
            grouped.push(cur);
          } else {
            if (cur.title === 'Analysis Session' && msg.role === 'user') {
              cur.title = msg.content.slice(0, 36).trim() || 'Analysis Session';
            }
            cur.messages.push(msg);
            if (msgDt) cur.lastTime = msgDt;
          }
        }
        const reversedSessions = [...grouped].reverse();
        setSessions(reversedSessions);
        setActiveSessionId(prev => {
          const exists = reversedSessions.some(s => s.id === prev);
          return exists ? prev : reversedSessions[0].id;
        });
      } else {
        const defaultSession = { id: Date.now(), title: 'New Analysis', messages: [] };
        setSessions([defaultSession]);
        setActiveSessionId(defaultSession.id);
      }
    } catch (err) {
      console.error('Failed to load analytics history:', err);
    }
  };

  const handleNewChat = () => {
    const newSession = {
      id: Date.now(),
      title: 'New Analysis',
      messages: []
    };
    setSessions(prev => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
    setInputQuery('');
  };

  const togglePin = (sessionId) => {
    setPinnedSessions(prev => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  };

  const handleClearHistory = async () => {
    if (!activeWorkspace) return;
    try {
      // Clear ONLY Business Analytics history
      await chatAPI.clear(activeWorkspace.id, 'analytics');
      const fresh = [{ id: Date.now(), title: 'New Analysis', messages: [] }];
      setSessions(fresh);
      setActiveSessionId(fresh[0].id);
    } catch (err) {
      console.error('Failed to clear analytics history:', err);
    }
  };

  const updateActiveSessionMessages = (updater) => {
    setSessions(prev => prev.map(s => {
      if (s.id === activeSessionId) {
        const nextMsgs = typeof updater === 'function' ? updater(s.messages) : updater;
        let newTitle = s.title;
        if (s.title === 'New Analysis' && nextMsgs.length > 0) {
          const firstUser = nextMsgs.find(m => m.role === 'user');
          if (firstUser) newTitle = firstUser.content.slice(0, 32);
        }
        return { ...s, title: newTitle, messages: nextMsgs };
      }
      return s;
    }));
  };

  const handleSend = async (queryText = inputQuery) => {
    const trimmed = queryText.trim();
    if (!trimmed || !selectedDocId || !activeWorkspace || loading) return;

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
    };

    updateActiveSessionMessages(prev => [...prev, userMsg]);
    setInputQuery('');
    setLoading(true);

    try {
      const res = await analyticsAPI.query({
        query: trimmed,
        document_id: parseInt(selectedDocId, 10),
        workspace_id: activeWorkspace.id,
      });

      // Turn off initial loading spinner as words start predicting
      setLoading(false);

      // Word-by-word streaming prediction
      const fullAnswer = res.data.answer || '';
      const words = fullAnswer.split(/(\s+)/); // Preserves words, spaces, and line breaks
      const assistantId = Date.now() + 1;

      // Initialize empty assistant message
      const initialAssistant = {
        id: assistantId,
        role: 'assistant',
        content: '',
        chart: null,
        raw_data: null,
        isStreaming: true,
        created_at: new Date().toISOString(),
      };
      updateActiveSessionMessages(prev => [...prev, initialAssistant]);

      // Predict word-by-word into the message
      let currentIdx = 0;
      let accumulatedText = '';

      await new Promise((resolve) => {
        const streamInterval = setInterval(() => {
          if (currentIdx < words.length) {
            accumulatedText += words[currentIdx];
            currentIdx++;
            updateActiveSessionMessages(prev => {
              const updated = [...prev];
              const lastIdx = updated.length - 1;
              if (lastIdx >= 0 && updated[lastIdx].id === assistantId) {
                updated[lastIdx] = {
                  ...updated[lastIdx],
                  content: accumulatedText,
                };
              }
              return updated;
            });
          } else {
            clearInterval(streamInterval);
            // Done predicting words: attach interactive Plotly chart & raw data preview
            updateActiveSessionMessages(prev => {
              const updated = [...prev];
              const lastIdx = updated.length - 1;
              if (lastIdx >= 0 && updated[lastIdx].id === assistantId) {
                updated[lastIdx] = {
                  ...updated[lastIdx],
                  content: fullAnswer,
                  chart: res.data.chart,
                  raw_data: res.data.raw_data,
                  isStreaming: false,
                };
              }
              return updated;
            });
            resolve();
          }
        }, 22); // 22ms per word - lively, visible word-by-word prediction
      });

    } catch (err) {
      console.error('Analytics query error:', err);
      const errorMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        isError: true,
        content: `⚠️ Error running analysis: ${err.response?.data?.detail || err.message}`,
        created_at: new Date().toISOString(),
      };
      updateActiveSessionMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (id, text) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Real-time search filter across both title AND message content!
  const filteredSessions = sessions.filter(s => {
    const q = searchQuery.toLowerCase().trim();
    const matchesSearch = !q || 
      s.title.toLowerCase().includes(q) || 
      s.messages.some(m => (m.content || '').toLowerCase().includes(q));
    if (historyTab === 'pinned') return matchesSearch && pinnedSessions.has(s.id);
    return matchesSearch;
  });

  const sampleQueries = [
    'Which customer generated the highest revenue?',
    'Show monthly sales trend for the last six months',
    'Compare branch performance across regions',
    'Revenue share by product category',
    'Top 5 products by total sales',
    'Average transaction value by category',
  ];

  const selectedDoc = dataDocs.find(d => String(d.id) === String(selectedDocId));

  return (
    <div className="chat-layout" style={{ display: 'flex', height: '100%', width: '100%', background: '#0a0a0f' }}>
      
      {/* ── Left Column: Dedicated Business Analytics Conversation History with Real-Time Search ── */}
      <div className="conv-history-panel" style={{
        width: '320px',
        borderRight: '1px solid rgba(255,255,255,0.06)',
        backgroundColor: '#0a0a0f',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0
      }}>
        {/* Panel Header */}
        <div style={{ padding: '20px 20px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ fontSize: '15px', fontWeight: '700', color: '#e2e8f0', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <BarChart3 size={17} color="#818cf8" />
              <span>Analytics History</span>
            </h2>
            <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
              Business & Chart Conversations
            </div>
          </div>
          <button 
            onClick={handleNewChat}
            title="New Analysis Chat"
            style={{ 
              background: 'rgba(99, 102, 241, 0.1)', 
              border: '1px solid rgba(99, 102, 241, 0.3)', 
              borderRadius: '6px', 
              color: '#818cf8', 
              padding: '6px', 
              cursor: 'pointer' 
            }}
          >
            <Plus size={16} />
          </button>
        </div>

        {/* Primary New Chat Button */}
        <div style={{ padding: '0 20px 14px' }}>
          <button 
            onClick={handleNewChat}
            style={{ 
              width: '100%', 
              padding: '10px 14px', 
              background: '#4f46e5', 
              color: '#fff', 
              borderRadius: '8px', 
              border: 'none', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              gap: '8px', 
              fontWeight: '600', 
              fontSize: '13px',
              cursor: 'pointer' 
            }}
          >
            <Plus size={16} /> New Analysis
          </button>
        </div>

        {/* Search Conversations Input */}
        <div style={{ padding: '0 20px 12px' }}>
          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: '12px', top: '11px', color: '#64748b' }} />
            <input 
              type="text" 
              placeholder="Search analytics chats..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ 
                width: '100%', 
                background: 'rgba(255,255,255,0.04)', 
                border: '1px solid rgba(255,255,255,0.08)', 
                borderRadius: '8px', 
                padding: '9px 10px 9px 36px', 
                color: '#e2e8f0', 
                fontSize: '13px', 
                outline: 'none' 
              }}
            />
          </div>
        </div>

        {/* Filter Tabs: All | Pinned | Recent */}
        <div style={{ padding: '0 20px 14px', display: 'flex', gap: '6px' }}>
          <button 
            onClick={() => setHistoryTab('all')}
            style={{ 
              flex: 1, 
              background: historyTab === 'all' ? '#4f46e5' : 'rgba(255,255,255,0.04)', 
              color: historyTab === 'all' ? '#fff' : '#94a3b8', 
              border: 'none', 
              padding: '6px', 
              borderRadius: '6px', 
              fontSize: '12px', 
              cursor: 'pointer',
              fontWeight: '500' 
            }}
          >
            All
          </button>
          <button 
            onClick={() => setHistoryTab('pinned')}
            style={{ 
              flex: 1, 
              background: historyTab === 'pinned' ? '#4f46e5' : 'rgba(255,255,255,0.04)', 
              color: historyTab === 'pinned' ? '#fff' : '#94a3b8', 
              border: 'none', 
              padding: '6px', 
              borderRadius: '6px', 
              fontSize: '12px', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              gap: '4px', 
              cursor: 'pointer',
              fontWeight: '500' 
            }}
          >
            <Pin size={12} /> Pinned
          </button>
          <button 
            onClick={() => setHistoryTab('recent')}
            style={{ 
              flex: 1, 
              background: historyTab === 'recent' ? '#4f46e5' : 'rgba(255,255,255,0.04)', 
              color: historyTab === 'recent' ? '#fff' : '#94a3b8', 
              border: 'none', 
              padding: '6px', 
              borderRadius: '6px', 
              fontSize: '12px', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              gap: '4px', 
              cursor: 'pointer',
              fontWeight: '500' 
            }}
          >
            <Clock size={12} /> Recent
          </button>
        </div>

        {/* Sessions List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0 8px 8px', color: '#94a3b8', fontSize: '11px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            <span>Analytics Chats ({filteredSessions.length})</span>
            {searchQuery && <span style={{ color: '#818cf8' }}>Filtered</span>}
          </div>

          {filteredSessions.length === 0 ? (
            <div style={{ padding: '24px 16px', textAlign: 'center', color: '#64748b', fontSize: '12px' }}>
              {searchQuery ? `No chats matching "${searchQuery}"` : 'No analytics chats yet. Ask a question to begin!'}
            </div>
          ) : (
            filteredSessions.map((session) => {
              const isPinned = pinnedSessions.has(session.id);
              const isActive = session.id === activeSessionId;
              return (
                <div 
                  key={session.id}
                  onClick={() => setActiveSessionId(session.id)}
                  style={{ 
                    padding: '10px 12px', 
                    background: isActive ? 'rgba(79,70,229,0.18)' : 'rgba(255,255,255,0.02)', 
                    border: isActive ? '1px solid rgba(79,70,229,0.5)' : '1px solid rgba(255,255,255,0.04)', 
                    borderRadius: '8px', 
                    display: 'flex', 
                    gap: '10px', 
                    alignItems: 'flex-start', 
                    cursor: 'pointer', 
                    marginBottom: '6px',
                    transition: 'all 0.15s ease' 
                  }}
                >
                  <MessageSquare size={15} style={{ color: isActive ? '#818cf8' : '#64748b', marginTop: '3px', flexShrink: 0 }} />
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{ color: isActive ? '#fff' : '#e2e8f0', fontSize: '13px', fontWeight: isActive ? '600' : '500', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                      {session.title}
                    </div>
                    <div style={{ color: '#64748b', fontSize: '11px', marginTop: '3px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span>{session.messages.length} msg{session.messages.length !== 1 ? 's' : ''}</span>
                      {session.messages.some(m => m.chart) && (
                        <span style={{ color: '#818cf8', display: 'flex', alignItems: 'center', gap: '2px' }}>
                          • 📊 chart
                        </span>
                      )}
                    </div>
                  </div>
                  <button 
                    onClick={(e) => { e.stopPropagation(); togglePin(session.id); }}
                    title={isPinned ? 'Unpin' : 'Pin conversation'}
                    style={{ 
                      background: 'none', 
                      border: 'none', 
                      color: isPinned ? '#818cf8' : '#475569', 
                      cursor: 'pointer', 
                      padding: '2px',
                      flexShrink: 0 
                    }}
                  >
                    <Pin size={12} fill={isPinned ? '#818cf8' : 'none'} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* ── Right Column: Business Analytics Main Chat Panel ── */}
      <div className="chat-shell" style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0, background: '#0f0f16' }}>
        
        {/* Top Header Bar */}
        <div className="topbar" style={{
          padding: '14px 24px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          background: 'rgba(10, 10, 15, 0.95)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
          flexShrink: 0
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0 }}>
            <div style={{
              width: '34px',
              height: '34px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(139, 92, 246, 0.25))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#818cf8',
              flexShrink: 0
            }}>
              <BarChart3 size={18} />
            </div>
            <div>
              <div style={{ fontSize: '15px', fontWeight: '600', color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>Business Analytics Chat</span>
                <span className="tag" style={{ fontSize: '11px', padding: '2px 8px', background: 'rgba(79,70,229,0.15)', color: '#818cf8' }}>
                  {activeWorkspace?.name || 'Workspace'}
                </span>
              </div>
              <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                Active Session: <strong style={{ color: '#cbd5e1' }}>{activeSession.title}</strong>
              </div>
            </div>
          </div>

          {/* Dataset Dropdown & Action Buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {dataDocs.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <label style={{ fontSize: '12px', color: '#94a3b8', whiteSpace: 'nowrap' }}>Dataset:</label>
                <select
                  className="input select"
                  value={selectedDocId}
                  onChange={(e) => setSelectedDocId(e.target.value)}
                  style={{
                    fontSize: '12px',
                    padding: '6px 12px',
                    background: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(79, 70, 229, 0.35)',
                    color: '#e2e8f0',
                    borderRadius: '6px',
                    maxWidth: '220px'
                  }}
                >
                  {dataDocs.map((doc) => (
                    <option key={doc.id} value={doc.id} style={{ background: '#0f172a', color: '#e2e8f0' }}>
                      📊 {doc.original_filename}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <button
              onClick={handleClearHistory}
              title="Clear Analytics History"
              style={{
                background: 'transparent',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                color: '#94a3b8',
                padding: '6px 10px',
                fontSize: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                cursor: 'pointer'
              }}
            >
              <Trash2 size={14} /> Clear
            </button>
          </div>
        </div>

        {/* Content Area */}
        {dataDocs.length === 0 ? (
          <div style={{ flex: 1, padding: '40px', overflowY: 'auto' }}>
            {failedDocs.length > 0 && (
              <div className="card mb-16" style={{ background: 'var(--danger-dim)', borderColor: 'var(--danger)' }}>
                <div className="flex items-center gap-8 mb-8">
                  <AlertCircle size={16} color="var(--danger)" />
                  <strong style={{ color: 'var(--danger)' }}>Previous upload(s) failed — please re-upload</strong>
                </div>
                {failedDocs.map(d => (
                  <div key={d.id} style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                    ❌ <strong>{d.original_filename}</strong>
                    {d.error_message && <span style={{ color: 'var(--text-muted)' }}> — {d.error_message}</span>}
                  </div>
                ))}
              </div>
            )}
            <div className="empty-state card" style={{ maxWidth: '600px', margin: '40px auto', textAlign: 'center', padding: '40px' }}>
              <FileSpreadsheet size={48} color="#818cf8" style={{ margin: '0 auto 16px' }} />
              <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#fff', marginBottom: '8px' }}>
                No Excel or CSV Spreadsheets in this Workspace
              </h3>
              <p style={{ color: '#94a3b8', fontSize: '14px', lineHeight: 1.6, marginBottom: '24px' }}>
                Please go to <strong>Knowledge Base</strong> and upload a spreadsheet (<code>.xlsx</code> or <code>.csv</code>) to unlock conversational AI analytics, metric calculations, and automatic Plotly graphing.
              </p>
              <a href="/documents" className="btn btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                <span>Upload Spreadsheet to Knowledge Base</span>
                <ArrowRight size={14} />
              </a>
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Chat Messages Feed */}
            <div className="chat-messages" style={{
              flex: 1,
              overflowY: 'auto',
              padding: '24px 32px',
              display: 'flex',
              flexDirection: 'column',
              gap: '24px'
            }}>
              {messages.length === 0 ? (
                <div className="empty-state" style={{ margin: 'auto', textAlign: 'center', maxWidth: '720px', padding: '40px 20px' }}>
                  <div style={{
                    width: '64px',
                    height: '64px',
                    borderRadius: '16px',
                    background: 'rgba(99, 102, 241, 0.15)',
                    border: '1px solid rgba(99, 102, 241, 0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto 16px',
                    color: '#818cf8'
                  }}>
                    <BarChart3 size={32} />
                  </div>
                  <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#fff', marginBottom: '8px' }}>
                    Conversational Business Analytics & Charting
                  </h3>
                  <p style={{ color: '#94a3b8', fontSize: '14px', marginBottom: '28px', lineHeight: 1.6 }}>
                    Ask questions in plain English against <strong style={{ color: '#818cf8' }}>{selectedDoc?.original_filename}</strong>.<br />
                    The AI runs deterministic calculations, generates executive summaries, and predicts insights word-by-word with interactive Plotly charts.
                  </p>

                  {/* Sample Prompt Cards */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                    {sampleQueries.map((q, idx) => (
                      <div
                        key={idx}
                        onClick={() => handleSend(q)}
                        style={{
                          padding: '12px 16px',
                          background: 'rgba(15, 23, 42, 0.6)',
                          border: '1px solid rgba(255, 255, 255, 0.06)',
                          borderRadius: '10px',
                          color: '#cbd5e1',
                          fontSize: '13px',
                          textAlign: 'left',
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.5)';
                          e.currentTarget.style.background = 'rgba(99, 102, 241, 0.1)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.06)';
                          e.currentTarget.style.background = 'rgba(15, 23, 42, 0.6)';
                        }}
                      >
                        💡 {q}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <div key={msg.id || idx} style={{ display: 'flex', gap: '16px', maxWidth: '920px', width: '100%', margin: msg.role === 'user' ? '0 0 0 auto' : '0 auto 0 0' }}>
                    {/* Assistant Avatar */}
                    {msg.role !== 'user' && (
                      <div style={{
                        width: '32px',
                        height: '32px',
                        borderRadius: '8px',
                        background: 'rgba(99, 102, 241, 0.2)',
                        color: '#818cf8',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0
                      }}>
                        <BarChart3 size={18} />
                      </div>
                    )}

                    {/* Message Body */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      {msg.role === 'user' ? (
                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                          <div style={{
                            background: '#312e81',
                            color: '#e2e8f0',
                            padding: '12px 18px',
                            borderRadius: '18px 18px 4px 18px',
                            maxWidth: '85%',
                            fontSize: '14px',
                            lineHeight: 1.6,
                            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.2)'
                          }}>
                            {msg.content}
                          </div>
                        </div>
                      ) : (
                        <div style={{
                          background: 'rgba(15, 23, 42, 0.95)',
                          border: '1px solid rgba(148, 163, 184, 0.15)',
                          borderRadius: '4px 18px 18px 18px',
                          padding: '20px 24px',
                          boxShadow: '0 10px 30px rgba(0, 0, 0, 0.25)'
                        }}>
                          {/* Header with Copy */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                            <span style={{ fontSize: '15px', fontWeight: '600', color: '#fff', display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <Sparkles size={16} color="#818cf8" /> AI Data Insights
                            </span>
                            <button
                              onClick={() => handleCopy(msg.id || idx, msg.content)}
                              style={{
                                background: 'none',
                                border: 'none',
                                color: copiedId === (msg.id || idx) ? '#10b981' : '#94a3b8',
                                fontSize: '12px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px',
                                cursor: 'pointer'
                              }}
                            >
                              {copiedId === (msg.id || idx) ? <Check size={14} /> : <Copy size={14} />}
                              <span>{copiedId === (msg.id || idx) ? 'Copied' : 'Copy'}</span>
                            </button>
                          </div>

                          {/* Text / Markdown Report with Word-by-Word Streaming Cursor */}
                          <div style={{ color: '#cbd5e1', fontSize: '14px', lineHeight: 1.7, minHeight: '24px' }}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {msg.content || (msg.isStreaming ? '...' : '')}
                            </ReactMarkdown>
                            {msg.isStreaming && (
                              <span style={{
                                display: 'inline-block',
                                width: '7px',
                                height: '15px',
                                backgroundColor: '#818cf8',
                                marginLeft: '4px',
                                verticalAlign: 'middle',
                                borderRadius: '1px',
                                animation: 'pulse 0.8s infinite ease-in-out'
                              }} />
                            )}
                          </div>

                          {/* Interactive Plotly Chart (appears when word prediction completes) */}
                          {msg.chart && !msg.isStreaming && (
                            <InlineChart chartData={msg.chart} />
                          )}

                          {/* Collapsible Source Data Preview */}
                          {msg.raw_data && !msg.isStreaming && (
                            <DataTablePreview rawData={msg.raw_data} />
                          )}
                        </div>
                      )}
                    </div>

                    {/* User Avatar */}
                    {msg.role === 'user' && (
                      <div style={{
                        width: '32px',
                        height: '32px',
                        borderRadius: '50%',
                        background: '#4f46e5',
                        color: '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 'bold',
                        flexShrink: 0
                      }}>
                        U
                      </div>
                    )}
                  </div>
                ))
              )}

              {/* Initial Calculating / Loading Indicator (before word prediction begins) */}
              {loading && (
                <div style={{ display: 'flex', gap: '16px', maxWidth: '800px', width: '100%' }}>
                  <div style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '8px',
                    background: 'rgba(99, 102, 241, 0.2)',
                    color: '#818cf8',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0
                  }}>
                    <BarChart3 size={18} />
                  </div>
                  <div style={{
                    background: 'rgba(15, 23, 42, 0.95)',
                    border: '1px solid rgba(148, 163, 184, 0.15)',
                    borderRadius: '4px 18px 18px 18px',
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    color: '#818cf8',
                    fontSize: '13px'
                  }}>
                    <div className="typing-dots" style={{ display: 'inline-flex', gap: '4px' }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#818cf8' }}></span>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#818cf8' }}></span>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#818cf8' }}></span>
                    </div>
                    <span>Analyzing dataset & calculating statistics...</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Quick Prompts Pills */}
            <div style={{
              padding: '8px 32px 4px',
              display: 'flex',
              gap: '8px',
              overflowX: 'auto',
              background: 'transparent'
            }}>
              <span style={{ fontSize: '11px', color: '#818cf8', display: 'flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap' }}>
                <Sparkles size={12} /> Suggestions:
              </span>
              {sampleQueries.slice(0, 4).map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(q)}
                  disabled={loading}
                  style={{
                    background: 'rgba(99, 102, 241, 0.1)',
                    color: '#818cf8',
                    border: '1px solid rgba(99, 102, 241, 0.2)',
                    padding: '4px 12px',
                    borderRadius: '16px',
                    fontSize: '11px',
                    whiteSpace: 'nowrap',
                    cursor: 'pointer'
                  }}
                >
                  {q}
                </button>
              ))}
            </div>

            {/* Chat Input Area */}
            <div className="chat-input-area" style={{ padding: '12px 32px 24px' }}>
              <div style={{
                background: 'rgba(15, 15, 26, 0.95)',
                border: '1px solid rgba(79, 70, 229, 0.3)',
                borderRadius: '16px',
                padding: '12px 16px',
                display: 'flex',
                alignItems: 'center',
                gap: '12px'
              }}>
                <textarea
                  className="chat-textarea"
                  placeholder={selectedDoc ? `Ask about ${selectedDoc.original_filename} or request a chart (e.g., 'Compare sales across regions')...` : "Select a spreadsheet..."}
                  value={inputQuery}
                  onChange={(e) => setInputQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  rows={1}
                  disabled={loading || !selectedDoc}
                  style={{
                    flex: 1,
                    background: 'transparent',
                    border: 'none',
                    color: '#e2e8f0',
                    fontSize: '14px',
                    outline: 'none',
                    resize: 'none',
                    maxHeight: '100px'
                  }}
                />
                <button
                  className="chat-send-btn"
                  onClick={() => handleSend()}
                  disabled={!inputQuery.trim() || loading || !selectedDoc}
                  style={{
                    background: '#4f46e5',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '8px',
                    width: '36px',
                    height: '36px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: (!inputQuery.trim() || loading || !selectedDoc) ? 'not-allowed' : 'pointer',
                    opacity: (!inputQuery.trim() || loading || !selectedDoc) ? 0.4 : 1,
                    flexShrink: 0
                  }}
                >
                  <Send size={16} />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Analytics;
