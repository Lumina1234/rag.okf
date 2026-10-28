import React, { createContext, useContext, useState, useEffect } from 'react';
import { authAPI, workspaceAPI } from '../lib/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspace, setActiveWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('token');
      if (token) {
        try {
          const res = await authAPI.me();
          setUser(res.data);
          await refreshWorkspaces();
        } catch (err) {
          console.error('Auth init failed:', err);
          logout();
        }
      }
      setLoading(false);
    };
    initAuth();
  }, []);

  const refreshWorkspaces = async () => {
    try {
      let res = await workspaceAPI.list();
      let wsList = res.data;
      if (wsList.length === 0) {
        try {
          const defaultWs = await workspaceAPI.create({
            name: 'General Workspace',
            workspace_type: 'business',
            description: 'Default business workspace'
          });
          wsList = [defaultWs.data];
        } catch (e) {
          console.error('Failed to auto-create default workspace:', e);
        }
      }
      setWorkspaces(wsList);
      if (wsList.length > 0) {
        const savedWsId = localStorage.getItem('activeWorkspaceId');
        const found = wsList.find(w => w.id === parseInt(savedWsId));
        const selected = found || wsList[0];
        setActiveWorkspace(selected);
        localStorage.setItem('activeWorkspaceId', selected.id);
      } else {
        setActiveWorkspace(null);
      }
    } catch (err) {
      console.error('Failed to fetch workspaces:', err);
    }
  };

  const login = async (username, password) => {
    const res = await authAPI.login({ username, password });
    localStorage.setItem('token', res.data.access_token);
    setUser({ id: res.data.user_id, username: res.data.username, role: res.data.role });
    await refreshWorkspaces();
    return res.data;
  };

  const register = async (userData) => {
    await authAPI.register(userData);
    return login(userData.username, userData.password);
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('activeWorkspaceId');
    setUser(null);
    setWorkspaces([]);
    setActiveWorkspace(null);
  };

  const selectWorkspace = (ws) => {
    setActiveWorkspace(ws);
    localStorage.setItem('activeWorkspaceId', ws.id);
  };

  return (
    <AuthContext.Provider value={{
      user,
      workspaces,
      activeWorkspace,
      loading,
      login,
      register,
      logout,
      selectWorkspace,
      refreshWorkspaces
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
