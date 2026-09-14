// api.js
// Single fetch client. No page may call fetch/axios directly.
// All endpoints live under /api/v1 and follow the error shape:
//   { detail: "human-readable", code: "SNAKE_CASE_CODE" }

import { getMsalInstance, loginRequest } from '@/lib/auth';

const BASE = '/api/v1';

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function getAccessToken() {
  const msalInstance = getMsalInstance();
  const accounts = msalInstance?.getAllAccounts() ?? [];
  if (accounts.length === 0) {
    throw new ApiError('Not authenticated', 401, 'UNAUTHENTICATED');
  }
  try {
    const response = await msalInstance.acquireTokenSilent({
      ...loginRequest,
      account: accounts[0],
    });
    return response.idToken;
  } catch {
    throw new ApiError('Session expired - please sign in again', 401, 'TOKEN_EXPIRED');
  }
}

// ─── Internal request helpers ──────────────────────────────────────────────
async function jsonRequest(path, { method = 'GET', body, signal, headers = {} } = {}) {
  const token = await getAccessToken();
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    signal,
  };
  if (body !== undefined) opts.body = JSON.stringify(body);

  let res;
  try {
    res = await fetch(`${BASE}${path}`, opts);
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError('Network error - backend unreachable', 0, 'NETWORK');
  }

  let data = null;
  try { data = await res.json(); } catch { /* empty body OK */ }

  if (!res.ok) {
    // Backend errors come back as either { detail: "...", code: "..." }
    // or wrapped in FastAPI's { detail: { detail: "...", code: "..." } }
    const inner = data?.detail && typeof data.detail === 'object' ? data.detail : data;
    const msg = inner?.detail || `Request failed with status ${res.status}`;
    const code = inner?.code || 'UNKNOWN';
    throw new ApiError(msg, res.status, code);
  }
  return data;
}

async function multipartRequest(path, formData, { signal } = {}) {
  const token = await getAccessToken();
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      body: formData,
      signal,
      // Browser sets Content-Type with boundary automatically - don't override
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError('Network error - backend unreachable', 0, 'NETWORK');
  }

  let data = null;
  try { data = await res.json(); } catch { /* empty body OK */ }

  if (!res.ok) {
    const inner = data?.detail && typeof data.detail === 'object' ? data.detail : data;
    throw new ApiError(
      inner?.detail || `Upload failed with status ${res.status}`,
      res.status,
      inner?.code || 'UNKNOWN',
    );
  }
  return data;
}

function waitForNextPoll(intervalMs, { signal, isCancelled } = {}) {
  return new Promise((resolve) => {
    if (signal?.aborted || isCancelled?.()) {
      resolve();
      return;
    }

    const timerId = setTimeout(() => {
      signal?.removeEventListener?.('abort', onAbort);
      resolve();
    }, intervalMs);

    function onAbort() {
      clearTimeout(timerId);
      signal?.removeEventListener?.('abort', onAbort);
      resolve();
    }

    signal?.addEventListener?.('abort', onAbort, { once: true });
  });
}

