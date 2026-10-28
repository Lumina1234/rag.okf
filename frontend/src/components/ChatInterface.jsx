import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, Trash2, Sparkles, MessageSquare, Bot, ChevronDown, 
  Search, Paperclip, Pin, Clock, Globe, Plus, Moon, Sun, BarChart3 
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { chatAPI, streamChat, documentAPI, systemAPI, analyticsAPI } from '../lib/api';
import MessageBubble from './MessageBubble';

const ChatInterface = () => {
  const { activeWorkspace } = useAuth();

  // Sessions: array of { id, title, messages: [] }
  const [sessions, setSessions] = useState([
    { id: 1, title: 'New Conversation', messages: [] }
  ]);
  const [activeSessionId, setActiveSessionId] = useState(1);

  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [availableModels, setAvailableModels] = useState(['gemma4:12b', 'qwen3:4b', 'tinyllama:latest']);
  const [selectedModel, setSelectedModel] = useState('gemma4:12b');
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [historyTab, setHistoryTab] = useState('all'); // 'all' | 'pinned' | 'recent'
  const [isSearchingChat, setIsSearchingChat] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [pinnedSessions, setPinnedSessions] = useState(new Set());
  const [lastQuestion, setLastQuestion] = useState('');
  const [datasets, setDatasets] = useState([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState('');

  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  // Active session messages
  const activeSession = sessions.find(s => s.id === activeSessionId) || sessions[0];
  const messages = activeSession ? activeSession.messages : [];

  useEffect(() => {
    if (activeWorkspace) {
      loadHistory();
      documentAPI.list(activeWorkspace.id).then(res => {
        const readyDataDocs = (res.data || []).filter(d => 
          ['xlsx', 'xls', 'csv'].includes((d.file_type || '').toLowerCase()) && d.status === 'ready'
        );
        setDatasets(readyDataDocs);
      }).catch(() => {});
    }
  }, [activeWorkspace?.id]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  // Load models from backend
  useEffect(() => {
    systemAPI.models().then(res => {
      if (res.data && res.data.length > 0) {
        setAvailableModels(res.data);
      }
    }).catch(() => {});
  }, []);

  const loadHistory = async () => {
    try {
      const res = await chatAPI.history(activeWorkspace.id, 500, 'workspace');
      if (res.data && res.data.length > 0) {
        // Group messages into conversation sessions by time gap (> 30 mins)
        const grouped = [];
        let cur = null;
        for (const msg of res.data) {
          const msgDt = msg.created_at ? new Date(msg.created_at).getTime() : 0;
          const shouldStartNew = !cur || (msgDt && cur.lastTime && (msgDt - cur.lastTime > 30 * 60 * 1000));
          if (shouldStartNew) {
            const title = msg.role === 'user' ? (msg.content.slice(0, 36).trim() || 'Conversation') : 'Conversation';
            cur = {
              id: msg.id || Date.now(),
              title: title,
              messages: [msg],
              lastTime: msgDt,
              createdAt: msg.created_at,
            };
            grouped.push(cur);
          } else {
            if (cur.title === 'Conversation' && msg.role === 'user') {
              cur.title = msg.content.slice(0, 36).trim() || 'Conversation';
            }
            cur.messages.push(msg);
            if (msgDt) cur.lastTime = msgDt;
          }
        }
        // Most recent conversation first in the sidebar
        const reversedSessions = [...grouped].reverse();
        setSessions(reversedSessions);
        setActiveSessionId(prev => {
          const exists = reversedSessions.some(s => s.id === prev);
          return exists ? prev : reversedSessions[0].id;
        });
      } else {
        setSessions([{ id: Date.now(), title: 'New Conversation', messages: [] }]);
      }
    } catch (err) {
      console.error('Failed to load chat history:', err);
    }
  };

  const handleClearHistory = async () => {
    if (!activeWorkspace) return;
    try {
      await chatAPI.clear(activeWorkspace.id, 'workspace');
      setSessions([{ id: Date.now(), title: 'New Conversation', messages: [] }]);
    } catch (err) {
      console.error('Failed to clear history:', err);
    }
  };

  // Start a fresh, clean chat session
  const handleNewChat = () => {
    const newSession = {
      id: Date.now(),
      title: 'New Conversation',
      messages: []
    };
    setSessions(prev => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
    setInput('');
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !activeWorkspace) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('workspace_id', activeWorkspace.id);

    try {
      await documentAPI.upload(formData);
      alert(`Uploaded ${file.name} successfully to ${activeWorkspace.name}!`);
    } catch (err) {
      alert(`Upload failed: ${err.response?.data?.detail || err.message}`);
    }
  };

  const stripEchoedContext = (text) => {
    if (!text) return '';
    let cleaned = text.replace(/^\s*\{"type":\s*"sources"[\s\S]*?\}\s*/i, '');
    cleaned = cleaned.replace(/^\s*\{"type":\s*"trace"[\s\S]*?\}\s*/i, '');
    cleaned = cleaned.replace(/^(CONTEXT FROM DOCUMENTS:[\s\S]*?QUESTION:\s*[^\n]*\n*)/i, '');
    cleaned = cleaned.replace(/^Document content:[\s\S]*?Question:\s*[^\n]*\n*/i, '');
    cleaned = cleaned.replace(/^\s*Question:\s*[\s\S]*?\b(Direct answer|Answer):\s*/i, '');
    cleaned = cleaned.replace(/^\s*(Direct answer|Answer):\s*/i, '');
    cleaned = cleaned.replace(/^QUESTION:\s*[^\n]*\n*/i, '');
    cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
    return cleaned.trimStart();
  };

  const updateActiveSessionMessages = (updater) => {
    setSessions(prev => prev.map(s => {
      if (s.id === activeSessionId) {
        const nextMsgs = typeof updater === 'function' ? updater(s.messages) : updater;
        // Auto-title session after the first user question
        let newTitle = s.title;
        if (s.title === 'New Conversation' && nextMsgs.length > 0) {
          const firstUser = nextMsgs.find(m => m.role === 'user');
          if (firstUser) newTitle = firstUser.content.slice(0, 32);
        }
        return { ...s, title: newTitle, messages: nextMsgs };
      }
      return s;
    }));
  };

  const handleSend = async (questionText = input) => {
    if (!questionText.trim() || !activeWorkspace || isStreaming) return;

    setLastQuestion(questionText);
    const userMessage = { role: 'user', content: questionText };
    updateActiveSessionMessages(prev => [...prev, userMessage, { role: 'assistant', content: '', sources: [], traces: [] }]);
    setInput('');
    setIsStreaming(true);

    // If a dataset is explicitly selected or query asks for analytics/charts with an available dataset
    const isAnalyticsIntent = Boolean(
      selectedDatasetId || 
      (datasets.length > 0 && /(chart|pie|bar|trend|plot|sales|revenue|profit|margin|outlier|breakdown|kpi)/i.test(questionText))
    );

    if (isAnalyticsIntent && datasets.length > 0) {
      const targetDocId = parseInt(selectedDatasetId || datasets[0].id, 10);
      try {
        const res = await analyticsAPI.query({
          query: questionText,
          document_id: targetDocId,
          workspace_id: activeWorkspace.id,
        });
        const matchedDoc = datasets.find(d => d.id === targetDocId);
        
        // Predict word-by-word into workspace chat
        const fullAnswer = res.data.answer || '';
        const words = fullAnswer.split(/(\s+)/);
        let accumulated = '';
        let wordIdx = 0;

        await new Promise((resolve) => {
          const timer = setInterval(() => {
            if (wordIdx < words.length) {
              accumulated += words[wordIdx];
              wordIdx++;
              updateActiveSessionMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: 'assistant',
                  content: accumulated,
                  chart: null,
                  raw_data: null,
                  sources: [{ document_name: matchedDoc?.original_filename || 'Dataset', score: 1.0 }],
                  traces: [{ step: 'analytics', message: 'Predicting data insights word-by-word...' }],
                  isStreaming: true,
                };
                return updated;
              });
            } else {
              clearInterval(timer);
              updateActiveSessionMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: 'assistant',
                  content: fullAnswer,
                  chart: res.data.chart,
                  raw_data: res.data.raw_data,
                  sources: [{ document_name: matchedDoc?.original_filename || 'Dataset', score: 1.0 }],
                  traces: [{ step: 'analytics', message: 'Deterministic analytics & chart generation complete' }],
                  isStreaming: false,
                };
                return updated;
              });
              resolve();
            }
          }, 22);
        });
      } catch (err) {
        console.error('Workspace chat analytics error:', err);
        updateActiveSessionMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: 'assistant',
            content: `⚠️ Analytics Error: ${err.response?.data?.detail || err.message}`,
            sources: [],
            traces: [],
          };
          return updated;
        });
      } finally {
        setIsStreaming(false);
      }
      return;
    }

    let currentSources = [];
    let currentTraces = [];
    let assistantText = '';

    await streamChat({
      question: questionText,
      workspaceId: activeWorkspace.id,
      model: selectedModel,
      onSources: (sources) => {
        currentSources = sources;
        updateActiveSessionMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            sources: currentSources,
            traces: currentTraces,
          };
          return updated;
        });
      },
      onTrace: (trace) => {
        const nextTraces = [...currentTraces.filter((item) => item.step !== trace.step), trace];
        currentTraces = nextTraces;
        updateActiveSessionMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            traces: currentTraces,
            sources: currentSources,
          };
          return updated;
        });
      },
      onToken: (token) => {
        assistantText += token;
        const cleaned = stripEchoedContext(assistantText);
        updateActiveSessionMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: 'assistant',
            content: cleaned,
            sources: currentSources,
            traces: currentTraces,
          };
          return updated;
        });
      },
      onDone: () => {
        setIsStreaming(false);
      },
      onError: (err) => {
        console.error('Streaming error:', err);
        updateActiveSessionMessages(prev => [
          ...prev.slice(0, -1),
          { role: 'assistant', content: `⚠️ Error generating answer: ${err}` }
        ]);
        setIsStreaming(false);
      }
    });
  };

  const handleRegenerate = () => {
    if (lastQuestion) {
      handleSend(lastQuestion);
    }
  };

  const togglePin = (sessionId) => {
    setPinnedSessions(prev => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  };

  const filteredSessions = sessions.filter(s => {
    const q = searchQuery.toLowerCase().trim();
    const matchesSearch = !q || s.title.toLowerCase().includes(q) || s.messages.some(m => (m.content || '').toLowerCase().includes(q));
    if (historyTab === 'pinned') return matchesSearch && pinnedSessions.has(s.id);
    return matchesSearch;
  });

  const suggestedPrompts = [
    'Compare Wi-Fi vs Bluetooth',
    'Advantages of 5G',
    'What is a Mesh Network?',
    'Applications of ZigBee',
    'Summarize this document',
    'Explain key concepts'
  ];

  return (
    <div className="chat-layout" style={{ display: 'flex', height: '100%', width: '100%', background: isDarkMode ? '#0a0a0f' : '#f8fafc' }}>
      <input 
        type="file" 
        ref={fileInputRef} 
        style={{ display: 'none' }} 
        onChange={handleFileUpload} 
      />

      {/* Middle Column: Conversation History */}
      <div className="conv-history-panel" style={{
        width: '320px', 
        borderRight: '1px solid rgba(255,255,255,0.05)', 
        backgroundColor: '#0a0a0f', 
        display: 'flex', 
        flexDirection: 'column'
      }}>
        <div style={{ padding: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
          <h2 style={{ fontSize: '16px', fontWeight: '600', color: '#e2e8f0', margin: 0 }}>Workspace History</h2>
          <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>Document Q&A & RAG Chats</div>
        </div>
          <button 
            onClick={handleNewChat}
            title="New Chat"
            style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: '#94a3b8', padding: '6px', cursor: 'pointer' }}
          >
            <Plus size={16} />
          </button>
        </div>
        
        <div style={{ padding: '0 20px 16px' }}>
          <button 
            onClick={handleNewChat}
            style={{ width: '100%', padding: '12px', background: '#4f46e5', color: '#fff', borderRadius: '8px', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', fontWeight: '600', cursor: 'pointer' }}
          >
            <Plus size={18} /> New Chat
          </button>
        </div>

        <div style={{ padding: '0 20px 16px' }}>
          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: '12px', top: '12px', color: '#64748b' }} />
            <input 
              type="text" 
              placeholder="Search conversations..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ width: '100%', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px', padding: '10px 10px 10px 36px', color: '#e2e8f0', fontSize: '13px', outline: 'none' }}
            />
          </div>
        </div>

        <div style={{ padding: '0 20px', display: 'flex', gap: '8px', marginBottom: '20px' }}>
          <button 
            onClick={() => setHistoryTab('all')}
            style={{ flex: 1, background: historyTab === 'all' ? '#4f46e5' : 'rgba(255,255,255,0.03)', color: historyTab === 'all' ? '#fff' : '#94a3b8', border: 'none', padding: '6px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer' }}
          >
            All
          </button>
          <button 
            onClick={() => setHistoryTab('pinned')}
            style={{ flex: 1, background: historyTab === 'pinned' ? '#4f46e5' : 'rgba(255,255,255,0.03)', color: historyTab === 'pinned' ? '#fff' : '#94a3b8', border: 'none', padding: '6px', borderRadius: '6px', fontSize: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', cursor: 'pointer' }}
          >
            <Pin size={12} /> Pinned
          </button>
          <button 
            onClick={() => setHistoryTab('recent')}
            style={{ flex: 1, background: historyTab === 'recent' ? '#4f46e5' : 'rgba(255,255,255,0.03)', color: historyTab === 'recent' ? '#fff' : '#94a3b8', border: 'none', padding: '6px', borderRadius: '6px', fontSize: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', cursor: 'pointer' }}
          >
            <Clock size={12} /> Recent
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px' }}>
          <div style={{ marginBottom: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0 8px', marginBottom: '8px', color: '#cbd5e1', fontSize: '12px', fontWeight: '600' }}>
              <span>Workspace Chats</span>
              <span style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px', fontSize: '10px' }}>{filteredSessions.length}</span>
            </div>
            
            {filteredSessions.length === 0 ? (
              <div style={{ padding: '16px', textAlign: 'center', color: '#64748b', fontSize: '12px' }}>
                No conversations found
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
                      padding: '12px', 
                      background: isActive ? 'rgba(79,70,229,0.15)' : 'rgba(255,255,255,0.02)', 
                      border: isActive ? '1px solid rgba(79,70,229,0.4)' : '1px solid rgba(255,255,255,0.05)', 
                      borderRadius: '8px', 
                      display: 'flex', 
                      gap: '12px', 
                      alignItems: 'flex-start', 
                      cursor: 'pointer', 
                      marginBottom: '6px' 
                    }}
                  >
                    <MessageSquare size={16} style={{ color: isActive ? '#818cf8' : '#94a3b8', marginTop: '2px', flexShrink: 0 }} />
                    <div style={{ flex: 1, overflow: 'hidden' }}>
                      <div style={{ color: isActive ? '#fff' : '#e2e8f0', fontSize: '13px', fontWeight: isActive ? '600' : '500', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                        {session.title}
                      </div>
                      <div style={{ color: '#64748b', fontSize: '11px', marginTop: '4px' }}>
                        {session.messages.length} message{session.messages.length !== 1 ? 's' : ''}
                      </div>
                    </div>
                    <button 
                      onClick={(e) => { e.stopPropagation(); togglePin(session.id); }}
                      style={{ background: 'none', border: 'none', color: isPinned ? '#f59e0b' : '#475569', cursor: 'pointer', padding: 0 }}
                    >
                      <Pin size={14} fill={isPinned ? '#f59e0b' : 'none'} />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Right Column: Main Chat Area */}
      <div className="chat-shell" style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', background: '#0f0f16' }}>
        {/* Top Header */}
        <div className="topbar" style={{ padding: '16px 24px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="topbar-title flex items-center gap-8">
            <Sparkles size={18} className="text-accent" />
            <span style={{ fontSize: '18px', fontWeight: '600', color: '#fff' }}>{activeWorkspace?.name || 'General Workspace'}</span>
            <span className="tag" style={{ background: 'rgba(79,70,229,0.15)', color: '#818cf8', border: 'none', padding: '4px 10px', borderRadius: '12px' }}>{activeWorkspace?.workspace_type || 'Business'}</span>
          </div>

          <div className="topbar-actions" style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            {isSearchingChat && (
              <input 
                type="text" 
                placeholder="Find in chat..."
                onChange={(e) => {
                  const term = e.target.value.toLowerCase();
                  if (!term) return;
                  const el = document.querySelector(`.assistant-markdown-content`);
                  el?.scrollIntoView({ behavior: 'smooth' });
                }}
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', padding: '4px 8px', color: '#fff', fontSize: '12px' }}
              />
            )}
            {datasets.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <BarChart3 size={15} color="#818cf8" />
                <select
                  value={selectedDatasetId}
                  onChange={(e) => setSelectedDatasetId(e.target.value)}
                  style={{
                    fontSize: '12px',
                    padding: '5px 10px',
                    background: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(99, 102, 241, 0.4)',
                    color: '#e2e8f0',
                    borderRadius: '6px',
                    maxWidth: '180px'
                  }}
                  title="Select spreadsheet dataset for business analytics"
                >
                  <option value="" style={{ background: '#0f172a' }}>📚 All Documents</option>
                  {datasets.map(d => (
                    <option key={d.id} value={d.id} style={{ background: '#0f172a' }}>
                      📊 {d.original_filename}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <button 
              onClick={() => setIsSearchingChat(v => !v)}
              title="Search chat"
              style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
            >
              <Search size={18} />
            </button>
            <button 
              onClick={() => setIsDarkMode(v => !v)}
              title="Toggle theme"
              style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
            >
              {isDarkMode ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button 
              className="btn btn-ghost btn-sm" 
              onClick={handleClearHistory} 
              title="Clear Chat History" 
              style={{ display: 'flex', alignItems: 'center', gap: '6px', border: '1px solid rgba(255,255,255,0.1)', padding: '6px 12px', borderRadius: '6px', color: '#94a3b8', cursor: 'pointer' }}
            >
              <Trash2 size={14} /> Clear Chat
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="chat-messages" style={{ flex: 1, overflowY: 'auto', padding: '24px 40px' }}>
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">🤖</div>
              <h3>Ask anything about your documents</h3>
              <p>100% local RAG vector search & AI reasoning via Ollama</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <MessageBubble 
                key={idx} 
                role={msg.role} 
                content={msg.content} 
                sources={msg.sources} 
                chart={msg.chart}
                raw_data={msg.raw_data}
                onRegenerate={handleRegenerate}
              />
            ))
          )}

          {isStreaming && messages.length > 0 && messages[messages.length - 1].role === 'user' && (
            <div className="message-row assistant">
              <div className="avatar assistant">🤖</div>
              <div className="message-bubble assistant">
                <div className="typing-dots">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Suggested Prompts */}
        <div style={{ padding: '0 40px', marginBottom: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ color: '#818cf8', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: '600' }}>
            <Sparkles size={14} /> Suggested prompts:
          </span>
        </div>
        <div style={{ padding: '0 40px', marginBottom: '20px', display: 'flex', gap: '8px', overflowX: 'auto' }}>
          {suggestedPrompts.map((prompt, idx) => (
            <button 
              key={idx} 
              onClick={() => handleSend(prompt)}
              style={{ background: 'rgba(79,70,229,0.1)', color: '#818cf8', border: '1px solid rgba(79,70,229,0.2)', padding: '8px 16px', borderRadius: '20px', fontSize: '12px', whiteSpace: 'nowrap', cursor: 'pointer' }}
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Input area */}
        <div className="chat-input-area" style={{ padding: '0 40px 32px' }}>
          <div style={{ 
            background: 'rgba(15,15,26,0.95)', 
            border: '1px solid rgba(79,70,229,0.3)', 
            borderRadius: '16px', 
            padding: '16px',
            position: 'relative'
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
              <button 
                onClick={() => fileInputRef.current?.click()}
                title="Attach Document"
                style={{ background: 'none', border: 'none', color: '#94a3b8', padding: '4px', cursor: 'pointer' }}
              >
                <Paperclip size={20} />
              </button>
              <textarea
                style={{
                  width: '100%', background: 'transparent', border: 'none', color: '#e2e8f0', fontSize: '14px', resize: 'none', outline: 'none', padding: '4px 0'
                }}
                placeholder={activeWorkspace ? `Ask a question about documents in ${activeWorkspace.name}...` : "Select a workspace..."}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                rows={1}
                disabled={!activeWorkspace || isStreaming}
              />
              <button 
                onClick={() => handleSend()}
                disabled={!input.trim() || isStreaming || !activeWorkspace}
                style={{ 
                  background: '#6366f1', color: '#fff', border: 'none', borderRadius: '12px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
                  opacity: (!input.trim() || isStreaming || !activeWorkspace) ? 0.5 : 1
                }}
              >
                <Send size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px', paddingTop: '12px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', position: 'relative' }}>
                {/* Model Selector Dropdown */}
                <div style={{ position: 'relative' }}>
                  <button 
                    onClick={() => setShowModelDropdown(v => !v)}
                    style={{ background: 'none', border: 'none', color: '#cbd5e1', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
                  >
                    <Bot size={14} /> {selectedModel} <ChevronDown size={14} />
                  </button>
                  {showModelDropdown && (
                    <div style={{ position: 'absolute', bottom: '28px', left: 0, background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '6px', minWidth: '160px', zIndex: 100 }}>
                      {availableModels.map(m => (
                        <div 
                          key={m} 
                          onClick={() => { setSelectedModel(m); setShowModelDropdown(false); }}
                          style={{ padding: '8px 12px', color: selectedModel === m ? '#818cf8' : '#e2e8f0', fontSize: '12px', cursor: 'pointer', borderRadius: '4px', background: selectedModel === m ? 'rgba(129,140,248,0.1)' : 'transparent' }}
                        >
                          {m}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Web Search Toggle */}
                <div 
                  onClick={() => setWebSearchEnabled(v => !v)}
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', color: webSearchEnabled ? '#818cf8' : '#94a3b8', fontSize: '13px', cursor: 'pointer' }}
                >
                  <div style={{ width: '32px', height: '18px', background: webSearchEnabled ? '#6366f1' : 'rgba(255,255,255,0.1)', borderRadius: '10px', position: 'relative', transition: 'background 0.2s' }}>
                    <div style={{ width: '14px', height: '14px', background: '#fff', borderRadius: '50%', position: 'absolute', top: '2px', left: webSearchEnabled ? '16px' : '2px', transition: 'left 0.2s' }}></div>
                  </div>
                  <Globe size={14} /> Web Search
                </div>
              </div>
              <div style={{ color: '#475569', fontSize: '11px' }}>Press Enter to send</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
