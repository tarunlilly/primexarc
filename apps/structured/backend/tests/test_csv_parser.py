"""CSVParser tests.

Synthetic CSV bytes from `conftest.py` exercise the full bytes → DataFrame →
TableProfile path. Other tests build smaller CSV bytes inline.
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.csv_parser import CSVParseError, CSVParser


@pytest.fixture
def parser() -> CSVParser:
    return CSVParser()


# ─── Happy path on the canonical fixture ──────────────────────────────────

def test_parse_taltz_produces_six_string_columns(parser, taltz_bytes):
    profile = parser.parse("taltz_trust_segmentation.csv", taltz_bytes)
    assert profile.column_count == 6
    assert profile.row_count == 60
    assert profile.profiled_row_count == 60
    names = [c.name for c in profile.columns]
    assert names == ["TRUST_ID", "TRUST_NAME", "PRIORITY",
                     "FORMULARY_POSITION", "POSITION", "INDICATION"]
    # All columns are categorical / object → "string"
    for c in profile.columns:
        assert c.dtype == "string", f"{c.name} expected string, got {c.dtype}"


def test_parse_taltz_detects_nulls_in_optional_columns(parser, taltz_bytes):
    profile = parser.parse("taltz_trust_segmentation.csv", taltz_bytes)
    fp = next(c for c in profile.columns if c.name == "FORMULARY_POSITION")
    ind = next(c for c in profile.columns if c.name == "INDICATION")
    assert fp.null_count >= 1   # the fixture has gaps in these two cols
    assert ind.null_count >= 1


def test_parse_taltz_finds_unique_pk_candidate(parser, taltz_bytes):
    """TRUST_ID is 100% unique and 0% null — should be a PK candidate."""
    profile = parser.parse("taltz_trust_segmentation.csv", taltz_bytes)
    tid = next(c for c in profile.columns if c.name == "TRUST_ID")
    assert tid.null_count == 0
    assert tid.unique_count == profile.row_count


# ─── Error handling ───────────────────────────────────────────────────────

def test_parse_empty_bytes_raises(parser):
    with pytest.raises(CSVParseError):
        parser.parse("empty.csv", b"")


def test_parse_garbage_bytes_raises(parser):
    """Random non-CSV bytes shouldn't crash — should raise cleanly."""
    with pytest.raises(CSVParseError):
        parser.parse("garbage.csv", b"\x00\x01\x02\x03 not csv at all")


# ─── Date inference ───────────────────────────────────────────────────────

def test_parse_infers_datetime_for_date_named_columns(parser):
    csv = (
        b"id,event_date,name\n"
        b"1,2024-01-15,alpha\n"
        b"2,2024-02-20,beta\n"
        b"3,2024-03-25,gamma\n"
        b"4,2024-04-30,delta\n"
    )
    profile = parser.parse("dates.csv", csv)
    event = next(c for c in profile.columns if c.name == "event_date")
    assert event.dtype == "datetime"
    assert event.earliest is not None
    assert event.latest is not None


def test_parse_infers_datetime_for_dt_named_columns(parser):
    csv = (
        b"id,created_dt,updated_dt\n"
        b"1,2024-01-15,2024-01-16\n"
        b"2,2024-02-20,2024-02-21\n"
        b"3,2024-03-25,2024-03-26\n"
        b"4,2024-04-30,2024-05-01\n"
    )
    profile = parser.parse("audit_dt.csv", csv)
    created = next(c for c in profile.columns if c.name == "created_dt")
    updated = next(c for c in profile.columns if c.name == "updated_dt")
    assert created.dtype == "datetime"
    assert updated.dtype == "datetime"


def test_parse_scans_beyond_exported_samples_for_pii_patterns(parser):
    csv = (
        b"id,notes\n"
        b"1,alpha\n"
        b"2,beta\n"
        b"3,gamma\n"
        b"4,delta\n"
        b"5,epsilon\n"
        b"6,John Smith\n"
    )
    profile = parser.parse("pii_scan.csv", csv)
    notes = next(c for c in profile.columns if c.name == "notes")
    assert len(notes.sample_values) == 5
    assert notes.value_pattern_counts["scanned"] == 6
    assert notes.value_pattern_counts["person_name"] == 1