// ─── Public API ────────────────────────────────────────────────────────────
export const api = {
  // System
  health: (signal) => jsonRequest('/health', { signal }),
  me:     (signal) => jsonRequest('/me',     { signal }),

  // DB connection probes (synchronous, ~10s)
  connectTest: (credentials, { signal } = {}) =>
    jsonRequest('/connect/test', { method: 'POST', body: { credentials }, signal }),

  listTables: (credentials, schema_name, { signal } = {}) =>
    jsonRequest('/connect/tables', {
      method: 'POST',
      body: { credentials, schema: schema_name },
      signal,
    }),

  // Assessment - both kick off async jobs that return { job_id, status }
  assessCsv: (files, metadataFile = null, { signal, purpose = '' } = {}) => {
    const fd = new FormData();
    for (const f of files) fd.append('files', f, f.name);
    if (metadataFile) fd.append('metadata', metadataFile, metadataFile.name);
    if (purpose) fd.append('purpose', purpose);
    return multipartRequest('/assess/csv', fd, { signal });
  },

  assessDb: (credentials, schema_name, tables, metadataFile = null, { signal, purpose = '' } = {}) => {
    const fd = new FormData();
    fd.append('req', JSON.stringify({ credentials, schema: schema_name, tables }));
    if (metadataFile) fd.append('metadata', metadataFile, metadataFile.name);
    if (purpose) fd.append('purpose', purpose);
    return multipartRequest('/assess/db', fd, { signal });
  },

  getArchetypes: () => jsonRequest('/assess/archetypes'),

  getJob: (jobId, signal) =>
    jsonRequest(`/assess/jobs/${jobId}`, { signal }),

  cancelJob: (jobId, { signal } = {}) =>
    jsonRequest(`/assess/jobs/${jobId}/cancel`, { method: 'POST', signal }),

  runbook: (assessment) =>
    jsonRequest('/assess/runbook', { method: 'POST', body: assessment }),

  rescore: (assessment, approvedRuleIds, acknowledgedBlockerIds = [], dismissedRuleIds = []) =>
    jsonRequest('/assess/rescore', {
      method: 'POST',
      body: { assessment, approved_rule_ids: approvedRuleIds, acknowledged_blocker_ids: acknowledgedBlockerIds, dismissed_rule_ids: dismissedRuleIds },
    }),

  recomputePurpose: (assessment, purposeId) =>
    jsonRequest('/assess/recompute-purpose', {
      method: 'POST',
      body: { assessment, purpose_id: purposeId },
    }),

  exportMarkdown: async (assessment) => {
    const token = await getAccessToken();
    const res = await fetch(`${BASE}/export/markdown`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(assessment),
    });
    if (!res.ok) throw new ApiError(`Export failed (${res.status})`, res.status);
    return res.text();
  },

  // Support
  submitTicket: (payload, signal) =>
    jsonRequest('/support/tickets', { method: 'POST', body: payload, signal }),

  // History
  getHistory: (limit = 5, signal) =>
    jsonRequest(`/history?limit=${limit}`, { signal }),

  getRun: (runId, signal) =>
    jsonRequest(`/history/${runId}`, { signal }),

  deleteRun: (runId) =>
    jsonRequest(`/history/${runId}`, { method: 'DELETE' }),

  clearHistory: () =>
    jsonRequest('/history', { method: 'DELETE' }),

  // Admin (superuser only)
  adminLlmStatus: (signal) =>
    jsonRequest('/admin/llm-status', { signal }),

  adminGetUsers: (limit = 10, offset = 0, signal) =>
    jsonRequest(`/admin/users?limit=${limit}&offset=${offset}`, { signal }),

  adminUpdateUser: (userId, patch) =>
    jsonRequest(`/admin/users/${userId}`, { method: 'PATCH', body: patch }),

  adminGetRuns: (limit = 10, offset = 0, signal) =>
    jsonRequest(`/admin/runs?limit=${limit}&offset=${offset}`, { signal }),

  adminSystem: (signal) =>
    jsonRequest('/admin/system', { signal }),
};

// ─── Polling helper ────────────────────────────────────────────────────────
// Caller pattern:
//   const job = await api.assessCsv(files);
//   const result = await pollJob(job.job_id, { onProgress: p => setProg(p) });
//
// Throws ApiError on failure status. Returns the SchemaAssessment on done.
// Returns null when the caller cancels polling cooperatively.
export async function pollJob(jobId, { intervalMs = 2000, signal, onProgress, isCancelled } = {}) {
  while (true) {
    if (signal?.aborted || isCancelled?.()) return null;
    const j = await api.getJob(jobId, signal);
    if (signal?.aborted || isCancelled?.()) return null;
    if (onProgress) onProgress(j.progress, j.status, j.phase || '');
    if (j.status === 'done')   return j.result;
    if (j.status === 'cancelled') {
      throw new ApiError(
        j.error?.detail || 'Assessment cancelled',
        409,
        j.error?.code || 'JOB_CANCELLED',
      );
    }
    if (j.status === 'failed') {
      throw new ApiError(
        j.error?.detail || 'Job failed',
        500,
        j.error?.code || 'JOB_FAILED',
      );
    }
    await waitForNextPoll(intervalMs, { signal, isCancelled });
  }
}

export async function rescore(assessment, approvedRuleIds) {
  return api.rescore(assessment, approvedRuleIds);
}
