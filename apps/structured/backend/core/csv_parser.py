"""CSVParser — reads an uploaded CSV, returns TableProfile.

Privacy guarantee from CLAUDE.md: raw rows never leave this module. Only
profile-level statistics (counts, dtypes, samples truncated to 40 chars)
flow downstream into the scorer.

ydata-profiling integration: after the fast pandas-based profiling pass,
the enricher (core/ydata_enricher.py) runs in minimal mode to extract
ML-signal-quality metrics (near-constants, infinites, type mismatches,
Phi_k correlations, missingness patterns). These feed dimension rules in
the "Feature & Signal Readiness" dimension. Controlled by settings.ydata_enabled.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from typing import IO

import pandas as pd
import numpy as np

from config import settings
from core.models import ColumnProfile, DType, TableProfile
from core.ydata_enricher import enrich as ydata_enrich

logger = logging.getLogger(__name__)

# Sentinel values that masquerade as data but mean "missing"
_SURROGATE_NULL_TOKENS = frozenset({
    "-1", "999", "9999", "-999", "n/a", "na", "none", "null",
    "unknown", "unk", ".", "?", "missing", "",
})
_NUMERIC_SURROGATE_VALUES = frozenset({-1, -999, 999, 9999})


_PANDAS_TO_DTYPE: dict[str, DType] = {
    "int64": "int", "int32": "int", "int16": "int", "int8": "int",
    "Int64": "int", "Int32": "int",
    "float64": "float", "float32": "float", "Float64": "float",
    "bool": "bool", "boolean": "bool",
    "object": "string", "string": "string",
    "datetime64[ns]": "datetime",
    "datetime64[ns, UTC]": "datetime",
}

_VALUE_SCAN_LIMIT = 100
_EMAIL_VALUE_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SSN_VALUE_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_PERSON_NAME_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]{1,29}$")
_ORG_NAME_STOPWORDS = {
    "association", "center", "centre", "clinic", "company", "corp",
    "corporation", "foundation", "group", "health", "hospital", "inc",
    "institute", "llc", "ltd", "network", "org", "pharma", "services",
    "system", "systems", "team", "university",
}
_SUPPORTED_DELIMITERS = ",;\t|"


def _coerce_dtype(pd_dtype: str) -> DType:
    if pd_dtype in _PANDAS_TO_DTYPE:
        return _PANDAS_TO_DTYPE[pd_dtype]
    if "datetime" in pd_dtype:
        return "datetime"
    if "int" in pd_dtype:
        return "int"
    if "float" in pd_dtype:
        return "float"
    return "object"


def _truncate(v: object, limit: int = 40) -> str:
    s = "" if v is None else str(v)
    return s[: limit - 1] + "…" if len(s) > limit else s


def _looks_like_person_name(value: object) -> bool:
    text = " ".join(str(value).replace(",", " ").split()).strip()
    if not text or len(text) > 80 or "@" in text:
        return False
    if any(ch.isdigit() for ch in text):
        return False

    tokens = [token.strip(".") for token in text.split(" ") if token]
    if not 2 <= len(tokens) <= 4:
        return False
    if any(token.lower() in _ORG_NAME_STOPWORDS for token in tokens):
        return False
    return all(_PERSON_NAME_TOKEN_RE.fullmatch(token) for token in tokens)


def _scan_value_patterns(series: pd.Series) -> dict[str, int]:
    values = series.dropna().head(_VALUE_SCAN_LIMIT).tolist()
    if not values:
        return {}

    counts: dict[str, int] = {"scanned": 0}
    for raw_value in values:
        text = str(raw_value).strip()
        if not text:
            continue

        counts["scanned"] += 1
        if _EMAIL_VALUE_RE.search(text):
            counts["email"] = counts.get("email", 0) + 1
            continue
        if _SSN_VALUE_RE.search(text):
            counts["ssn"] = counts.get("ssn", 0) + 1
            continue
        if _looks_like_person_name(text):
            counts["person_name"] = counts.get("person_name", 0) + 1

    return counts if counts["scanned"] else {}


class CSVParseError(ValueError):
    """Raised when a CSV cannot be parsed into a TableProfile."""


class CSVParser:
    """Stateless: instantiate once, call `parse()` per file."""

    def parse(self, filename: str, content: bytes) -> TableProfile:
        """Parse raw CSV bytes into a TableProfile.

        Caps row count via settings.max_rows_per_table. Tries common
        delimiters and infers dtypes via pandas. Datetime columns are
        recognised by pandas heuristics; if a string column looks like
        a date, downstream rules will still see it as `string` — that's
        acceptable for v1 since rule logic mostly cares about *presence*
        of datetime columns, not coverage of every implicit one.
        """
        delimiter = self._detect_delimiter(content)
        df = self._read_dataframe(content, delimiter)
        if df.empty:
            raise CSVParseError(f"{filename}: file produced an empty dataframe")

        full_row_count = max(len(df), self._count_rows(content, delimiter))

        # Release raw bytes — no longer needed after count + parse.
        del content

        # Cap rows (deterministic: take first N, no random sampling)
        n_rows = len(df)
        if n_rows > settings.max_rows_per_table:
            df = df.iloc[: settings.max_rows_per_table].copy()
            logger.info(f"{filename}: truncated from {n_rows:,} to {len(df):,} rows for profiling")

        # Try to coerce string columns that look like dates — improves
        # detection rate for the temporal-integrity rules.
        df = self._try_parse_dates(df)

        profile = self._build_profile(filename, df, full_row_count=full_row_count)

        # ydata enrichment pass — attaches ML-signal metrics to the profile
        column_dtypes = {cp.name: cp.dtype for cp in profile.columns}
        enrichment = ydata_enrich(df, column_dtypes)
        profile.infinite_columns = enrichment.infinite_columns
        profile.near_constant_columns = enrichment.near_constant_columns
        profile.type_mismatches = enrichment.type_mismatches
        profile.correlated_pairs_mixed = enrichment.correlated_pairs_mixed
        profile.missingness_groups = enrichment.missingness_groups

        return profile

    # ── Internals ─────────────────────────────────────────────────────────
    def _detect_delimiter(self, content: bytes) -> str:
        sample = content[:8192].decode("utf-8-sig", errors="replace")
        try:
            return csv.Sniffer().sniff(sample, delimiters=_SUPPORTED_DELIMITERS).delimiter
        except csv.Error:
            header = sample.splitlines()[0] if sample else ""
            counts = {delimiter: header.count(delimiter) for delimiter in _SUPPORTED_DELIMITERS}
            best = max(counts, key=counts.get, default=",")
            return best if counts.get(best, 0) > 0 else ","

    def _read_dataframe(self, content: bytes, delimiter: str) -> pd.DataFrame:
        # Prefer the C engine once we've sniffed a single-character delimiter.
        # Fall back to the python engine only for compatibility edge cases.
        try:
            return pd.read_csv(
                io.BytesIO(content),
                sep=delimiter,
                engine="c",
                encoding="utf-8-sig",
                nrows=settings.max_rows_per_table,
            )
        except Exception as exc:  # noqa: BLE001
            try:
                return pd.read_csv(
                    io.BytesIO(content),
                    sep=delimiter,
                    engine="python",
                    encoding="utf-8-sig",
                    nrows=settings.max_rows_per_table,
                )
            except Exception as fallback_exc:  # noqa: BLE001
                raise CSVParseError(f"could not parse CSV: {fallback_exc}") from fallback_exc

    def _count_rows(self, content: bytes, delimiter: str) -> int:
        """Count data rows without materializing the full CSV into a DataFrame."""
        try:
            with io.TextIOWrapper(
                io.BytesIO(content),
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            ) as stream:
                reader = csv.reader(stream, delimiter=delimiter)
                if next(reader, None) is None:
                    return 0
                return sum(1 for _ in reader)
        except Exception:
            return 0

    def _try_parse_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Best-effort date parsing for object columns whose name *looks*
        date-like. Avoids the expensive 'try parsing every object column'
        path that pandas takes when format inference is enabled globally.

        Name-hinted columns use a lower threshold (50%) because the name
        itself is strong evidence of temporal intent — a column named
        `updated_at` or `outcome_observed_at` should be parsed as datetime
        even when sparse or partially populated.
        """
        date_hints = ("date", "time", "_at", "_on", "_dt", "_ts", "timestamp")
        for col in df.columns:
            if df[col].dtype != object:
                continue
            has_hint = any(h in col.lower() for h in date_hints)
            if not has_hint:
                continue
            try:
                converted = pd.to_datetime(df[col], errors="coerce", utc=False)
                threshold = 0.50 if has_hint else 0.75
                if converted.notna().mean() >= threshold:
                    df[col] = converted
            except Exception:
                continue  # leave column as-is on any failure
        return df

    def _build_profile(self, name: str, df: pd.DataFrame, full_row_count: int) -> TableProfile:
        row_count = len(df)
        col_count = df.shape[1]
        dup = int(df.duplicated().sum())
        missing_pct = float(df.isna().mean().mean() * 100) if col_count else 0.0

        columns: list[ColumnProfile] = []
        for col_name in df.columns:
            s = df[col_name]
            dtype = _coerce_dtype(str(s.dtype))
            null_count = int(s.isna().sum())
            null_pct = (null_count / row_count * 100) if row_count else 0.0
            unique = int(s.nunique(dropna=True))
            value_pattern_counts = _scan_value_patterns(s) if dtype in ("string", "object") else {}

            samples: list[str] = []
            for v in s.dropna().head(5).tolist():
                samples.append(_truncate(v))

            mean = std = mn = mx = None
            quart = None
            skew = kurtosis = None
            earliest = latest = None
            surrogate_null_count = 0

            if dtype in ("int", "float"):
                try:
                    numeric_s = pd.to_numeric(s, errors="coerce")
                    mean = float(numeric_s.mean())
                    std = float(numeric_s.std()) if row_count > 1 else 0.0
                    mn = float(numeric_s.min())
                    mx = float(numeric_s.max())
                    q = numeric_s.quantile([0.25, 0.50, 0.75]).tolist()
                    quart = [float(x) for x in q]
                    if row_count > 2:
                        sk = numeric_s.skew()
                        ku = numeric_s.kurt()
                        skew = round(float(sk), 4) if pd.notna(sk) else None
                        kurtosis = round(float(ku), 4) if pd.notna(ku) else None
                    surrogate_null_count = int(numeric_s.dropna().isin(_NUMERIC_SURROGATE_VALUES).sum())
                except Exception:  # noqa: BLE001
                    pass
            elif dtype in ("string", "object"):
                as_lower = s.dropna().astype(str).str.strip().str.lower()
                surrogate_null_count = int(as_lower.isin(_SURROGATE_NULL_TOKENS).sum())

            days_since_latest: int | None = None
            if dtype == "datetime":
                try:
                    earliest = str(s.min())
                    latest = str(s.max())
                    # Compute freshness at profiling time (scorer stays deterministic)
                    from datetime import datetime as _dt_cls, timezone as _tz
                    latest_ts = s.max()
                    if pd.notna(latest_ts):
                        now = _dt_cls.now(_tz.utc)
                        latest_aware = pd.Timestamp(latest_ts)
                        if latest_aware.tzinfo is None:
                            latest_aware = latest_aware.tz_localize("UTC")
                        days_since_latest = max(0, (now - latest_aware).days)
                except Exception:  # noqa: BLE001
                    pass

            columns.append(ColumnProfile(
                name=str(col_name),
                dtype=dtype,
                null_count=null_count,
                null_pct=round(null_pct, 2),
                unique_count=unique,
                sample_values=samples,
                value_pattern_counts=value_pattern_counts,
                mean=mean, std=std, min_value=mn, max_value=mx,
                quartiles=quart, skew=skew, kurtosis=kurtosis,
                earliest=earliest, latest=latest,
                days_since_latest=days_since_latest,
                surrogate_null_count=surrogate_null_count,
            ))

        # Multicollinearity: flag highly correlated numeric pairs
        multicol_flags: list[dict] = []
        num_cols = df.select_dtypes(include=[np.number])
        if num_cols.shape[1] >= 2 and row_count >= 20:
            try:
                corr = num_cols.corr().abs()
                cols_list = corr.columns.tolist()
                for i in range(len(cols_list)):
                    for j in range(i + 1, len(cols_list)):
                        r = corr.iloc[i, j]
                        if pd.notna(r) and r >= 0.95:
                            multicol_flags.append({
                                "col_a": cols_list[i],
                                "col_b": cols_list[j],
                                "abs_r": round(float(r), 4),
                            })
            except Exception:  # noqa: BLE001
                pass

        return TableProfile(
            name=name,
            row_count=full_row_count,  # report the FULL count, not the capped sample
            profiled_row_count=row_count,
            column_count=col_count,
            duplicate_row_count=dup,
            missing_cells_pct=round(missing_pct, 2),
            columns=columns,
            multicollinearity_flags=multicol_flags,
        )
