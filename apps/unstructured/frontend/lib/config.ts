/**
 * Centralized configuration for API URLs
 */

// Use HTTPS for production, HTTP only for local development
const DEFAULT_API_URL = "http://127.0.0.1:8000"

/**
 * Get the API base URL from environment variables or return the default
 * Uses 127.0.0.1 instead of localhost for better server-side compatibility
 *
 * In production (browser), if the page is loaded over HTTPS, use HTTPS for API calls
 * to avoid Mixed Content errors.
 *
 * @returns The API base URL
 */
export function getApiUrl(): string {
  const runtimeEnv = (window as any).__ENV__ ?? {}
  const envUrl = runtimeEnv.VITE_API_URL || import.meta.env.VITE_API_URL
  if (envUrl) {
    return envUrl
  }

  // When deployed over HTTPS, route through the same origin so nginx
  // can proxy /api/ to the backend — avoids CORS preflight entirely.
  if (typeof window !== 'undefined' && window.location.protocol === 'https:') {
    return window.location.origin
  }

  return DEFAULT_API_URL
}

/**
 * Default API URL constant (for cases where you need the default value directly)
 */
export const DEFAULT_API_BASE_URL = DEFAULT_API_URL

