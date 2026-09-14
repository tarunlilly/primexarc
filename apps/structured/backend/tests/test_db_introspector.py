"""DBIntrospector tests — mocked so no real network calls happen.

Coverage:
- URL construction for postgres + redshift
- connect_args carries the timeout
- Error message → error code translation via the OperationalError path
- asyncio.wait_for timeout fires within bound
"""
from __future__ import annotations

import asyncio
import time
from contextlib import nullcontext

import pytest
from sqlalchemy.exc import OperationalError

from core.db_introspector import (
    DBConnectionError,
    DBIntrospector,
    _build_url,
    _connect_args,
)
from core.models import DBCredentials


# ─── Helpers ──────────────────────────────────────────────────────────────

def _creds(engine="postgres", password="secret"):
    return DBCredentials(
        engine=engine,
        host="db.internal.lilly.com",
        port=5432 if engine == "postgres" else 5439,
        database="analytics_prod",
        username="reader",
        password=password,
        ssl=True,
    )


# ─── URL construction ─────────────────────────────────────────────────────

def test_build_url_postgres_uses_psycopg_driver():
    url = _build_url(_creds("postgres"))
    assert url.startswith("postgresql+psycopg2://")
    assert "reader:secret@" in url
    assert "@db.internal.lilly.com:5432/analytics_prod" in url


def test_build_url_redshift_uses_redshift_connector_driver():
    url = _build_url(_creds("redshift"))
    assert url.startswith("redshift+redshift_connector://")
    assert "reader:secret@" in url


def test_build_url_url_encodes_password_special_chars():
    """Passwords with @, :, /, etc. must be URL-encoded or they corrupt the URL."""
    url = _build_url(_creds(password="p@ss:word/with"))
    assert "p%40ss%3Aword%2Fwith" in url
    # The literal special chars should NOT appear in the credentials section
    creds_section = url.split("@db.internal.lilly.com")[0]
    assert "p@ss" not in creds_section[len("postgresql+psycopg://"):]


def test_connect_args_postgres_includes_timeout_and_ssl():
    args = _connect_args(_creds("postgres"))
    assert "connect_timeout" in args
    assert args["connect_timeout"] >= 1
    assert args.get("sslmode") in ("require", "prefer")


def test_connect_args_redshift_includes_timeout_and_ssl():
    args = _connect_args(_creds("redshift"))
    assert "timeout" in args
    assert "ssl" in args


# ─── Error code translation ───────────────────────────────────────────────
# These exercise the OperationalError → DBConnectionError mapping in
# _engine_for(). We mock create_engine/engine.connect to raise.

def test_auth_failed_maps_to_auth_failed_code(mocker):
    introspector = DBIntrospector()
    fake_engine = mocker.MagicMock()
    fake_engine.connect.side_effect = OperationalError(
        "FATAL: password authentication failed for user 'reader'", {}, Exception(),
    )
    mocker.patch("core.db_introspector.create_engine", return_value=fake_engine)

    with pytest.raises(DBConnectionError) as exc_info:
        introspector._sync_connect_and_ping(_creds())
    assert exc_info.value.code == "AUTH_FAILED"
    assert "username/password" in exc_info.value.description.lower()


def test_host_unreachable_maps_to_host_unreachable_code(mocker):
    introspector = DBIntrospector()
    fake_engine = mocker.MagicMock()
    fake_engine.connect.side_effect = OperationalError(
        "could not translate host name 'bad-host' to address", {}, Exception(),
    )
    mocker.patch("core.db_introspector.create_engine", return_value=fake_engine)

    with pytest.raises(DBConnectionError) as exc_info:
        introspector._sync_connect_and_ping(_creds())
    assert exc_info.value.code == "HOST_UNREACHABLE"
    assert "whitelist" in exc_info.value.description.lower() or "allowlist" in exc_info.value.description.lower()


