/**
 * Bouncer authentication utilities for the PrimeXarc shell.
 *
 * Bouncer (EliLilly CATS ingress auth proxy) handles Azure AD / OIDC login.
 * After authentication it sets a session cookie and exposes session API
 * endpoints under /_apps_system/session/.
 *
 * The shell has no backend of its own, so there is no backend fallback.
 * In local dev (no Bouncer), the fallback user activates automatically.
 */

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
  email: 'shell-dev@lilly.com',
  name: 'Shell Developer',
  upn: 'shell-dev@lilly.com',
  department: 'Development',
}

/**
 * Fetch the current authenticated user from Bouncer's session endpoint.
 *
 * Strategy:
 * 1. Try Bouncer's /_apps_system/session/user (available behind CATS ingress).
 * 2. Return the dev fallback (no backend fallback - shell has no backend).
 */
async function getBouncerUser(): Promise<BouncerUser> {
  try {
    const resp = await fetch('/_apps_system/session/user', {
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    })
    if (resp.ok) {
      const data = await resp.json()
      const demo = data.demographics ?? data
      const email = demo.mail ?? demo.userPrincipalName ?? data.email ?? data.upn
      const name = demo.displayName ?? data.displayName ?? data.name
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
    // Bouncer not available - local dev
  }

  return FALLBACK_USER
}

/**
 * Fetch a live Azure AD bearer token from Bouncer.
 */
async function getBouncerToken(): Promise<string> {
  try {
    const resp = await fetch('/_apps_system/session/user', {
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    })
    if (resp.ok) {
      const data = await resp.json()
      if (data.azureToken && typeof data.azureToken === 'string') {
        return data.azureToken.replace(/^Bearer\s+/i, '')
      }
    }
  } catch {
    // fall through
  }

  try {
    const resp = await fetch('/_apps_system/session/token', {
      credentials: 'include',
      headers: { 'Accept': 'application/json' },
    })
    if (resp.ok) {
      const contentType = resp.headers.get('content-type') ?? ''
      if (!contentType.includes('application/json')) {
        const text = (await resp.text()).trim()
        return text.replace(/^Bearer\s+/i, '') || 'dev-token'
      }
      const data = await resp.json()
      const token =
        data.token ?? data.access_token ?? data.accessToken ??
        data.bearer_token ?? data.bearerToken ?? data.id_token ?? data.jwt
      if (token) return String(token).replace(/^Bearer\s+/i, '')
    }
  } catch {
    // fall through
  }

  return 'dev-token'
}

// ─── Module-level cache ──────────────────────────────────────────────────

const CACHE_TTL = 50 * 60 * 1000 // 50 minutes

let _userPromise: Promise<BouncerUser> | null = null
let _resolvedUser: BouncerUser | null = null

export function getCachedUser(): Promise<BouncerUser> {
  if (!_userPromise) {
    _userPromise = getBouncerUser().then(user => {
      _resolvedUser = user
      setTimeout(() => { _userPromise = null; _resolvedUser = null }, CACHE_TTL)
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

let _tokenPromise: Promise<string> | null = null

export function getCachedToken(): Promise<string> {
  if (!_tokenPromise) {
    _tokenPromise = getCachedUser().then(user => {
      if (user.azureToken) {
        setTimeout(() => { _tokenPromise = null }, CACHE_TTL)
        return user.azureToken
      }
      return getBouncerToken().then(token => {
        setTimeout(() => { _tokenPromise = null }, CACHE_TTL)
        return token
      })
    })
  }
  return _tokenPromise
}

export function clearTokenCache(): void {
  _tokenPromise = null
}
