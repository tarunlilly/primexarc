/// <reference types="vite/client" />

/**
 * Runtime environment injected by docker/entrypoint.sh into window.__ENV__.
 * In local dev these are undefined - functions in lib/config.ts fall back
 * to localhost defaults.
 */
interface ShellEnv {
  STRUCTURED_URL?: string
  UNSTRUCTURED_URL?: string
}

interface Window {
  __ENV__?: ShellEnv
}
