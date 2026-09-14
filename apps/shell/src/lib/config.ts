/**
 * Shell configuration - app URLs and build metadata.
 *
 * Production hostnames are injected at deploy time via window.__ENV__
 * (set by docker/entrypoint.sh), not baked at build time. This matches
 * PrimeData's existing runtime-config pattern and avoids stale-bundle bugs.
 *
 * In local dev, window.__ENV__ is undefined and functions fall back to
 * localhost ports matching each app's dev server.
 */

export function getStructuredUrl(): string {
  if (typeof window !== 'undefined' && window.__ENV__?.STRUCTURED_URL) {
    return window.__ENV__.STRUCTURED_URL
  }
  return 'http://localhost:5173'
}

export function getUnstructuredUrl(): string {
  if (typeof window !== 'undefined' && window.__ENV__?.UNSTRUCTURED_URL) {
    return window.__ENV__.UNSTRUCTURED_URL
  }
  return 'http://localhost:3000'
}

export const BUILD_STAMP = 'v0.1.0-dev'