def test_driver_timeout_maps_to_connection_timeout_code(mocker):
    introspector = DBIntrospector()
    fake_engine = mocker.MagicMock()
    fake_engine.connect.side_effect = OperationalError(
        "connection timed out", {}, Exception(),
    )
    mocker.patch("core.db_introspector.create_engine", return_value=fake_engine)

    with pytest.raises(DBConnectionError) as exc_info:
        introspector._sync_connect_and_ping(_creds())
    assert exc_info.value.code == "CONNECTION_TIMEOUT"
    assert "whitelist" in exc_info.value.description.lower() or "credentials" in exc_info.value.description.lower()


def test_unknown_operational_error_maps_to_unknown(mocker):
    introspector = DBIntrospector()
    fake_engine = mocker.MagicMock()
    fake_engine.connect.side_effect = OperationalError(
        "something weird happened", {}, Exception(),
    )
    mocker.patch("core.db_introspector.create_engine", return_value=fake_engine)

    with pytest.raises(DBConnectionError) as exc_info:
        introspector._sync_connect_and_ping(_creds())
    assert exc_info.value.code == "UNKNOWN_ERROR"


def test_sync_list_tables_uses_single_catalog_query(mocker):
    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_result = mocker.MagicMock()
    fake_result.mappings.return_value.all.return_value = [
        {"name": "claims", "column_count": 12},
        {"name": "members", "column_count": 5},
    ]
    fake_conn.execute.return_value = fake_result

    fake_engine = mocker.MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = fake_conn
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    tables = introspector._sync_list_tables(_creds(), "analytics")

    assert [(t.name, t.column_count) for t in tables] == [
        ("claims", 12),
        ("members", 5),
    ]
    assert fake_conn.execute.call_count == 1
    _sql, params = fake_conn.execute.call_args.args
    assert params == {"schema_name": "analytics"}


def test_sync_profile_tables_uses_db_row_cap_and_statement_timeout(mocker, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "max_rows_per_db_table", 7)
    monkeypatch.setattr(settings, "max_rows_per_redshift_table", 50_000)
    monkeypatch.setattr(settings, "db_query_timeout", 9)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_count_result = mocker.MagicMock()
    fake_count_result.scalar.return_value = 25_000
    fake_result = mocker.MagicMock()
    fake_result.keys.return_value = ["id", "created_at"]
    fake_result.fetchmany.side_effect = [
        [
            (1, "2024-01-01T00:00:00"),
            (2, "2024-01-02T00:00:00"),
        ],
        [],
    ]
    # Phase 1: statement_timeout + COUNT; Phase 2: statement_timeout + sample query
    fake_conn.execute.side_effect = [None, fake_count_result, None, fake_result]

    fake_engine = mocker.MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = fake_conn
    fake_inspector = mocker.MagicMock()
    fake_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
    fake_inspector.get_columns.return_value = [
        {"name": "id", "type": mocker.MagicMock(__class__=type("IntegerType", (), {}))},
        {"name": "created_at", "type": mocker.MagicMock(__class__=type("DateTimeType", (), {}))},
    ]
    mocker.patch("core.db_introspector.inspect", return_value=fake_inspector)
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    profiles = introspector._sync_profile_tables(_creds(), "analytics", ["claims"])

    assert len(profiles) == 1
    assert profiles[0].name == "claims"
    assert profiles[0].row_count == 25_000
    assert profiles[0].profiled_row_count == 2
    assert fake_conn.execute.call_count == 4
    assert fake_result.fetchall.called is False

    timeout_stmt = str(fake_conn.execute.call_args_list[0].args[0])
    assert "statement_timeout" in timeout_stmt
    assert "9000" in timeout_stmt

    count_sql = str(fake_conn.execute.call_args_list[1].args[0])
    assert "SELECT COUNT(*) AS row_count FROM \"analytics\".\"claims\"" in count_sql

    sample_sql, params = fake_conn.execute.call_args_list[3].args
    sample_sql_text = str(sample_sql)
    assert "ROW_NUMBER() OVER (ORDER BY \"id\") AS _arc_rn" in sample_sql_text
    assert "SELECT \"id\", \"created_at\" FROM ranked" in sample_sql_text
    assert "WHERE MOD(_arc_rn - 1, :step) = 0" in sample_sql_text
    assert params == {"n": 7, "step": 3572}


