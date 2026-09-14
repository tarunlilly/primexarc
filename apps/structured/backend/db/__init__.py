"""ARC history-DB persistence layer.

This package owns ALL persistent database I/O for ARC's backend:
- `schema.py` — SQLAlchemy ORM models (the source of truth for the Python side)
- `session.py` — async engine + sessionmaker
- `history_store.py` — read/write functions consumed by core/ and api/
- `migrations/` — Alembic revisions
- `sql/` — DDL snapshots that mirror each Alembic revision (DBA-readable)

Anything outside this package that needs DB access goes through
`history_store.py`. No raw SQL strings allowed elsewhere.
"""
