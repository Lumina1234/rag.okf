import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { documentAPI } from '../lib/api';
import { streamSummarize } from '../lib/summarizeAPI';
import { FileText, Tv2, Globe, AlignLeft, Loader, Copy, Check, ChevronDown } from 'lucide-react';

const SOURCE_MODES = [
  { id: 'text',     label: 'Paste Text',    icon: <AlignLeft size={15} /> },
  { id: 'url',      label: 'Article URL',   icon: <Globe size={15} /> },
  { id: 'youtube',  label: 'YouTube URL',   icon: <Tv2 size={15} /> },
  { id: 'document', label: 'My Document',   icon: <FileText size={15} /> },
];

const SUMMARY_TYPES = [
  { id: 'quick',     label: '⚡ Quick'         },
  { id: 'detailed',  label: '📖 Detailed'      },
  { id: 'simple',    label: '🧒 Simple'         },
  { id: 'study',     label: '📚 Study Notes'   },
  { id: 'executive', label: '💼 Executive'     },
  { id: 'keypoints', label: '🔑 Key Points'    },
];

const SOURCE_BADGE = {
  youtube:  { label: '🎬 YouTube',  color: '#ff4444' },
  url:      { label: '🌐 Article',  color: '#4488ff' },
  document: { label: '📄 Document', color: '#44cc88' },
  text:     { label: '📝 Text',     color: '#aa88ff' },
};