def test_sync_profile_tables_uses_redshift_specific_row_cap(mocker, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "max_rows_per_db_table", 150_000)
    monkeypatch.setattr(settings, "max_rows_per_redshift_table", 50_000)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    # svv_table_info lookup for Redshift
    fake_svv_result = mocker.MagicMock()
    fake_svv_result.fetchone.return_value = (125_000,)
    fake_result = mocker.MagicMock()
    fake_result.keys.return_value = ["id", "created_at"]
    fake_result.fetchmany.side_effect = [
        [
            (1, "2024-01-01T00:00:00"),
            (2, "2024-01-02T00:00:00"),
        ],
        [],
    ]
    # Phase 1: statement_timeout + svv_table_info; Phase 2: statement_timeout + sample
    fake_conn.execute.side_effect = [None, fake_svv_result, None, fake_result]

    fake_engine = mocker.MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = fake_conn
    fake_inspector = mocker.MagicMock()
    fake_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
    fake_inspector.get_columns.return_value = [
        {"name": "id", "type": mocker.MagicMock(__class__=type("IntegerType", (), {}))},
        {"name": "created_at", "type": mocker.MagicMock(__class__=type("DateTimeType", (), {}))},
    ]
    mocker.patch("core.db_introspector.inspect", return_value=fake_inspector)
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    profiles = introspector._sync_profile_tables(_creds("redshift"), "analytics", ["claims"])

    assert len(profiles) == 1
    assert profiles[0].row_count == 125_000
    assert profiles[0].profiled_row_count == 2

    # Redshift should use TABLESAMPLE, not ROW_NUMBER
    sample_sql = str(fake_conn.execute.call_args_list[3].args[0])
    assert "TABLESAMPLE SYSTEM" in sample_sql
    assert "ROW_NUMBER" not in sample_sql


def test_sync_profile_tables_preserves_empty_table_row_count(mocker, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "max_rows_per_db_table", 5)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_count_result = mocker.MagicMock()
    fake_count_result.scalar.return_value = 0
    fake_result = mocker.MagicMock()
    fake_result.keys.return_value = ["id", "created_at"]
    fake_result.fetchmany.side_effect = [[]]
    # Phase 1: statement_timeout + COUNT; Phase 2: statement_timeout + sample
    fake_conn.execute.side_effect = [None, fake_count_result, None, fake_result]

    fake_engine = mocker.MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = fake_conn
    fake_inspector = mocker.MagicMock()
    fake_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
    fake_inspector.get_columns.return_value = [
        {"name": "id", "type": mocker.MagicMock(__class__=type("IntegerType", (), {}))},
        {"name": "created_at", "type": mocker.MagicMock(__class__=type("DateTimeType", (), {}))},
    ]
    mocker.patch("core.db_introspector.inspect", return_value=fake_inspector)
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    profiles = introspector._sync_profile_tables(_creds(), "analytics", ["claims"])

    assert len(profiles) == 1
    assert profiles[0].row_count == 0
    assert profiles[0].profiled_row_count == 0
    assert profiles[0].column_count == 2
    assert profiles[0].columns == []


