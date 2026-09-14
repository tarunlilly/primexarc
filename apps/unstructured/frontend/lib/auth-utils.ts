/**
 * Authentication utility functions — delegates to Bouncer session APIs.
 */

import { initializeDefaultUser } from './default-auth'
import { getBouncerToken, initializeBouncerSession } from './bouncer-auth'

/**
 * Initialize authentication on app load.
 * Fetches the live Azure AD token from Bouncer and stores it in the cookie.
 */
export async function initializeAuth(): Promise<{ success: boolean }> {
  try {
    await initializeDefaultUser()
    return { success: true }
  } catch (error) {
    console.error('Failed to initialize authentication:', error)
    return { success: false }
  }
}

/**
 * Get the current user's API token from the cookie (synchronous).
 * Call exchangeToken() to refresh from Bouncer when the token is stale.
 */
export function getUserToken(): string {
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
 * Refresh the token from Bouncer and update the cookie.
 * Called by api-client.ts on 401 responses.
 */
export async function exchangeToken(): Promise<{ success: boolean; token?: string }> {
  try {
    await initializeBouncerSession()
    const token = await getBouncerToken()
    return { success: true, token }
  } catch (error) {
    console.error('Failed to exchange token:', error)
    return { success: false }
  }
}



