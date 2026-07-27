"""Build row flags, propagate them, and apply configured coverage profiles."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from eurusd_research.config import CoverageProfileConfig
from eurusd_research.research.models import CoverageLineage
from eurusd_research.research.registry import (
    FLAG_COLUMNS,
    QUALITY_FLAGS,
    RULES,
    SENSITIVITY_FLAGS,
)

LINEAGE_COLUMNS = (
    "dataset_version",
    "raw_sha256",
    "audit_result_content_sha256",
    "audit_gap_table_sha256",
    "audit_monthly_table_sha256",
    "coverage_method_id",
    "coverage_method_version",
    "coverage_config_sha256",
    "repository_version",
)


def _audit_quality_flags(audit: Mapping[str, Any], row_count: int) -> dict[str, bool]:
    schema = audit["schema_results"]
    timestamp = audit["timestamp_results"]
    ohlc = audit["ohlc_results"]
    duplicates = audit["duplicate_results"]
    return {
        "schema_valid": bool(
            schema["mandatory_schema_satisfied"]
            and schema["row_count"] == row_count
            and schema["row_count_matches_manifest"]
        ),
        "timestamp_valid": bool(
            timestamp["successful_parsing_count"] == row_count
            and timestamp["source_values_with_explicit_timezone_count"] == row_count
            and timestamp["unparseable_count"] == 0
            and timestamp["off_15_minute_grid_count"] == 0
            and timestamp["chronologically_ordered"]
        ),
        "ohlc_valid": ohlc["combined_invalid_ohlc_count"] == 0,
        "duplicate_free": duplicates["duplicate_primary_timestamp_row_count"] == 0,
    }


def _endpoints(gaps: pd.DataFrame, category: str) -> pd.DatetimeIndex:
    selected = gaps.loc[
        gaps["preliminary_category"].eq(category),
        ["timestamp_before", "timestamp_after"],
    ]
    return pd.DatetimeIndex(pd.to_datetime(selected.stack(), utc=True).unique())


def _lineage_columns(frame: pd.DataFrame, lineage: CoverageLineage) -> pd.DataFrame:
    values = lineage.to_dict()
    for column in LINEAGE_COLUMNS:
        frame[column] = pd.Categorical.from_codes(
            codes=np.zeros(len(frame), dtype=np.int8), categories=[values[column]]
        )
    return frame


def build_row_flags(
    raw_timestamp_values: pd.Series,
    audit: Mapping[str, Any],
    gaps: pd.DataFrame,
    monthly_coverage: pd.DataFrame,
    lineage: CoverageLineage,
) -> pd.DataFrame:
    """Assign descriptive Task 02-backed flags to every raw observation."""
    timestamps = pd.to_datetime(
        raw_timestamp_values, errors="coerce", utc=True, format="mixed"
    )
    if timestamps.isna().any():
        raise ValueError("Audited timestamp values could not be joined to coverage")
    row_count = len(timestamps)
    quality = _audit_quality_flags(audit, row_count)
    gap_after = pd.DatetimeIndex(pd.to_datetime(gaps["timestamp_after"], utc=True))
    impaired_months = set(
        monthly_coverage.loc[
            monthly_coverage["continuity_impaired_month"], "month"
        ].astype(str)
    )
    boundary_months = set(
        monthly_coverage.loc[monthly_coverage["boundary_month"], "month"].astype(str)
    )
    partial = audit["partial_period_results"]
    partial_years: set[int] = set()
    if partial["incomplete_first_year"]:
        partial_years.add(int(partial["first_year"]))
    if partial["incomplete_final_year"]:
        partial_years.add(int(partial["final_year"]))
    affected = audit["continuity_investigation_2023"]["concentrated_2023_period"]
    affected_start = pd.Timestamp(affected["first_timestamp_before"])
    affected_end = pd.Timestamp(affected["last_timestamp_after"])
    utc_values = timestamps.array.tz_convert(None).to_numpy(dtype="datetime64[ns]")
    utc_date = pd.Series(
        utc_values.astype("datetime64[D]").astype(str), index=timestamps.index
    )
    utc_month = pd.Series(
        utc_values.astype("datetime64[M]").astype(str), index=timestamps.index
    )

    frame = pd.DataFrame(
        {
            "raw_row_number": pd.RangeIndex(start=2, stop=row_count + 2),
            "raw_timestamp": raw_timestamp_values.astype(str).to_numpy(),
            "timestamp_utc": timestamps,
            "utc_date": utc_date,
            "utc_month": utc_month,
            "utc_year": timestamps.dt.year,
            "raw_available": True,
            "schema_valid": quality["schema_valid"],
            "timestamp_valid": quality["timestamp_valid"],
            "ohlc_valid": quality["ohlc_valid"],
            "duplicate_free": quality["duplicate_free"],
            "cadence_valid": ~timestamps.isin(gap_after),
            "weekly_gap_boundary": timestamps.isin(
                _endpoints(gaps, "likely_weekly_closure")
            ),
            "long_nonweekly_gap_boundary": timestamps.isin(
                _endpoints(gaps, "long_nonweekly_gap")
            ),
            "nonweekend_gap_boundary": timestamps.isin(
                _endpoints(gaps, "non_weekend_intraday")
            ),
            "unclassified_gap_boundary": timestamps.isin(
                _endpoints(gaps, "unclassified")
            ),
            "continuity_impaired_period": utc_month.isin(impaired_months),
            "affected_period_2023": timestamps.between(
                affected_start, affected_end, inclusive="both"
            ),
            "partial_boundary_year": timestamps.dt.year.isin(partial_years),
            "partial_boundary_month": utc_month.isin(boundary_months),
        }
    )
    frame["research_eligible_default"] = frame[list(QUALITY_FLAGS)].all(axis=1)
    frame["requires_sensitivity_analysis"] = frame[list(SENSITIVITY_FLAGS)].any(axis=1)
    frame["eligibility_status"] = "fully_eligible"
    frame.loc[frame["requires_sensitivity_analysis"], "eligibility_status"] = (
        "conditionally_eligible"
    )
    frame.loc[~frame["research_eligible_default"], "eligibility_status"] = (
        "structurally_ineligible"
    )
    return _lineage_columns(frame, lineage)


def aggregate_flags(
    row_flags: pd.DataFrame, level: str, lineage: CoverageLineage
) -> pd.DataFrame:
    """Propagate flags to observed UTC periods using registered any/all semantics."""
    key_by_level = {
        "date": "utc_date",
        "month": "utc_month",
        "year": "utc_year",
    }
    if level == "row":
        return row_flags
    if level == "dataset":
        record: dict[str, object] = {"dataset": lineage.dataset_version}
        for flag, rule in RULES.items():
            record[flag] = bool(
                row_flags[flag].all()
                if rule.aggregation == "all"
                else row_flags[flag].any()
            )
        record["observed_row_count"] = len(row_flags)
        return _lineage_columns(pd.DataFrame([record]), lineage)
    if level not in key_by_level:
        raise ValueError(f"Unsupported coverage level: {level}")
    key = key_by_level[level]
    aggregations = {flag: rule.aggregation for flag, rule in RULES.items()}
    grouped = row_flags.groupby(key, sort=True, observed=True)
    frame = grouped[list(FLAG_COLUMNS)].agg(aggregations).reset_index()
    frame["observed_row_count"] = grouped.size().to_numpy()
    return _lineage_columns(frame, lineage)


def apply_profile(frame: pd.DataFrame, profile: CoverageProfileConfig) -> pd.Series:
    """Evaluate a named profile against one coverage-level flag frame."""
    referenced = (*profile.require_all, *profile.require_any, *profile.exclude_any)
    unknown = sorted(set(referenced).difference(RULES))
    if unknown:
        raise ValueError(f"Coverage profile references unknown flags: {unknown}")
    mask = pd.Series(True, index=frame.index, dtype=bool)
    if profile.require_all:
        mask &= frame[list(profile.require_all)].all(axis=1)
    if profile.require_any:
        mask &= frame[list(profile.require_any)].any(axis=1)
    if profile.exclude_any:
        mask &= ~frame[list(profile.exclude_any)].any(axis=1)
    return mask


def build_profile_masks(
    flags_by_level: Mapping[str, pd.DataFrame],
    profiles: Mapping[str, CoverageProfileConfig],
) -> dict[str, pd.DataFrame]:
    """Build reversible named inclusion masks at all supported levels."""
    output: dict[str, pd.DataFrame] = {}
    for level, frame in flags_by_level.items():
        output[level] = pd.DataFrame(
            {name: apply_profile(frame, profile) for name, profile in profiles.items()}
        )
    return output


def validate_canonical_profile_algebra(
    profiles: Mapping[str, CoverageProfileConfig],
) -> None:
    """Prove canonical profile relationships over every referenced truth assignment."""
    names = {
        "DEFAULT_RESEARCH",
        "STRICT_CONTINUITY",
        "SENSITIVITY_FULL",
        "SENSITIVITY_2023",
    }
    if missing := names.difference(profiles):
        raise ValueError(f"Canonical coverage profiles are missing: {sorted(missing)}")
    referenced = sorted(
        {
            flag
            for name in names
            for flag in (
                *profiles[name].require_all,
                *profiles[name].require_any,
                *profiles[name].exclude_any,
            )
        }
    )
    truth_table = pd.DataFrame(
        product((False, True), repeat=len(referenced)), columns=referenced
    )
    masks = {name: apply_profile(truth_table, profiles[name]) for name in sorted(names)}
    default = masks["DEFAULT_RESEARCH"]
    strict = masks["STRICT_CONTINUITY"]
    sensitivity = masks["SENSITIVITY_FULL"]
    sensitivity_2023 = masks["SENSITIVITY_2023"]
    if (strict & sensitivity).any():
        raise ValueError("STRICT_CONTINUITY and SENSITIVITY_FULL must be disjoint")
    if not (strict | sensitivity).equals(default):
        raise ValueError(
            "STRICT_CONTINUITY union SENSITIVITY_FULL must equal DEFAULT_RESEARCH"
        )
    if (sensitivity_2023 & ~sensitivity).any():
        raise ValueError("SENSITIVITY_2023 must be a subset of SENSITIVITY_FULL")
