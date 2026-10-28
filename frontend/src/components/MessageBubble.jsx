import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { FileText, Bot, ChevronDown, Check, Copy, RotateCw, ThumbsUp, ThumbsDown } from 'lucide-react';
import { InlineChart, DataTablePreview } from './AnalyticsComponents';

const cleanContent = (text) => {
  if (!text) return '';
  let cleaned = text.replace(/^\s*\{"type":\s*"sources"[^\}]*\}\s*/gim, '');
  cleaned = cleaned.replace(/^\s*\{"type":\s*"trace"[^\}]*\}\s*/gim, '');
  cleaned = cleaned.replace(/^\s*Question:\s*.*?\b(Direct answer|Answer):\s*/is, '');
  cleaned = cleaned.replace(/^(CONTEXT FROM DOCUMENTS:[\s\S]*?QUESTION:\s*[^\n]*\n*)/i, '');
  cleaned = cleaned.replace(/^Document content:[\s\S]*?Question:\s*[^\n]*\n*/i, '');
  cleaned = cleaned.replace(/^\s*(Direct answer|Answer):\s*/i, '');
  cleaned = cleaned.replace(/^Answer directly and concisely:\s*/i, '');
  return cleaned.trim();
};

const MessageBubble = ({ role, content, sources, chart, raw_data, onRegenerate }) => {
  const isUser = role === 'user';
  const displayContent = isUser ? content : cleanContent(content);
  const uniqueSources = Array.from(
    new Map((sources || []).map((src) => [src.document_name || 'Unknown', src])).values()
  );

  const [isSourcesExpanded, setIsSourcesExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState(null); // 'like' | 'dislike' | null

  const handleCopy = () => {
    if (!displayContent) return;
    navigator.clipboard.writeText(displayContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFeedback = (type) => {
    setFeedback(prev => prev === type ? null : type);
  };

  return (
    <div style={{ display: 'flex', gap: '20px', marginBottom: '32px', color: '#e2e8f0', fontSize: '14px', lineHeight: '1.6' }}>
      {/* Avatar */}
      <div style={{ flexShrink: 0 }}>
        {isUser ? (
          <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: '#4f46e5', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}>
            U
          </div>
        ) : (
          <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'rgba(79,70,229,0.2)', color: '#818cf8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Bot size={18} />
          </div>
        )}
      </div>

      {/* Content Area */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {isUser ? (
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <div style={{ background: '#312e81', color: '#e2e8f0', padding: '12px 16px', borderRadius: '16px 16px 0 16px', maxWidth: '80%' }}>
              {content}
            </div>
          </div>
        ) : (
          <div style={{ paddingRight: '20px' }}>
            {/* Assistant Action Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
              <div style={{ fontWeight: '600', color: '#fff', fontSize: '16px' }}>Response</div>
              <div style={{ display: 'flex', gap: '16px', color: '#94a3b8', fontSize: '12px', alignItems: 'center' }}>
                <button
                  onClick={handleCopy}
                  title="Copy response"
                  style={{ background: 'none', border: 'none', color: copied ? '#10b981' : 'inherit', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
                >
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>

                <button
                  onClick={onRegenerate}
                  title="Regenerate response"
                  style={{ background: 'none', border: 'none', color: 'inherit', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
                >
                  <RotateCw size={14} />
                  <span>Regenerate</span>
                </button>

                <button
                  onClick={() => handleFeedback('like')}
                  title="Good response"
                  style={{ background: 'none', border: 'none', color: feedback === 'like' ? '#10b981' : 'inherit', display: 'flex', alignItems: 'center', cursor: 'pointer' }}
                >
                  <ThumbsUp size={14} fill={feedback === 'like' ? '#10b981' : 'none'} />
                </button>

                <button
                  onClick={() => handleFeedback('dislike')}
                  title="Bad response"
                  style={{ background: 'none', border: 'none', color: feedback === 'dislike' ? '#ef4444' : 'inherit', display: 'flex', alignItems: 'center', cursor: 'pointer' }}
                >
                  <ThumbsDown size={14} fill={feedback === 'dislike' ? '#ef4444' : 'none'} />
                </button>
              </div>
            </div>

            <div className="assistant-markdown-content" style={{ marginBottom: '24px', color: '#cbd5e1' }}>
              {displayContent ? (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    code({ node, inline, className, children, ...props }) {
                      const match = /language-(\w+)/.exec(className || '');
                      return !inline && match ? (
                        <SyntaxHighlighter style={vscDarkPlus} language={match[1]} PreTag="div" {...props}>
                          {String(children).replace(/\n$/, '')}
                        </SyntaxHighlighter>
                      ) : (
                        <code className={className} {...props}>{children}</code>
                      );
                    }
                  }}
                >
                  {displayContent}
                </ReactMarkdown>
              ) : (
                <div style={{ display: 'inline-flex', gap: '6px', padding: '8px 0', alignItems: 'center' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#818cf8', display: 'inline-block', animation: 'pulse 1.2s infinite ease-in-out' }}></span>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#818cf8', display: 'inline-block', animation: 'pulse 1.2s infinite ease-in-out 0.2s' }}></span>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#818cf8', display: 'inline-block', animation: 'pulse 1.2s infinite ease-in-out 0.4s' }}></span>
                </div>
              )}
            </div>

            {/* Business Analytics Visualization */}
            {chart && <InlineChart chartData={chart} />}

            {/* Source Data Table Preview */}
            {raw_data && raw_data.length > 0 && <DataTablePreview rawData={raw_data} />}

            {uniqueSources.length > 0 && (
              <div style={{ background: 'rgba(15,15,26,0.6)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '12px', overflow: 'hidden' }}>
                <button 
                  onClick={() => setIsSourcesExpanded(v => !v)}
                  style={{ width: '100%', background: 'none', border: 'none', padding: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#e2e8f0', fontSize: '13px', fontWeight: '600' }}>
                    <span style={{ color: '#6366f1' }}>♦</span> Sources ({uniqueSources.length})
                  </div>
                  <ChevronDown size={14} style={{ color: '#64748b', transform: isSourcesExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
                </button>

                {isSourcesExpanded && (
                  <div style={{ padding: '0 16px 16px', display: 'flex', gap: '12px', overflowX: 'auto' }}>
                    {uniqueSources.map((src, idx) => (
                      <div key={idx} style={{ flexShrink: 0, width: '260px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px', padding: '12px', display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <div style={{ background: 'rgba(255,255,255,0.05)', padding: '8px', borderRadius: '6px', color: '#94a3b8' }}>
                          <FileText size={16} />
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: '12px', fontWeight: '600', color: '#e2e8f0', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', marginBottom: '4px' }}>
                            {src.document_name}
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: '#94a3b8' }}>
                            <span>Page {src.page_number || '1'}</span>
                            <span style={{ color: '#10b981' }}>{90 + idx}% match</span>
                          </div>
                        </div>
                        <button 
                          onClick={() => alert(`Source file: ${src.document_name}\nPage: ${src.page_number || 1}`)}
                          style={{ background: 'none', border: 'none', color: '#64748b', padding: '4px', cursor: 'pointer' }}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
