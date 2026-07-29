from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.daily_aggregation import (
    DailyAggregationResult,
    _aggregate_profile,
    _expected_schedule,
    aggregate_daily_profiles,
)
from eurusd_research.studies.task04 import _population_reconciliation


def _raw_day(
    date: str,
    *,
    periods: int = 96,
    start: str = "00:00",
    base: float = 1.10,
) -> pd.DataFrame:
    timestamps = pd.date_range(f"{date}T{start}:00Z", periods=periods, freq="15min")
    values = np.arange(periods, dtype=float) * 0.00001
    return pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "utc_date": date,
            "open": base + values,
            "high": base + values + 0.0004,
            "low": base + values - 0.0002,
            "close": base + values + 0.0001,
            "raw_row_number": np.arange(2, periods + 2),
        }
    )


def _weekly_gap() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp_before": "2024-01-05T21:45:00Z",
                "timestamp_after": "2024-01-07T22:00:00Z",
                "preliminary_category": "likely_weekly_closure",
            }
        ]
    )


def test_expected_schedule_uses_utc_and_task02_weekly_endpoints() -> None:
    dates = pd.DatetimeIndex(
        pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-06", "2024-01-07"])
    )
    schedule = _expected_schedule(dates, _weekly_gap())
    assert schedule.loc["2024-01-04", "expected_m15_rows"] == 96
    assert schedule.loc["2024-01-05", "expected_m15_rows"] == 88
    assert schedule.loc["2024-01-06", "expected_m15_rows"] == 0
    assert schedule.loc["2024-01-07", "expected_m15_rows"] == 8
    assert str(schedule.loc["2024-01-05", "expected_last_timestamp_utc"]).endswith(
        "21:45:00+00:00"
    )


def test_daily_aggregation_ohlc_range_and_no_rounding() -> None:
    config = load_task04_config()
    raw = _raw_day("2024-01-04")
    schedule = _expected_schedule(
        pd.DatetimeIndex(pd.to_datetime(["2024-01-04"])), _weekly_gap()
    )
    result = _aggregate_profile(
        raw,
        pd.Series(True, index=raw.index),
        schedule,
        profile="DEFAULT_RESEARCH",
        config=config,
        first_dataset_date="2024-01-01",
        last_dataset_date="2024-01-10",
    ).iloc[0]
    assert result["daily_open"] == pytest.approx(raw.iloc[0]["open"])
    assert result["daily_high"] == pytest.approx(raw["high"].max())
    assert result["daily_low"] == pytest.approx(raw["low"].min())
    assert result["daily_close"] == pytest.approx(raw.iloc[-1]["close"])
    assert result["daily_range_price"] == pytest.approx(
        raw["high"].max() - raw["low"].min()
    )
    assert result["daily_range_pips"] == pytest.approx(
        (raw["high"].max() - raw["low"].min()) / config.pip_size
    )
    assert result["analysis_eligible"]
    assert not result["is_partial_daily_observation"]
    assert len(result["contributing_rows_sha256"]) == 64


def test_friday_weekend_partial_boundary_and_profile_specific_aggregation() -> None:
    config = load_task04_config()
    friday = _raw_day("2024-01-05", periods=88)
    friday.loc[:, "raw_row_number"] = np.arange(2, 90)
    sunday = _raw_day("2024-01-07", periods=8, start="22:00")
    sunday.loc[:, "raw_row_number"] = np.arange(90, 98)
    monday = _raw_day("2024-01-08")
    monday.loc[:, "raw_row_number"] = np.arange(98, 194)
    raw = pd.concat([friday, sunday, monday], ignore_index=True)
    dates = pd.DatetimeIndex(pd.to_datetime(["2024-01-05", "2024-01-07", "2024-01-08"]))
    schedule = _expected_schedule(dates, _weekly_gap())
    result = _aggregate_profile(
        raw,
        pd.Series(True, index=raw.index),
        schedule,
        profile="DEFAULT_RESEARCH",
        config=config,
        first_dataset_date="2024-01-05",
        last_dataset_date="2024-01-08",
    ).set_index("utc_date")
    assert result.loc["2024-01-05", "is_boundary_date"]
    assert not result.loc["2024-01-05", "analysis_eligible"]
    assert result.loc["2024-01-07", "is_weekend_date"]
    assert not result.loc["2024-01-07", "analysis_eligible"]
    assert result.loc["2024-01-08", "is_boundary_date"]

    profile_mask = pd.Series(True, index=raw.index)
    profile_mask.iloc[-1] = False
    partial = _aggregate_profile(
        raw,
        profile_mask,
        schedule,
        profile="STRICT_CONTINUITY",
        config=config,
        first_dataset_date="2024-01-01",
        last_dataset_date="2024-01-10",
    ).set_index("utc_date")
    assert partial.loc["2024-01-08", "is_partial_daily_observation"]
    assert (
        "incomplete_daily_observation" in partial.loc["2024-01-08", "exclusion_reasons"]
    )


