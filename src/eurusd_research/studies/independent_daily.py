"""Independent raw-to-daily reconstruction for Task 04 reconciliation.

The only research-layer dependency is COVERAGE-001 mask construction. Those
masks are accepted only after exact row/date membership digests match the
registered Task 03 evidence. No Task 04 aggregation code is imported.
"""

from __future__ import annotations

import gc
import hashlib
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from eurusd_research.config import load_config
from eurusd_research.data.registry import sha256_file
from eurusd_research.research.coverage import build_coverage
from eurusd_research.studies.configuration import Task04Config
from eurusd_research.studies.integrity import validate_task03_row_membership

PROFILES = (
    "DEFAULT_RESEARCH",
    "STRICT_CONTINUITY",
    "SENSITIVITY_FULL",
    "SENSITIVITY_2023",
)


def _lineage_digest(row_numbers: pd.Series) -> str:
    value = ",".join(str(int(item)) for item in row_numbers).encode("ascii")
    return hashlib.sha256(value).hexdigest()


def _schedule(root: Path, dates: pd.DatetimeIndex) -> pd.DataFrame:
    gaps = pd.read_csv(root / "reports/audits/timestamp_gaps.csv")
    weekly = gaps.loc[gaps["preliminary_category"].eq("likely_weekly_closure")]
    before = pd.to_datetime(weekly["timestamp_before"], utc=True)
    after = pd.to_datetime(weekly["timestamp_after"], utc=True)
    friday = {value.date(): value for value in before if value.weekday() == 4}
    sunday = {value.date(): value for value in after if value.weekday() == 6}
    rows: list[dict[str, object]] = []
    for value in dates:
        day = pd.Timestamp(value, tz="UTC")
        first: pd.Timestamp | None = None
        last: pd.Timestamp | None = None
        source = "no_primary_market_grid"
        if day.weekday() <= 3:
            first, last, source = (
                day,
                day + timedelta(hours=23, minutes=45),
                "full_utc_weekday",
            )
        elif day.weekday() == 4:
            first, last, source = day, friday.get(day.date()), "task02_weekly_boundary"
        elif day.weekday() == 6:
            first, last, source = (
                sunday.get(day.date()),
                day + timedelta(hours=23, minutes=45),
                "task02_weekly_boundary",
            )
        expected = (
            0
            if first is None or last is None
            else int((last - first) / timedelta(minutes=15)) + 1
        )
        rows.append(
            {
                "utc_date": day.strftime("%Y-%m-%d"),
                "expected_first_timestamp_utc": first,
                "expected_last_timestamp_utc": last,
                "expected_m15_rows": expected,
                "expected_schedule_source": source,
            }
        )
    return pd.DataFrame(rows)


def _one_profile(
    raw: pd.DataFrame,
    mask: pd.Series,
    schedule: pd.DataFrame,
    profile: str,
    config: Task04Config,
) -> pd.DataFrame:
    selected = raw.loc[mask.to_numpy()]
    grouped = selected.groupby("utc_date", sort=True, observed=True)
    aggregated = grouped.agg(
        daily_open=("open", "first"),
        daily_high=("high", "max"),
        daily_low=("low", "min"),
        daily_close=("close", "last"),
        first_timestamp_utc=("timestamp_utc", "first"),
        last_timestamp_utc=("timestamp_utc", "last"),
        observed_m15_rows=("raw_row_number", "size"),
        first_raw_row_number=("raw_row_number", "first"),
        last_raw_row_number=("raw_row_number", "last"),
    )
    aggregated["contributing_rows_sha256"] = grouped["raw_row_number"].agg(
        _lineage_digest
    )
    deltas = grouped["timestamp_utc"].diff()
    aggregated["continuous_expected_grid"] = (
        (deltas.isna() | deltas.eq(timedelta(minutes=15)))
        .groupby(selected["utc_date"])
        .all()
    )
    frame = schedule.merge(
        aggregated.reset_index(), on="utc_date", how="left", validate="one_to_one"
    )
    dates = pd.to_datetime(frame["utc_date"], utc=True)
    frame["profile"] = profile
    frame["weekday_number"] = dates.dt.weekday
    frame["weekday_name"] = dates.dt.day_name()
    frame["observed_m15_rows"] = frame["observed_m15_rows"].fillna(0).astype(int)
    frame["contributing_raw_row_count"] = frame["observed_m15_rows"]
    frame["daily_range_price"] = frame["daily_high"] - frame["daily_low"]
    frame["daily_range_pips"] = frame["daily_range_price"] / config.pip_size
    frame["observed_coverage_ratio"] = np.divide(
        frame["observed_m15_rows"],
        frame["expected_m15_rows"],
        out=np.zeros(len(frame), dtype=float),
        where=frame["expected_m15_rows"].to_numpy() != 0,
    )
    frame["first_expected_interval_present"] = frame["expected_m15_rows"].gt(0) & frame[
        "first_timestamp_utc"
    ].eq(frame["expected_first_timestamp_utc"])
    frame["last_expected_interval_present"] = frame["expected_m15_rows"].gt(0) & frame[
        "last_timestamp_utc"
    ].eq(frame["expected_last_timestamp_utc"])
    frame["continuous_expected_grid"] = (
        frame["continuous_expected_grid"].astype("boolean").fillna(False).astype(bool)
    )
    frame["is_weekday"] = frame["weekday_number"].lt(5)
    frame["is_weekend_date"] = ~frame["is_weekday"]
    frame["is_boundary_date"] = frame["utc_date"].isin(
        (str(raw["utc_date"].iloc[0]), str(raw["utc_date"].iloc[-1]))
    )
    frame["zero_contribution"] = frame["observed_m15_rows"].eq(0)
    frame["complete"] = (
        frame["observed_m15_rows"].ge(config.daily_completeness.minimum_daily_rows)
        & frame["expected_m15_rows"].gt(0)
        & frame["observed_coverage_ratio"].ge(
            config.daily_completeness.minimum_coverage_ratio
        )
        & frame["observed_m15_rows"].eq(frame["expected_m15_rows"])
        & (
            frame["first_expected_interval_present"]
            | (not config.daily_completeness.require_first_expected_interval)
        )
        & (
            frame["last_expected_interval_present"]
            | (not config.daily_completeness.require_last_expected_interval)
        )
        & frame["continuous_expected_grid"]
    )
    frame["incomplete"] = ~frame["complete"]
    frame["nonzero_partial"] = ~frame["zero_contribution"] & frame["incomplete"]
    frame["is_partial_daily_observation"] = frame["incomplete"]
    frame["analysis_eligible"] = (
        frame["is_weekday"] & frame["complete"] & ~frame["is_boundary_date"]
    )
    frame["contributing_rows_sha256"] = frame["contributing_rows_sha256"].fillna(
        hashlib.sha256(b"").hexdigest()
    )

    def exclusion_reasons(row: pd.Series) -> str:
        reasons: list[str] = []
        if row["zero_contribution"]:
            reasons.extend(
                ("zero_profile_contribution", "task03_profile_ineligible_date")
            )
        if not row["is_weekday"]:
            reasons.append("weekend_utc_date")
        if row["expected_m15_rows"] == 0:
            reasons.append("no_expected_market_grid")
        if row["incomplete"]:
            reasons.append("incomplete_daily_observation")
        if row["is_boundary_date"]:
            reasons.append("dataset_boundary_date")
        return "|".join(reasons)

    frame["exclusion_reasons"] = frame.apply(exclusion_reasons, axis=1)
    return frame.drop(
        columns=["expected_first_timestamp_utc", "expected_last_timestamp_utc"]
    )


