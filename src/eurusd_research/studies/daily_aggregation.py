"""UTC daily OHLC aggregation from Task 03 profile masks."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from eurusd_research.research.models import CoverageResult
from eurusd_research.studies.configuration import Task04Config

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
PROFILE_SLUGS = {
    "DEFAULT_RESEARCH": "default_research",
    "STRICT_CONTINUITY": "strict_continuity",
    "SENSITIVITY_FULL": "sensitivity_full",
    "SENSITIVITY_2023": "sensitivity_2023",
}


@dataclass(slots=True)
class DailyAggregationResult:
    """Profile-specific daily records plus the one-row-per-date output."""

    by_profile: dict[str, pd.DataFrame]
    wide_observations: pd.DataFrame
    raw_row_count: int


def _row_lineage_digest(values: pd.Series) -> str:
    payload = ",".join(str(int(value)) for value in values).encode()
    return hashlib.sha256(payload).hexdigest()


def _expected_schedule(dates: pd.DatetimeIndex, gaps: pd.DataFrame) -> pd.DataFrame:
    weekly = gaps.loc[
        gaps["preliminary_category"].eq("likely_weekly_closure"),
        ["timestamp_before", "timestamp_after"],
    ].copy()
    weekly["timestamp_before"] = pd.to_datetime(weekly["timestamp_before"], utc=True)
    weekly["timestamp_after"] = pd.to_datetime(weekly["timestamp_after"], utc=True)
    friday_end = {
        timestamp.date(): timestamp
        for timestamp in weekly["timestamp_before"]
        if timestamp.weekday() == 4
    }
    sunday_start = {
        timestamp.date(): timestamp
        for timestamp in weekly["timestamp_after"]
        if timestamp.weekday() == 6
    }
    records: list[dict[str, Any]] = []
    for date in dates:
        start = pd.Timestamp(date, tz="UTC")
        weekday = start.weekday()
        expected_start: pd.Timestamp | None
        expected_end: pd.Timestamp | None
        schedule_source: str
        if weekday <= 3:
            expected_start = start
            expected_end = start + timedelta(hours=23, minutes=45)
            schedule_source = "full_utc_weekday"
        elif weekday == 4:
            expected_start = start
            expected_end = friday_end.get(start.date())
            schedule_source = "task02_weekly_boundary"
        elif weekday == 6:
            expected_start = sunday_start.get(start.date())
            expected_end = start + timedelta(hours=23, minutes=45)
            schedule_source = "task02_weekly_boundary"
        else:
            expected_start = None
            expected_end = None
            schedule_source = "no_primary_market_grid"
        expected_rows = 0
        if expected_start is not None and expected_end is not None:
            duration = expected_end - expected_start
            if duration >= timedelta(0):
                expected_rows = int(duration / timedelta(minutes=15)) + 1
        records.append(
            {
                "utc_date": start.strftime("%Y-%m-%d"),
                "expected_first_timestamp_utc": expected_start,
                "expected_last_timestamp_utc": expected_end,
                "expected_m15_rows": expected_rows,
                "expected_schedule_source": schedule_source,
            }
        )
    return pd.DataFrame.from_records(records).set_index("utc_date")


def _aggregate_profile(
    raw: pd.DataFrame,
    mask: pd.Series,
    schedule: pd.DataFrame,
    *,
    profile: str,
    config: Task04Config,
    first_dataset_date: str,
    last_dataset_date: str,
) -> pd.DataFrame:
    selected = raw.loc[mask.to_numpy()].copy()
    grouped = {
        str(utc_date): group
        for utc_date, group in selected.groupby("utc_date", sort=True, observed=True)
    }
    records: list[dict[str, Any]] = []
    for utc_date in schedule.index:
        group = grouped.get(str(utc_date))
        schedule_row = schedule.loc[str(utc_date)]
        expected_rows = int(schedule_row["expected_m15_rows"])
        date_timestamp = pd.Timestamp(str(utc_date), tz="UTC")
        weekday_number = int(date_timestamp.weekday())
        weekday_name = date_timestamp.day_name()
        is_weekday = weekday_number < 5
        is_boundary = str(utc_date) in {first_dataset_date, last_dataset_date}
        if group is None:
            zero_reasons = [
                "zero_profile_contribution",
                "task03_profile_ineligible_date",
            ]
            if not is_weekday:
                zero_reasons.append("weekend_utc_date")
            if expected_rows == 0:
                zero_reasons.append("no_expected_market_grid")
            zero_reasons.append("incomplete_daily_observation")
            if is_boundary:
                zero_reasons.append("dataset_boundary_date")
            records.append(
                {
                    "utc_date": str(utc_date),
                    "weekday_number": weekday_number,
                    "weekday_name": weekday_name,
                    "daily_open": math.nan,
                    "daily_high": math.nan,
                    "daily_low": math.nan,
                    "daily_close": math.nan,
                    "daily_range_price": math.nan,
                    "daily_range_pips": math.nan,
                    "first_timestamp_utc": pd.NaT,
                    "last_timestamp_utc": pd.NaT,
                    "observed_m15_rows": 0,
                    "expected_m15_rows": expected_rows,
                    "observed_coverage_ratio": 0.0,
                    "first_expected_interval_present": False,
                    "last_expected_interval_present": False,
                    "continuous_expected_grid": False,
                    "is_weekday": is_weekday,
                    "is_weekend_date": not is_weekday,
                    "is_boundary_date": is_boundary,
                    "is_partial_daily_observation": True,
                    "analysis_eligible": False,
                    "exclusion_reasons": "|".join(zero_reasons),
                    "profile": profile,
                    "first_raw_row_number": math.nan,
                    "last_raw_row_number": math.nan,
                    "contributing_raw_row_count": 0,
                    "contributing_rows_sha256": hashlib.sha256(b"").hexdigest(),
                    "expected_schedule_source": schedule_row[
                        "expected_schedule_source"
                    ],
                }
            )
            continue
        ordered = group.sort_values("timestamp_utc", kind="stable")
        first_timestamp = ordered["timestamp_utc"].iloc[0]
        last_timestamp = ordered["timestamp_utc"].iloc[-1]
        expected_first = schedule_row["expected_first_timestamp_utc"]
        expected_last = schedule_row["expected_last_timestamp_utc"]
        observed_rows = len(ordered)
        coverage_ratio = observed_rows / expected_rows if expected_rows else 0.0
        first_present = bool(
            expected_rows and first_timestamp == pd.Timestamp(expected_first)
        )
        last_present = bool(
            expected_rows and last_timestamp == pd.Timestamp(expected_last)
        )
        on_grid = bool(
            observed_rows <= 1
            or ordered["timestamp_utc"].diff().iloc[1:].eq(timedelta(minutes=15)).all()
        )
        complete = bool(
            observed_rows >= config.daily_completeness.minimum_daily_rows
            and expected_rows > 0
            and coverage_ratio >= config.daily_completeness.minimum_coverage_ratio
            and observed_rows == expected_rows
            and (
                first_present
                or not config.daily_completeness.require_first_expected_interval
            )
            and (
                last_present
                or not config.daily_completeness.require_last_expected_interval
            )
            and on_grid
        )
        eligible = bool(
            is_weekday
            and complete
            and (
                not config.daily_completeness.exclude_dataset_boundary_dates
                or not is_boundary
            )
        )
        reasons: list[str] = []
        if not is_weekday:
            reasons.append("weekend_utc_date")
        if expected_rows == 0:
            reasons.append("no_expected_market_grid")
        if not complete:
            reasons.append("incomplete_daily_observation")
        if is_boundary:
            reasons.append("dataset_boundary_date")
        high = float(ordered["high"].max())
        low = float(ordered["low"].min())
        records.append(
            {
                "utc_date": str(utc_date),
                "weekday_number": weekday_number,
                "weekday_name": weekday_name,
                "daily_open": float(ordered["open"].iloc[0]),
                "daily_high": high,
                "daily_low": low,
                "daily_close": float(ordered["close"].iloc[-1]),
                "daily_range_price": high - low,
                "daily_range_pips": (high - low) / config.pip_size,
                "first_timestamp_utc": first_timestamp,
                "last_timestamp_utc": last_timestamp,
                "observed_m15_rows": observed_rows,
                "expected_m15_rows": expected_rows,
                "observed_coverage_ratio": coverage_ratio,
                "first_expected_interval_present": first_present,
                "last_expected_interval_present": last_present,
                "continuous_expected_grid": on_grid,
                "is_weekday": is_weekday,
                "is_weekend_date": not is_weekday,
                "is_boundary_date": is_boundary,
                "is_partial_daily_observation": not complete,
                "analysis_eligible": eligible,
                "exclusion_reasons": "|".join(reasons),
                "profile": profile,
                "first_raw_row_number": int(ordered["raw_row_number"].iloc[0]),
                "last_raw_row_number": int(ordered["raw_row_number"].iloc[-1]),
                "contributing_raw_row_count": observed_rows,
                "contributing_rows_sha256": _row_lineage_digest(
                    ordered["raw_row_number"]
                ),
                "expected_schedule_source": schedule_row["expected_schedule_source"],
            }
        )
    return (
        pd.DataFrame.from_records(records)
        .sort_values("utc_date")
        .reset_index(drop=True)
    )


def _mixed_sensitivity_by_date(row_flags: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "long_nonweekly_gap_boundary",
        "nonweekend_gap_boundary",
        "unclassified_gap_boundary",
        "continuity_impaired_period",
        "affected_period_2023",
        "partial_boundary_year",
        "partial_boundary_month",
    ]
    grouped = row_flags.groupby("utc_date", sort=True, observed=True)
    mixed = grouped[columns].nunique().gt(1).any(axis=1)
    affected = grouped["affected_period_2023"].any()
    condition_count = grouped[columns].any().sum(axis=1)
    return pd.DataFrame(
        {
            "utc_date": mixed.index.astype(str),
            "mixed_sensitivity_conditions": mixed.to_numpy(),
            "sensitivity_condition_count": condition_count.to_numpy(dtype=int),
            "date_affected_by_audited_2023_interval": affected.to_numpy(),
        }
    )


def aggregate_daily_profiles(
    *,
    raw_path: Path,
    coverage: CoverageResult,
    gaps: pd.DataFrame,
    config: Task04Config,
    lineage: Mapping[str, str],
) -> DailyAggregationResult:
    """Build each profile at row level before UTC-date aggregation."""
    usecols = ["timestamp_utc", "open", "high", "low", "close"]
    raw = pd.read_csv(raw_path, usecols=usecols)
    if len(raw) != len(coverage.flags_by_level["row"]):
        raise ValueError("Raw prices do not reconcile with Task 03 row masks")
    raw["timestamp_utc"] = pd.to_datetime(
        raw["timestamp_utc"], utc=True, errors="raise", format="mixed"
    )
    if not raw["timestamp_utc"].is_monotonic_increasing:
        raise ValueError("Raw timestamps are not ordered after Task 03 validation")
    raw["utc_date"] = raw["timestamp_utc"].dt.strftime("%Y-%m-%d")
    raw["raw_row_number"] = np.arange(2, len(raw) + 2)
    dates = pd.DatetimeIndex(
        pd.to_datetime(sorted(raw["utc_date"].unique()), format="%Y-%m-%d")
    )
    schedule = _expected_schedule(dates, gaps)
    first_date = str(raw["utc_date"].iloc[0])
    last_date = str(raw["utc_date"].iloc[-1])
    profiles = (config.primary_coverage_profile, *config.sensitivity_profiles)
    masks = coverage.profile_masks_by_level["row"]
    missing_profiles = sorted(set(profiles).difference(masks))
    if missing_profiles:
        raise ValueError(f"Task 03 profiles are missing: {missing_profiles}")
    by_profile = {
        profile: _aggregate_profile(
            raw,
            masks[profile],
            schedule,
            profile=profile,
            config=config,
            first_dataset_date=first_date,
            last_dataset_date=last_date,
        )
        for profile in profiles
    }
    primary = by_profile[config.primary_coverage_profile].copy()
    primary = primary.rename(columns={"analysis_eligible": "primary_profile_eligible"})
    all_dates = pd.DataFrame(
        {
            "utc_date": dates.strftime("%Y-%m-%d"),
            "weekday_number": dates.weekday,
            "weekday_name": dates.day_name(),
        }
    )
    primary_columns = [
        column
        for column in primary
        if column not in {"profile", "weekday_number", "weekday_name"}
    ]
    wide = all_dates.merge(
        primary[primary_columns], on="utc_date", how="left", validate="one_to_one"
    )
    for profile, frame in by_profile.items():
        slug = PROFILE_SLUGS[profile]
        selected = frame[
            [
                "utc_date",
                "analysis_eligible",
                "is_partial_daily_observation",
                "observed_m15_rows",
                "expected_m15_rows",
                "observed_coverage_ratio",
                "daily_range_pips",
                "contributing_rows_sha256",
            ]
        ].rename(
            columns={
                column: f"{slug}_{column}"
                for column in frame.columns
                if column != "utc_date"
            }
        )
        wide = wide.merge(selected, on="utc_date", how="left", validate="one_to_one")
    wide = wide.merge(
        _mixed_sensitivity_by_date(coverage.flags_by_level["row"]),
        on="utc_date",
        how="left",
        validate="one_to_one",
    )
    for key, value in lineage.items():
        wide[key] = value
    return DailyAggregationResult(by_profile, wide, len(raw))
