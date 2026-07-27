"""Read-only, reproducible technical audit of the registered raw EUR/USD CSV."""

from __future__ import annotations

import csv
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from eurusd_research.config import DataConfig
from eurusd_research.data.gaps import (
    GAP_COLUMNS,
    build_gap_table,
    expand_missing_timestamps,
)
from eurusd_research.data.quality_models import AuditResult, json_safe
from eurusd_research.data.registry import (
    DatasetManifest,
    ManifestError,
    read_manifest,
    sha256_file,
)

LOGGER = logging.getLogger(__name__)
PRICE_COLUMNS = ("open", "high", "low", "close")
COUNT_COLUMN = "volume_or_tick_count"
SOURCE_COLUMN = "source"
OHLC_VIOLATION_COLUMNS = (
    "row_number",
    "timestamp_utc",
    "open",
    "high",
    "low",
    "close",
    "all_finite",
    "all_positive",
    "high_ge_low",
    "high_ge_open",
    "high_ge_close",
    "low_le_open",
    "low_le_close",
)
EXTREME_MOVEMENT_COLUMNS = (
    "interval_class",
    "timestamp_before",
    "timestamp_after",
    "interval_minutes",
    "close_before",
    "close_after",
    "close_change",
    "absolute_close_change",
    "before_open",
    "before_high",
    "before_low",
    "before_close",
    "after_open",
    "after_high",
    "after_low",
    "after_close",
)
COUNT_DISTRIBUTION_COLUMNS = ("value", "count", "percentage")
ANNUAL_COVERAGE_COLUMNS = (
    "year",
    "first_timestamp",
    "last_timestamp",
    "bar_count",
    "unique_utc_dates",
    "gaps_beginning_in_period",
    "gaps_ending_in_period",
    "gaps_touching_period",
    "estimated_missing_m15_timestamps_in_period",
    "count_field_non_null_count",
    "count_field_complete_percentage",
    "count_field_median",
)
MONTHLY_COVERAGE_COLUMNS = (
    "month",
    "first_timestamp",
    "last_timestamp",
    "bar_count",
    "unique_utc_dates",
    "gaps_beginning_in_period",
    "gaps_ending_in_period",
    "gaps_touching_period",
    "estimated_missing_m15_timestamps_in_period",
    "nonweekly_gaps_touching_period",
    "nonweekend_gaps_touching_period",
    "estimated_nonweekly_missing_timestamps_in_period",
    "estimated_nonweekend_missing_timestamps_in_period",
    "count_field_non_null_count",
    "count_field_complete_percentage",
    "count_field_median",
    "boundary_month",
    "sparse_month",
    "continuity_impaired_month",
    "partial_observed_month",
    "classification_reasons",
)


def _iso(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return cast(str, pd.Timestamp(value).isoformat().replace("+00:00", "Z"))


def _describe(
    series: pd.Series,
    percentiles: tuple[float, ...] = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99),
) -> dict[str, Any]:
    clean = series.dropna()
    if clean.empty:
        return {"sample_size": 0}
    quantiles = clean.quantile(list(percentiles))
    return {
        "sample_size": int(clean.size),
        "mean": float(clean.mean()),
        "median": float(clean.median()),
        "standard_deviation": float(clean.std(ddof=1)) if clean.size > 1 else 0.0,
        "minimum": float(clean.min()),
        "maximum": float(clean.max()),
        "percentiles": {
            f"{level * 100:g}": float(value) for level, value in quantiles.items()
        },
    }


