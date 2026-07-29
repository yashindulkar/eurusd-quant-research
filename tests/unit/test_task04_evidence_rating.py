from __future__ import annotations

from typing import Any, cast

import pandas as pd

from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.task04 import _evidence_rating

ORDER = "Thursday|Friday|Wednesday|Tuesday|Monday"


def _inputs() -> dict[str, pd.DataFrame]:
    coverage = pd.DataFrame(
        [
            {
                "profile": "DEFAULT_RESEARCH",
                "eligible_daily_observations": 1000,
                "kruskal_statistic": 20.0,
                "kruskal_p_value": 0.001,
                "epsilon_squared": 0.07,
                "weekday_order_high_to_low": ORDER,
                "rank_correlation_with_primary": 1.0,
            },
            {
                "profile": "STRICT_CONTINUITY",
                "eligible_daily_observations": 900,
                "kruskal_statistic": 18.0,
                "kruskal_p_value": 0.001,
                "epsilon_squared": 0.07,
                "weekday_order_high_to_low": ORDER,
                "rank_correlation_with_primary": 1.0,
            },
            {
                "profile": "SENSITIVITY_FULL",
                "eligible_daily_observations": 200,
                "kruskal_statistic": 2.0,
                "kruskal_p_value": 0.5,
                "epsilon_squared": 0.0,
                "weekday_order_high_to_low": ORDER,
                "rank_correlation_with_primary": -0.3,
            },
            {
                "profile": "SENSITIVITY_2023",
                "eligible_daily_observations": 120,
                "kruskal_statistic": 1.0,
                "kruskal_p_value": 0.5,
                "epsilon_squared": 0.0,
                "weekday_order_high_to_low": ORDER,
                "rank_correlation_with_primary": -0.3,
            },
        ]
    )
    weekday = pd.DataFrame(
        [
            {
                "profile": "DEFAULT_RESEARCH",
                "analysis_scope": "complete_weekday_dates",
                "weekday_name": day,
                "sample_size": 200,
                "median": 100.0,
                "median_ci_lower": 95.0,
                "median_ci_upper": 105.0,
            }
            for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
        ]
    )
    periods = pd.DataFrame(
        [
            {
                "analysis_period": name,
                "sample_size": 500,
                "weekday_order_high_to_low": ORDER,
                "rank_correlation_with_full": 1.0,
                "kruskal_statistic": 20.0,
                "kruskal_p_value": 0.001,
                "epsilon_squared": 0.07,
            }
            for name in (
                "full_eligible_sample",
                "pre_2020",
                "covid_era",
                "post_2021",
                "development_70",
                "validation_30",
            )
        ]
    )
    yearly = pd.DataFrame(
        [
            {
                "sufficient_for_inference": True,
                "sample_size": 250,
                "kruskal_statistic": 10.0,
                "kruskal_p_value": 0.01,
                "epsilon_squared": 0.03,
                "weekday_order_high_to_low": ORDER,
            }
            for _ in range(4)
        ]
    )
    regime = pd.DataFrame(
        [
            {
                "volatility_regime": regime_name,
                "weekday_name": day,
                "sample_size": 60,
                "median": float(100 - position),
            }
            for regime_name in ("LOW", "MEDIUM", "HIGH")
            for position, day in enumerate(ORDER.split("|"))
        ]
    )
    extreme = pd.DataFrame(
        [
            {
                "analysis_variant": name,
                "sample_size": 1000,
                "rank_correlation_with_primary": 1.0,
                "kruskal_statistic": 20.0,
                "kruskal_p_value": 0.001,
                "epsilon_squared": 0.07,
            }
            for name in (
                "primary_raw_distribution",
                "winsorised_1_99",
                "exclude_largest_1_percent",
            )
        ]
    )
    regime_tests = pd.DataFrame(
        [
            {
                "volatility_regime": regime_name,
                "test_name": "kruskal_wallis",
                "statistic": 10.0,
                "p_value": 0.02,
                "numerator_degrees_of_freedom": 4,
                "sample_size": 300,
                "group_count": 5,
            }
            for regime_name in ("LOW", "MEDIUM", "HIGH")
        ]
    )
    return {
        "coverage_comparison": coverage,
        "weekday_stats": weekday,
        "period_results": periods,
        "yearly_tests": yearly,
        "regime_stats": regime,
        "regime_tests": regime_tests,
        "extreme_results": extreme,
    }


def _rate(
    frames: dict[str, pd.DataFrame], *, resolved: bool = False
) -> tuple[str, dict[str, object]]:
    config = load_task04_config()
    if resolved:
        config = config.model_copy(update={"timestamp_semantics_status": "RESOLVED"})
    return _evidence_rating(**frames, config=config)


