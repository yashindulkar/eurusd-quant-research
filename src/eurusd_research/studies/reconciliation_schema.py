"""Strict candidate-evidence schemas used only by independent reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

EXCLUSION_REASON_ORDER = (
    "zero_profile_contribution",
    "task03_profile_ineligible_date",
    "weekend_utc_date",
    "no_expected_market_grid",
    "incomplete_daily_observation",
    "dataset_boundary_date",
)

REGIME_LINEAGE_COMPARISON_COLUMNS = (
    "utc_date",
    "profile",
    "daily_range_pips",
    "lagged_trailing_median_range_pips",
    "prior_regime_measure_count",
    "past_only_low_threshold",
    "past_only_high_threshold",
    "volatility_regime",
    "regime_warmup",
    "regime_classification_reason",
    "volatility_lookback",
    "volatility_minimum_history",
)

REGIME_LINEAGE_OUTPUT_COLUMNS = (
    *REGIME_LINEAGE_COMPARISON_COLUMNS,
    "dataset_version",
    "raw_sha256",
    "audit_fingerprint",
    "coverage_fingerprint",
    "coverage_config_fingerprint",
    "task04_config_fingerprint",
    "preregistration_fingerprint",
    "method_id",
    "method_version",
    "repository_version",
)

DAILY_PROFILE_OUTPUT_COLUMNS = (
    "utc_date",
    "weekday_number",
    "weekday_name",
    "daily_open",
    "daily_high",
    "daily_low",
    "daily_close",
    "daily_range_price",
    "daily_range_pips",
    "first_timestamp_utc",
    "last_timestamp_utc",
    "observed_m15_rows",
    "expected_m15_rows",
    "observed_coverage_ratio",
    "first_expected_interval_present",
    "last_expected_interval_present",
    "continuous_expected_grid",
    "is_weekday",
    "is_weekend_date",
    "is_boundary_date",
    "is_partial_daily_observation",
    "analysis_eligible",
    "exclusion_reasons",
    "profile",
    "first_raw_row_number",
    "last_raw_row_number",
    "contributing_raw_row_count",
    "contributing_rows_sha256",
    "expected_schedule_source",
    "zero_contribution",
    "nonzero_partial",
    "incomplete",
    "complete",
    "dataset_version",
    "raw_sha256",
    "audit_fingerprint",
    "coverage_fingerprint",
    "coverage_config_fingerprint",
    "task04_config_fingerprint",
    "preregistration_fingerprint",
    "method_id",
    "method_version",
    "repository_version",
)


@dataclass(frozen=True, slots=True)
class CandidateCsvSchema:
    """Explicit physical and semantic contract for one candidate CSV."""

    required_columns: tuple[str, ...]
    exact_columns: bool = True
    empty_string_columns: tuple[str, ...] = ()
    nullable_columns: tuple[str, ...] = ()
    numeric_columns: tuple[str, ...] = ()
    boolean_columns: tuple[str, ...] = ()
    date_columns: tuple[str, ...] = ()


def schema_from_expected(
    expected: pd.DataFrame,
    *,
    exact_columns: bool = True,
    empty_string_columns: tuple[str, ...] = (),
) -> CandidateCsvSchema:
    """Derive a strict comparison schema from independently calculated evidence."""
    numeric = tuple(
        column
        for column in expected.columns
        if expected[column].dtype.kind in "iufc" and expected[column].dtype.kind != "b"
    )
    boolean = tuple(
        column for column in expected.columns if expected[column].dtype.kind == "b"
    )
    nullable = tuple(
        column for column in expected.columns if expected[column].isna().any()
    )
    dates = tuple(
        column
        for column in expected.columns
        if column == "utc_date" or column in {"date_start", "date_end"}
    )
    return CandidateCsvSchema(
        required_columns=tuple(expected.columns),
        exact_columns=exact_columns,
        empty_string_columns=empty_string_columns,
        nullable_columns=nullable,
        numeric_columns=numeric,
        boolean_columns=boolean,
        date_columns=dates,
    )


def canonical_exclusion_reasons(value: object) -> str:
    """Validate and return the registered deterministic exclusion representation."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        raise ValueError("exclusion_reasons must distinguish empty string from null")
    text = str(value)
    if not text:
        return ""
    if text.strip() != text:
        raise ValueError("exclusion_reasons cannot contain surrounding whitespace")
    tokens = tuple(text.split("|"))
    if any(not token for token in tokens):
        raise ValueError("exclusion_reasons contains an empty token")
    unknown = set(tokens).difference(EXCLUSION_REASON_ORDER)
    if unknown:
        raise ValueError(f"Unknown exclusion reason: {sorted(unknown)}")
    if len(tokens) != len(set(tokens)):
        raise ValueError("exclusion_reasons contains duplicate tokens")
    ordered = tuple(item for item in EXCLUSION_REASON_ORDER if item in tokens)
    if tokens != ordered:
        raise ValueError("exclusion_reasons is not in registered canonical order")
    return text


