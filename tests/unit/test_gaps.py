from __future__ import annotations

import pandas as pd

from eurusd_research.data.gaps import (
    build_gap_table,
    classify_gap,
    estimated_missing_bars,
    expand_missing_timestamps,
)


def test_estimated_missing_bar_calculation() -> None:
    assert estimated_missing_bars(15) == 0
    assert estimated_missing_bars(30) == 1
    assert estimated_missing_bars(31) == 0
    assert estimated_missing_bars(60) == 3
    assert estimated_missing_bars(-15) == 0


def test_gap_classifications_are_conservative() -> None:
    friday = pd.Timestamp("2024-01-05T21:45:00Z")
    sunday = pd.Timestamp("2024-01-07T22:00:00Z")
    options = {
        "weekly_minimum_minutes": 1440,
        "large_gap_minimum_minutes": 720,
    }
    assert classify_gap(friday, sunday, 2895, **options)[0] == ("likely_weekly_closure")

    monday = pd.Timestamp("2024-01-08T10:00:00Z")
    tuesday = pd.Timestamp("2024-01-09T10:00:00Z")
    assert classify_gap(monday, tuesday, 1440, **options)[0] == "long_nonweekly_gap"
    assert (
        classify_gap(monday, pd.Timestamp("2024-01-08T10:45:00Z"), 45, **options)[0]
        == "non_weekend_intraday"
    )
    saturday = pd.Timestamp("2024-01-06T01:00:00Z")
    assert (
        classify_gap(saturday, pd.Timestamp("2024-01-06T01:30:00Z"), 30, **options)[0]
        == "unclassified"
    )


def test_build_gap_table_retains_every_gap() -> None:
    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2024-01-05T21:45:00Z",
                "2024-01-07T22:00:00Z",
                "2024-01-07T22:15:00Z",
                "2024-01-07T23:00:00Z",
            ],
            utc=True,
        )
    )
    result = build_gap_table(
        timestamps,
        cadence_minutes=15,
        weekly_minimum_minutes=1440,
        large_gap_minimum_minutes=720,
    )
    assert len(result) == 2
    assert result.iloc[0]["estimated_missing_m15_timestamps"] == 192
    assert list(result["preliminary_category"]) == [
        "likely_weekly_closure",
        "unclassified",
    ]


def test_missing_timestamp_expansion_crosses_period_boundaries() -> None:
    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2020-02-29T23:30:00Z",
                "2020-03-01T00:30:00Z",
                "2020-12-31T23:45:00Z",
                "2021-01-01T00:30:00Z",
            ],
            utc=True,
        )
    )
    gaps = build_gap_table(
        timestamps,
        cadence_minutes=15,
        weekly_minimum_minutes=10_000,
        large_gap_minimum_minutes=720,
    )
    expanded = expand_missing_timestamps(gaps, 15)
    assert (
        expanded["missing_timestamp_utc"]
        .dt.strftime("%Y-%m")
        .value_counts()
        .to_dict()["2020-02"]
        == 1
    )
    assert expanded["missing_timestamp_utc"].dt.year.value_counts().to_dict()[2021] == 2
    assert len(expanded) == int(gaps["estimated_missing_m15_timestamps"].sum())


def test_non_grid_interval_is_not_expanded() -> None:
    timestamps = pd.Series(
        pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T00:31:00Z"], utc=True)
    )
    gaps = build_gap_table(
        timestamps,
        cadence_minutes=15,
        weekly_minimum_minutes=1440,
        large_gap_minimum_minutes=720,
    )
    assert gaps.iloc[0]["estimated_missing_m15_timestamps"] == 0
    assert expand_missing_timestamps(gaps, 15).empty
