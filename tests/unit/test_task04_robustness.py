from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.robustness import (
    assign_past_only_volatility_regime,
    chronological_outputs,
    chronological_periods,
    coverage_profile_outputs,
    extreme_event_outputs,
    rank_correlation,
    significant_pair_labels,
    volatility_regime_outputs,
    weekday_order,
    yearly_outputs,
)


def _long_frame(rows: int = 500) -> pd.DataFrame:
    dates = pd.bdate_range("2019-01-01", periods=rows, tz="UTC")
    return pd.DataFrame(
        {
            "utc_date": dates.strftime("%Y-%m-%d"),
            "weekday_name": dates.day_name(),
            "daily_range_pips": 50
            + np.sin(np.arange(rows) / 7) * 5
            + np.arange(rows) % 5,
            "analysis_eligible": True,
        }
    )


def test_chronological_split_preserves_order_and_boundaries() -> None:
    config = load_task04_config()
    frame = _long_frame()
    periods = chronological_periods(frame, config)
    development = periods["development_70"]
    validation = periods["validation_30"]
    assert len(development) + len(validation) == len(frame)
    assert development["utc_date"].max() < validation["utc_date"].min()
    assert periods["pre_2020"]["utc_date"].max() < "2020-01-01"
    assert periods["post_2021"].empty


def test_volatility_regime_excludes_current_and_future_information() -> None:
    config = load_task04_config().model_copy(
        update={"volatility_lookback": 5, "volatility_minimum_history": 8}
    )
    frame = _long_frame(80)
    first = assign_past_only_volatility_regime(frame, config)
    changed_current = frame.copy()
    changed_current.loc[40, "daily_range_pips"] = 10_000
    second = assign_past_only_volatility_regime(changed_current, config)
    assert first.loc[40, "volatility_regime"] == second.loc[40, "volatility_regime"]
    changed_future = frame.copy()
    changed_future.loc[60:, "daily_range_pips"] = 20_000
    future = assign_past_only_volatility_regime(changed_future, config)
    pd.testing.assert_series_equal(
        first.loc[:59, "volatility_regime"],
        future.loc[:59, "volatility_regime"],
    )
    assert (first.loc[:12, "volatility_regime"] == "UNCLASSIFIED").any()
    assert {
        "prior_regime_measure_count",
        "regime_warmup",
        "regime_classification_reason",
        "volatility_lookback",
        "volatility_minimum_history",
    }.issubset(first.columns)
    assert first.loc[:12, "regime_warmup"].all()
    assert first.loc[13, "volatility_regime"] != "UNCLASSIFIED"
    assert not first.loc[13, "regime_warmup"]


def test_extreme_sensitivity_is_reversible_and_order_helpers() -> None:
    config = load_task04_config()
    frame = _long_frame()
    frame.loc[len(frame) - 1, "daily_range_pips"] = 1_000
    output = extreme_event_outputs(frame, config)
    assert tuple(output["analysis_variant"]) == (
        "primary_raw_distribution",
        "winsorised_1_99",
        "exclude_largest_1_percent",
    )
    assert (
        output.loc[
            output["analysis_variant"].eq("primary_raw_distribution"),
            "excluded_observation_count",
        ].iloc[0]
        == 0
    )
    assert (
        output.loc[
            output["analysis_variant"].eq("exclude_largest_1_percent"),
            "excluded_observation_count",
        ].iloc[0]
        > 0
    )
    order = weekday_order(frame)
    assert set(order) == {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
    assert rank_correlation(order, order) == pytest.approx(1.0)
    assert np.isnan(rank_correlation(("Monday",), ("Monday",)))


def test_significant_pair_labels_preserve_registered_direction() -> None:
    frame = pd.DataFrame(
        {
            "effect_direction": [
                "Monday<Tuesday",
                "Monday>Wednesday",
                "no_direction",
                "Thursday>Friday",
            ],
            "significant": [True, True, True, False],
        }
    )
    assert significant_pair_labels(frame) == (
        "Monday<Tuesday",
        "Monday>Wednesday",
        "no_direction",
    )
    tied = pd.DataFrame({"effect_direction": ["no_direction"], "significant": [False]})
    assert significant_pair_labels(tied) == ()
    assert significant_pair_labels(pd.DataFrame()) == ()


def test_custom_period_outputs_are_canonical_plotting_evidence() -> None:
    config = load_task04_config()
    custom_boundaries = config.period_boundaries.model_copy(
        update={
            "pre_2020_end_exclusive": "2019-06-01",
            "covid_start_inclusive": "2019-06-01",
            "covid_end_inclusive": "2020-06-01",
            "post_2021_start_inclusive": "2020-06-02",
        }
    )
    custom = config.model_copy(update={"period_boundaries": custom_boundaries})
    frame = _long_frame(500)
    periods = chronological_periods(frame, custom)
    output, _ = chronological_outputs(frame, custom)
    indexed = output.set_index("analysis_period")
    for period, selected in periods.items():
        assert indexed.loc[period, "date_start"] == selected["utc_date"].min()
        assert indexed.loc[period, "date_end"] == selected["utc_date"].max()
        for day in custom.weekday_inclusion:
            expected = selected.loc[
                selected["weekday_name"].eq(day), "daily_range_pips"
            ].median()
            assert indexed.loc[period, f"{day.lower()}_median_pips"] == pytest.approx(
                expected
            )


def test_year_regime_and_profile_robustness_outputs_are_complete() -> None:
    config = load_task04_config().model_copy(
        update={
            "bootstrap_resamples": 100,
            "volatility_lookback": 5,
            "volatility_minimum_history": 8,
            "minimum_yearly_weekday_sample": 2,
        }
    )
    frame = _long_frame(500)
    yearly_stats, yearly_tests = yearly_outputs(frame, config)
    assert set(yearly_stats["weekday_name"]) == set(config.weekday_inclusion)
    assert yearly_tests["sufficient_for_inference"].all()

    regime_stats, regime_tests, lineage = volatility_regime_outputs(frame, config)
    assert set(regime_stats["volatility_regime"]) == {"LOW", "MEDIUM", "HIGH"}
    assert set(regime_tests["volatility_regime"]) == {"LOW", "MEDIUM", "HIGH"}
    assert len(lineage) == len(frame)

    by_profile = {
        profile: frame.copy()
        for profile in (
            config.primary_coverage_profile,
            *config.sensitivity_profiles,
        )
    }
    statistics, tests, pairwise, effects, comparison = coverage_profile_outputs(
        by_profile, config
    )
    assert set(statistics["profile"]) == set(by_profile)
    assert set(tests["profile"]) == set(by_profile)
    assert set(pairwise["profile"]) == set(by_profile)
    assert set(effects["profile"]) == set(by_profile)
    assert set(comparison["profile"]) == set(by_profile)
