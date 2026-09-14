---
name: db-connection-health
description: Use this skill when diagnosing database connection errors, driver
  installation issues, SQLAlchemy dialect mismatches, or verifying that a Postgres
  or Redshift connection is correctly configured in ARC. Triggers on
  phrases like "connection failed", "can't load plugin", "driver error", "postgres
  not connecting", "redshift issue", "test the connection", "check database config".
version: 1.0.0
user-invocable: true
tools: Read, Bash, WebSearch
---

# DB Connection Health

When invoked, run through these steps. All paths are relative to `apps/structured/`.

## 1. Identify what's installed and what dialect is configured

Read `backend/requirements.txt` to see which DB driver packages are present.
Read `backend/core/db_introspector.py` `_build_url()` to see the dialect string
being used for each engine type.

## 2. Check for known driver/dialect mismatches

| Driver in requirements.txt | Correct dialect string | SQLAlchemy compat |
|---|---|---|
| `psycopg2-binary` | `postgresql+psycopg2://` | 1.4 and 2.x |
| `psycopg[binary]` (psycopg3) | `postgresql+psycopg://` | **2.x ONLY** |
| `redshift-connector` + `sqlalchemy-redshift` | `redshift+redshift_connector://` | 1.4 and 2.x |

**Common failure pattern:** `psycopg[binary]` + `SQLAlchemy<2.0` always fails with
"Can't load plugin: sqlalchemy.dialects:postgresql.psycopg". Fix: use `psycopg2-binary`
and change the URL scheme to `postgresql+psycopg2://`.

## 3. Check logging coverage

Connection failures should ALWAYS produce a log line. Verify in `db_introspector.py`
that `test_connection()` logs at WARNING on failure, and that `_engine_for()` logs
before raising `DBConnectionError`. If any are silent, that is a bug to fix.

## 4. Check credential masking

Verify that host addresses and usernames are masked before logging (truncate to
first 3 chars + `***`). Full credentials must not appear in logs.

## 5. Report findings

Summarize: what's installed, what dialect string is used, whether there's a mismatch,
and the exact one-line fix if needed.

## 6. If asked to fix

Apply the change to:
1. `backend/requirements.txt` - swap the driver package
2. `backend/core/db_introspector.py` `_build_url()` - update the dialect string
3. Rebuild: `docker-compose build backend` from `apps/structured/`
4. Test: `POST /api/v1/connect/test` with valid credentials -> `ok: true`

## Adding a new data source

When a new source type is requested:
1. Find the SQLAlchemy dialect name
2. Add driver package to `backend/requirements.txt` with pinned minor version
3. Add branch in `_build_url()` and `_connect_args()` in `backend/core/db_introspector.py`
4. Add engine string to `DBEngine` Literal in `backend/core/models.py`
5. Update frontend engine `<select>` in the assess page with new option and default port
6. Add a test in `backend/tests/`
