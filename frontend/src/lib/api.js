import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 300000,  // 5 minutes for large file uploads
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Handle 401 globally
api.interceptors.response.use(
  (res) => res,
  (err) => {
    // Only force logout/redirect if it's a 401 on an authenticated route (NOT the login endpoint)
    if (err.response?.status === 401 && !err.config.url.includes('/auth/login')) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authAPI = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
};

// ── Workspaces ────────────────────────────────────────────────────────────────
export const workspaceAPI = {
  list: () => api.get('/workspaces/'),
  create: (data) => api.post('/workspaces/', data),
  get: (id) => api.get(`/workspaces/${id}`),
  delete: (id) => api.delete(`/workspaces/${id}`),
};

// ── Documents ─────────────────────────────────────────────────────────────────
export const documentAPI = {
  list: (workspaceId) => api.get('/documents/', { params: { workspace_id: workspaceId } }),
  upload: (formData) => api.post('/documents/upload', formData),
  get: (id) => api.get(`/documents/${id}`),
  download: (id) => api.get(`/documents/${id}/download`, { responseType: 'blob' }),
  delete: (id) => api.delete(`/documents/${id}`),
};

// ── Chat (streaming) ──────────────────────────────────────────────────────────
export const chatAPI = {
  history: (workspaceId, limit = 500, chatType = 'workspace') =>
    api.get('/chat/history', { params: { workspace_id: workspaceId, limit, chat_type: chatType } }),
  clear: (workspaceId, chatType = 'workspace') =>
    api.post('/chat/clear', null, { params: { workspace_id: workspaceId, chat_type: chatType } }),
};

export async function streamChat({ question, workspaceId, model, onSources, onTrace, onToken, onDone, onError }) {
  const token = localStorage.getItem('token');
  let buffer = '';

  try {
    const response = await fetch('/api/chat/query', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: token ? `Bearer ${token}` : '',
      },
      body: JSON.stringify({ question, workspace_id: workspaceId, model, stream: true }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      onError?.(errData.detail || 'Server error: ' + response.status);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    const processBuffer = (isFinal = false) => {
      while (buffer.length > 0) {
        const trimmedLeading = buffer.trimStart();

        // 1. Check if buffer starts with a JSON event line
        if (trimmedLeading.startsWith('{"type"')) {
          const newlineIdx = buffer.indexOf('\n');
          if (newlineIdx !== -1) {
            const line = buffer.slice(0, newlineIdx).trim();
            buffer = buffer.slice(newlineIdx + 1);
            if (line) {
              try {
                const parsed = JSON.parse(line);
                if (parsed?.type === 'sources') {
                  onSources?.(parsed.data || []);
                  continue;
                }
                if (parsed?.type === 'trace') {
                  onTrace?.(parsed);
                  continue;
                }
              } catch (e) {
                // Not a valid JSON event line, fall through to emit as text
              }
              onToken?.(line + '\n');
            }
            continue;
          } else if (!isFinal) {
            // JSON line still incoming; wait for the newline delimiter
            break;
          } else {
            // isFinal is true - process trailing JSON event even without newline
            const line = buffer.trim();
            buffer = '';
            try {
              const parsed = JSON.parse(line);
              if (parsed?.type === 'sources') {
                onSources?.(parsed.data || []);
                continue;
              }
              if (parsed?.type === 'trace') {
                onTrace?.(parsed);
                continue;
              }
            } catch (e) {}
            continue;
          }
        }

        // 2. Buffer does not start with {"type". Check if {"type" appears inside buffer.
        const splitIdx = buffer.indexOf('{"type"');
        if (splitIdx > 0) {
          const textChunk = buffer.slice(0, splitIdx);
          buffer = buffer.slice(splitIdx);
          onToken?.(textChunk);
          continue;
        }

        // 3. If buffer ends with an incomplete prefix of '{"type"', hold it for next chunk
        if (!isFinal) {
          const partialMatch = buffer.match(/\n?\s*\{("type")?$/);
          if (partialMatch && partialMatch.index !== undefined && partialMatch.index < buffer.length) {
            const textBefore = buffer.slice(0, partialMatch.index);
            if (textBefore) {
              onToken?.(textBefore);
              buffer = buffer.slice(partialMatch.index);
            }
            break;
          }
        }

        // 4. Pure LLM text tokens - emit immediately so the user sees words live!
        if (buffer.trimStart().startsWith('{"type"')) {
          try {
            const parsed = JSON.parse(buffer.trim());
            if (parsed?.type === 'sources') {
              onSources?.(parsed.data || []);
              buffer = '';
              break;
            }
            if (parsed?.type === 'trace') {
              onTrace?.(parsed);
              buffer = '';
              break;
            }
          } catch (e) {}
        }
        onToken?.(buffer);
        buffer = '';
        break;
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        if (buffer) {
          processBuffer(true);
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      processBuffer(false);
    }

    onDone?.();
  } catch (err) {
    onError?.(err.message);
  }
}

// ── Analytics ─────────────────────────────────────────────────────────────────
export const analyticsAPI = {
  query: (data) => api.post('/analytics/query', data),
  dashboard: (workspaceId) => api.get(`/analytics/dashboard/${workspaceId}`),
  history: (workspaceId) => api.get('/analytics/history', { params: { workspace_id: workspaceId } }),
  clearHistory: (workspaceId) => api.delete('/analytics/history', { params: { workspace_id: workspaceId } }),
};

// ── System ────────────────────────────────────────────────────────────────────
export const systemAPI = {
  status: () => api.get('/system/status'),
  models: () => api.get('/system/models'),
  adminHistory: () => api.get('/system/admin/history'),
};

export default api;
