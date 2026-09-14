# Phase 4 Export Design

## Goal

Surface ARC assessment history and insights to upper-layer systems: BI dashboards, Cortex AI agents, internal tooling, and future AI co-pilots. This is a Phase 4 effort — nothing here is built yet.

## Direction: MCP server first

The primary interface will be an **MCP server** that exposes ARC's history store as AI-queryable tools. This allows Claude, Cortex agents, and similar AI assistants to query assessment data conversationally without building a dedicated REST consumer.

### Proposed MCP tools

| Tool | Input | Output |
|---|---|---|
| `arc.list_assessments` | `since?`, `source_type?`, `schema?`, `limit?` | Array of run summaries (run_id, source_name, overall_score, tier, created_at) |
| `arc.get_assessment` | `run_id` | Full `SchemaAssessment` JSON (same shape as the live result) |
| `arc.list_failing_checks` | `run_id?`, `dimension_id?`, `severity?` | Distilled findings — "what should I fix first?" |
| `arc.compare_runs` | `run_id_a`, `run_id_b` | Score delta per dimension |

### Architecture

- New sibling service, separate Dockerfile, mounted at `/mcp` behind the same ingress.
- Reads from `history_assessment` schema using the same `history_store.py` helpers (shared via package or direct DB connection with a read-only role).
- Auth: service token for the MCP client; per-call user context flows in via MCP client headers. User scoping (`user_id`) is enforced the same way the REST API does it.
- No changes to the main ARC backend beyond confirming `result_json` is populated (already done in this release).

## Inbound REST API (parked)

A read-only REST endpoint `/api/v1/runs?since=&schema=&user=` would serve the same data in standard JSON. Useful for Power BI, Snowflake connectors, and scripted integrations.

**Why parked:** a long-lived service token with read access to all users' history requires CyberOps review. The scope, token rotation policy, and audit logging requirements need to be agreed before shipping. Revisit when there's a concrete upstream consumer identified.

## Outbound push (deprioritized)

ARC posting results to a configured webhook or Snowflake landing table is a valid pattern but requires the upstream to maintain a receiver. No concrete consumer identified yet.

## Data contract

When Phase 4 starts, the export contract should be based on the `SchemaAssessment` Pydantic model in `app/backend/core/models.py`. The `result_json` column on `assessment_runs` already persists this exact shape — no new serialization work needed. Any consumer should treat `result_json` as the authoritative source and not attempt to reconstruct from the denormalized aggregate columns.

## When to start

After items 1–2 of this release are verified in production (real `result_json` rows exist, `/history/{id}` returns full detail). The MCP server skeleton can begin once a concrete AI agent consumer is identified (Cortex integration, internal copilot, etc.).