def test_sync_profile_tables_orders_by_columns_when_no_primary_key(mocker, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "max_rows_per_db_table", 3)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_count_result = mocker.MagicMock()
    fake_count_result.scalar.return_value = 9
    fake_result = mocker.MagicMock()
    fake_result.keys.return_value = ["created_at", "region"]
    fake_result.fetchmany.side_effect = [[("2024-01-01", "EMEA")], []]
    # Phase 1: statement_timeout + COUNT; Phase 2: statement_timeout + sample
    fake_conn.execute.side_effect = [None, fake_count_result, None, fake_result]

    fake_engine = mocker.MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = fake_conn
    fake_inspector = mocker.MagicMock()
    fake_inspector.get_pk_constraint.return_value = {"constrained_columns": []}
    fake_inspector.get_columns.return_value = [
        {"name": "created_at", "type": mocker.MagicMock(__class__=type("DateTimeType", (), {}))},
        {"name": "region", "type": mocker.MagicMock(__class__=type("StringType", (), {}))},
    ]
    mocker.patch("core.db_introspector.inspect", return_value=fake_inspector)
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    introspector._sync_profile_tables(_creds(), "analytics", ["claims"])

    sample_sql = str(fake_conn.execute.call_args_list[3].args[0])
    assert "ROW_NUMBER() OVER (ORDER BY \"created_at\", \"region\") AS _arc_rn" in sample_sql
    _sample_sql, params = fake_conn.execute.call_args_list[3].args
    assert params == {"n": 3, "step": 3}


# ─── Async timeout behavior ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_test_connection_caps_at_asyncio_timeout(mocker, monkeypatch):
    """If the underlying sync call hangs, asyncio.wait_for should fire."""
    from config import settings
    monkeypatch.setattr(settings, "db_connect_timeout", 1)  # 1s for fast test

    def hang(_creds):
        import time
        time.sleep(5)  # would exceed the 1+1s timeout

    introspector = DBIntrospector()
    mocker.patch.object(introspector, "_sync_connect_and_ping", side_effect=hang)
    ok, code, _detail, description, _elapsed = await introspector.test_connection(_creds())
    assert not ok
    assert code == "CONNECTION_TIMEOUT"
    assert description


@pytest.mark.asyncio
async def test_test_connection_returns_ok_on_success(mocker):
    introspector = DBIntrospector()
    mocker.patch.object(introspector, "_sync_connect_and_ping", return_value=None)
    ok, code, detail, description, elapsed = await introspector.test_connection(_creds())
    assert ok is True
    assert code == "OK"
    assert elapsed >= 0
    assert description == ""


@pytest.mark.asyncio
async def test_list_tables_caps_at_asyncio_timeout(mocker, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "db_connect_timeout", 1)
    monkeypatch.setattr(settings, "db_query_timeout", 1)

    def hang(_creds, _schema_name):
        time.sleep(5)

    introspector = DBIntrospector()
    mocker.patch.object(introspector, "_sync_list_tables", side_effect=hang)

    with pytest.raises(DBConnectionError) as exc_info:
        await introspector.list_tables(_creds(), "public")

    assert exc_info.value.code == "CONNECTION_TIMEOUT"


# ─── Redshift-specific fixes ────────────────────────────────────────────────


def test_configure_profile_session_redshift_tolerates_failure(mocker):
    """On Redshift, SET statement_timeout failure should not propagate."""
    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_conn.execute.side_effect = Exception("permission denied for SET")

    # Redshift: should NOT raise
    introspector._configure_profile_session(fake_conn, "redshift")

    # Postgres: SHOULD raise
    fake_conn.execute.side_effect = Exception("permission denied for SET")
    with pytest.raises(Exception, match="permission denied"):
        introspector._configure_profile_session(fake_conn, "postgres")


def test_count_table_rows_redshift_uses_svv_table_info(mocker):
    """When svv_table_info has a row count, use it without falling back to COUNT(*)."""
    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_svv_result = mocker.MagicMock()
    fake_svv_result.fetchone.return_value = (42_000,)
    fake_conn.execute.return_value = fake_svv_result

    count = introspector._count_table_rows_redshift(fake_conn, "analytics", "events")

    assert count == 42_000
    # Should only call execute once (svv_table_info query), no fallback
    assert fake_conn.execute.call_count == 1
    sql_text = str(fake_conn.execute.call_args.args[0])
    assert "svv_table_info" in sql_text