def _load_csv_once(
    path: Path, expected_columns: tuple[str, ...]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load source text once while retaining malformed/empty-row evidence."""
    rows: list[list[str]] = []
    malformed: list[dict[str, Any]] = []
    empty_rows = 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return pd.DataFrame(), {
                "columns": [],
                "malformed_rows": [],
                "completely_empty_rows": 0,
            }
        for line_number, row in enumerate(reader, start=2):
            if not row or all(not value.strip() for value in row):
                empty_rows += 1
                continue
            if len(row) != len(header):
                malformed.append(
                    {
                        "line_number": line_number,
                        "observed_field_count": len(row),
                        "expected_field_count": len(header),
                    }
                )
                continue
            rows.append(row)
    frame = pd.DataFrame(rows, columns=header, dtype="object")
    return frame, {
        "columns": header,
        "malformed_rows": malformed,
        "completely_empty_rows": empty_rows,
        "expected_columns": list(expected_columns),
    }


def _missing_results(
    raw: pd.DataFrame, numeric: dict[str, pd.Series]
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for column in raw.columns:
        source = raw[column]
        stripped = source.str.strip()
        null_count = int(source.isna().sum())
        item: dict[str, Any] = {
            "null_count": null_count,
            "null_percentage": 100.0 * null_count / len(raw) if len(raw) else 0.0,
            "empty_string_count": int(stripped.eq("").sum()),
        }
        if column in numeric:
            values = numeric[column]
            item.update(
                {
                    "nan_count": int(values.isna().sum()),
                    "positive_infinity_count": int(np.isposinf(values).sum()),
                    "negative_infinity_count": int(np.isneginf(values).sum()),
                    "invalid_numeric_token_count": int(
                        (values.isna() & stripped.ne("")).sum()
                    ),
                }
            )
        results[column] = item
    return results


def _timestamp_results(raw_values: pd.Series) -> tuple[pd.Series, dict[str, Any]]:
    stripped = raw_values.str.strip()
    parsed = pd.to_datetime(stripped, errors="coerce", utc=True, format="mixed")
    explicit_tz = stripped.str.contains(r"(?:Z|[+-]\d\d:\d\d)$", regex=True, na=False)
    valid = parsed.dropna()
    diffs = valid.diff().dt.total_seconds().div(60)
    interval_counts = {
        str(float(key)): int(value)
        for key, value in diffs.value_counts().sort_index().items()
    }
    off_grid = valid[
        (valid.dt.second != 0)
        | (valid.dt.microsecond != 0)
        | (~valid.dt.minute.isin([0, 15, 30, 45]))
    ]
    return parsed, {
        "source_value_count": len(raw_values),
        "successful_parsing_count": int(parsed.notna().sum()),
        "unparseable_count": int(parsed.isna().sum()),
        "unparseable_samples": stripped[parsed.isna()].head(10).tolist(),
        "source_values_with_explicit_timezone_count": int(explicit_tz.sum()),
        "source_values_without_explicit_timezone_count": int((~explicit_tz).sum()),
        "parsed_timezone_aware": bool(isinstance(parsed.dtype, pd.DatetimeTZDtype)),
        "parsed_timezone": str(parsed.dt.tz),
        "utc_normalized": str(parsed.dt.tz) == "UTC",
        "chronologically_ordered": bool(valid.is_monotonic_increasing),
        "backward_interval_count": int((diffs < 0).sum()),
        "zero_length_interval_count": int((diffs == 0).sum()),
        "below_15_minute_interval_count": int(((diffs > 0) & (diffs < 15)).sum()),
        "exact_15_minute_interval_count": int((diffs == 15).sum()),
        "greater_than_15_minute_interval_count": int((diffs > 15).sum()),
        "exact_15_minute_interval_percentage": (
            100.0 * int((diffs == 15).sum()) / int(diffs.notna().sum())
            if diffs.notna().any()
            else 0.0
        ),
        "first_timestamp": _iso(valid.iloc[0]) if not valid.empty else None,
        "last_timestamp": _iso(valid.iloc[-1]) if not valid.empty else None,
        "nonzero_seconds_count": int((valid.dt.second != 0).sum()),
        "nonzero_microseconds_count": int((valid.dt.microsecond != 0).sum()),
        "off_15_minute_grid_count": len(off_grid),
        "off_grid_samples": [_iso(value) for value in off_grid.head(10)],
        "unexpected_minute_values": sorted(
            int(value)
            for value in valid.dt.minute[
                ~valid.dt.minute.isin([0, 15, 30, 45])
            ].unique()
        ),
        "interval_distribution_minutes": interval_counts,
    }


def _ohlc_results(
    raw: pd.DataFrame,
    numeric: dict[str, pd.Series],
    timestamps: pd.Series,
    unusual_range_quantile: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    o, h, low, close = (numeric[column] for column in PRICE_COLUMNS)
    finite = pd.Series(True, index=raw.index)
    positive = pd.Series(True, index=raw.index)
    for values in (o, h, low, close):
        finite &= np.isfinite(values)
        positive &= values > 0
    rules = {
        "all_ohlc_finite": finite,
        "all_ohlc_positive": positive,
        "high_ge_low": h >= low,
        "high_ge_open": h >= o,
        "high_ge_close": h >= close,
        "low_le_open": low <= o,
        "low_le_close": low <= close,
    }
    invalid = ~pd.concat(rules, axis=1).all(axis=1)
    violations = pd.DataFrame(
        {
            "row_number": raw.index[invalid] + 2,
            "timestamp_utc": timestamps[invalid],
            "open": o[invalid],
            "high": h[invalid],
            "low": low[invalid],
            "close": close[invalid],
            "all_finite": finite[invalid],
            "all_positive": positive[invalid],
            "high_ge_low": rules["high_ge_low"][invalid],
            "high_ge_open": rules["high_ge_open"][invalid],
            "high_ge_close": rules["high_ge_close"][invalid],
            "low_le_open": rules["low_le_open"][invalid],
            "low_le_close": rules["low_le_close"][invalid],
        },
        columns=OHLC_VIOLATION_COLUMNS,
    )
    ranges = h - low
    finite_ranges = ranges[np.isfinite(ranges)]
    threshold = (
        float(finite_ranges.quantile(unusual_range_quantile))
        if not finite_ranges.empty
        else None
    )
    unusual = (
        raw.loc[ranges >= threshold, list(PRICE_COLUMNS)].copy()
        if threshold
        else raw.iloc[0:0]
    )
    if not unusual.empty:
        unusual.insert(0, "timestamp_utc", timestamps.loc[unusual.index])
        unusual["range"] = ranges.loc[unusual.index]
        unusual = unusual.sort_values("range", ascending=False).head(25)
    return {
        "rule_violation_counts": {
            name: int((~result.fillna(False)).sum()) for name, result in rules.items()
        },
        "combined_invalid_ohlc_count": int(invalid.sum()),
        "affected_timestamps_sample": [
            _iso(value) for value in timestamps[invalid].head(10)
        ],
        "zero_range_candle_count": int((h == low).sum()),
        "flat_candle_count": int(((o == h) & (h == low) & (low == close)).sum()),
        "zero_body_candle_count": int((o == close).sum()),
        "unusual_range_definition": (
            f"range >= configured {unusual_range_quantile:.3%} percentile"
        ),
        "unusual_range_threshold": threshold,
        "unusual_range_count": int((ranges >= threshold).sum()) if threshold else 0,
        "largest_range_observations": json_safe(unusual.to_dict("records")),
    }, violations


def _precision_results(
    raw: pd.DataFrame, numeric: dict[str, pd.Series], timestamps: pd.Series
) -> dict[str, Any]:
    years = timestamps.dt.year
    by_year: dict[str, Any] = {}
    for year in sorted(int(value) for value in years.dropna().unique()):
        mask = years == year
        columns: dict[str, Any] = {}
        for column in PRICE_COLUMNS:
            text = raw.loc[mask, column].str.strip()
            parts = text.str.extract(r"^([+-]?)(\d+)(?:\.(\d+))?$")
            decimal_places = parts[2].str.len().fillna(0)
            maximum_places = (
                int(decimal_places.max()) if not decimal_places.empty else 0
            )
            scale = 10**maximum_places
            valid_text = parts[1].notna()
            integer_part = pd.to_numeric(parts.loc[valid_text, 1]).astype("int64")
            fractional_text = (
                parts.loc[valid_text, 2]
                .fillna("")
                .str.pad(maximum_places, side="right", fillchar="0")
                .replace("", "0")
            )
            fractional_part = pd.to_numeric(fractional_text).astype("int64")
            sign = parts.loc[valid_text, 0].eq("-").map({True: -1, False: 1})
            scaled = ((integer_part * scale + fractional_part) * sign).to_numpy(
                dtype="int64"
            )
            unique = np.unique(scaled)
            increments = np.diff(unique)
            positive = increments[increments > 0]
            temporal_changes = pd.Series(scaled).diff().abs().dropna().astype("int64")
            common = temporal_changes[temporal_changes > 0].value_counts().head(5)
            columns[column] = {
                "source_decimal_place_distribution": {
                    str(int(key)): int(value)
                    for key, value in decimal_places.value_counts().sort_index().items()
                },
                "maximum_source_decimal_places": maximum_places,
                "minimum_positive_increment": (
                    float(positive.min() / scale) if len(positive) else None
                ),
                "common_positive_temporal_increments": [
                    {"increment": float(key / scale), "count": int(value)}
                    for key, value in common.items()
                ],
            }
        by_year[str(year)] = columns
    observed_maximums = {
        year: max(
            details[column]["maximum_source_decimal_places"] for column in PRICE_COLUMNS
        )
        for year, details in by_year.items()
    }
    return {
        "method": (
            "original source-text decimal counts and direct digit-to-scaled-integer "
            "conversion; binary floating point is not used for increments"
        ),
        "caution": "Absent trailing zeros are not treated as missing precision.",
        "by_year": by_year,
        "apparent_maximum_decimal_places_by_year": observed_maximums,
        "structural_change_years": [
            year
            for year, previous in zip(
                list(observed_maximums)[1:], list(observed_maximums)[:-1], strict=True
            )
            if observed_maximums[year] != observed_maximums[previous]
        ],
    }


def _count_results(
    values: pd.Series,
    raw_values: pd.Series,
    timestamps: pd.Series,
    percentiles: tuple[float, ...],
) -> tuple[dict[str, Any], pd.DataFrame]:
    finite = values[np.isfinite(values)]
    years = timestamps.dt.year
    year_records: list[dict[str, Any]] = []
    for year in sorted(int(value) for value in years.dropna().unique()):
        stats = _describe(values[years == year], percentiles)
        stats["year"] = year
        stats["null_count"] = int(values[years == year].isna().sum())
        year_records.append(stats)
    distribution = (
        values.value_counts(dropna=False)
        .sort_index()
        .rename_axis("value")
        .reset_index(name="count")
    )
    distribution["percentage"] = 100.0 * distribution["count"] / len(values)
    return {
        "configured_dtype": "non_negative_count",
        "inferred_pandas_dtype_from_source_text": str(
            pd.api.types.infer_dtype(raw_values, skipna=True)
        ),
        "parsed_dtype": str(values.dtype),
        "null_count": int(values.isna().sum()),
        "non_finite_count": int((~np.isfinite(values) & values.notna()).sum()),
        "summary_statistics": _describe(finite, percentiles),
        "below_zero_count": int((values < 0).sum()),
        "equal_zero_count": int((values == 0).sum()),
        "non_integer_count": int(
            ((values.notna()) & (np.isfinite(values)) & (values % 1 != 0)).sum()
        ),
        "bounded_1_to_15_count": int(values.between(1, 15).sum()),
        "bounded_1_to_15_percentage": (
            100.0 * int(values.between(1, 15).sum()) / len(values)
            if len(values)
            else 0.0
        ),
        "hypothesis_assessment": {
            "confirmed_observation": "Empirical bounds and distribution are reported.",
            "possible_interpretation": (
                "Values bounded from 1 to 15 may represent constituent M1 "
                "observation count in an M15 aggregation."
            ),
            "limitation": "Source documentation is required for confirmation.",
        },
        "distribution_by_year": year_records,
    }, distribution


def _source_results(raw_values: pd.Series, timestamps: pd.Series) -> dict[str, Any]:
    stripped = raw_values.str.strip()
    records: list[dict[str, Any]] = []
    for value, count in stripped.value_counts(dropna=False).items():
        mask = stripped.eq(value)
        records.append(
            {
                "value": None if pd.isna(value) else str(value),
                "count": int(count),
                "first_timestamp": _iso(timestamps[mask].min()),
                "last_timestamp": _iso(timestamps[mask].max()),
            }
        )
    changes = stripped.ne(stripped.shift()) & stripped.notna()
    return {
        "unique_non_null_values": sorted(
            str(value) for value in stripped.dropna().unique()
        ),
        "value_details": records,
        "null_count": int(raw_values.isna().sum()),
        "empty_count": int(stripped.eq("").sum()),
        "leading_or_trailing_whitespace_count": int(raw_values.ne(stripped).sum()),
        "casefold_collision_groups": {
            key: sorted(values)
            for key, values in _casefold_groups(stripped).items()
            if len(values) > 1
        },
        "source_change_count": max(
            int(changes.sum()) - (1 if len(raw_values) else 0), 0
        ),
        "source_change_timestamps": [
            _iso(value) for value in timestamps[changes].iloc[1:11]
        ],
        "interpretation_limit": (
            "A consistent label does not prove an unchanged upstream feed."
        ),
    }


def _casefold_groups(values: pd.Series) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for value in values.dropna().unique():
        groups.setdefault(str(value).casefold(), set()).add(str(value))
    return groups


def _coverage_tables(
    timestamps: pd.Series,
    gaps: pd.DataFrame,
    missing_timestamps: pd.DataFrame,
    counts: pd.Series,
    sparse_fraction: float,
    continuity_gap_threshold: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Allocate absent timestamps to their physical UTC periods."""
    valid = timestamps.notna()
    base = pd.DataFrame({"timestamp": timestamps[valid], "count": counts[valid]})
    base["year"] = base["timestamp"].dt.year

    def month_labels(values: pd.Series) -> pd.Series:
        return (
            values.dt.year.astype("string")
            + "-"
            + values.dt.month.astype("string").str.zfill(2)
        )

    base["month"] = month_labels(base["timestamp"])

    def period_series(values: pd.Series, key: str) -> pd.Series:
        parsed = pd.to_datetime(values, utc=True)
        return parsed.dt.year if key == "year" else month_labels(parsed)

    gap_periods = (
        {
            key: (
                period_series(gaps["timestamp_before"], key),
                period_series(gaps["timestamp_after"], key),
            )
            for key in ("year", "month")
        }
        if not gaps.empty
        else {}
    )
    missing_periods = (
        {
            key: period_series(missing_timestamps["missing_timestamp_utc"], key)
            for key in ("year", "month")
        }
        if not missing_timestamps.empty
        else {}
    )

    def gap_period_sets(key: str) -> tuple[pd.Series, pd.Series, dict[Any, int]]:
        if gaps.empty:
            empty = pd.Series(dtype="object")
            return empty, empty, {}
        beginning, ending = gap_periods[key]
        touch_frame = pd.DataFrame(
            {
                "gap_id": pd.concat(
                    [gaps["gap_id"], gaps["gap_id"]], ignore_index=True
                ),
                "period": pd.concat([beginning, ending], ignore_index=True),
            }
        )
        if not missing_timestamps.empty:
            missing_period = missing_periods[key]
            touch_frame = pd.concat(
                [
                    touch_frame,
                    pd.DataFrame(
                        {
                            "gap_id": missing_timestamps["gap_id"].to_numpy(),
                            "period": missing_period.to_numpy(),
                        }
                    ),
                ],
                ignore_index=True,
            )
        touching = (
            touch_frame.drop_duplicates()
            .groupby("period", sort=True)["gap_id"]
            .nunique()
            .to_dict()
        )
        return beginning, ending, {key: int(value) for key, value in touching.items()}

    def missing_counts(key: str, category: str | None = None) -> dict[Any, int]:
        if missing_timestamps.empty:
            return {}
        selected = missing_timestamps
        if category is not None:
            selected = selected[selected["preliminary_category"] == category]
        periods = missing_periods[key].loc[selected.index]
        return {
            period: int(value)
            for period, value in periods.value_counts().sort_index().items()
        }

    def records(group_key: str) -> pd.DataFrame:
        beginning, ending, touching = gap_period_sets(group_key)
        missing_all = missing_counts(group_key)
        missing_nonweekend = missing_counts(group_key, "non_weekend_intraday")
        missing_nonweekly = {}
        if not missing_timestamps.empty:
            selected = missing_timestamps[
                missing_timestamps["preliminary_category"] != "likely_weekly_closure"
            ]
            periods = missing_periods[group_key].loc[selected.index]
            missing_nonweekly = {
                period: int(value)
                for period, value in periods.value_counts().sort_index().items()
            }
        output: list[dict[str, Any]] = []
        for key, group in base.groupby(group_key, sort=True):
            record = {
                group_key: key,
                "first_timestamp": group["timestamp"].min(),
                "last_timestamp": group["timestamp"].max(),
                "bar_count": len(group),
                "unique_utc_dates": int(group["timestamp"].dt.date.nunique()),
                "gaps_beginning_in_period": int((beginning == key).sum()),
                "gaps_ending_in_period": int((ending == key).sum()),
                "gaps_touching_period": touching.get(key, 0),
                "estimated_missing_m15_timestamps_in_period": missing_all.get(key, 0),
                "count_field_non_null_count": int(group["count"].notna().sum()),
                "count_field_complete_percentage": float(
                    100.0 * group["count"].notna().mean()
                ),
                "count_field_median": float(group["count"].median()),
            }
            if group_key == "month":
                if gaps.empty:
                    nonweekly_touch = 0
                    nonweekend_touch = 0
                else:
                    touches = (beginning == key) | (ending == key)
                    nonweekly_touch = int(
                        (
                            touches
                            & (gaps["preliminary_category"] != "likely_weekly_closure")
                        ).sum()
                    )
                    nonweekend_touch = int(
                        (
                            touches
                            & (gaps["preliminary_category"] == "non_weekend_intraday")
                        ).sum()
                    )
                record.update(
                    {
                        "nonweekly_gaps_touching_period": nonweekly_touch,
                        "nonweekend_gaps_touching_period": nonweekend_touch,
                        "estimated_nonweekly_missing_timestamps_in_period": (
                            missing_nonweekly.get(key, 0)
                        ),
                        "estimated_nonweekend_missing_timestamps_in_period": (
                            missing_nonweekend.get(key, 0)
                        ),
                    }
                )
            output.append(record)
        return pd.DataFrame(output)

    annual = records("year").reindex(columns=ANNUAL_COVERAGE_COLUMNS)
    monthly = records("month")
    monthly["boundary_month"] = False
    if not monthly.empty:
        monthly.loc[[monthly.index[0], monthly.index[-1]], "boundary_month"] = True
    monthly["sparse_month"] = False
    for _year, indices in monthly.groupby(monthly["month"].str[:4]).groups.items():
        candidates = monthly.loc[indices]
        reference = float(candidates["bar_count"].median())
        monthly.loc[indices, "sparse_month"] = (
            candidates["bar_count"] < sparse_fraction * reference
        )
    monthly["continuity_impaired_month"] = (
        monthly["nonweekend_gaps_touching_period"] >= continuity_gap_threshold
    )
    monthly["partial_observed_month"] = monthly[
        ["boundary_month", "sparse_month", "continuity_impaired_month"]
    ].any(axis=1)

    def reasons(row: pd.Series) -> str:
        values: list[str] = []
        if row["boundary_month"]:
            values.append("observed_dataset_boundary")
        if row["sparse_month"]:
            values.append(f"bar_count_below_{sparse_fraction:g}_year_median")
        if row["continuity_impaired_month"]:
            values.append(
                f"nonweekend_gaps_touching_period>={continuity_gap_threshold}"
            )
        return "|".join(values)

    monthly["classification_reasons"] = monthly.apply(reasons, axis=1)
    monthly = monthly.reindex(columns=MONTHLY_COVERAGE_COLUMNS)
    calendar = {
        "utc_weekday_bar_counts": {
            str(key): int(value)
            for key, value in base["timestamp"]
            .dt.day_name()
            .value_counts()
            .sort_index()
            .items()
        },
        "utc_hour_bar_counts": {
            str(int(key)): int(value)
            for key, value in base["timestamp"]
            .dt.hour.value_counts()
            .sort_index()
            .items()
        },
        "minute_within_hour_bar_counts": {
            str(int(key)): int(value)
            for key, value in base["timestamp"]
            .dt.minute.value_counts()
            .sort_index()
            .items()
        },
        "interpretation_limit": "Coverage diagnostics only; not market behaviour.",
    }
    return annual, monthly, calendar


def _weekly_boundaries(
    timestamps: pd.Series, cadence_minutes: int, weekly_minimum_minutes: int
) -> dict[str, Any]:
    valid = timestamps.dropna().reset_index(drop=True)
    diffs = valid.diff().dt.total_seconds().div(60)
    weekly_positions = diffs[
        (diffs >= weekly_minimum_minutes)
        & valid.shift().dt.weekday.isin([4, 5])
        & valid.dt.weekday.isin([6, 0])
    ].index
    before = valid.shift().loc[weekly_positions]
    after = valid.loc[weekly_positions]

    def time_counts(values: pd.Series) -> dict[str, int]:
        labels = values.dt.strftime("%H:%M")
        return {str(key): int(value) for key, value in labels.value_counts().items()}

    yearly: list[dict[str, Any]] = []
    for year in sorted(int(value) for value in after.dt.year.unique()):
        mask = after.dt.year == year
        yearly.append(
            {
                "year": year,
                "friday_or_saturday_last_bar_times_utc": time_counts(before[mask]),
                "sunday_or_monday_first_bar_times_utc": time_counts(after[mask]),
            }
        )
    common_before = before.dt.hour * 60 + before.dt.minute
    common_after = after.dt.hour * 60 + after.dt.minute
    return {
        "boundary_count": len(weekly_positions),
        "common_last_bar_times_utc": time_counts(before),
        "common_first_bar_times_utc": time_counts(after),
        "variation_by_year": yearly,
        "unusually_early_last_boundaries": [
            _iso(value)
            for value in before[common_before < common_before.quantile(0.05)].head(20)
        ],
        "unusually_late_first_boundaries": [
            _iso(value)
            for value in after[common_after > common_after.quantile(0.95)].head(20)
        ],
        "rule": (
            f"interval >= {weekly_minimum_minutes} minutes with weekday transition "
            "Friday/Saturday to Sunday/Monday; expected cadence "
            f"{cadence_minutes} minutes"
        ),
        "interpretation_limit": (
            "No session or fixed-UTC-offset explanation is assigned."
        ),
    }


def _movement_diagnostics(
    raw: pd.DataFrame,
    numeric: dict[str, pd.Series],
    timestamps: pd.Series,
    top_n: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    interval = timestamps.diff().dt.total_seconds().div(60)
    change = numeric["close"].diff()
    records: list[pd.DataFrame] = []
    summary: dict[str, Any] = {}
    for label, mask in {
        "exact_15_minute": interval == 15,
        "longer_than_15_minute_gap": interval > 15,
    }.items():
        positions = change.abs()[mask].nlargest(top_n).index
        output: list[dict[str, Any]] = []
        for position in positions:
            prior = position - 1
            output.append(
                {
                    "interval_class": label,
                    "timestamp_before": timestamps.iloc[prior],
                    "timestamp_after": timestamps.iloc[position],
                    "interval_minutes": interval.iloc[position],
                    "close_before": numeric["close"].iloc[prior],
                    "close_after": numeric["close"].iloc[position],
                    "close_change": change.iloc[position],
                    "absolute_close_change": abs(change.iloc[position]),
                    **{
                        f"before_{column}": numeric[column].iloc[prior]
                        for column in PRICE_COLUMNS
                    },
                    **{
                        f"after_{column}": numeric[column].iloc[position]
                        for column in PRICE_COLUMNS
                    },
                }
            )
        frame = pd.DataFrame(output, columns=EXTREME_MOVEMENT_COLUMNS)
        records.append(frame)
        summary[label] = {
            "sample_size": int(mask.sum()),
            "absolute_change_statistics": _describe(change[mask].abs()),
            "largest_observations": json_safe(frame.head(10).to_dict("records")),
        }
    non_empty = [frame for frame in records if not frame.empty]
    combined = (
        pd.concat(non_empty, ignore_index=True)
        if non_empty
        else pd.DataFrame(columns=EXTREME_MOVEMENT_COLUMNS)
    )
    return summary, combined


def _internal_consistency(
    counts: pd.Series,
    timestamps: pd.Series,
    gaps: pd.DataFrame,
    missing_timestamps: pd.DataFrame,
    affected_period: dict[str, Any] | None,
    *,
    large_gap_minimum_minutes: int,
    low_count_quantile: float,
    percentiles: tuple[float, ...],
    boundary_radius_bars: int,
) -> dict[str, Any]:
    threshold = float(counts.quantile(low_count_quantile))
    low = counts < threshold
    timestamp_strings = timestamps.astype(str)

    def endpoint_mask(selected: pd.DataFrame) -> pd.Series:
        mask = pd.Series(False, index=counts.index)
        if selected.empty:
            return mask
        endpoint_values = set(selected["timestamp_before"].astype(str)) | set(
            selected["timestamp_after"].astype(str)
        )
        mask |= timestamp_strings.isin(endpoint_values)
        if boundary_radius_bars:
            positions = np.flatnonzero(mask.to_numpy())
            expanded = np.concatenate(
                [
                    np.arange(
                        max(0, int(position) - boundary_radius_bars),
                        min(
                            len(mask),
                            int(position) + boundary_radius_bars + 1,
                        ),
                    )
                    for position in positions
                ]
            )
            mask.iloc[np.unique(expanded)] = True
        return mask

    weekly = gaps[gaps["preliminary_category"] == "likely_weekly_closure"]
    large = gaps[gaps["duration_minutes"] >= large_gap_minimum_minutes]
    weekly_mask = endpoint_mask(weekly)
    large_mask = endpoint_mask(large)

    nonweekly = gaps[gaps["preliminary_category"] != "likely_weekly_closure"]
    impaired_dates: set[object] = set()
    if not nonweekly.empty:
        impaired_dates |= set(
            pd.to_datetime(nonweekly["timestamp_before"], utc=True).dt.date
        )
        impaired_dates |= set(
            pd.to_datetime(nonweekly["timestamp_after"], utc=True).dt.date
        )
    if not missing_timestamps.empty:
        selected_missing = missing_timestamps[
            missing_timestamps["preliminary_category"] != "likely_weekly_closure"
        ]
        impaired_dates |= set(
            pd.to_datetime(selected_missing["missing_timestamp_utc"], utc=True).dt.date
        )
    observed_dates = timestamps.dt.date
    impaired_date_mask = observed_dates.isin(impaired_dates)
    boundary_date_mask = observed_dates.isin(
        {observed_dates.dropna().min(), observed_dates.dropna().max()}
    )
    weekly_dates = set(
        pd.to_datetime(weekly["timestamp_before"], utc=True).dt.date
    ) | set(pd.to_datetime(weekly["timestamp_after"], utc=True).dt.date)
    expected_weekly_date_mask = observed_dates.isin(weekly_dates) & ~impaired_date_mask
    ordinary_mask = (
        ~impaired_date_mask & ~boundary_date_mask & ~expected_weekly_date_mask
    )

    affected_mask = pd.Series(False, index=counts.index)
    affected_comparator = pd.Series(False, index=counts.index)
    if affected_period:
        start = pd.to_datetime(affected_period["first_timestamp_before"], utc=True)
        end = pd.to_datetime(affected_period["last_timestamp_after"], utc=True)
        affected_mask = timestamps.between(start, end)
        affected_comparator = (timestamps.dt.year == 2023) & ~affected_mask

    def statistics(mask: pd.Series) -> dict[str, Any]:
        return {
            "sample_size": int(mask.sum()),
            "count_field_summary": _describe(counts[mask], percentiles),
            "low_count_observation_count": int((low & mask).sum()),
            "low_count_rate_percentage": (
                float(100.0 * low[mask].mean()) if mask.any() else 0.0
            ),
        }

    def comparison(
        mask: pd.Series, comparator: pd.Series | None = None
    ) -> dict[str, Any]:
        compared = ~mask if comparator is None else comparator
        return {
            "subset": statistics(mask),
            "comparator_subset": statistics(compared),
        }

    return {
        "low_value_definition": (
            f"below empirical configured {low_count_quantile:g} quantile"
        ),
        "low_value_threshold": threshold,
        "configured_percentiles": list(percentiles),
        "weekly_boundary_mask_definition": (
            "rows immediately before and after classified weekly gaps"
            f" plus {boundary_radius_bars} configured adjacent bars"
        ),
        "large_gap_mask_definition": (
            "rows immediately before and after gaps with duration >= "
            f"{large_gap_minimum_minutes} configured minutes"
        ),
        "all_observations": statistics(pd.Series(True, index=counts.index)),
        "weekly_boundary_observations": comparison(weekly_mask),
        "large_gap_observations": comparison(large_mask),
        "continuity_impaired_utc_date_observations": comparison(impaired_date_mask),
        "computed_2023_affected_period_observations": comparison(
            affected_mask, affected_comparator
        ),
        "utc_date_quality_counts": {
            "boundary_date_observations": int(boundary_date_mask.sum()),
            "expected_weekly_boundary_date_observations": int(
                expected_weekly_date_mask.sum()
            ),
            "continuity_impaired_date_observations": int(impaired_date_mask.sum()),
            "ordinary_date_observations": int(ordinary_mask.sum()),
        },
        "affected_period_bounds": affected_period,
        "interpretation_limit": (
            "Descriptive associations only; no causal meaning assigned."
        ),
    }


def _gap_summary(
    gaps: pd.DataFrame, *, weekly_minutes: int, large_minutes: int
) -> dict[str, Any]:
    if gaps.empty:
        return {
            "gap_count": 0,
            "estimated_missing_m15_timestamps": 0,
            "category_counts": {},
            "gap_size_frequency": [],
            "largest_gaps": [],
        }
    frequency = (
        gaps.groupby("duration_minutes", sort=True)
        .agg(
            gap_count=("duration_minutes", "size"),
            first_occurrence=("timestamp_before", "min"),
            last_occurrence=("timestamp_before", "max"),
            estimated_missing_m15_timestamps=(
                "estimated_missing_m15_timestamps",
                "sum",
            ),
        )
        .reset_index()
    )
    return {
        "gap_count": len(gaps),
        "estimated_missing_m15_timestamps": int(
            gaps["estimated_missing_m15_timestamps"].sum()
        ),
        "category_counts": {
            str(key): int(value)
            for key, value in gaps["preliminary_category"].value_counts().items()
        },
        "category_definitions": {
            "likely_weekly_closure": (
                f"Duration >= {weekly_minutes} minutes; endpoint weekdays "
                "Friday/Saturday "
                "to Sunday/Monday."
            ),
            "long_nonweekly_gap": (
                f"Duration >= {large_minutes} minutes outside the weekly rule; "
                "UTC-date crossing is recorded separately; cause unresolved."
            ),
            "non_weekend_intraday": (
                "Both endpoints Monday-Friday and duration below "
                f"{large_minutes} minutes."
            ),
            "unclassified": "All other intervals above expected cadence.",
        },
        "gap_size_frequency": json_safe(frequency.to_dict("records")),
        "largest_gaps": json_safe(
            gaps.nlargest(25, "duration_minutes").to_dict("records")
        ),
    }


def _investigate_2023(
    gaps: pd.DataFrame,
    monthly: pd.DataFrame,
    *,
    recurring_minimum_count: int,
    large_gap_minutes: int,
) -> dict[str, Any]:
    outside_weekly = gaps[
        gaps["preliminary_category"] != "likely_weekly_closure"
    ].copy()
    non_weekend = gaps[gaps["preliminary_category"] == "non_weekend_intraday"].copy()
    if outside_weekly.empty:
        return {
            "all_gaps_outside_weekly_rule_by_year": [],
            "non_weekend_intraday_gaps_by_year": [],
            "gap_size_frequency_by_year": [],
            "monthly_missing_timestamps": [],
            "monthly_non_weekend_intraday_missing_timestamps": [],
            "concentrated_2023_period": None,
            "recurring_intraday_pattern_2023": [],
            "materially_different_from_2022_and_2024": False,
        }
    outside_after = pd.to_datetime(outside_weekly["timestamp_after"], utc=True)
    outside_weekly["year"] = outside_after.dt.year
    non_weekend_after = pd.to_datetime(non_weekend["timestamp_after"], utc=True)
    non_weekend["year"] = non_weekend_after.dt.year
    annual_outside = (
        outside_weekly.groupby("year")
        .agg(
            gap_count=("duration_minutes", "size"),
            estimated_missing_m15_timestamps=(
                "estimated_missing_m15_timestamps",
                "sum",
            ),
        )
        .reset_index()
    )
    annual_non_weekend = (
        non_weekend.groupby("year")
        .agg(
            gap_count=("duration_minutes", "size"),
            estimated_missing_m15_timestamps=(
                "estimated_missing_m15_timestamps",
                "sum",
            ),
        )
        .reset_index()
    )
    frequency = (
        outside_weekly.groupby(["year", "duration_minutes"])
        .size()
        .rename("gap_count")
        .reset_index()
    )
    intraday_2023 = non_weekend[non_weekend["year"] == 2023]
    duration_frequency = intraday_2023["duration_minutes"].value_counts()
    recurring_durations = duration_frequency[
        (duration_frequency >= recurring_minimum_count)
        & (duration_frequency.index < large_gap_minutes)
    ].index
    systematic = intraday_2023[
        intraday_2023["duration_minutes"].isin(recurring_durations)
    ]
    patterns = []
    if not intraday_2023.empty:
        pattern = (
            pd.DataFrame(
                {
                    "before_time_utc": pd.to_datetime(
                        intraday_2023["timestamp_before"], utc=True
                    ).dt.strftime("%H:%M"),
                    "after_time_utc": pd.to_datetime(
                        intraday_2023["timestamp_after"], utc=True
                    ).dt.strftime("%H:%M"),
                    "duration_minutes": intraday_2023["duration_minutes"],
                }
            )
            .value_counts()
            .head(20)
            .rename("count")
            .reset_index()
        )
        patterns = json_safe(pattern.to_dict("records"))
    annual_map = annual_non_weekend.set_index("year")[
        "estimated_missing_m15_timestamps"
    ].to_dict()
    adjacent = [annual_map.get(2022, 0), annual_map.get(2024, 0)]
    materially_different = annual_map.get(2023, 0) > max([*adjacent, 0]) * 2
    monthly_non_weekend = (
        non_weekend.assign(month=non_weekend_after.dt.strftime("%Y-%m"))
        .groupby("month")
        .agg(
            gap_count=("duration_minutes", "size"),
            estimated_missing_m15_timestamps=(
                "estimated_missing_m15_timestamps",
                "sum",
            ),
        )
        .reset_index()
    )
    return {
        "all_gaps_outside_weekly_rule_by_year": json_safe(
            annual_outside.to_dict("records")
        ),
        "non_weekend_intraday_gaps_by_year": json_safe(
            annual_non_weekend.to_dict("records")
        ),
        "gap_size_frequency_by_year": json_safe(frequency.to_dict("records")),
        "monthly_missing_timestamps": json_safe(
            monthly[
                [
                    "month",
                    "gaps_ending_in_period",
                    "estimated_missing_m15_timestamps_in_period",
                ]
            ].to_dict("records")
        ),
        "monthly_non_weekend_intraday_missing_timestamps": json_safe(
            monthly_non_weekend.to_dict("records")
        ),
        "concentrated_2023_period": (
            {
                "definition": (
                    "2023 non-weekend intraday durations occurring at least "
                    f"{recurring_minimum_count} times and below "
                    f"{large_gap_minutes} minutes"
                ),
                "included_duration_minutes": sorted(
                    float(value) for value in recurring_durations
                ),
                "first_timestamp_before": _iso(
                    pd.to_datetime(systematic["timestamp_before"], utc=True).min()
                ),
                "last_timestamp_after": _iso(
                    pd.to_datetime(systematic["timestamp_after"], utc=True).max()
                ),
                "gap_count": len(systematic),
                "estimated_missing_m15_timestamps": int(
                    systematic["estimated_missing_m15_timestamps"].sum()
                ),
            }
            if not systematic.empty
            else None
        ),
        "recurring_intraday_pattern_2023": patterns,
        "materiality_rule": (
            "2023 estimated non-weekend intraday missing timestamps > 2x each of "
            "2022 and 2024"
        ),
        "materially_different_from_2022_and_2024": bool(materially_different),
    }


def _readiness(
    *,
    failures: list[str],
    gaps: pd.DataFrame,
    partial_periods: bool,
    unresolved: list[str],
) -> dict[str, Any]:
    """Apply criteria declared independently of observed production results."""
    if failures:
        return {
            "state": "NOT_READY",
            "reasons": failures,
            "required_actions": [
                "Resolve every fatal identity, schema, timestamp, duplicate, or "
                "OHLC issue."
            ],
        }
    conditional_reasons: list[str] = []
    non_weekly = gaps[gaps["preliminary_category"] != "likely_weekly_closure"]
    if not non_weekly.empty:
        conditional_reasons.append(
            f"{len(non_weekly)} gaps outside the conservative weekly-closure rule"
        )
    if partial_periods:
        conditional_reasons.append("Partial boundary years or months are present")
    if unresolved:
        conditional_reasons.append("Source semantics remain undocumented")
    if conditional_reasons:
        return {
            "state": "CONDITIONALLY_READY",
            "reasons": conditional_reasons,
            "required_actions": [
                "Define research-specific coverage/exclusion treatment before "
                "feature work.",
                "Obtain source documentation for unresolved field and timestamp "
                "semantics.",
                "Retain sensitivity checks for affected periods.",
            ],
        }
    return {
        "state": "READY",
        "reasons": ["No material technical integrity issue detected"],
        "required_actions": [],
    }


def _unresolved_assumptions(config: DataConfig) -> list[str]:
    unresolved: list[str] = []
    if config.timestamp_convention is None:
        unresolved.append(
            "Whether timestamp_utc denotes candle open time or candle close time."
        )
    if config.quote_convention is None:
        unresolved.append("The EUR/USD price quote convention.")
    if config.count_field_semantics is None:
        unresolved.append(
            "The semantic meaning of volume_or_tick_count; it is treated only as "
            "a source-provided count field."
        )
    if not config.upstream_feed_continuity_documented:
        unresolved.append(
            "Continuity and identity of the upstream feed behind the source label."
        )
    return unresolved


def _warning_list(
    *,
    gaps: pd.DataFrame,
    investigation: dict[str, Any],
    partial: dict[str, Any],
    unresolved: list[str],
    count_invalid: bool = False,
    source_invalid: bool = False,
) -> list[str]:
    warnings: list[str] = []
    nonweekly = gaps[gaps["preliminary_category"] != "likely_weekly_closure"]
    if not nonweekly.empty:
        warnings.append(
            f"COVERAGE: {len(nonweekly)} gaps fall outside the configured weekly rule."
        )
    if investigation.get("materially_different_from_2022_and_2024"):
        warnings.append(
            "COVERAGE: 2023 satisfies the predefined continuity-impairment "
            "materiality rule."
        )
    if partial.get("incomplete_first_year") or partial.get("incomplete_final_year"):
        warnings.append("COVERAGE: The first or final observed year is partial.")
    impaired = partial.get("continuity_impaired_months", [])
    if impaired:
        warnings.append(
            "COVERAGE: Continuity-impaired months were detected: "
            + ", ".join(impaired)
            + "."
        )
    if count_invalid:
        warnings.append(
            "DATA_VALUE: The source-provided count field has invalid or missing values."
        )
    if source_invalid:
        warnings.append("DATA_VALUE: Source labels contain null or empty values.")
    labels = (
        ("timestamp_utc denotes candle open", "SEMANTIC: Timestamp convention"),
        ("price quote convention", "SEMANTIC: Quote convention"),
        ("volume_or_tick_count", "SEMANTIC: Source-provided count-field semantics"),
        ("upstream feed", "SEMANTIC: Upstream-feed continuity"),
    )
    for fragment, label in labels:
        if any(fragment in item for item in unresolved):
            warnings.append(f"{label} remains unresolved.")
    return warnings


def run_raw_data_audit(
    path: Path,
    config: DataConfig,
    *,
    repository_root: Path,
    manifest_path: Path | None = None,
    audit_timestamp: datetime | None = None,
) -> tuple[AuditResult, dict[str, pd.DataFrame]]:
    """Run the complete audit without writing to or mutating the raw CSV."""
    started = time.perf_counter()
    audit_time = (audit_timestamp or datetime.now(UTC)).astimezone(UTC)
    resolved_manifest_path = manifest_path or (
        repository_root / config.registered_manifest_path
    )
    unresolved = _unresolved_assumptions(config)
    failures: list[str] = []
    LOGGER.info("Audit stage: read authoritative manifest and verify identity")
    try:
        manifest = read_manifest(resolved_manifest_path)
    except ManifestError as error:
        failures.append(str(error))
        return _minimal_failed_result(
            path, config, audit_time, None, None, None, failures, unresolved
        ), _empty_tables()
    try:
        stat_before = path.stat()
        checksum_before = sha256_file(path)
    except (FileNotFoundError, OSError) as error:
        failures.append(str(error))
        return _minimal_failed_result(
            path, config, audit_time, manifest, None, None, failures, unresolved
        ), _empty_tables()
    actual_relative = path.resolve().relative_to(repository_root.resolve()).as_posix()
    actual_version = f"sha256:{checksum_before[:16]}"
    if manifest.logical_dataset_name != config.dataset_logical_name:
        failures.append("Manifest/config logical dataset identifiers disagree")
    if manifest.relative_file_path != config.raw_dataset_path.as_posix():
        failures.append("Manifest/config registered relative paths disagree")
    if manifest.dataset_version != config.expected_dataset_version:
        failures.append("Manifest/config dataset versions disagree")
    if actual_relative != manifest.relative_file_path:
        failures.append("Manifest/file relative paths disagree")
    if checksum_before != manifest.sha256:
        failures.append("Manifest/file SHA-256 values disagree")
    if stat_before.st_size != manifest.file_size_bytes:
        failures.append("Manifest/file sizes disagree")
    if actual_version != config.expected_dataset_version:
        failures.append("Configuration/file dataset versions disagree")

    LOGGER.info("Audit stage: load CSV source text")
    raw, load_details = _load_csv_once(path, config.expected_columns)
    observed_columns = tuple(load_details["columns"])
    missing_columns = [
        column for column in config.expected_columns if column not in observed_columns
    ]
    unexpected_columns = [
        column for column in observed_columns if column not in config.expected_columns
    ]
    exact_schema = observed_columns == config.expected_columns
    if manifest.detected_columns != observed_columns:
        failures.append("Manifest/file column names or order disagree")
    if manifest.detected_columns != config.expected_columns:
        failures.append("Manifest/config column names or order disagree")
    if len(raw) != manifest.row_count:
        failures.append("Manifest/file row counts disagree")
    if not exact_schema:
        failures.append("Mandatory CSV schema names/order are not satisfied")
    if load_details["malformed_rows"]:
        failures.append("Malformed CSV rows were detected")
    if missing_columns:
        return _minimal_failed_result(
            path,
            config,
            audit_time,
            manifest,
            raw,
            load_details,
            failures,
            unresolved,
        ), _empty_tables()

    LOGGER.info("Audit stage: parse timestamps and numeric fields")
    timestamps, timestamp_results = _timestamp_results(raw[config.timestamp_column])
    numeric = {
        column: pd.to_numeric(raw[column].str.strip(), errors="coerce")
        for column in (*PRICE_COLUMNS, COUNT_COLUMN)
    }
    duplicate_timestamp = timestamps.duplicated(keep=False) & timestamps.notna()
    duplicate_rows = raw.duplicated(keep=False)
    if timestamp_results["unparseable_count"]:
        failures.append("One or more timestamps are unparseable")
    if timestamp_results["source_values_without_explicit_timezone_count"]:
        failures.append("One or more source timestamps lack an explicit timezone")
    if duplicate_timestamp.any():
        failures.append("Duplicate primary timestamps affect interpretation")
    if not timestamp_results["chronologically_ordered"]:
        failures.append("Timestamps are not chronologically ordered")
    if timestamp_results["off_15_minute_grid_count"]:
        failures.append("One or more timestamps are off the M15 grid")
    first_matches = timestamp_results["first_timestamp"] == manifest.first_timestamp
    last_matches = timestamp_results["last_timestamp"] == manifest.last_timestamp
    if not first_matches or not last_matches:
        failures.append("Manifest/file timestamp boundaries disagree")

    missing_results = _missing_results(raw, numeric)
    LOGGER.info("Audit stage: validate OHLC and descriptive fields")
    ohlc_results, ohlc_violations = _ohlc_results(
        raw, numeric, timestamps, config.audit.unusual_range_quantile
    )
    if ohlc_results["combined_invalid_ohlc_count"]:
        failures.append("Material invalid OHLC records are present")
    count_results, count_distribution = _count_results(
        numeric[COUNT_COLUMN],
        raw[COUNT_COLUMN],
        timestamps,
        config.audit.report_percentiles,
    )
    count_invalid = bool(
        count_results["null_count"]
        or count_results["non_finite_count"]
        or count_results["below_zero_count"]
        or count_results["non_integer_count"]
    )
    source_results = _source_results(raw[SOURCE_COLUMN], timestamps)
    source_invalid = bool(source_results["null_count"] or source_results["empty_count"])

    LOGGER.info("Audit stage: gaps, missing-grid allocation, and coverage")
    gaps = build_gap_table(
        timestamps,
        cadence_minutes=config.audit.cadence_minutes,
        weekly_minimum_minutes=config.audit.weekly_gap_minimum_minutes,
        large_gap_minimum_minutes=config.audit.large_gap_minimum_minutes,
    )
    missing_grid = expand_missing_timestamps(gaps, config.audit.cadence_minutes)
    annual, monthly, calendar = _coverage_tables(
        timestamps,
        gaps,
        missing_grid,
        numeric[COUNT_COLUMN],
        config.audit.sparse_month_fraction,
        config.audit.continuity_impaired_min_nonweekend_gap_count,
    )
    expected_missing = int(gaps["estimated_missing_m15_timestamps"].sum())
    if (
        len(missing_grid) != expected_missing
        or int(annual["estimated_missing_m15_timestamps_in_period"].sum())
        != expected_missing
        or int(monthly["estimated_missing_m15_timestamps_in_period"].sum())
        != expected_missing
    ):
        failures.append("Missing-timestamp period allocations do not reconcile")
    investigation = _investigate_2023(
        gaps,
        monthly,
        recurring_minimum_count=config.audit.recurring_gap_minimum_count,
        large_gap_minutes=config.audit.large_gap_minimum_minutes,
    )
    years = timestamps.dropna().dt.year
    partial = {
        "incomplete_first_year": bool(
            timestamp_results["first_timestamp"]
            and not timestamp_results["first_timestamp"].endswith("01-01T00:00:00Z")
        ),
        "first_year": int(years.min()) if not years.empty else None,
        "incomplete_final_year": bool(
            timestamp_results["last_timestamp"]
            and not timestamp_results["last_timestamp"].endswith("12-31T23:45:00Z")
        ),
        "final_year": int(years.max()) if not years.empty else None,
        "final_timestamp_observation": (
            "Coverage ends at the observed registered final timestamp; no assumption "
            "is made that later data should exist."
        ),
        "boundary_months": monthly.loc[monthly["boundary_month"], "month"].tolist(),
        "sparse_months": monthly.loc[monthly["sparse_month"], "month"].tolist(),
        "continuity_impaired_months": monthly.loc[
            monthly["continuity_impaired_month"], "month"
        ].tolist(),
        "partial_observed_months": monthly.loc[
            monthly["partial_observed_month"], "month"
        ].tolist(),
        "definitions": {
            "boundary_month": "first or final observed UTC month",
            "sparse_month": (
                f"bar count below {config.audit.sparse_month_fraction:.0%} of "
                "within-year monthly median"
            ),
            "continuity_impaired_month": (
                "non-weekend intraday gaps touching month >= "
                f"{config.audit.continuity_impaired_min_nonweekend_gap_count}"
            ),
        },
    }
    warnings = _warning_list(
        gaps=gaps,
        investigation=investigation,
        partial=partial,
        unresolved=unresolved,
        count_invalid=count_invalid,
        source_invalid=source_invalid,
    )
    readiness = _readiness(
        failures=failures,
        gaps=gaps,
        partial_periods=bool(partial["partial_observed_months"]),
        unresolved=unresolved,
    )
    movement_summary, movements = _movement_diagnostics(
        raw, numeric, timestamps, config.audit.extreme_movement_rows_per_class
    )
    stat_after = path.stat()
    checksum_after = sha256_file(path)
    if (
        stat_before.st_size,
        stat_before.st_mtime_ns,
        checksum_before,
    ) != (stat_after.st_size, stat_after.st_mtime_ns, checksum_after):
        failures.append("Raw file changed during audit")
        readiness = _readiness(
            failures=failures, gaps=gaps, partial_periods=True, unresolved=unresolved
        )
    affected = investigation.get("concentrated_2023_period")
    result = AuditResult(
        audit_metadata={
            "audit_timestamp_utc": audit_time.isoformat().replace("+00:00", "Z"),
            "audit_method_version": "raw-data-quality-audit-v2",
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "read_only": True,
            "effective_thresholds": {
                "cadence_minutes": config.audit.cadence_minutes,
                "weekly_gap_minimum_minutes": config.audit.weekly_gap_minimum_minutes,
                "large_gap_minimum_minutes": config.audit.large_gap_minimum_minutes,
                "continuity_impaired_min_nonweekend_gap_count": (
                    config.audit.continuity_impaired_min_nonweekend_gap_count
                ),
                "recurring_gap_minimum_count": config.audit.recurring_gap_minimum_count,
            },
            "deterministic_serialization": {
                "stable": (
                    "analytical content, ordered warnings/failures, CSV and Markdown"
                ),
                "volatile_json_fields": [
                    "audit_metadata.audit_timestamp_utc",
                    "audit_metadata.elapsed_seconds",
                    "dataset_identity.raw_file_modification_timestamp_utc",
                ],
            },
        },
        dataset_identity={
            "manifest_relative_path": config.registered_manifest_path.as_posix(),
            "relative_file_path": actual_relative,
            "file_exists": True,
            "file_size_bytes": stat_after.st_size,
            "manifest_file_size_bytes": manifest.file_size_bytes,
            "file_size_matches_manifest": stat_after.st_size
            == manifest.file_size_bytes,
            "sha256_before": checksum_before,
            "sha256_after": checksum_after,
            "manifest_sha256": manifest.sha256,
            "checksum_matches_manifest": checksum_after == manifest.sha256,
            "raw_file_modification_timestamp_utc": datetime.fromtimestamp(
                stat_after.st_mtime, UTC
            )
            .isoformat()
            .replace("+00:00", "Z"),
            "dataset_version": actual_version,
            "manifest_dataset_version": manifest.dataset_version,
            "logical_dataset_name": config.dataset_logical_name,
            "manifest_logical_dataset_name": manifest.logical_dataset_name,
            "raw_unchanged_during_audit": checksum_before == checksum_after
            and stat_before.st_mtime_ns == stat_after.st_mtime_ns,
            "manifest_config_file_reconciliation_satisfied": not any(
                "Manifest/" in failure or "Configuration/file" in failure
                for failure in failures
            ),
        },
        schema_results={
            "row_count": len(raw),
            "manifest_row_count": manifest.row_count,
            "row_count_matches_manifest": len(raw) == manifest.row_count,
            "column_count": len(observed_columns),
            "exact_column_names_and_order": list(observed_columns),
            "manifest_columns": list(manifest.detected_columns),
            "configured_expected_columns": list(config.expected_columns),
            "configured_expected_types": {
                "timestamp_utc": "UTC-aware timestamp",
                **{column: "finite positive decimal" for column in PRICE_COLUMNS},
                COUNT_COLUMN: "non-negative integer-like count",
                SOURCE_COLUMN: "non-empty string",
            },
            "inferred_pandas_dtypes_source_text": {
                column: str(pd.api.types.infer_dtype(raw[column], skipna=True))
                for column in raw.columns
            },
            "parsed_pandas_dtypes": {
                config.timestamp_column: str(timestamps.dtype),
                **{column: str(values.dtype) for column, values in numeric.items()},
                SOURCE_COLUMN: str(raw[SOURCE_COLUMN].dtype),
            },
            "unexpected_columns": unexpected_columns,
            "missing_expected_columns": missing_columns,
            "mandatory_schema_satisfied": exact_schema,
            "completely_empty_rows": load_details["completely_empty_rows"],
            "malformed_row_count": len(load_details["malformed_rows"]),
            "malformed_row_samples": load_details["malformed_rows"][:10],
            "column_name_whitespace_issues": [
                column for column in observed_columns if column != column.strip()
            ],
            "string_value_whitespace_counts": {
                column: int(raw[column].ne(raw[column].str.strip()).sum())
                for column in raw.columns
            },
        },
        timestamp_results={
            **timestamp_results,
            "manifest_first_timestamp": manifest.first_timestamp,
            "manifest_last_timestamp": manifest.last_timestamp,
            "first_timestamp_matches_manifest": first_matches,
            "last_timestamp_matches_manifest": last_matches,
            "timestamps_before_manifest_boundary": int(
                (
                    timestamps
                    < pd.to_datetime(
                        manifest.first_timestamp, utc=True, errors="coerce"
                    )
                ).sum()
            ),
            "timestamps_after_manifest_boundary": int(
                (
                    timestamps
                    > pd.to_datetime(manifest.last_timestamp, utc=True, errors="coerce")
                ).sum()
            ),
            "timestamp_convention": config.timestamp_convention or "unresolved",
        },
        duplicate_results={
            "duplicate_primary_timestamp_row_count": int(duplicate_timestamp.sum()),
            "duplicate_primary_timestamp_value_count": int(
                timestamps[duplicate_timestamp].nunique()
            ),
            "duplicate_timestamp_samples": [
                _iso(value) for value in timestamps[duplicate_timestamp].head(10)
            ],
            "duplicate_complete_row_count": int(duplicate_rows.sum()),
            "duplicate_complete_row_samples": json_safe(
                raw[duplicate_rows].head(10).to_dict("records")
            ),
        },
        missing_value_results=missing_results,
        ohlc_results=ohlc_results,
        price_precision_results=_precision_results(raw, numeric, timestamps),
        count_field_results=count_results,
        source_results=source_results,
        gap_summary=_gap_summary(
            gaps,
            weekly_minutes=config.audit.weekly_gap_minimum_minutes,
            large_minutes=config.audit.large_gap_minimum_minutes,
        ),
        continuity_investigation_2023=investigation,
        calendar_coverage=calendar,
        partial_period_results=partial,
        weekly_boundary_results=_weekly_boundaries(
            timestamps,
            config.audit.cadence_minutes,
            config.audit.weekly_gap_minimum_minutes,
        ),
        movement_diagnostics=movement_summary,
        internal_consistency_results=_internal_consistency(
            numeric[COUNT_COLUMN],
            timestamps,
            gaps,
            missing_grid,
            affected,
            large_gap_minimum_minutes=config.audit.large_gap_minimum_minutes,
            low_count_quantile=config.audit.low_count_quantile,
            percentiles=config.audit.report_percentiles,
            boundary_radius_bars=config.audit.relationship_boundary_radius_bars,
        ),
        annual_coverage=json_safe(annual.to_dict("records")),
        monthly_coverage=json_safe(monthly.to_dict("records")),
        warnings=warnings,
        failures=failures,
        unresolved_assumptions=unresolved,
        final_readiness_assessment=readiness,
    )
    tables = {
        "timestamp_gaps.csv": gaps,
        "annual_coverage.csv": annual,
        "monthly_coverage.csv": monthly,
        "ohlc_violations.csv": ohlc_violations,
        "extreme_price_movements.csv": movements,
        "count_field_distribution.csv": count_distribution.reindex(
            columns=COUNT_DISTRIBUTION_COLUMNS
        ),
    }
    LOGGER.info(
        "Audit calculations complete in %.2f seconds", time.perf_counter() - started
    )
    return result, tables


def _empty_tables() -> dict[str, pd.DataFrame]:
    return {
        "timestamp_gaps.csv": pd.DataFrame(columns=GAP_COLUMNS),
        "annual_coverage.csv": pd.DataFrame(columns=ANNUAL_COVERAGE_COLUMNS),
        "monthly_coverage.csv": pd.DataFrame(columns=MONTHLY_COVERAGE_COLUMNS),
        "ohlc_violations.csv": pd.DataFrame(columns=OHLC_VIOLATION_COLUMNS),
        "extreme_price_movements.csv": pd.DataFrame(columns=EXTREME_MOVEMENT_COLUMNS),
        "count_field_distribution.csv": pd.DataFrame(
            columns=COUNT_DISTRIBUTION_COLUMNS
        ),
    }


def _minimal_failed_result(
    path: Path,
    config: DataConfig,
    audit_time: datetime,
    manifest: DatasetManifest | None,
    raw: pd.DataFrame | None,
    details: dict[str, Any] | None,
    failures: list[str],
    unresolved: list[str],
) -> AuditResult:
    empty: dict[str, Any] = {}
    warnings = _warning_list(
        gaps=pd.DataFrame(columns=GAP_COLUMNS),
        investigation={},
        partial={},
        unresolved=unresolved,
    )
    columns = details["columns"] if details else []
    return AuditResult(
        audit_metadata={
            "audit_timestamp_utc": audit_time.isoformat().replace("+00:00", "Z"),
            "audit_method_version": "raw-data-quality-audit-v2",
            "read_only": True,
        },
        dataset_identity={
            "file_exists": path.is_file(),
            "manifest_loaded": manifest is not None,
            "logical_dataset_name": config.dataset_logical_name,
        },
        schema_results={
            "row_count": len(raw) if raw is not None else 0,
            "exact_column_names_and_order": columns,
            "configured_expected_columns": list(config.expected_columns),
            "missing_expected_columns": [
                value for value in config.expected_columns if value not in columns
            ],
            "unexpected_columns": [
                value for value in columns if value not in config.expected_columns
            ],
            "mandatory_schema_satisfied": False,
            "completely_empty_rows": (
                details["completely_empty_rows"] if details else 0
            ),
            "malformed_row_count": len(details["malformed_rows"]) if details else 0,
        },
        timestamp_results=empty,
        duplicate_results=empty,
        missing_value_results=empty,
        ohlc_results=empty,
        price_precision_results=empty,
        count_field_results=empty,
        source_results=empty,
        gap_summary=empty,
        continuity_investigation_2023=empty,
        calendar_coverage=empty,
        partial_period_results=empty,
        weekly_boundary_results=empty,
        movement_diagnostics=empty,
        internal_consistency_results=empty,
        annual_coverage=[],
        monthly_coverage=[],
        warnings=warnings,
        failures=failures,
        unresolved_assumptions=unresolved,
        final_readiness_assessment={
            "state": "NOT_READY",
            "reasons": failures,
            "required_actions": ["Restore authoritative manifest/file agreement."],
        },
    )