def load_candidate_csv(path: Path, schema: CandidateCsvSchema) -> pd.DataFrame:
    """Load one CSV with schema-specific empty, null, type, and column semantics."""
    frame = pd.read_csv(path)
    missing = tuple(sorted(set(schema.required_columns).difference(frame.columns)))
    if missing:
        raise ValueError(f"Candidate CSV is missing required columns: {missing}")
    extra = tuple(sorted(set(frame.columns).difference(schema.required_columns)))
    if schema.exact_columns and extra:
        raise ValueError(f"Candidate CSV has unexpected columns: {extra}")
    if schema.exact_columns and tuple(frame.columns) != schema.required_columns:
        raise ValueError("Candidate CSV columns are not in registered order")
    frame = frame.loc[:, schema.required_columns].copy()
    for column in schema.empty_string_columns:
        if column not in frame:
            raise ValueError(f"Empty-string column is not registered: {column}")
        frame[column] = frame[column].fillna("")
        if column == "exclusion_reasons":
            frame[column] = frame[column].map(canonical_exclusion_reasons)
    for column in schema.numeric_columns:
        converted = pd.to_numeric(frame[column], errors="coerce")
        invalid = converted.isna() & frame[column].notna()
        if invalid.any():
            raise ValueError(f"Candidate numeric column is malformed: {column}")
        values = converted.dropna().to_numpy(float)
        if not np.isfinite(values).all():
            raise ValueError(f"Candidate numeric column is non-finite: {column}")
        if column not in schema.nullable_columns and converted.isna().any():
            raise ValueError(f"Candidate numeric column is unexpectedly null: {column}")
        frame[column] = converted
    for column in schema.boolean_columns:
        if frame[column].isna().any() and column not in schema.nullable_columns:
            raise ValueError(f"Candidate Boolean column is unexpectedly null: {column}")
        values = set(frame[column].dropna().astype(str))
        if not values.issubset({"True", "False"}):
            raise ValueError(f"Candidate Boolean column is malformed: {column}")
        frame[column] = frame[column].map(
            lambda value: (
                value if isinstance(value, bool) or pd.isna(value) else value == "True"
            )
        )
    for column in schema.date_columns:
        values = frame[column].dropna().astype(str)
        if values.str.strip().ne(values).any():
            raise ValueError(f"Candidate date column has whitespace: {column}")
        pd.to_datetime(values, errors="raise")
    return frame


def project_registered_regime_lineage(frame: pd.DataFrame) -> pd.DataFrame:
    """Project a wider independent frame to the registered 12-field lineage."""
    missing = tuple(
        sorted(set(REGIME_LINEAGE_COMPARISON_COLUMNS).difference(frame.columns))
    )
    if missing:
        raise ValueError(f"Regime lineage is missing registered fields: {missing}")
    result = frame.loc[:, REGIME_LINEAGE_COMPARISON_COLUMNS].copy()
    keys = ("utc_date", "profile")
    if result.duplicated(list(keys)).any():
        raise ValueError("Regime lineage contains duplicate date/profile keys")
    return result.sort_values(list(keys), kind="stable").reset_index(drop=True)


def canonical_registered_output_paths(
    root_artifacts: tuple[str, ...], figure_filenames: tuple[str, ...]
) -> tuple[str, ...]:
    """Return the exact repository-style paths relative to the output root."""
    values = (*root_artifacts, *(f"figures/{name}" for name in figure_filenames))
    normalized: list[str] = []
    for value in values:
        path = Path(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or path.as_posix() != value
        ):
            raise ValueError(f"Registered output path is unsafe: {value}")
        if value.startswith("figures/"):
            if len(path.parts) != 2 or path.parts[0] != "figures":
                raise ValueError(f"Registered figure path is not canonical: {value}")
        elif len(path.parts) != 1:
            raise ValueError(f"Root output artifact cannot be nested: {value}")
        elif path.suffix.lower() == ".png":
            raise ValueError(f"Registered figure is missing figures/ prefix: {value}")
        normalized.append(value)
    if len(normalized) != len(set(normalized)):
        raise ValueError("Registered output paths contain duplicates")
    lowered = [item.casefold() for item in normalized]
    if len(lowered) != len(set(lowered)):
        raise ValueError("Registered output paths contain case-colliding entries")
    return tuple(sorted(normalized))


DAILY_PROFILE_SCHEMA = CandidateCsvSchema(
    required_columns=DAILY_PROFILE_OUTPUT_COLUMNS,
    empty_string_columns=("exclusion_reasons",),
    nullable_columns=(
        "daily_open",
        "daily_high",
        "daily_low",
        "daily_close",
        "daily_range_price",
        "daily_range_pips",
        "first_timestamp_utc",
        "last_timestamp_utc",
        "first_raw_row_number",
        "last_raw_row_number",
    ),
    numeric_columns=(
        "weekday_number",
        "daily_open",
        "daily_high",
        "daily_low",
        "daily_close",
        "daily_range_price",
        "daily_range_pips",
        "observed_m15_rows",
        "expected_m15_rows",
        "observed_coverage_ratio",
        "first_raw_row_number",
        "last_raw_row_number",
        "contributing_raw_row_count",
    ),
    boolean_columns=(
        "first_expected_interval_present",
        "last_expected_interval_present",
        "continuous_expected_grid",
        "is_weekday",
        "is_weekend_date",
        "is_boundary_date",
        "is_partial_daily_observation",
        "analysis_eligible",
        "zero_contribution",
        "nonzero_partial",
        "incomplete",
        "complete",
    ),
    date_columns=("utc_date",),
)

REGIME_LINEAGE_OUTPUT_SCHEMA = CandidateCsvSchema(
    required_columns=REGIME_LINEAGE_OUTPUT_COLUMNS,
    nullable_columns=(
        "lagged_trailing_median_range_pips",
        "past_only_low_threshold",
        "past_only_high_threshold",
    ),
    numeric_columns=(
        "daily_range_pips",
        "lagged_trailing_median_range_pips",
        "prior_regime_measure_count",
        "past_only_low_threshold",
        "past_only_high_threshold",
        "volatility_lookback",
        "volatility_minimum_history",
    ),
    boolean_columns=("regime_warmup",),
    date_columns=("utc_date",),
)
