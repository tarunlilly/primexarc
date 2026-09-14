"""DBIntrospector — connects to Postgres or Redshift, lists tables,
samples them, and produces TableProfile objects.

Connection strategy (from user requirements):
- Real connection code, not mocked.
- 30-second connect timeout enforced at TWO layers for reliability:
    1. Driver `connect_timeout` parameter (TCP-level, killed by libpq/socket)
    2. `asyncio.wait_for(...)` wrapper as belt-and-suspenders
- Credentials are never persisted. They live in memory for the duration
  of the request only.

Engine support:
- postgres: psycopg2 driver via SQLAlchemy URL "postgresql+psycopg2://..."
- redshift: redshift+redshift_connector dialect via sqlalchemy-redshift

Both engines share the same SQLAlchemy code path; only the URL differs.
"""
from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from contextlib import contextmanager
from typing import Generator

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from config import settings
from core.csv_parser import CSVParser
from core.models import DBCredentials, TableProfile, TableSummary
from core.ydata_enricher import enrich as ydata_enrich

logger = logging.getLogger(__name__)


class DBConnectionError(RuntimeError):
    """Raised by introspection methods. Carries a stable code for the API
    layer to translate into ConnectionTestResponse."""

    def __init__(self, code: str, detail: str, description: str = ""):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.description = description


def _connection_description(code: str) -> str:
    if code == "AUTH_FAILED":
        return (
            "ARC reached the database, but authentication failed. "
            "Verify the username/password and confirm the connection is allowed from Lilly."
        )
    if code in {"CONNECTION_TIMEOUT", "HOST_UNREACHABLE"}:
        return (
            "ARC could not reach the database. Common causes are a missing whitelist/allowlist "
            "entry, firewall or VPN restrictions, incorrect host or port, or invalid credentials."
        )
    if code == "UNKNOWN_ERROR":
        return (
            "ARC could not complete the connection. Common causes are missing whitelist access, "
            "incorrect credentials, SSL or network configuration issues, or a driver-level error."
        )
    return ""


# ─── URL construction ─────────────────────────────────────────────────────

def _build_url(creds: DBCredentials) -> str:
    """Build a SQLAlchemy connection URL from credentials.

    SECURITY: This returns a string that contains the password. Never log
    the result. We pass the credentials separately to create_engine where
    possible, but SQLAlchemy ultimately needs them in the URL.
    """
    pw = creds.password.get_secret_value()
    # URL-encode the password to handle special characters
    from urllib.parse import quote_plus
    pw_q = quote_plus(pw)
    user_q = quote_plus(creds.username)

    if creds.engine == "postgres":
        return (
            f"postgresql+psycopg2://{user_q}:{pw_q}"
            f"@{creds.host}:{creds.port}/{creds.database}"
        )
    if creds.engine == "redshift":
        return (
            f"redshift+redshift_connector://{user_q}:{pw_q}"
            f"@{creds.host}:{creds.port}/{creds.database}"
        )
    raise DBConnectionError("UNKNOWN_ERROR", f"Unsupported engine: {creds.engine}")


def _connect_args(creds: DBCredentials) -> dict:
    """Driver-specific kwargs, including the all-important connect_timeout."""
    timeout = settings.db_connect_timeout
    if creds.engine == "postgres":
        return {"connect_timeout": timeout, "sslmode": "require" if creds.ssl else "prefer"}
    if creds.engine == "redshift":
        return {"timeout": timeout, "ssl": creds.ssl}
    return {}


# ─── The introspector ─────────────────────────────────────────────────────