def test_rating_handles_effect_validation_ci_and_timestamp_cap() -> None:
    frames = _inputs()
    rating, detail = _rate(frames)
    assert rating == "MODERATE"
    assert detail["diagnostic_profile_concordance"] is False
    assert detail["required_profile_concordance"] is True
    assert detail["timestamp_semantics_rating_cap"] == "MODERATE"
    assert _rate(frames, resolved=True)[0] == "STRONG"

    negligible = _inputs()
    negligible["coverage_comparison"].loc[
        negligible["coverage_comparison"]["profile"].eq("DEFAULT_RESEARCH"),
        "epsilon_squared",
    ] = 0.005
    assert _rate(negligible)[0] == "WEAK"

    unstable = _inputs()
    unstable["period_results"].loc[
        unstable["period_results"]["analysis_period"].eq("validation_30"),
        "weekday_order_high_to_low",
    ] = "Monday|Tuesday|Wednesday|Thursday|Friday"
    assert _rate(unstable)[0] == "WEAK"

    wide = _inputs()
    wide["weekday_stats"]["median_ci_lower"] = 80.0
    wide["weekday_stats"]["median_ci_upper"] = 120.0
    assert _rate(wide)[0] == "WEAK"


def test_rating_handles_regime_year_extreme_and_missing_evidence() -> None:
    high_disagreement = _inputs()
    high_mask = high_disagreement["regime_stats"]["volatility_regime"].eq("HIGH")
    high_disagreement["regime_stats"].loc[high_mask, "median"] = [
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
    ]
    rating, detail = _rate(high_disagreement, resolved=True)
    assert rating == "MODERATE"
    strong_checks = cast(dict[str, Any], detail["strong_checks"])
    assert strong_checks["all_regimes_directionally_stable"] is False

    insufficient_years = _inputs()
    insufficient_years["yearly_tests"]["sufficient_for_inference"] = False
    assert _rate(insufficient_years, resolved=True)[0] == "INSUFFICIENT"

    reversed_extreme = _inputs()
    reversed_extreme["extreme_results"].loc[
        reversed_extreme["extreme_results"]["analysis_variant"].eq(
            "exclude_largest_1_percent"
        ),
        "rank_correlation_with_primary",
    ] = -1.0
    assert _rate(reversed_extreme)[0] == "WEAK"

    missing = _inputs()
    missing["regime_stats"] = missing["regime_stats"].loc[
        ~missing["regime_stats"]["volatility_regime"].eq("HIGH")
    ]
    assert _rate(missing)[0] == "INSUFFICIENT"


def test_missing_or_non_finite_required_evidence_is_insufficient() -> None:
    mutations = [
        ("coverage_comparison", "kruskal_p_value", float("nan")),
        ("coverage_comparison", "kruskal_statistic", float("nan")),
        ("coverage_comparison", "epsilon_squared", float("nan")),
        ("weekday_stats", "median_ci_upper", float("inf")),
        ("period_results", "kruskal_p_value", float("nan")),
        ("yearly_tests", "kruskal_p_value", float("nan")),
        ("regime_stats", "median", float("nan")),
        ("regime_tests", "p_value", float("nan")),
        ("extreme_results", "kruskal_p_value", float("nan")),
    ]
    for frame_name, column, value in mutations:
        frames = _inputs()
        frames[frame_name].loc[frames[frame_name].index[0], column] = value
        assert _rate(frames)[0] == "INSUFFICIENT", (frame_name, column)

    missing_high = _inputs()
    missing_high["regime_tests"] = missing_high["regime_tests"].loc[
        ~missing_high["regime_tests"]["volatility_regime"].eq("HIGH")
    ]
    assert _rate(missing_high)[0] == "INSUFFICIENT"

    too_small = _inputs()
    too_small["regime_tests"].loc[
        too_small["regime_tests"]["volatility_regime"].eq("HIGH"),
        "sample_size",
    ] = 99
    assert _rate(too_small)[0] == "INSUFFICIENT"


def test_high_regime_significance_is_required_context_not_a_tier_gate() -> None:
    significant = _inputs()
    nonsignificant = _inputs()
    nonsignificant["regime_tests"].loc[
        nonsignificant["regime_tests"]["volatility_regime"].eq("HIGH"),
        "p_value",
    ] = 0.9
    significant_rating, significant_detail = _rate(significant)
    nonsignificant_rating, nonsignificant_detail = _rate(nonsignificant)
    assert significant_rating == nonsignificant_rating == "MODERATE"
    assert significant_detail["high_regime_significance_role"] == "contextual_only"
    assert nonsignificant_detail["high_regime_kruskal_p_value"] == 0.9
