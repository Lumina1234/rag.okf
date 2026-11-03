/**
 * Organization API client for the Security & Organization Layer.
 * All requests use the JWT token from localStorage.
 */
import axios from 'axios';

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Organizations ────────────────────────────────────────────────────────────

export const orgAPI = {
  create: (data) => api.post('/organizations', data),
  list: () => api.get('/organizations'),
  get: (orgId) => api.get(`/organizations/${orgId}`),

  // Departments
  createDepartment: (orgId, data) => api.post(`/organizations/${orgId}/departments`, data),
  listDepartments: (orgId) => api.get(`/organizations/${orgId}/departments`),

  // Members
  addMember: (orgId, data) => api.post(`/organizations/${orgId}/members`, data),
  listMembers: (orgId) => api.get(`/organizations/${orgId}/members`),
  removeMember: (orgId, userId) => api.delete(`/organizations/${orgId}/members/${userId}`),

  // Workspaces
  createWorkspace: (orgId, data) => api.post(`/organizations/${orgId}/workspaces`, data),
  listWorkspaces: (orgId) => api.get(`/organizations/${orgId}/workspaces`),
};

// ── Roles ────────────────────────────────────────────────────────────────────

export const rolesAPI = {
  listTemplates: () => api.get('/roles'),
};

// ── Permissions ──────────────────────────────────────────────────────────────

export const permissionsAPI = {
  check: (organizationId, permissionKey) =>
    api.post('/permissions/check', { organization_id: organizationId, permission_key: permissionKey }),
};

// ── Document ACL ─────────────────────────────────────────────────────────────

export const documentACLAPI = {
  updateACL: (docId, data) => api.put(`/documents/${docId}/acl`, data),
  approve: (docId) => api.post(`/documents/${docId}/approve`),
  revoke: (docId) => api.post(`/documents/${docId}/revoke`),
};

// ── Audit Logs ───────────────────────────────────────────────────────────────

export const auditAPI = {
  getLogs: (orgId, limit = 100, offset = 0) =>
    api.get('/security/audit-logs', { params: { org_id: orgId, limit, offset } }),
};

export default api;
