from __future__ import annotations

from config import Settings


def test_history_db_url_enabled_when_host_present():
    settings = Settings(
        db_host="history.internal",
        db_name="arc",
        db_user="reader",
        db_password="secret",
    )

    assert settings.history_db_url.startswith("postgresql+asyncpg://reader:secret@history.internal:5432/")


def test_history_db_url_disabled_when_no_host():
    settings = Settings(
        db_host="",
        db_name="arc",
        db_user="reader",
        db_password="secret",
    )

    assert settings.history_db_url == ""


def test_history_db_url_disabled_when_explicitly_false():
    settings = Settings(
        history_db_enabled=False,
        db_host="history.internal",
        db_name="arc",
        db_user="reader",
        db_password="secret",
    )

    assert settings.history_db_url == ""