def test_parse_skips_date_inference_when_majority_unparseable(parser):
    """Don't promote a column to datetime if most values can't parse."""
    csv = (
        b"id,fake_date\n"
        b"1,not_a_date_one\n"
        b"2,not_a_date_two\n"
        b"3,2024-01-15\n"
        b"4,still_not_a_date\n"
    )
    profile = parser.parse("partial.csv", csv)
    fake = next(c for c in profile.columns if c.name == "fake_date")
    assert fake.dtype == "string"  # NOT promoted to datetime


# ─── Numeric handling ─────────────────────────────────────────────────────

def test_parse_populates_numeric_stats(parser):
    csv = (
        b"row_id,score\n"
        b"1,10\n2,20\n3,30\n4,40\n5,50\n6,60\n7,70\n8,80\n9,90\n10,100\n"
    )
    profile = parser.parse("nums.csv", csv)
    score = next(c for c in profile.columns if c.name == "score")
    assert score.dtype == "int"
    assert score.mean == 55.0
    assert score.min_value == 10.0
    assert score.max_value == 100.0
    assert score.quartiles is not None and len(score.quartiles) == 3


# ─── Sample truncation ────────────────────────────────────────────────────

def test_parse_truncates_long_sample_values(parser):
    long_val = "x" * 200
    csv = ("id,description\n" + "\n".join(f"{i},{long_val}" for i in range(3))).encode()
    profile = parser.parse("long.csv", csv)
    desc = next(c for c in profile.columns if c.name == "description")
    for sample in desc.sample_values:
        assert len(sample) <= 40, f"sample exceeded 40 chars: {len(sample)}"


# ─── Row-cap behaviour ────────────────────────────────────────────────────

def test_parse_caps_rows_for_profiling(parser, monkeypatch):
    """When a CSV exceeds max_rows_per_table, the profiled slice is capped."""
    from config import settings
    monkeypatch.setattr(settings, "max_rows_per_table", 10)

    csv_lines = ["id,name"] + [f"{i},name_{i}" for i in range(50)]
    csv = "\n".join(csv_lines).encode()
    profile = parser.parse("big.csv", csv)
    assert profile.row_count == 50
    assert profile.profiled_row_count == 10


def test_parse_counts_rows_with_non_comma_delimiters(parser, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "max_rows_per_table", 2)

    csv = b"id|name\n1|alpha\n2|beta\n3|gamma\n"
    profile = parser.parse("pipe.csv", csv)

    assert profile.row_count == 3
    assert profile.profiled_row_count == 2


def test_read_dataframe_uses_sniffed_delimiter_with_c_engine(parser, mocker):
    fake_df = pd.DataFrame({"id": [1], "name": ["alpha"]})
    read_csv = mocker.patch("core.csv_parser.pd.read_csv", return_value=fake_df)

    df = parser._read_dataframe(b"id|name\n1|alpha\n", "|")

    assert df.equals(fake_df)
    assert read_csv.call_count == 1
    assert read_csv.call_args.kwargs["sep"] == "|"
    assert read_csv.call_args.kwargs["engine"] == "c"


def test_read_dataframe_falls_back_to_python_engine(parser, mocker):
    fake_df = pd.DataFrame({"id": [1], "name": ["alpha"]})
    read_csv = mocker.patch(
        "core.csv_parser.pd.read_csv",
        side_effect=[ValueError("c-engine failed"), fake_df],
    )

    df = parser._read_dataframe(b"id,name\n1,alpha\n", ",")

    assert df.equals(fake_df)
    assert read_csv.call_count == 2
    assert read_csv.call_args_list[0].kwargs["engine"] == "c"
    assert read_csv.call_args_list[1].kwargs["engine"] == "python"
