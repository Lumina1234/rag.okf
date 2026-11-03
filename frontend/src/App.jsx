import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import ChatInterface from './components/ChatInterface';
import Documents from './pages/Documents';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import AdminHistory from './pages/AdminHistory';
import Login from './pages/Login';
import Summarize from './pages/Summarize';
import OrgSelection from './pages/OrgSelection';
import EduPortal from './pages/EduPortal';
import BizPortal from './pages/BizPortal';
import OrgAdmin from './pages/OrgAdmin';
import SuperAdmin from './pages/SuperAdmin';
import { systemAPI } from './lib/api';

const ProtectedLayout = () => {
  const { user, loading } = useAuth();
  const [systemStatus, setSystemStatus] = useState(null);

  useEffect(() => {
    if (user) {
      systemAPI.status().then(res => setSystemStatus(res.data)).catch(() => {});
    }
  }, [user]);

  if (loading) {
    return (
      <div className="login-page">
        <div className="spinner" style={{ width: '40px', height: '40px' }}></div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="app-shell">
      <Sidebar systemStatus={systemStatus} />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/chat" element={<ChatInterface />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/admin-history" element={<AdminHistory />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/summarize" element={<Summarize />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
};

const ProtectedOrgRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="login-page">
        <div className="spinner" style={{ width: '40px', height: '40px' }}></div>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/org-selection" element={<ProtectedOrgRoute><OrgSelection /></ProtectedOrgRoute>} />
          <Route path="/org/education" element={<ProtectedOrgRoute><EduPortal /></ProtectedOrgRoute>} />
          <Route path="/org/business" element={<ProtectedOrgRoute><BizPortal /></ProtectedOrgRoute>} />
          <Route path="/org/admin" element={<ProtectedOrgRoute><OrgAdmin /></ProtectedOrgRoute>} />
          <Route path="/super-admin" element={<ProtectedOrgRoute><SuperAdmin /></ProtectedOrgRoute>} />
          <Route path="/*" element={<ProtectedLayout />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
