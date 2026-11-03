import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { orgAPI } from '../lib/orgApi';
import { useAuth } from '../context/AuthContext';

/**
 * OrgSelection — shown after login when the user belongs to multiple organizations.
 * Lets the user pick which org context to enter (Education or Business portal).
 */
export default function OrgSelection() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    orgAPI.list()
      .then((res) => setOrgs(res.data))
      .catch(() => setError('Failed to load organizations.'))
      .finally(() => setLoading(false));
  }, []);

  const enterOrg = (org) => {
    localStorage.setItem('activeOrgId', org.id);
    localStorage.setItem('activeOrgType', org.org_type);
    localStorage.setItem('activeOrgName', org.name);
    if (org.org_type === 'education') {
      navigate('/org/education');
    } else {
      navigate('/org/business');
    }
  };

  const orgTypeIcon = (type) => (type === 'education' ? '🎓' : '🏢');
  const orgTypeLabel = (type) => (type === 'education' ? 'Education Portal' : 'Business Portal');
  const orgTypeBadge = (type) =>
    type === 'education'
      ? 'bg-blue-100 text-blue-800'
      : 'bg-green-100 text-green-800';

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-gray-500">Loading organizations…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 to-gray-800 flex items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-white mb-2">Select Organization</h1>
          <p className="text-gray-400">Choose which organization to work with, {user?.username}.</p>
        </div>

        {error && (
          <div className="bg-red-900 border border-red-700 text-red-200 rounded-lg p-4 mb-6 text-sm">
            {error}
          </div>
        )}

        {orgs.length === 0 && !error && (
          <div className="bg-gray-800 rounded-xl p-8 text-center border border-gray-700">
            <p className="text-gray-400 mb-4">You are not a member of any organization yet.</p>
            <p className="text-gray-500 text-sm">Contact your organization administrator to get access.</p>
          </div>
        )}

        <div className="grid gap-4">
          {orgs.map((org) => (
            <button
              key={org.id}
              onClick={() => enterOrg(org)}
              className="bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-gray-500
                         rounded-xl p-6 text-left transition-all duration-200 group w-full"
            >
              <div className="flex items-center gap-4">
                <span className="text-4xl">{orgTypeIcon(org.org_type)}</span>
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <h2 className="text-white font-semibold text-lg group-hover:text-blue-400 transition-colors">
                      {org.name}
                    </h2>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${orgTypeBadge(org.org_type)}`}>
                      {orgTypeLabel(org.org_type)}
                    </span>
                  </div>
                  <p className="text-gray-500 text-sm">@{org.slug}</p>
                </div>
                <span className="text-gray-600 group-hover:text-gray-400 text-xl">→</span>
              </div>
            </button>
          ))}
        </div>

        <div className="mt-6 text-center">
          <button
            onClick={() => navigate('/')}
            className="text-gray-500 hover:text-gray-300 text-sm transition-colors"
          >
            ← Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
