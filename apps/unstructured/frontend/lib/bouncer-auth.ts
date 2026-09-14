/**
 * Bouncer authentication utilities.
 *
 * Bouncer (EliLilly CATS ingress auth proxy) sits in front of this app and handles
 * the full Azure AD / OIDC login flow. After authentication it:
 *   - Sets a session cookie on the browser
 *   - Injects user identity headers into every forwarded request:
 *       X-USER-EMAIL, X-USER-NAME, X-UPN (configured in infra/deploy.yaml Ingress annotations)
 *   - Exposes session API endpoints under /_apps_system/session/
 *
 * These utilities call those session endpoints from the browser to obtain the real
 * user identity and a live Azure AD bearer token for backend API calls.
 */

import { getApiUrl } from './config'

export interface BouncerUser {
  email: string
  name: string
  upn: string
  id?: string
  samAccountName?: string
  department?: string
  groups?: string[]
  azureToken?: string
}

const FALLBACK_USER: BouncerUser = {
  email: 'primedata@lilly.com',
  name: 'PrimeData User',
  upn: 'primedata@lilly.com',
}

/**
 * Fetch the current authenticated user.
 *
 * Strategy:
 * 1. Try Bouncer's session API (/_apps_system/session/user) — available when
 *    Bouncer is the ingress proxy (CATS/production).
 * 2. Fall back to the backend's /api/v1/users/me — the backend reads the
 *    Bouncer-injected X-WEBAUTH-EMAIL / X-USER-NAME headers and returns the
 *    real authenticated user. This works even if the session endpoint is absent.
 * 3. Return the hardcoded default only in local dev (no Bouncer, no backend auth).
 */
export async function getBouncerUser(): Promise<BouncerUser> {
  // 1. Try Bouncer session endpoint first
  try {
    const resp = await fetch('/_apps_system/session/user', {
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    })
    if (resp.ok) {
      const data = await resp.json()
      // Support nested demographics structure (e.g. { demographics: { displayName, userPrincipalName, mail, ... } })
      const demo = data.demographics ?? data
      const email = demo.mail ?? demo.userPrincipalName ?? data.email ?? data.upn
      const name = demo.displayName ?? data.displayName ?? data.name
      // Only trust the response if it contains real identity data
      if (email && email !== FALLBACK_USER.email) {
        return {
          email,
          name: name ?? email,
          upn: demo.userPrincipalName ?? data.upn ?? email,
          id: data.id ?? demo.id,
          samAccountName: demo.onPremisesSamAccountName,
          department: demo.department ?? data.department,
          groups: data.groups,
          azureToken: data.azureToken,
        }
      }
    }
  } catch {
    // Bouncer session endpoint not available — try backend
  }

  // 2. Fall back to backend /api/v1/users/me (reads Bouncer-injected headers)
  try {
    const apiUrl = getApiUrl()
    const resp = await fetch(`${apiUrl}/api/v1/users/me`, {
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    })
    if (resp.ok) {
      const data = await resp.json()
      const email = data.email
      const name = data.name
      if (email && email !== FALLBACK_USER.email) {
        return {
          email,
          name: name ?? email,
          upn: email,
          id: data.id,
        }
      }
    }
  } catch {
    // Backend not reachable — use fallback
  }

  return FALLBACK_USER
}

/**
 * Fetch a live Azure AD bearer token.
 *
 * Strategy:
 * 1. Extract azureToken from the /session/user response (single fetch, always present).
 * 2. Fall back to the dedicated /session/token endpoint.
 * 3. Return 'default-user-token' for local dev.
 */
export async function getBouncerToken(): Promise<string> {
  // 1. Try to get the token from the session/user response (already fetched for user identity)
  try {
    const resp = await fetch('/_apps_system/session/user', {
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    })
    if (resp.ok) {
      const data = await resp.json()
      const token = data.azureToken
      if (token && typeof token === 'string') {
        return token.replace(/^Bearer\s+/i, '')
      }
    }
  } catch {
    // fall through
  }

  // 2. Fall back to dedicated session/token endpoint
  try {
    const resp = await fetch('/_apps_system/session/token', {
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    })
    if (!resp.ok) {
      console.warn('[Bouncer] session/token returned', resp.status)
      return 'default-user-token'
    }

    const contentType = resp.headers.get('content-type') ?? ''

    // Plain-text response — token is the raw body
    if (!contentType.includes('application/json')) {
      const text = (await resp.text()).trim()
      return text.replace(/^Bearer\s+/i, '') || 'default-user-token'
    }

    const data = await resp.json()
    const token =
      data.token ??
      data.access_token ??
      data.accessToken ??
      data.bearer_token ??
      data.bearerToken ??
      data.id_token ??
      data.jwt

    if (token) return String(token).replace(/^Bearer\s+/i, '')

    console.warn('[Bouncer] session/token: unrecognised response shape', data)
    return 'default-user-token'
  } catch (err) {
    console.warn('[Bouncer] session/token fetch failed:', err)
    return 'default-user-token'
  }
}

// Module-level user cache — single fetch shared by both user identity and token.
let _userPromise: Promise<BouncerUser> | null = null
let _resolvedUser: BouncerUser | null = null

export function getCachedUser(): Promise<BouncerUser> {
  if (!_userPromise) {
    _userPromise = getBouncerUser().then(user => {
      _resolvedUser = user
      setTimeout(() => { _userPromise = null; _resolvedUser = null }, 50 * 60 * 1000)
      return user
    })
  }
  return _userPromise
}

/** Returns the already-resolved user synchronously, or null if still loading. */
export function getResolvedUser(): BouncerUser | null {
  return _resolvedUser
}

export function clearUserCache(): void {
  _userPromise = null
  _resolvedUser = null
}

// Token cache — derived from the user cache (azureToken in session/user response).
// Falls back to the dedicated session/token endpoint if not present.
let _tokenPromise: Promise<string> | null = null

export function getCachedToken(): Promise<string> {
  if (!_tokenPromise) {
    _tokenPromise = getCachedUser().then(user => {
      if (user.azureToken) {
        setTimeout(() => { _tokenPromise = null }, 50 * 60 * 1000)
        return user.azureToken
      }
      // azureToken not in user response — fall back to dedicated endpoint
      return getBouncerToken().then(token => {
        setTimeout(() => { _tokenPromise = null }, 50 * 60 * 1000)
        return token
      })
    })
  }
  return _tokenPromise
}

export function clearTokenCache(): void {
  _tokenPromise = null
}


export async function initializeBouncerSession(): Promise<void> {
  try {
    const token = await getBouncerToken()
    const isProduction = typeof window !== 'undefined' && window.location.protocol === 'https:'
    if (typeof document !== 'undefined') {
      document.cookie = `primedata_api_token=${encodeURIComponent(token)}; path=/; max-age=3600; ${isProduction ? 'secure; ' : ''}samesite=lax`
    }
  } catch (error) {
    console.error('Failed to initialize Bouncer session:', error)
  }
}
