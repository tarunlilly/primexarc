// lib/user.js
// Returns the signed-in user's profile. In production, reads from the active
// MSAL account (populated after Azure AD login). In dev without credentials,
// falls back to MOCK_USER so UI work can proceed without Azure AD.

import { getMsalInstance } from '@/lib/auth';
import { api } from '@/lib/api';

export const ROLES = [
  'Developer',
  'Data Product Owner',
  'Technical SME',
  'Data Steward',
];

export const MOCK_USER = {
  id: 'u_dev',
  name: 'Dev User',
  initials: 'DU',
  email: 'dev@lilly.com',
  role: 'Data Product Owner',
  team: 'Patient Analytics · Oncology',
  data_products: [],
};

export async function getUserPhoto(msalInstance) {
  const accounts = msalInstance?.getAllAccounts() ?? [];
  if (!accounts.length) return null;
  try {
    const { accessToken } = await msalInstance.acquireTokenSilent({
      scopes: ['User.Read'],
      account: accounts[0],
    });
    const res = await fetch('https://graph.microsoft.com/v1.0/me/photo/$value', {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!res.ok) return null; // 404 = no photo set, 403 = no consent
    return URL.createObjectURL(await res.blob());
  } catch {
    return null;
  }
}

export function getCurrentUser() {
  const accounts = getMsalInstance()?.getAllAccounts() ?? [];
  if (accounts.length === 0) return null;

  const account = accounts[0];
  const name = account.name || 'Unknown User';
  const email = account.username || '';
  const parts = name.trim().split(/\s+/);
  const initials =
    parts.length >= 2
      ? `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
      : name.slice(0, 2).toUpperCase();

  return {
    id: account.localAccountId,
    name,
    initials,
    email,
    role: _meCache?.roles?.[0] || null,
    team: null,
    data_products: [],
    is_superuser: _meCache?.is_superuser ?? false,
  };
}

let _meCache = null;
let _meFetching = false;

export async function fetchMe() {
  if (_meCache) return _meCache;
  if (_meFetching) return null;
  _meFetching = true;
  try {
    _meCache = await api.me();
  } catch {
    try {
      const resp = await fetch('/api/v1/me');
      if (resp.ok) _meCache = await resp.json();
    } catch { /* ignore - /me is best-effort */ }
  }
  _meFetching = false;
  return _meCache;
}

export function getMeCache() {
  return _meCache;
}