class DBIntrospector:
    """Stateless: one instance per process is fine.

    All methods accept fresh credentials each call. No connection pooling
    — the security posture requires re-authentication per request.
    """

    # ── Connection test ───────────────────────────────────────────────────
    async def test_connection(self, creds: DBCredentials) -> tuple[bool, str, str, str, int]:
        """Try to open a connection within the timeout. Returns:
            (ok, code, detail, description, elapsed_ms)
        Possible codes: OK, CONNECTION_TIMEOUT, AUTH_FAILED,
                        HOST_UNREACHABLE, UNKNOWN_ERROR
        """
        start = time.monotonic()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._sync_connect_and_ping, creds),
                timeout=settings.db_connect_timeout + 1,  # +1s grace over driver
            )
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - start) * 1000)
            code = "CONNECTION_TIMEOUT"
            return (
                False,
                code,
                f"Connection attempt exceeded {settings.db_connect_timeout}s. "
                "Check firewall / VPN / whitelist.",
                _connection_description(code),
                elapsed,
            )
        except DBConnectionError as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.warning(
                "[%s] connection test failed (%s): %s | description=%s",
                creds.engine,
                exc.code,
                exc.detail,
                exc.description,
            )
            return (False, exc.code, exc.detail, exc.description, elapsed)
        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.monotonic() - start) * 1000)
            code = "UNKNOWN_ERROR"
            description = _connection_description(code)
            logger.warning(
                "[%s] connection test error: %s | description=%s",
                creds.engine,
                exc,
                description,
            )
            return (False, code, str(exc), description, elapsed)

        elapsed = int((time.monotonic() - start) * 1000)
        return (True, "OK", f"Connected in {elapsed} ms", "", elapsed)

    def _sync_connect_and_ping(self, creds: DBCredentials) -> None:
        """Synchronous helper run inside asyncio.to_thread()."""
        with self._engine_for(creds) as engine:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

    # ── List tables in a schema ───────────────────────────────────────────
    async def list_tables(self, creds: DBCredentials, schema_name: str) -> list[TableSummary]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._sync_list_tables, creds, schema_name),
                timeout=settings.db_connect_timeout + settings.db_query_timeout + 1,
            )
        except asyncio.TimeoutError as exc:
            code = "CONNECTION_TIMEOUT"
            raise DBConnectionError(
                code,
                "Listing tables exceeded the timeout.",
                _connection_description(code),
            ) from exc

    def _sync_list_tables(self, creds: DBCredentials, schema_name: str) -> list[TableSummary]:
        with self._engine_for(creds) as engine:
            if creds.engine == "redshift":
                # pg_catalog is always complete on Redshift — information_schema
                # omits late-binding views and returns 0 columns for many objects.
                relkinds = "('r', 'v')" if settings.db_include_views else "('r',)"
                sql = text(f"""
                    SELECT
                        c.relname AS name,
                        COUNT(a.attnum) AS column_count
                    FROM pg_catalog.pg_class c
                    JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
                    LEFT JOIN pg_catalog.pg_attribute a
                      ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
                    WHERE n.nspname = :schema_name
                      AND c.relkind IN {relkinds}
                    GROUP BY c.relname
                    ORDER BY c.relname
                """)
            else:
                table_types = "('BASE TABLE', 'VIEW')" if settings.db_include_views else "('BASE TABLE',)"
                sql = text(f"""
                    SELECT
                        t.table_name AS name,
                        COUNT(c.column_name) AS column_count
                    FROM information_schema.tables AS t
                    LEFT JOIN information_schema.columns AS c
                      ON c.table_schema = t.table_schema
                     AND c.table_name = t.table_name
                    WHERE t.table_schema = :schema_name
                      AND t.table_type IN {table_types}
                    GROUP BY t.table_name
                    ORDER BY t.table_name
                """)
            with engine.connect() as conn:
                rows = conn.execute(sql, {"schema_name": schema_name}).mappings().all()
            return [
                TableSummary(
                    name=row["name"],
                    column_count=int(row["column_count"]),
                )
                for row in rows
            ]

    def _configure_profile_session(self, conn, engine_name: str) -> None:
        """Apply per-connection safety bounds before large profiling queries.

        Redshift supports SET statement_timeout but it may be disabled by
        cluster parameter groups or user permissions -- tolerate failure.
        """
        timeout_ms = settings.db_query_timeout * 1000
        try:
            conn.execute(text(f"SET statement_timeout = {timeout_ms}"))
        except Exception:  # noqa: BLE001
            if engine_name == "redshift":
                logger.debug(
                    "SET statement_timeout not supported on this Redshift cluster; proceeding without"
                )
            else:
                raise

    def _count_table_rows(self, conn, schema_name: str, table_name: str) -> int:
        fq = f'"{schema_name}"."{table_name}"'
        sql = text(f"SELECT COUNT(*) AS row_count FROM {fq}")
        result = conn.execute(sql)
        row_count = result.scalar()
        return int(row_count or 0)

    def _count_table_rows_redshift(self, conn, schema_name: str, table_name: str) -> int:
        """Use Redshift system catalog for an approximate row count (instant).

        Falls back to exact COUNT(*) if the catalog has no entry (views,
        external tables, or freshly created tables not yet analyzed).
        """
        sql = text("""
            SELECT NVL("rows", 0) AS row_count
            FROM svv_table_info
            WHERE "schema" = :schema_name AND "table" = :table_name
        """)
        try:
            result = conn.execute(sql, {"schema_name": schema_name, "table_name": table_name})
            row = result.fetchone()
            if row and row[0] > 0:
                return int(row[0])
        except Exception:  # noqa: BLE001
            logger.debug(
                "svv_table_info lookup failed for %s.%s; falling back to COUNT(*)",
                schema_name,
                table_name,
            )
        return self._count_table_rows(conn, schema_name, table_name)

    def _quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _is_orderable_column_type(self, col_type) -> bool:
        if col_type is None:
            return True
        name = col_type.__class__.__name__.lower()
        unsupported = (
            "array", "binary", "blob", "bytea", "geography",
            "geometry", "json", "super", "variant",
        )
        return not any(token in name for token in unsupported)

    def _sample_columns(
        self, engine: Engine, schema_name: str, table_name: str,
        conn=None, engine_name: str = "postgres",
    ) -> tuple[list[str], list[str]]:
        inspector = inspect(engine)
        try:
            columns = inspector.get_columns(table_name, schema=schema_name)
        except Exception:  # noqa: BLE001
            logger.debug("Could not inspect columns for %s.%s", schema_name, table_name)
            columns = []

        column_names = [str(column["name"]) for column in columns]

        # Fallback: if SQLAlchemy inspector returned nothing (common on Redshift
        # late-binding views), query pg_catalog directly.
        if not column_names and engine_name == "redshift" and conn is not None:
            try:
                sql = text("""
                    SELECT a.attname
                    FROM pg_catalog.pg_attribute a
                    JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
                    JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
                    WHERE n.nspname = :schema_name AND c.relname = :table_name
                      AND a.attnum > 0 AND NOT a.attisdropped
                    ORDER BY a.attnum
                """)
                rows = conn.execute(sql, {"schema_name": schema_name, "table_name": table_name}).fetchall()
                column_names = [str(row[0]) for row in rows]
                logger.debug(
                    "pg_catalog fallback discovered %d columns for %s.%s",
                    len(column_names), schema_name, table_name,
                )
            except Exception:  # noqa: BLE001
                logger.debug("pg_catalog fallback also failed for %s.%s", schema_name, table_name)

        if not column_names:
            return [], []

        try:
            pk = inspector.get_pk_constraint(table_name, schema=schema_name)
            pk_columns = pk.get("constrained_columns") or []
            if pk_columns:
                return column_names, [str(column) for column in pk_columns]
        except Exception:  # noqa: BLE001
            logger.debug("Could not inspect primary key for %s.%s", schema_name, table_name)

        # For Redshift fallback path, we don't have type info — treat all as orderable
        if not columns:
            return column_names, column_names[:3]  # use first 3 columns for ordering

        return column_names, [
            str(column["name"])
            for column in columns
            if self._is_orderable_column_type(column.get("type"))
        ]

    def _build_systematic_sample_sql(
        self,
        schema_name: str,
        table_name: str,
        column_names: list[str],
        order_columns: list[str],
    ) -> str:
        fq = f'"{schema_name}"."{table_name}"'
        select_list = ", ".join(self._quote_identifier(column) for column in column_names)
        order_clause = ", ".join(self._quote_identifier(column) for column in order_columns)
        return (
            "WITH ranked AS ("
            f"SELECT {select_list}, ROW_NUMBER() OVER (ORDER BY {order_clause}) AS _arc_rn "
            f"FROM {fq}"
            ") "
            f"SELECT {select_list} FROM ranked "
            "WHERE MOD(_arc_rn - 1, :step) = 0 "
            "ORDER BY _arc_rn "
            "LIMIT :n"
        )

    def _build_redshift_sample_sql(
        self,
        schema_name: str,
        table_name: str,
        column_names: list[str],
        table_row_count: int,
        sample_limit: int,
    ) -> str:
        """Redshift-optimized sampling using TABLESAMPLE SYSTEM.

        TABLESAMPLE SYSTEM operates at the disk-block level -- it skips entire
        blocks without scanning them, making it vastly faster than ROW_NUMBER()
        on columnar storage. The percentage is computed to yield approximately
        sample_limit rows with a 50% safety margin; LIMIT caps the result.
        """
        fq = f'"{schema_name}"."{table_name}"'
        select_list = ", ".join(self._quote_identifier(c) for c in column_names)
        pct = min(100.0, (sample_limit * 1.5 / table_row_count) * 100)
        pct = max(0.01, pct)  # minimum 0.01%
        return f"SELECT {select_list} FROM {fq} TABLESAMPLE SYSTEM({pct:.4f}) LIMIT :n"

    def _sample_row_limit(self, engine_name: str) -> int:
        if engine_name == "redshift":
            return min(settings.max_rows_per_db_table, settings.max_rows_per_redshift_table)
        return settings.max_rows_per_db_table

    def _read_sample_dataframe(
        self,
        conn,
        schema_name: str,
        table_name: str,
        table_row_count: int,
        engine_name: str,
    ) -> pd.DataFrame:
        fq = f'"{schema_name}"."{table_name}"'
        column_names, order_columns = self._sample_columns(
            conn.engine, schema_name, table_name, conn=conn, engine_name=engine_name,
        )
        sample_limit = self._sample_row_limit(engine_name)
        params = {"n": sample_limit}

        if column_names and table_row_count > sample_limit:
            if engine_name == "redshift":
                sql = text(self._build_redshift_sample_sql(
                    schema_name, table_name, column_names, table_row_count, sample_limit,
                ))
            elif order_columns:
                sample_step = max(1, math.ceil(table_row_count / sample_limit))
                sql = text(self._build_systematic_sample_sql(
                    schema_name, table_name, column_names, order_columns,
                ))
                params["step"] = sample_step
            else:
                logger.warning(
                    "No stable ordering columns found for %s.%s; falling back to unordered sampling",
                    schema_name,
                    table_name,
                )
                sql = text(f"SELECT * FROM {fq} LIMIT :n")
        elif order_columns:
            order_clause = " ORDER BY " + ", ".join(self._quote_identifier(column) for column in order_columns)
            sql = text(f"SELECT * FROM {fq}{order_clause} LIMIT :n")
        else:
            logger.warning(
                "No stable ordering columns found for %s.%s; falling back to unordered sampling",
                schema_name,
                table_name,
            )
            sql = text(f"SELECT * FROM {fq} LIMIT :n")

        try:
            result = conn.execute(sql, params)
        except Exception:  # noqa: BLE001
            if engine_name == "redshift":
                logger.debug(
                    "Sampling query failed for %s.%s; falling back to simple LIMIT",
                    schema_name, table_name,
                )
                fallback_sql = text(f"SELECT * FROM {fq} LIMIT :n")
                result = conn.execute(fallback_sql, {"n": sample_limit})
            else:
                raise
        columns = list(result.keys())

        if not columns:
            return pd.DataFrame()

        rows: list[tuple] = []
        batch_size = min(1000, sample_limit)
        while True:
            batch = result.fetchmany(batch_size)
            if not batch:
                break
            rows.extend(batch)

        return pd.DataFrame(rows, columns=columns)

    # ── Profile selected tables ───────────────────────────────────────────
    async def profile_tables(
        self,
        creds: DBCredentials,
        schema_name: str,
        tables: list[str],
        cancel_event: threading.Event | None = None,
    ) -> list[TableProfile]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._sync_profile_tables, creds, schema_name, tables, cancel_event),
                # generous overall timeout: 10s connect + 20s per table query
                timeout=settings.db_connect_timeout
                        + settings.db_query_timeout * max(1, len(tables)) + 5,
            )
        except asyncio.TimeoutError as exc:
            raise DBConnectionError("CONNECTION_TIMEOUT",
                                    f"Profiling exceeded the timeout.") from exc

    def _sync_profile_tables(
        self,
        creds: DBCredentials,
        schema_name: str,
        tables: list[str],
        cancel_event: threading.Event | None = None,
    ) -> list[TableProfile]:
        results: list[TableProfile] = []
        parser = CSVParser()
        sample_limit = self._sample_row_limit(creds.engine)
        with self._engine_for(creds) as engine:
            for tname in tables:
                if cancel_event and cancel_event.is_set():
                    logger.info(
                        "Profiling cancellation acknowledged before table %s.%s",
                        schema_name,
                        tname,
                    )
                    break
                table_started = time.monotonic()

                # Phase 1: Acquire row count (resilient -- retry without session config)
                table_row_count = 0
                try:
                    with engine.connect() as conn:
                        self._configure_profile_session(conn, creds.engine)
                        if creds.engine == "redshift":
                            table_row_count = self._count_table_rows_redshift(
                                conn, schema_name, tname,
                            )
                        else:
                            table_row_count = self._count_table_rows(conn, schema_name, tname)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "Initial count failed for %s.%s (%s); retrying without session config",
                        schema_name, tname, exc,
                    )
                    try:
                        with engine.connect() as conn:
                            if creds.engine == "redshift":
                                table_row_count = self._count_table_rows_redshift(
                                    conn, schema_name, tname,
                                )
                            else:
                                table_row_count = self._count_table_rows(conn, schema_name, tname)
                    except Exception:  # noqa: BLE001
                        pass  # truly cannot count -- row_count stays 0

                # Phase 2: Sample data (row_count preserved on failure)
                try:
                    with engine.connect() as conn:
                        self._configure_profile_session(conn, creds.engine)
                        df = self._read_sample_dataframe(
                            conn, schema_name, tname, table_row_count, creds.engine,
                        )
                    elapsed_ms = int((time.monotonic() - table_started) * 1000)
                    if df.empty:
                        results.append(TableProfile(
                            name=tname, row_count=table_row_count, profiled_row_count=0,
                            column_count=len(df.columns),
                            columns=[],
                        ))
                        logger.info(
                            "Profiled table %s.%s engine=%s row_count=%d profiled_row_count=0 sample_limit=%d elapsed_ms=%d empty=True",
                            schema_name,
                            tname,
                            creds.engine,
                            table_row_count,
                            sample_limit,
                            elapsed_ms,
                        )
                        continue
                    df = parser._try_parse_dates(df)  # noqa: SLF001
                    profile = parser._build_profile(  # noqa: SLF001
                        name=tname, df=df, full_row_count=table_row_count,
                    )
                    # ydata enrichment pass
                    column_dtypes = {cp.name: cp.dtype for cp in profile.columns}
                    enrichment = ydata_enrich(df, column_dtypes)
                    profile.infinite_columns = enrichment.infinite_columns
                    profile.near_constant_columns = enrichment.near_constant_columns
                    profile.type_mismatches = enrichment.type_mismatches
                    profile.correlated_pairs_mixed = enrichment.correlated_pairs_mixed
                    profile.missingness_groups = enrichment.missingness_groups
                    results.append(profile)
                    logger.info(
                        "Profiled table %s.%s engine=%s row_count=%d profiled_row_count=%d sample_limit=%d elapsed_ms=%d",
                        schema_name,
                        tname,
                        creds.engine,
                        profile.row_count,
                        profile.profiled_row_count,
                        sample_limit,
                        elapsed_ms,
                    )
                except Exception as exc:  # noqa: BLE001
                    elapsed_ms = int((time.monotonic() - table_started) * 1000)
                    logger.warning(
                        "Failed to profile table %s.%s engine=%s row_count=%d sample_limit=%d elapsed_ms=%d: %s",
                        schema_name,
                        tname,
                        creds.engine,
                        table_row_count,
                        sample_limit,
                        elapsed_ms,
                        exc,
                    )
                    results.append(TableProfile(
                        name=tname, row_count=table_row_count, column_count=0,
                        columns=[], error=str(exc),
                    ))
        return results

    # ── Engine context manager ────────────────────────────────────────────
    @contextmanager
    def _engine_for(self, creds: DBCredentials) -> Generator[Engine, None, None]:
        """Build a short-lived Engine for one logical operation.
        Translates driver errors into DBConnectionError with stable codes.
        """
        url = _build_url(creds)
        args = _connect_args(creds)
        try:
            engine = create_engine(url, connect_args=args, poolclass=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] engine construction failed: %s", creds.engine, exc)
            code = "UNKNOWN_ERROR"
            raise DBConnectionError(
                code,
                f"Failed to construct engine: {exc}",
                _connection_description(code),
            ) from exc
        try:
            yield engine
        except OperationalError as exc:
            # Common operational failures: auth, network, SSL
            msg = str(exc).lower()
            if "password authentication failed" in msg or "authentication failed" in msg:
                code = "AUTH_FAILED"
                raise DBConnectionError(
                    code,
                    "Authentication failed — check username/password.",
                    _connection_description(code),
                ) from exc
            if "could not translate host name" in msg or "name or service not known" in msg:
                code = "HOST_UNREACHABLE"
                raise DBConnectionError(
                    code,
                    f"Host {creds.host} could not be resolved.",
                    _connection_description(code),
                ) from exc
            if "timeout" in msg or "timed out" in msg:
                code = "CONNECTION_TIMEOUT"
                raise DBConnectionError(
                    code,
                    "Driver-level connection timeout.",
                    _connection_description(code),
                ) from exc
            code = "UNKNOWN_ERROR"
            raise DBConnectionError(code, str(exc), _connection_description(code)) from exc
        except SQLAlchemyError as exc:
            code = "UNKNOWN_ERROR"
            raise DBConnectionError(code, str(exc), _connection_description(code)) from exc
        finally:
            engine.dispose()