export default function Summarize() {
  const { activeWorkspace } = useAuth();

  const [sourceMode, setSourceMode]     = useState('text');
  const [summaryType, setSummaryType]   = useState('quick');
  const [inputText, setInputText]       = useState('');
  const [inputUrl, setInputUrl]         = useState('');
  const [docId, setDocId]               = useState('');
  const [docs, setDocs]                 = useState([]);
  const [docsLoading, setDocsLoading]   = useState(false);

  const [isStreaming, setIsStreaming]   = useState(false);
  const [output, setOutput]             = useState('');
  const [sources, setSources]           = useState([]);
  const [statusMsg, setStatusMsg]       = useState('');
  const [error, setError]               = useState('');
  const [copied, setCopied]             = useState(false);

  const outputRef = useRef(null);

  // Load documents when switching to document mode
  useEffect(() => {
    if (sourceMode === 'document' && activeWorkspace) {
      setDocsLoading(true);
      documentAPI.list(activeWorkspace.id)
        .then(res => setDocs(res.data || []))
        .catch(() => setDocs([]))
        .finally(() => setDocsLoading(false));
    }
  }, [sourceMode, activeWorkspace]);

  // Auto-scroll output
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [output, statusMsg]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setOutput('');
    setSources([]);
    setStatusMsg('');
    setIsStreaming(true);

    let statusBuffer = '';
    let outputBuffer = '';

    const isStatusLine = (t) =>
      t.startsWith('*') && t.endsWith('*') && t.includes('...');

    await streamSummarize({
      inputType: sourceMode === 'text' ? 'text'
               : sourceMode === 'url' && inputUrl.includes('youtu') ? 'youtube'
               : sourceMode,
      content:    sourceMode === 'text' ? inputText : null,
      url:        (sourceMode === 'url' || sourceMode === 'youtube') ? inputUrl : null,
      documentId: sourceMode === 'document' ? parseInt(docId) : null,
      workspaceId: activeWorkspace?.id,
      summaryType,

      onSources: (data) => setSources(data || []),

      onToken: (token) => {
        if (isStatusLine(token.trim())) {
          setStatusMsg(token.trim().replace(/\*/g, ''));
        } else {
          outputBuffer += token;
          setOutput(outputBuffer);
          setStatusMsg('');
        }
      },

      onDone: () => {
        setIsStreaming(false);
        setStatusMsg('');
      },

      onError: (msg) => {
        setError(msg);
        setIsStreaming(false);
        setStatusMsg('');
      },
    });
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(output).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const canSubmit = !isStreaming && (
    (sourceMode === 'text' && inputText.trim().length > 10) ||
    ((sourceMode === 'url' || sourceMode === 'youtube') && inputUrl.trim().length > 5) ||
    (sourceMode === 'document' && docId)
  );

  return (
    <div style={{ padding: '24px', maxWidth: '900px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
          📝 Universal Summarizer
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
          Summarize YouTube videos, web articles, documents, or pasted text.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        {/* Source Mode Tabs */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
          {SOURCE_MODES.map(m => (
            <button
              key={m.id}
              type="button"
              onClick={() => { setSourceMode(m.id); setError(''); }}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '7px 14px', borderRadius: '8px', fontSize: '13px',
                fontWeight: 500, cursor: 'pointer', border: '1px solid',
                background: sourceMode === m.id ? 'var(--accent)' : 'var(--surface)',
                borderColor: sourceMode === m.id ? 'var(--accent)' : 'var(--border)',
                color: sourceMode === m.id ? '#fff' : 'var(--text-secondary)',
                transition: 'all 0.15s',
              }}
            >
              {m.icon} {m.label}
            </button>
          ))}
        </div>

        {/* Input area */}
        <div className="card" style={{ padding: '16px', marginBottom: '14px' }}>
          {sourceMode === 'text' && (
            <>
              <label className="input-label">Paste your text here</label>
              <textarea
                className="input"
                placeholder="Paste the article, notes, or any text you want summarized..."
                value={inputText}
                onChange={e => setInputText(e.target.value)}
                rows={7}
                style={{ resize: 'vertical', fontFamily: 'inherit' }}
              />
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {inputText.length} characters
              </div>
            </>
          )}

          {(sourceMode === 'url' || sourceMode === 'youtube') && (
            <>
              <label className="input-label">
                {sourceMode === 'youtube' ? '🎬 YouTube video URL' : '🌐 Web article URL'}
              </label>
              <input
                type="url"
                className="input"
                placeholder={
                  sourceMode === 'youtube'
                    ? 'https://www.youtube.com/watch?v=...'
                    : 'https://example.com/article'
                }
                value={inputUrl}
                onChange={e => setInputUrl(e.target.value)}
              />
              {sourceMode === 'youtube' && (
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px' }}>
                  ℹ️ Works with videos that have captions/transcripts enabled.
                </p>
              )}
            </>
          )}

          {sourceMode === 'document' && (
            <>
              <label className="input-label">Select a document from your workspace</label>
              {docsLoading ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Loading documents...</div>
              ) : docs.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
                  No documents found. Upload a PDF from the Documents page first.
                </div>
              ) : (
                <select
                  className="input"
                  value={docId}
                  onChange={e => setDocId(e.target.value)}
                >
                  <option value="">-- Select a document --</option>
                  {docs.map(d => (
                    <option key={d.id} value={d.id}>
                      {d.original_filename} ({(d.file_size / 1024).toFixed(0)} KB)
                    </option>
                  ))}
                </select>
              )}
            </>
          )}
        </div>

        {/* Summary type selector */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
          {SUMMARY_TYPES.map(t => (
            <button
              key={t.id}
              type="button"
              onClick={() => setSummaryType(t.id)}
              style={{
                padding: '6px 13px', borderRadius: '20px', fontSize: '12px',
                fontWeight: 500, cursor: 'pointer', border: '1px solid',
                background: summaryType === t.id ? 'var(--accent-dim)' : 'transparent',
                borderColor: summaryType === t.id ? 'var(--accent)' : 'var(--border)',
                color: summaryType === t.id ? 'var(--accent)' : 'var(--text-muted)',
                transition: 'all 0.15s',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="card mb-16" style={{
            background: 'var(--danger-dim)', borderColor: 'var(--danger)',
            color: 'var(--danger)', fontSize: '13px', padding: '10px 14px',
          }}>
            ⚠️ {error}
          </div>
        )}

        <button
          type="submit"
          disabled={!canSubmit}
          className="btn btn-primary"
          style={{ width: '100%', marginBottom: '20px', padding: '12px', fontSize: '14px' }}
        >
          {isStreaming
            ? <><Loader size={15} className="spin" style={{ marginRight: '8px' }} /> Summarizing...</>
            : '✨ Generate Summary'
          }
        </button>
      </form>

      {/* Status message */}
      {statusMsg && (
        <div style={{
          fontSize: '13px', color: 'var(--text-muted)', fontStyle: 'italic',
          marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px',
        }}>
          <Loader size={13} className="spin" /> {statusMsg}
        </div>
      )}

      {/* Sources badges */}
      {sources.length > 0 && (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
          {sources.map((s, i) => {
            const st = s.source_type || 'text';
            const badge = SOURCE_BADGE[st] || SOURCE_BADGE.text;
            return (
              <span key={i} style={{
                padding: '4px 10px', borderRadius: '12px', fontSize: '11px',
                fontWeight: 600, background: badge.color + '22', color: badge.color,
                border: `1px solid ${badge.color}44`,
              }}>
                {badge.label}: {s.document_name}
              </span>
            );
          })}
        </div>
      )}

      {/* Output area */}
      {(output || isStreaming) && (
        <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 16px', borderBottom: '1px solid var(--border)',
            background: 'var(--surface-alt)',
          }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)' }}>
              Summary
            </span>
            {output && (
              <button
                onClick={handleCopy}
                style={{
                  display: 'flex', alignItems: 'center', gap: '5px',
                  fontSize: '12px', color: 'var(--text-muted)', background: 'none',
                  border: 'none', cursor: 'pointer', padding: '4px 8px',
                  borderRadius: '6px',
                }}
              >
                {copied ? <><Check size={13} /> Copied!</> : <><Copy size={13} /> Copy</>}
              </button>
            )}
          </div>
          <div
            ref={outputRef}
            style={{
              padding: '20px',
              maxHeight: '60vh',
              overflowY: 'auto',
              whiteSpace: 'pre-wrap',
              fontSize: '14px',
              lineHeight: '1.7',
              color: 'var(--text-primary)',
              fontFamily: 'inherit',
            }}
          >
            {output}
            {isStreaming && (
              <span style={{
                display: 'inline-block', width: '2px', height: '14px',
                background: 'var(--accent)', marginLeft: '2px',
                animation: 'blink 1s infinite',
                verticalAlign: 'middle',
              }} />
            )}
          </div>
        </div>
      )}

      <style>{`
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      `}</style>
    </div>
  );
}
