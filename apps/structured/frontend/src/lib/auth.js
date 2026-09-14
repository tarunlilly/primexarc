import { PublicClientApplication, LogLevel } from '@azure/msal-browser';

// Scopes are static - they don't vary by environment.
export const loginRequest = {
  scopes: ['openid', 'profile', 'email', 'User.Read'],
};

let _instance = null;

export function getMsalInstance() {
  return _instance;
}

export async function loadAuthConfig() {
  if (_instance) return _instance;

  const res = await fetch('/api/config');
  if (!res.ok) throw new Error('Auth config unavailable - server returned ' + res.status);

  const { clientId, tenantId } = await res.json();

  _instance = new PublicClientApplication({
    auth: {
      clientId,
      authority: `https://login.microsoftonline.com/${tenantId}`,
      redirectUri: '/',
      postLogoutRedirectUri: '/',
    },
    cache: {
      cacheLocation: 'sessionStorage',
      storeAuthStateInCookie: false,
    },
    system: {
      loggerOptions: {
        loggerCallback: (level, message, containsPii) => {
          if (containsPii) return;
          if (level === LogLevel.Error) console.error('[MSAL]', message);
        },
        logLevel: LogLevel.Error,
      },
    },
  });

  return _instance;
}
