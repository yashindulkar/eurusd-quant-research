from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.statistics import (
    bootstrap_interval,
    cliffs_delta,
    descriptive_record,
    epsilon_squared,
    holm_adjust,
    omnibus_effect_records,
    omnibus_records,
    pairwise_records,
    weekday_statistics,
)


def _frame(values_by_day: dict[str, list[float]]) -> pd.DataFrame:
    records = []
    counter = 0
    for day, values in values_by_day.items():
        for value in values:
            counter += 1
            records.append(
                {
                    "utc_date": f"2024-01-{counter:02d}",
                    "weekday_name": day,
                    "daily_range_pips": value,
                    "analysis_eligible": True,
                }
            )
    return pd.DataFrame(records)


def test_descriptive_statistics_percentiles_and_determinism() -> None:
    config = load_task04_config()
    values = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
    first = descriptive_record(
        values, full_sample_median=2.5, config=config, label="fixture"
    )
    second = descriptive_record(
        values, full_sample_median=2.5, config=config, label="fixture"
    )
    assert first == second
    assert first["sample_size"] == 4
    assert first["missing_count"] == 1
    assert first["mean"] == pytest.approx(2.5)
    assert first["median"] == pytest.approx(2.5)
    assert first["variance"] == pytest.approx(5 / 3)
    assert first["interquartile_range"] == pytest.approx(1.5)
    assert first["median_absolute_deviation"] == pytest.approx(1.0)
    assert first["proportion_above_full_sample_median"] == 0.5
    assert first["percentile_1"] == pytest.approx(1.03)

    empty = descriptive_record(
        np.array([np.nan]), full_sample_median=0, config=config, label="empty"
    )
    assert empty["sample_size"] == 0
    assert math.isnan(empty["mean"])


def test_bootstrap_degenerate_and_invalid_groups() -> None:
    low, high = bootstrap_interval(
        np.array([5.0]),
        np.mean,
        confidence_level=0.95,
        resamples=100,
        seed=1,
    )
    assert (low, high) == (5.0, 5.0)
    low, high = bootstrap_interval(
        np.array([]),
        np.mean,
        confidence_level=0.95,
        resamples=100,
        seed=1,
    )
    assert math.isnan(low) and math.isnan(high)


def test_holm_cliffs_delta_and_epsilon_size() -> None:
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted.tolist() == pytest.approx([0.03, 0.06, 0.06])
    assert holm_adjust([]).size == 0
    assert cliffs_delta(np.array([3, 4]), np.array([1, 2])) == 1.0
    assert cliffs_delta(np.array([1, 2]), np.array([3, 4])) == -1.0
    assert math.isnan(cliffs_delta(np.array([]), np.array([1])))
    assert epsilon_squared(12, 100, 5) == pytest.approx(8 / 95)
    assert math.isnan(epsilon_squared(1, 5, 5))


def test_omnibus_pairwise_ties_constant_and_all_ten_comparisons() -> None:
    config = load_task04_config()
    values = {
        day: [
            float(10 + index),
            float(11 + index),
            float(12 + index),
            float(13 + index),
        ]
        for index, day in enumerate(config.weekday_inclusion)
    }
    frame = _frame(values)
    tests = omnibus_records(frame, config=config, profile="P", analysis_scope="fixture")
    assert set(tests["test_name"]) == {
        "kruskal_wallis",
        "one_way_anova",
        "welch_anova",
        "brown_forsythe_levene",
    }
    degrees = tests.set_index("test_name")
    assert degrees.loc["kruskal_wallis", "numerator_degrees_of_freedom"] == 4
    assert math.isnan(degrees.loc["kruskal_wallis", "denominator_degrees_of_freedom"])
    assert degrees.loc["one_way_anova", "denominator_degrees_of_freedom"] == 15
    assert degrees.loc["brown_forsythe_levene", "denominator_degrees_of_freedom"] == 15
    assert degrees.loc["welch_anova", "numerator_degrees_of_freedom"] == 4
    assert degrees.loc["welch_anova", "denominator_degrees_of_freedom"] > 0
    pairs = pairwise_records(
        frame, config=config, profile="P", analysis_scope="fixture"
    )
    assert len(pairs) == 10
    assert (pairs["holm_adjusted_p_value"] >= pairs["unadjusted_p_value"]).all()
    assert set(pairs["effect_direction"]).issubset(
        {f"{a}>{b}" for a in config.weekday_inclusion for b in config.weekday_inclusion}
        | {
            f"{a}<{b}"
            for a in config.weekday_inclusion
            for b in config.weekday_inclusion
        }
        | {"no_direction"}
    )
    effects = omnibus_effect_records(
        frame, config=config, profile="P", analysis_scope="fixture"
    )
    assert set(effects["effect_size_method"]) == {
        "epsilon_squared",
        "eta_squared",
        "omega_squared",
    }

    identical = _frame({day: [5.0, 5.0, 5.0] for day in config.weekday_inclusion})
    identical_tests = omnibus_records(
        identical, config=config, profile="P", analysis_scope="constant"
    )
    primary = identical_tests.loc[
        identical_tests["test_name"].eq("kruskal_wallis")
    ].iloc[0]
    assert primary["statistic"] == 0
    assert primary["p_value"] == 1
    tied_pairs = pairwise_records(
        identical, config=config, profile="P", analysis_scope="constant"
    )
    assert len(tied_pairs) == 10
    assert (tied_pairs["unadjusted_p_value"] == 1).all()


def test_insufficient_groups_and_weekday_table_stable_order() -> None:
    config = load_task04_config()
    frame = _frame({"Monday": [1.0, 2.0]})
    tests = omnibus_records(frame, config=config, profile="P", analysis_scope="small")
    assert tests["p_value"].isna().all()
    assert pairwise_records(
        frame, config=config, profile="P", analysis_scope="small"
    ).empty
    effects = omnibus_effect_records(
        frame, config=config, profile="P", analysis_scope="small"
    )
    assert effects["effect_size"].isna().all()
    described = weekday_statistics(
        frame, config=config, profile="P", analysis_scope="small"
    )
    assert tuple(described["weekday_name"]) == config.weekday_inclusion
    assert (
        described.loc[described["weekday_name"].eq("Tuesday"), "sample_size"].iloc[0]
        == 0
    )
