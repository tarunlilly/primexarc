"""MetadataParser — parses an optional data dictionary CSV upload.

Accepts both:
- Standard-format metadata files (Metadata Standard field names)
- Generic dictionary CSVs (old format with fewer fields)

All Standard fields are mapped from display names to snake_case on the
MetadataEntry model. Unknown columns are preserved in `extensions`.
Every parsed value carries a `source` flag (authored/measured/derived/system).
See app/docs/metadata_layer.md §2.0.
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from core.models import MetadataEntry, MetadataProfile

logger = logging.getLogger(__name__)

# Maps display-name → MetadataEntry field name. Covers both Standard names
# and the old generic names. Case-insensitive matching applied after
# normalization (lowercase, strip, spaces→underscores).
_COLUMN_MAP: dict[str, str] = {
    # Identity (required)
    "column_name": "column_name",
    "table_name": "table_name",
    # Old generic fields (backwards compatible)
    "description": "description",
    "business_owner": "business_owner",
    "data_steward": "data_steward",
    "pii_classification": "pii_classification",
    "sensitivity_level": "sensitivity_level",
    "retention_policy": "retention_policy",
    "source_system": "source_system",
    "refresh_frequency": "refresh_frequency",
    "last_updated": "last_updated",
    # Standard fields
    "definition": "definition",
    "data_type": "data_type_declared",
    "data_type_declared": "data_type_declared",
    "nullable": "nullable_declared",
    "nullable_declared": "nullable_declared",
    "valid_values/range": "valid_values_range",
    "valid_values_range": "valid_values_range",
    "primary/foreign_key": "primary_foreign_key",
    "primary_foreign_key": "primary_foreign_key",
    "entity_classification": "entity_classification",
    "field_role": "field_role",
    "pii_flag": "pii_flag",
    "pii_category": "pii_category",
    "security_classification": "security_classification",
    "consent_basis_/_permitted_use": "consent_basis",
    "consent_basis": "consent_basis",
    "ai/ml_usage_approval": "ai_ml_usage_approval",
    "ai_ml_usage_approval": "ai_ml_usage_approval",
    "target/label_indicator": "target_label_indicator",
    "target_label_indicator": "target_label_indicator",
    "unit_of_measure": "unit_of_measure",
    "cardinality": "cardinality_declared",
    "cardinality_declared": "cardinality_declared",
    "protected_attribute": "protected_attribute",
    "timezone/temporal_semantics": "timezone_temporal",
    "timezone_temporal": "timezone_temporal",
    "lastsyncedat": "last_synced_at",
    "last_synced_at": "last_synced_at",
    "grain": "grain",
    "data_owner": "business_owner",
    "lineage": "lineage",
    "usage_context": "usage_context",
    "source": "source",
}

_VALID_SOURCES = {"authored", "measured", "derived", "system"}

_ENRICHMENT_FIELDS = {
    "description", "definition", "business_owner", "data_steward",
    "pii_classification", "sensitivity_level", "retention_policy",
    "source_system", "refresh_frequency", "last_updated",
    "data_type_declared", "nullable_declared", "valid_values_range",
    "primary_foreign_key", "entity_classification", "field_role",
    "pii_flag", "pii_category", "security_classification",
    "consent_basis", "ai_ml_usage_approval", "target_label_indicator",
    "unit_of_measure", "cardinality_declared", "protected_attribute",
    "timezone_temporal", "last_synced_at", "grain", "lineage",
    "usage_context",
}


class MetadataParseError(ValueError):
    pass


class MetadataParser:
    def parse(self, content: bytes, filename: str = "metadata.csv") -> MetadataProfile:
        """Parse raw bytes into a MetadataProfile.

        Raises MetadataParseError if `column_name` is missing or the file
        cannot be parsed as CSV. Unknown columns are preserved in each
        entry's `extensions` dict.
        """
        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as exc:
            raise MetadataParseError(f"Could not parse {filename} as CSV: {exc}") from exc

        # Normalize column names for matching
        raw_cols = list(df.columns)
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        if "column_name" not in df.columns:
            raise MetadataParseError(
                f"{filename} must have a 'column_name' column. "
                f"Found: {raw_cols}"
            )

        # Classify columns into mapped vs unknown
        mapped_cols: dict[str, str] = {}  # df_col → model field
        unknown_cols: list[str] = []
        for col in df.columns:
            if col in _COLUMN_MAP:
                mapped_cols[col] = _COLUMN_MAP[col]
            else:
                unknown_cols.append(col)

        # Detect source column presence
        has_source_col = "source" in mapped_cols
        parser_notes: list[str] = []
        if not has_source_col:
            parser_notes.append(
                "No 'source' column found — all values default to 'authored'."
            )

        df = df.where(df.notna(), other=None)

        entries: list[MetadataEntry] = []
        for row in df.to_dict("records"):
            try:
                # Build kwargs for MetadataEntry from mapped columns
                kwargs: dict = {}
                extensions: dict = {}
                for col, value in row.items():
                    if value is None:
                        continue
                    value = str(value).strip()
                    if not value:
                        continue
                    if col in mapped_cols:
                        field = mapped_cols[col]
                        if field == "source":
                            kwargs["source"] = value.lower() if value.lower() in _VALID_SOURCES else "authored"
                        else:
                            kwargs[field] = value
                    else:
                        extensions[col] = value

                if "column_name" not in kwargs:
                    continue

                # Default source if not provided
                if "source" not in kwargs:
                    kwargs["source"] = "authored"

                if extensions:
                    kwargs["extensions"] = extensions

                entries.append(MetadataEntry(**kwargs))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping malformed metadata row: %s", exc)

        # Coverage: % of entries with at least one enrichment field populated
        cols_with_any = sum(
            1 for e in entries
            if any(getattr(e, f, None) for f in _ENRICHMENT_FIELDS)
        )
        total = len(entries)
        coverage = round(cols_with_any / max(total, 1) * 100, 1)

        if unknown_cols:
            parser_notes.append(
                f"Unknown columns preserved as extensions: {', '.join(unknown_cols)}"
            )

        logger.info(
            "MetadataParser: %d entries from %s, %.1f%% coverage, %d unknown cols",
            total, filename, coverage, len(unknown_cols),
        )
        return MetadataProfile(
            entries=entries,
            total_columns=total,
            columns_with_metadata=cols_with_any,
            coverage_pct=coverage,
            unknown_columns=unknown_cols,
            parser_notes=parser_notes,
        )