def rebuild_daily_profiles(
    root: Path,
    config: Task04Config,
    *,
    profiles: tuple[str, ...] = PROFILES,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame, str, str]:
    """Rebuild every profile-date and validate exact upstream memberships."""
    raw_path = root / "data/raw/EURUSD_M15_UTC.csv"
    raw_sha = sha256_file(raw_path)
    if raw_sha != config.required_raw_sha256:
        raise ValueError("Independent raw checksum does not match registration")
    research_config = load_config(root)
    coverage = build_coverage(
        root=root, config=research_config, repository_version="independent-v2.5"
    )
    task03 = validate_task03_row_membership(
        root,
        coverage,
        research_config,
        expected_fingerprint=config.required_task03_row_membership_fingerprint,
    )
    raw = pd.read_csv(
        raw_path, usecols=["timestamp_utc", "open", "high", "low", "close"]
    )
    if len(raw) != task03.observed_row_count:
        raise ValueError("Independent raw population does not match Task 03")
    raw["timestamp_utc"] = pd.to_datetime(
        raw["timestamp_utc"], utc=True, format="mixed", errors="raise"
    )
    if not raw["timestamp_utc"].is_monotonic_increasing:
        raise ValueError("Independent raw timestamps are not ordered")
    raw["utc_date"] = raw["timestamp_utc"].dt.strftime("%Y-%m-%d")
    raw["raw_row_number"] = np.arange(2, len(raw) + 2)
    dates = pd.DatetimeIndex(pd.to_datetime(sorted(raw["utc_date"].unique())))
    if len(dates) != task03.observed_date_count:
        raise ValueError("Independent observed-date count does not match Task 03")
    schedule = _schedule(root, dates)
    masks = coverage.profile_masks_by_level["row"]
    default = masks["DEFAULT_RESEARCH"].to_numpy(bool)
    strict = masks["STRICT_CONTINUITY"].to_numpy(bool)
    sensitivity = masks["SENSITIVITY_FULL"].to_numpy(bool)
    sensitivity_2023 = masks["SENSITIVITY_2023"].to_numpy(bool)
    if np.any(strict & ~default):
        raise ValueError("Independent Task 03 algebra: STRICT is not a DEFAULT subset")
    if np.any(strict & sensitivity):
        raise ValueError(
            "Independent Task 03 algebra: STRICT overlaps SENSITIVITY_FULL"
        )
    if not np.array_equal(strict | sensitivity, default):
        raise ValueError(
            "Independent Task 03 algebra: STRICT union SENSITIVITY_FULL "
            "differs from DEFAULT"
        )
    if np.any(sensitivity_2023 & ~sensitivity):
        raise ValueError(
            "Independent Task 03 algebra: SENSITIVITY_2023 is not a sensitivity subset"
        )
    frames: dict[str, pd.DataFrame] = {}
    unknown = sorted(set(profiles).difference(PROFILES))
    if unknown:
        raise ValueError(f"Unknown independent coverage profiles: {unknown}")
    for profile in profiles:
        frames[profile] = _one_profile(raw, masks[profile], schedule, profile, config)
        gc.collect()
    return (
        frames,
        coverage.flags_by_level["row"].copy(),
        coverage.profile_masks_by_level["row"].copy(),
        raw_sha,
        task03.evidence_fingerprint,
    )