def test_zero_contribution_profile_date_remains_explicit_and_nullable() -> None:
    config = load_task04_config()
    raw = _raw_day("2024-01-04")
    schedule = _expected_schedule(
        pd.DatetimeIndex(pd.to_datetime(["2024-01-04"])), _weekly_gap()
    )
    result = _aggregate_profile(
        raw,
        pd.Series(False, index=raw.index),
        schedule,
        profile="STRICT_CONTINUITY",
        config=config,
        first_dataset_date="2024-01-01",
        last_dataset_date="2024-01-10",
    )
    assert len(result) == 1
    row = result.iloc[0]
    assert row["observed_m15_rows"] == 0
    assert row["contributing_raw_row_count"] == 0
    assert pd.isna(row["daily_open"])
    assert pd.isna(row["daily_high"])
    assert pd.isna(row["daily_low"])
    assert pd.isna(row["daily_close"])
    assert pd.isna(row["daily_range_pips"])
    assert not row["analysis_eligible"]
    assert "zero_profile_contribution" in row["exclusion_reasons"]
    assert "task03_profile_ineligible_date" in row["exclusion_reasons"]


def test_population_terminology_separates_zero_and_nonzero_partial() -> None:
    config = load_task04_config()
    profile = pd.DataFrame(
        {
            "utc_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "weekday_name": ["Monday", "Tuesday", "Wednesday"],
            "is_weekday": [True, True, True],
            "is_weekend_date": [False, False, False],
            "is_partial_daily_observation": [True, True, False],
            "is_boundary_date": [False, False, False],
            "observed_m15_rows": [0, 95, 96],
            "analysis_eligible": [False, False, True],
        }
    )
    flags = pd.DataFrame(
        {
            "utc_date": profile["utc_date"],
            "long_nonweekly_gap_boundary": [False, False, False],
            "nonweekend_gap_boundary": [False, False, False],
            "unclassified_gap_boundary": [False, False, False],
            "continuity_impaired_period": [False, False, False],
            "affected_period_2023": [False, False, False],
            "partial_boundary_year": [False, False, False],
            "partial_boundary_month": [False, False, False],
        }
    )
    aggregation = DailyAggregationResult(
        by_profile={"DEFAULT_RESEARCH": profile},
        wide_observations=pd.DataFrame({"utc_date": profile["utc_date"]}),
        raw_row_count=191,
    )
    output = _population_reconciliation(
        aggregation,
        flags,
        pd.DataFrame({"DEFAULT_RESEARCH": [False, True, True]}),
        config,
    )
    metrics = output.loc[
        output["profile"].eq("DEFAULT_RESEARCH") & output["weekday"].eq("")
    ].set_index("metric")["value"]
    assert metrics["zero_contribution_dates"] == 1
    assert metrics["nonzero_partial_dates"] == 1
    assert metrics["incomplete_dates"] == 2
    assert metrics["complete_dates"] == 1
    assert metrics["incomplete_dates"] == (
        metrics["zero_contribution_dates"] + metrics["nonzero_partial_dates"]
    )


def test_profile_orchestration_uses_synthetic_row_masks_before_aggregation(
    tmp_path: Path,
) -> None:
    config = load_task04_config()
    raw = _raw_day("2024-01-04")
    raw_path = tmp_path / "synthetic.csv"
    raw.drop(columns=["utc_date", "raw_row_number"]).to_csv(raw_path, index=False)
    profiles = (config.primary_coverage_profile, *config.sensitivity_profiles)
    row_flags = pd.DataFrame(
        {
            "utc_date": raw["utc_date"],
            "long_nonweekly_gap_boundary": False,
            "nonweekend_gap_boundary": False,
            "unclassified_gap_boundary": False,
            "continuity_impaired_period": False,
            "affected_period_2023": False,
            "partial_boundary_year": False,
            "partial_boundary_month": False,
        }
    )
    masks = {
        profile: pd.Series(profile != "SENSITIVITY_2023", index=raw.index)
        for profile in profiles
    }
    coverage = SimpleNamespace(
        flags_by_level={"row": row_flags},
        profile_masks_by_level={"row": masks},
    )
    result = aggregate_daily_profiles(
        raw_path=raw_path,
        coverage=coverage,
        gaps=_weekly_gap(),
        config=config,
        lineage={"fixture_lineage": "synthetic-only"},
    )
    assert set(result.by_profile) == set(profiles)
    assert len(result.wide_observations) == 1
    assert result.wide_observations["fixture_lineage"].iloc[0] == "synthetic-only"
    assert result.by_profile["SENSITIVITY_2023"]["observed_m15_rows"].iloc[0] == 0
