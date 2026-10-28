import React, { useState, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { UploadCloud, FileText, Trash2, CheckCircle2, AlertCircle, Loader2, Download } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { documentAPI } from '../lib/api';

const Documents = () => {
  const { activeWorkspace } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (activeWorkspace) {
      loadDocuments();
      // Auto-refresh every 2 seconds to update processing status
      const interval = setInterval(loadDocuments, 2000);
      return () => clearInterval(interval);
    }
  }, [activeWorkspace?.id]);

  const loadDocuments = async () => {
    try {
      const res = await documentAPI.list(activeWorkspace.id);
      setDocuments(res.data);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  };

  const onDrop = async (acceptedFiles) => {
    if (!acceptedFiles.length || !activeWorkspace) return;
    setUploading(true);
    setError(null);

    for (const file of acceptedFiles) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('workspace_id', activeWorkspace.id);

      try {
        await documentAPI.upload(formData);
        // Refresh after successful upload
        setTimeout(() => loadDocuments(), 1000);
      } catch (err) {
        const detailMsg = err.response?.data?.detail || err.message;
        setError(`Failed to upload ${file.name}: ${detailMsg}`);
        await loadDocuments();
      }
    }

    setUploading(false);
  };

  const handleDownload = async (doc) => {
    try {
      const res = await documentAPI.download(doc.id);
      const href = URL.createObjectURL(new Blob([res.data], {
        type: res.headers['content-type'] || 'application/octet-stream',
      }));
      const link = document.createElement('a');
      link.href = href;
      link.setAttribute('download', doc.original_filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
    } catch (err) {
      console.error('Failed to download document:', err);
      setError(err.response?.data?.detail || 'Failed to download document');
    }
  };

  const handleDelete = async (docId) => {
    if (!window.confirm('Delete this document and remove its embeddings from the vector database?')) return;
    try {
      await documentAPI.delete(docId);
      setDocuments(prev => prev.filter(d => d.id !== docId));
    } catch (err) {
      console.error('Failed to delete document:', err);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'text/plain': ['.txt', '.md']
    }
  });

  const getFileIcon = (fileType) => {
    switch (fileType) {
      case 'pdf': return '📕';
      case 'docx': case 'doc': return '📘';
      case 'xlsx': case 'xls': case 'csv': return '📊';
      case 'pptx': case 'ppt': return '📙';
      default: return '📄';
    }
  };

  return (
    <div className="page-area">
      <div className="page-header">
        <h1>Knowledge Base Documents</h1>
        <p>Upload files to process, chunk, and index into the local FAISS vector database for <strong>{activeWorkspace?.name || 'Workspace'}</strong></p>
      </div>

      {error && (
        <div className="card mb-16" style={{ borderColor: 'var(--danger)', background: 'var(--danger-dim)' }}>
          <div className="flex items-center gap-8 text-danger">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Drag and Drop Zone */}
      <div {...getRootProps()} className={`upload-zone ${isDragActive ? 'active' : ''}`}>
        <input {...getInputProps()} />
        {uploading ? (
          <div>
            <Loader2 size={48} className="animate-spin text-accent" style={{ margin: '0 auto 12px' }} />
            <div className="upload-title">Processing and indexing document...</div>
            <div className="upload-sub">Generating local BGE-M3 embeddings & building FAISS index</div>
          </div>
        ) : (
          <div>
            <UploadCloud size={48} className="upload-icon text-accent" style={{ margin: '0 auto 12px' }} />
            <div className="upload-title">
              {isDragActive ? 'Drop files here...' : 'Drag & drop files here, or click to browse'}
            </div>
            <div className="upload-sub">Supports PDF, Word (DOCX), Excel (XLSX, CSV), PowerPoint (PPTX), Text & Markdown</div>
            <div className="supported-formats">
              <span className="format-badge">.PDF</span>
              <span className="format-badge">.DOCX</span>
              <span className="format-badge">.XLSX</span>
              <span className="format-badge">.CSV</span>
              <span className="format-badge">.PPTX</span>
              <span className="format-badge">.TXT</span>
            </div>
          </div>
        )}
      </div>

      {/* Document List */}
      <div style={{ marginTop: '32px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>
          Indexed Files ({documents.length})
        </h2>

        {documents.length === 0 ? (
          <div className="empty-state">
            <FileText size={48} className="empty-icon" style={{ margin: '0 auto 12px' }} />
            <h3>No documents uploaded yet</h3>
            <p>Upload PDF notes, reports, invoices, or spreadsheets above to build your offline AI knowledge base.</p>
          </div>
        ) : (
          <div className="doc-list">
            {documents.map((doc) => (
              <div key={doc.id}>
                <div className="doc-item">
                  <div className="doc-icon">{getFileIcon(doc.file_type)}</div>
                  <div className="doc-info">
                    <div className="doc-name">{doc.original_filename}</div>
                    <div className="doc-meta">
                      <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
                      <span>•</span>
                      <span>{doc.chunk_count} FAISS Chunks</span>
                      <span>•</span>
                      <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-12">
                    <span className={`status-badge ${doc.status}`}>
                      {doc.status === 'ready' && <CheckCircle2 size={12} />}
                      {doc.status === 'processing' && <Loader2 size={12} className="animate-spin" />}
                      {doc.status === 'failed' && <AlertCircle size={12} />}
                      {doc.status.toUpperCase()}
                    </span>

                    <button 
                      className="btn btn-ghost btn-sm" 
                      onClick={() => handleDownload(doc)}
                      title="Download document"
                    >
                      <Download size={14} />
                    </button>

                    <button 
                      className="btn btn-ghost btn-sm text-danger" 
                      onClick={() => handleDelete(doc.id)}
                      title="Delete document"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                
                {/* Show error message if document failed */}
                {doc.status === 'failed' && doc.error_message && (
                  <div className="card" style={{ borderColor: 'var(--danger)', background: 'var(--danger-dim)', marginTop: '8px' }}>
                    <div className="flex items-start gap-8 text-danger" style={{ fontSize: '12px' }}>
                      <AlertCircle size={14} style={{ marginTop: '2px', flexShrink: 0 }} />
                      <span>{doc.error_message}</span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Documents;