def test_count_table_rows_redshift_falls_back_to_count_star(mocker):
    """When svv_table_info returns no rows, fall back to COUNT(*)."""
    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    # First call: svv_table_info returns no row
    fake_svv_result = mocker.MagicMock()
    fake_svv_result.fetchone.return_value = None
    # Second call: COUNT(*) returns actual count
    fake_count_result = mocker.MagicMock()
    fake_count_result.scalar.return_value = 7_500
    fake_conn.execute.side_effect = [fake_svv_result, fake_count_result]

    count = introspector._count_table_rows_redshift(fake_conn, "analytics", "events")

    assert count == 7_500
    assert fake_conn.execute.call_count == 2


def test_count_table_rows_redshift_falls_back_on_svv_exception(mocker):
    """When svv_table_info query raises (permission denied), fall back to COUNT(*)."""
    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    # First call: svv_table_info raises
    # Second call: COUNT(*) returns actual count
    fake_count_result = mocker.MagicMock()
    fake_count_result.scalar.return_value = 3_000
    fake_conn.execute.side_effect = [Exception("permission denied"), fake_count_result]

    count = introspector._count_table_rows_redshift(fake_conn, "analytics", "events")

    assert count == 3_000


def test_build_redshift_sample_sql_uses_tablesample():
    """Redshift sample SQL should use TABLESAMPLE SYSTEM, not ROW_NUMBER."""
    introspector = DBIntrospector()
    sql = introspector._build_redshift_sample_sql(
        schema_name="analytics",
        table_name="events",
        column_names=["id", "event_type", "created_at"],
        table_row_count=500_000,
        sample_limit=10_000,
    )

    assert "TABLESAMPLE SYSTEM(" in sql
    assert "LIMIT :n" in sql
    assert "ROW_NUMBER" not in sql
    assert '"analytics"."events"' in sql
    assert '"id"' in sql
    assert '"event_type"' in sql
    assert '"created_at"' in sql
    # Percentage should be ~3% (10000*1.5/500000*100 = 3.0)
    assert "3.0000" in sql


def test_sync_profile_tables_preserves_row_count_on_sample_failure(mocker, monkeypatch):
    """When sampling fails but COUNT succeeds, row_count must be preserved (not 0)."""
    from config import settings

    monkeypatch.setattr(settings, "max_rows_per_db_table", 10_000)

    introspector = DBIntrospector()

    call_count = [0]

    def fake_connect():
        cm = mocker.MagicMock()
        conn = mocker.MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            # Phase 1: count succeeds
            fake_count_result = mocker.MagicMock()
            fake_count_result.scalar.return_value = 50_000
            conn.execute.side_effect = [None, fake_count_result]
        else:
            # Phase 2: sampling fails
            conn.execute.side_effect = [None, Exception("query timeout after 120s")]
        cm.__enter__ = mocker.MagicMock(return_value=conn)
        cm.__exit__ = mocker.MagicMock(return_value=False)
        return cm

    fake_engine = mocker.MagicMock()
    fake_engine.connect = fake_connect
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    profiles = introspector._sync_profile_tables(_creds(), "analytics", ["big_table"])

    assert len(profiles) == 1
    # Critical: row_count preserved from phase 1, NOT zeroed out
    assert profiles[0].row_count == 50_000
    assert profiles[0].error is not None
    assert "timeout" in profiles[0].error


def test_sync_list_tables_includes_views_when_configured(mocker, monkeypatch):
    """When db_include_views=True, SQL should include VIEW in table_type filter."""
    from config import settings
    monkeypatch.setattr(settings, "db_include_views", True)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_result = mocker.MagicMock()
    fake_result.mappings.return_value.all.return_value = [
        {"name": "base_table", "column_count": 5},
        {"name": "my_view", "column_count": 3},
    ]
    fake_conn.execute.return_value = fake_result

    fake_engine = mocker.MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = fake_conn
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    tables = introspector._sync_list_tables(_creds(), "analytics")

    assert len(tables) == 2
    sql_text = str(fake_conn.execute.call_args.args[0])
    assert "'VIEW'" in sql_text
    assert "'BASE TABLE'" in sql_text


