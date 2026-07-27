"""Deterministic cadence-gap calculations and conservative classification."""

from __future__ import annotations

import numpy as np
import pandas as pd

GAP_COLUMNS = (
    "gap_id",
    "timestamp_before",
    "timestamp_after",
    "duration_minutes",
    "estimated_missing_m15_timestamps",
    "is_grid_aligned_interval",
    "crosses_utc_date",
    "weekday_before",
    "weekday_after",
    "preliminary_category",
    "classification_reason",
)
MISSING_TIMESTAMP_COLUMNS = ("gap_id", "missing_timestamp_utc", "preliminary_category")


def estimated_missing_bars(duration_minutes: float, cadence_minutes: int = 15) -> int:
    """Count absent grid timestamps for a positive cadence-aligned interval."""
    if cadence_minutes <= 0:
        raise ValueError("cadence_minutes must be positive")
    if not np.isfinite(duration_minutes) or duration_minutes <= cadence_minutes:
        return 0
    ratio = duration_minutes / cadence_minutes
    if not np.isclose(ratio, round(ratio), atol=1e-9):
        return 0
    return max(round(ratio) - 1, 0)


def _timestamp_on_grid(timestamp: pd.Timestamp, cadence_minutes: int) -> bool:
    cadence_ns = pd.Timedelta(cadence_minutes, unit="min").value
    return bool(timestamp.value % cadence_ns == 0)


def classify_gap(
    before: pd.Timestamp,
    after: pd.Timestamp,
    duration_minutes: float,
    *,
    weekly_minimum_minutes: int,
    large_gap_minimum_minutes: int,
) -> tuple[str, str]:
    """Assign an observation-only category without a calendar-cause claim."""
    before_weekday = before.weekday()
    after_weekday = after.weekday()
    crosses_date = before.date() != after.date()
    if (
        duration_minutes >= weekly_minimum_minutes
        and before_weekday in {4, 5}
        and after_weekday in {6, 0}
    ):
        return (
            "likely_weekly_closure",
            f"duration >= {weekly_minimum_minutes} configured minutes; "
            "Friday/Saturday before and Sunday/Monday after",
        )
    if duration_minutes >= large_gap_minimum_minutes:
        date_text = "crosses a UTC date" if crosses_date else "is within one UTC date"
        return (
            "long_nonweekly_gap",
            f"duration >= {large_gap_minimum_minutes} configured minutes outside "
            f"the weekly rule; interval {date_text}; cause unresolved",
        )
    if before_weekday < 5 and after_weekday < 5:
        date_text = "crosses a UTC date" if crosses_date else "is within one UTC date"
        return (
            "non_weekend_intraday",
            "both endpoints are Monday-Friday; duration is below the configured "
            f"large-gap threshold; interval {date_text}",
        )
    return (
        "unclassified",
        "interval does not satisfy the configured descriptive category rules",
    )


def build_gap_table(
    timestamps: pd.Series,
    *,
    cadence_minutes: int,
    weekly_minimum_minutes: int,
    large_gap_minimum_minutes: int,
) -> pd.DataFrame:
    """Build one stable row for every positive interval above expected cadence."""
    valid = timestamps.dropna().reset_index(drop=True)
    differences = valid.diff().dt.total_seconds().div(60)
    records: list[dict[str, object]] = []
    for position in differences[differences > cadence_minutes].index:
        before = valid.iloc[position - 1]
        after = valid.iloc[position]
        duration = float(differences.iloc[position])
        aligned = (
            _timestamp_on_grid(before, cadence_minutes)
            and _timestamp_on_grid(after, cadence_minutes)
            and estimated_missing_bars(duration, cadence_minutes) > 0
        )
        category, reason = classify_gap(
            before,
            after,
            duration,
            weekly_minimum_minutes=weekly_minimum_minutes,
            large_gap_minimum_minutes=large_gap_minimum_minutes,
        )
        records.append(
            {
                "gap_id": len(records) + 1,
                "timestamp_before": before,
                "timestamp_after": after,
                "duration_minutes": duration,
                "estimated_missing_m15_timestamps": (
                    estimated_missing_bars(duration, cadence_minutes) if aligned else 0
                ),
                "is_grid_aligned_interval": aligned,
                "crosses_utc_date": before.date() != after.date(),
                "weekday_before": before.day_name(),
                "weekday_after": after.day_name(),
                "preliminary_category": category,
                "classification_reason": reason,
            }
        )
    return pd.DataFrame.from_records(records, columns=GAP_COLUMNS)


def expand_missing_timestamps(gaps: pd.DataFrame, cadence_minutes: int) -> pd.DataFrame:
    """Vector-expand only valid aligned absent grid points."""
    if gaps.empty:
        return pd.DataFrame(columns=MISSING_TIMESTAMP_COLUMNS)
    valid = gaps[
        gaps["is_grid_aligned_interval"]
        & (gaps["estimated_missing_m15_timestamps"] > 0)
    ].reset_index(drop=True)
    if valid.empty:
        return pd.DataFrame(columns=MISSING_TIMESTAMP_COLUMNS)
    counts = valid["estimated_missing_m15_timestamps"].to_numpy(dtype="int64")
    repeated_positions = np.repeat(np.arange(len(valid)), counts)
    group_starts = np.repeat(np.cumsum(counts) - counts, counts)
    offsets = np.arange(int(counts.sum())) - group_starts + 1
    before = pd.to_datetime(valid["timestamp_before"], utc=True).array.take(
        repeated_positions
    )
    missing = before + pd.to_timedelta(offsets * cadence_minutes, unit="min")
    return pd.DataFrame(
        {
            "gap_id": valid["gap_id"].to_numpy()[repeated_positions],
            "missing_timestamp_utc": missing,
            "preliminary_category": valid["preliminary_category"].to_numpy()[
                repeated_positions
            ],
        },
        columns=MISSING_TIMESTAMP_COLUMNS,
    )
