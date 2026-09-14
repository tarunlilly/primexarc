/**
 * Authentication utilities — delegates to Bouncer (CATS ingress auth proxy).
 *
 * Bouncer handles the Azure AD / OIDC login flow and exposes session endpoints
 * under /_apps_system/session/. See lib/bouncer-auth.ts for the implementation.
 */

import { initializeBouncerSession } from './bouncer-auth'

/**
 * Get the current user's API token.
 * Returns the Bouncer Azure AD token, or 'default-user-token' in local dev.
 */
export function getDefaultUserToken(): string {
  // Synchronous read from the cookie (already populated by initializeDefaultUser).
  // The cookie is refreshed on app load via initializeDefaultUser().
  if (typeof document !== 'undefined') {
    const cookie = document.cookie
      .split('; ')
      .find((row) => row.startsWith('primedata_api_token='))
    if (cookie) {
      const value = cookie.split('=').slice(1).join('=')
      if (value) return decodeURIComponent(value)
    }
  }
  return 'default-user-token'
}

/**
 * Initialize session on app load.
 * Fetches the live Azure AD token from Bouncer and stores it in the
 * primedata_api_token cookie for use by api-client.ts.
 */
export async function initializeDefaultUser(): Promise<void> {
  await initializeBouncerSession()
}

/**
 * Get the current user object.
 * Use useDefaultUser() hook (default-user-context.tsx) for the live React value.
 */
export async function getDefaultUser() {
  const { getBouncerUser } = await import('./bouncer-auth')
  return getBouncerUser()
}