def test_sync_list_tables_excludes_views_when_disabled(mocker, monkeypatch):
    """When db_include_views=False, SQL should only include BASE TABLE."""
    from config import settings
    monkeypatch.setattr(settings, "db_include_views", False)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_result = mocker.MagicMock()
    fake_result.mappings.return_value.all.return_value = [
        {"name": "base_table", "column_count": 5},
    ]
    fake_conn.execute.return_value = fake_result

    fake_engine = mocker.MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = fake_conn
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    tables = introspector._sync_list_tables(_creds(), "analytics")

    assert len(tables) == 1
    sql_text = str(fake_conn.execute.call_args.args[0])
    assert "'BASE TABLE'" in sql_text
    assert "'VIEW'" not in sql_text


def test_read_sample_dataframe_uses_tablesample_for_redshift(mocker, monkeypatch):
    """When engine is redshift and rows > limit, TABLESAMPLE should be used."""
    from config import settings
    monkeypatch.setattr(settings, "max_rows_per_db_table", 10_000)
    monkeypatch.setattr(settings, "max_rows_per_redshift_table", 10_000)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_result = mocker.MagicMock()
    fake_result.keys.return_value = ["id", "value"]
    fake_result.fetchmany.side_effect = [[(1, "a"), (2, "b")], []]
    fake_conn.execute.return_value = fake_result
    fake_conn.engine = mocker.MagicMock()

    fake_inspector = mocker.MagicMock()
    fake_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
    fake_inspector.get_columns.return_value = [
        {"name": "id", "type": mocker.MagicMock(__class__=type("IntegerType", (), {}))},
        {"name": "value", "type": mocker.MagicMock(__class__=type("StringType", (), {}))},
    ]
    mocker.patch("core.db_introspector.inspect", return_value=fake_inspector)

    df = introspector._read_sample_dataframe(
        fake_conn, "analytics", "big_table", 200_000, "redshift",
    )

    assert len(df) == 2
    sql_text = str(fake_conn.execute.call_args.args[0])
    assert "TABLESAMPLE SYSTEM" in sql_text
    assert "ROW_NUMBER" not in sql_text


def test_sync_list_tables_uses_pg_catalog_for_redshift(mocker, monkeypatch):
    """Redshift should use pg_catalog instead of information_schema for table listing."""
    from config import settings
    monkeypatch.setattr(settings, "db_include_views", True)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_result = mocker.MagicMock()
    fake_result.mappings.return_value.all.return_value = [
        {"name": "events", "column_count": 15},
        {"name": "events_view", "column_count": 8},
    ]
    fake_conn.execute.return_value = fake_result

    fake_engine = mocker.MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = fake_conn
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    tables = introspector._sync_list_tables(_creds("redshift"), "analytics")

    assert len(tables) == 2
    assert tables[0].name == "events"
    assert tables[0].column_count == 15
    sql_text = str(fake_conn.execute.call_args.args[0])
    assert "pg_catalog.pg_class" in sql_text
    assert "pg_catalog.pg_attribute" in sql_text
    assert "information_schema" not in sql_text


def test_sync_list_tables_still_uses_information_schema_for_postgres(mocker, monkeypatch):
    """Postgres should still use information_schema (it works fine there)."""
    from config import settings
    monkeypatch.setattr(settings, "db_include_views", True)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_result = mocker.MagicMock()
    fake_result.mappings.return_value.all.return_value = [
        {"name": "users", "column_count": 10},
    ]
    fake_conn.execute.return_value = fake_result

    fake_engine = mocker.MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = fake_conn
    mocker.patch.object(introspector, "_engine_for", return_value=nullcontext(fake_engine))

    tables = introspector._sync_list_tables(_creds("postgres"), "public")

    assert len(tables) == 1
    sql_text = str(fake_conn.execute.call_args.args[0])
    assert "information_schema" in sql_text
    assert "pg_catalog.pg_class" not in sql_text


def test_sample_columns_uses_pg_catalog_fallback_on_redshift(mocker):
    """When inspector.get_columns fails on Redshift, fall back to pg_catalog."""
    introspector = DBIntrospector()
    fake_engine = mocker.MagicMock()
    fake_conn = mocker.MagicMock()

    # Inspector fails (returns empty)
    fake_inspector = mocker.MagicMock()
    fake_inspector.get_columns.side_effect = Exception("relation does not exist")
    fake_inspector.get_pk_constraint.return_value = {"constrained_columns": []}
    mocker.patch("core.db_introspector.inspect", return_value=fake_inspector)

    # pg_catalog fallback returns columns
    fake_pg_result = mocker.MagicMock()
    fake_pg_result.fetchall.return_value = [("id",), ("event_type",), ("created_at",)]
    fake_conn.execute.return_value = fake_pg_result

    column_names, order_columns = introspector._sample_columns(
        fake_engine, "analytics", "late_binding_view",
        conn=fake_conn, engine_name="redshift",
    )

    assert column_names == ["id", "event_type", "created_at"]
    # With no type info from inspector, uses first 3 columns for ordering
    assert order_columns == ["id", "event_type", "created_at"]
    # Verify pg_catalog was queried
    sql_text = str(fake_conn.execute.call_args.args[0])
    assert "pg_catalog.pg_attribute" in sql_text


def test_sample_columns_returns_empty_when_both_paths_fail(mocker):
    """When both inspector AND pg_catalog fail, return empty lists gracefully."""
    introspector = DBIntrospector()
    fake_engine = mocker.MagicMock()
    fake_conn = mocker.MagicMock()

    # Inspector fails
    fake_inspector = mocker.MagicMock()
    fake_inspector.get_columns.side_effect = Exception("relation does not exist")
    mocker.patch("core.db_introspector.inspect", return_value=fake_inspector)

    # pg_catalog also fails
    fake_conn.execute.side_effect = Exception("permission denied")

    column_names, order_columns = introspector._sample_columns(
        fake_engine, "analytics", "inaccessible_view",
        conn=fake_conn, engine_name="redshift",
    )

    assert column_names == []
    assert order_columns == []


def test_read_sample_dataframe_falls_back_on_query_failure(mocker, monkeypatch):
    """When TABLESAMPLE fails on Redshift, fall back to simple SELECT * LIMIT."""
    from config import settings
    monkeypatch.setattr(settings, "max_rows_per_db_table", 10_000)
    monkeypatch.setattr(settings, "max_rows_per_redshift_table", 10_000)

    introspector = DBIntrospector()
    fake_conn = mocker.MagicMock()
    fake_conn.engine = mocker.MagicMock()

    # First execute: TABLESAMPLE fails; Second execute: LIMIT succeeds
    fake_fallback_result = mocker.MagicMock()
    fake_fallback_result.keys.return_value = ["id", "name", "status"]
    fake_fallback_result.fetchmany.side_effect = [[(1, "alice", "active"), (2, "bob", "inactive")], []]
    fake_conn.execute.side_effect = [
        Exception("TABLESAMPLE clause is not supported for this relation type"),
        fake_fallback_result,
    ]

    fake_inspector = mocker.MagicMock()
    fake_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
    fake_inspector.get_columns.return_value = [
        {"name": "id", "type": mocker.MagicMock(__class__=type("IntegerType", (), {}))},
        {"name": "name", "type": mocker.MagicMock(__class__=type("StringType", (), {}))},
        {"name": "status", "type": mocker.MagicMock(__class__=type("StringType", (), {}))},
    ]
    mocker.patch("core.db_introspector.inspect", return_value=fake_inspector)

    df = introspector._read_sample_dataframe(
        fake_conn, "analytics", "large_view", 50_000, "redshift",
    )

    # Should have data from fallback
    assert len(df) == 2
    assert list(df.columns) == ["id", "name", "status"]
    # First call was TABLESAMPLE (failed), second was LIMIT (succeeded)
    assert fake_conn.execute.call_count == 2
    fallback_sql = str(fake_conn.execute.call_args_list[1].args[0])
    assert "LIMIT" in fallback_sql
    assert "TABLESAMPLE" not in fallback_sql
