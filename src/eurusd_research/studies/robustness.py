"""Prespecified chronological, regime, and extreme-event robustness analyses."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from eurusd_research.studies.configuration import Task04Config
from eurusd_research.studies.statistics import (
    epsilon_squared,
    omnibus_effect_records,
    omnibus_records,
    pairwise_records,
    weekday_statistics,
)


def eligible_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Select and order inferentially eligible weekday dates."""
    return (
        frame.loc[frame["analysis_eligible"]]
        .sort_values("utc_date", kind="stable")
        .reset_index(drop=True)
    )


def weekday_order(frame: pd.DataFrame) -> tuple[str, ...]:
    """Order weekdays from highest to lowest median with calendar tie-breaking."""
    medians = frame.groupby("weekday_name", observed=True)["daily_range_pips"].median()
    calendar = {
        name: index
        for index, name in enumerate(
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
        )
    }
    return tuple(
        sorted(
            medians.index,
            key=lambda name: (-float(medians[name]), calendar[str(name)]),
        )
    )


def rank_correlation(
    reference_order: tuple[str, ...], comparison_order: tuple[str, ...]
) -> float:
    """Spearman rank agreement over common weekdays."""
    common = [name for name in reference_order if name in comparison_order]
    if len(common) < 2:
        return math.nan
    reference = [reference_order.index(name) for name in common]
    comparison = [comparison_order.index(name) for name in common]
    return float(stats.spearmanr(reference, comparison).statistic)


def significant_pair_labels(pairwise: pd.DataFrame) -> tuple[str, ...]:
    """Return registered effect directions for significant pairwise rows only."""
    if pairwise.empty:
        return ()
    return tuple(
        str(row.effect_direction) for row in pairwise.itertuples() if row.significant
    )


def _kruskal_summary(
    frame: pd.DataFrame, config: Task04Config
) -> tuple[float, float, float]:
    groups = [
        frame.loc[frame["weekday_name"].eq(day), "daily_range_pips"].to_numpy()
        for day in config.weekday_inclusion
    ]
    groups = [group for group in groups if len(group)]
    if len(groups) < 2:
        return math.nan, math.nan, math.nan
    same = all(np.all(group == groups[0][0]) for group in groups)
    if same:
        statistic, p_value = 0.0, 1.0
    else:
        result = stats.kruskal(*groups)
        statistic, p_value = float(result.statistic), float(result.pvalue)
    return (
        statistic,
        p_value,
        epsilon_squared(statistic, sum(map(len, groups)), len(groups)),
    )


def chronological_periods(
    frame: pd.DataFrame, config: Task04Config
) -> dict[str, pd.DataFrame]:
    """Build all fixed chronological periods plus ordered development/validation."""
    ordered = eligible_daily(frame)
    dates = pd.to_datetime(ordered["utc_date"], utc=True)
    boundaries = config.period_boundaries
    split = math.floor(len(ordered) * config.chronological_split_fraction)
    return {
        "full_eligible_sample": ordered,
        "pre_2020": ordered.loc[
            dates < pd.Timestamp(boundaries.pre_2020_end_exclusive, tz="UTC")
        ],
        "covid_era": ordered.loc[
            dates.between(
                pd.Timestamp(boundaries.covid_start_inclusive, tz="UTC"),
                pd.Timestamp(boundaries.covid_end_inclusive, tz="UTC"),
                inclusive="both",
            )
        ],
        "post_2021": ordered.loc[
            dates >= pd.Timestamp(boundaries.post_2021_start_inclusive, tz="UTC")
        ],
        "development_70": ordered.iloc[:split],
        "validation_30": ordered.iloc[split:],
    }


def chronological_outputs(
    frame: pd.DataFrame, config: Task04Config
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Summarise fixed periods and the protected chronological split."""
    periods = chronological_periods(frame, config)
    full_order = weekday_order(periods["full_eligible_sample"])
    records: list[dict[str, Any]] = []
    split_records: list[dict[str, Any]] = []
    full_pairwise = pairwise_records(
        periods["full_eligible_sample"],
        config=config,
        profile=config.primary_coverage_profile,
        analysis_scope="full_eligible_sample",
    )
    full_significant = set(significant_pair_labels(full_pairwise))
    for name, selected in periods.items():
        statistic, p_value, effect = _kruskal_summary(selected, config)
        order = weekday_order(selected)
        medians = selected.groupby("weekday_name", observed=True)[
            "daily_range_pips"
        ].median()
        record = {
            "analysis_period": name,
            "date_start": selected["utc_date"].min() if not selected.empty else "",
            "date_end": selected["utc_date"].max() if not selected.empty else "",
            "sample_size": len(selected),
            "weekday_order_high_to_low": "|".join(order),
            "rank_correlation_with_full": rank_correlation(full_order, order),
            "kruskal_statistic": statistic,
            "kruskal_p_value": p_value,
            "epsilon_squared": effect,
            "significant": bool(np.isfinite(p_value) and p_value < config.alpha),
            **{
                f"{day.lower()}_median_pips": float(medians.get(day, math.nan))
                for day in config.weekday_inclusion
            },
        }
        records.append(record)
        if name in {"development_70", "validation_30"}:
            pairwise = pairwise_records(
                selected,
                config=config,
                profile=config.primary_coverage_profile,
                analysis_scope=name,
            )
            split_records.append(
                {
                    **record,
                    "significant_pairwise_count": (
                        int(pairwise["significant"].sum()) if not pairwise.empty else 0
                    ),
                    "significant_pairs": (
                        "|".join(significant_pair_labels(pairwise))
                        if not pairwise.empty
                        else ""
                    ),
                    "primary_significant_pairs_retained": (
                        len(set(significant_pair_labels(pairwise)) & full_significant)
                        if not pairwise.empty
                        else 0
                    ),
                    "primary_significant_pair_count": len(full_significant),
                }
            )
    return pd.DataFrame(records), pd.DataFrame(split_records)


def yearly_outputs(
    frame: pd.DataFrame, config: Task04Config
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate year-by-year weekday summaries and omnibus comparisons."""
    eligible = eligible_daily(frame).copy()
    eligible["year"] = pd.to_datetime(eligible["utc_date"]).dt.year
    statistic_records: list[dict[str, Any]] = []
    omnibus_records_output: list[dict[str, Any]] = []
    for year, year_frame in eligible.groupby("year", sort=True):
        counts = year_frame["weekday_name"].value_counts()
        sufficient = all(
            int(counts.get(day, 0)) >= config.minimum_yearly_weekday_sample
            for day in config.weekday_inclusion
        )
        order = weekday_order(year_frame)
        medians = year_frame.groupby("weekday_name")["daily_range_pips"].median()
        means = year_frame.groupby("weekday_name")["daily_range_pips"].mean()
        for day in config.weekday_inclusion:
            statistic_records.append(
                {
                    "year": int(year),
                    "weekday_name": day,
                    "sample_size": int(counts.get(day, 0)),
                    "mean": float(means.get(day, math.nan)),
                    "median": float(medians.get(day, math.nan)),
                    "rank_high_to_low": (
                        order.index(day) + 1 if day in order else math.nan
                    ),
                    "is_highest": bool(order and day == order[0]),
                    "is_lowest": bool(order and day == order[-1]),
                    "profile": config.primary_coverage_profile,
                    "sufficient_for_inference": sufficient,
                }
            )
        statistic, p_value, effect = _kruskal_summary(year_frame, config)
        omnibus_records_output.append(
            {
                "year": int(year),
                "sample_size": len(year_frame),
                "kruskal_statistic": statistic,
                "kruskal_p_value": p_value,
                "epsilon_squared": effect,
                "weekday_order_high_to_low": "|".join(order),
                "significant": bool(np.isfinite(p_value) and p_value < config.alpha),
                "profile": config.primary_coverage_profile,
                "sufficient_for_inference": sufficient,
            }
        )
    return (
        pd.DataFrame(statistic_records),
        pd.DataFrame(omnibus_records_output),
    )


def assign_past_only_volatility_regime(
    frame: pd.DataFrame, config: Task04Config
) -> pd.DataFrame:
    """Assign regimes using only lagged outcomes and prior regime measures."""
    ordered = eligible_daily(frame).copy()
    outcomes = ordered["daily_range_pips"].astype(float)
    trailing = (
        outcomes.shift(1)
        .rolling(
            config.volatility_lookback,
            min_periods=config.volatility_lookback,
        )
        .median()
    )
    labels: list[str] = []
    low_thresholds: list[float] = []
    high_thresholds: list[float] = []
    prior_measure_counts: list[int] = []
    classification_reasons: list[str] = []
    for position, value in enumerate(trailing):
        history = trailing.iloc[:position].dropna()
        prior_measure_counts.append(len(history))
        if pd.isna(value):
            labels.append("UNCLASSIFIED")
            low_thresholds.append(math.nan)
            high_thresholds.append(math.nan)
            classification_reasons.append("lagged_lookback_not_complete")
            continue
        if len(history) < config.volatility_minimum_history:
            labels.append("UNCLASSIFIED")
            low_thresholds.append(math.nan)
            high_thresholds.append(math.nan)
            classification_reasons.append("insufficient_prior_regime_measures")
            continue
        low, high = history.quantile(list(config.regime_quantiles))
        low_thresholds.append(float(low))
        high_thresholds.append(float(high))
        if value <= low:
            labels.append("LOW")
        elif value >= high:
            labels.append("HIGH")
        else:
            labels.append("MEDIUM")
        classification_reasons.append("classified_from_past_only_history")
    ordered["lagged_trailing_median_range_pips"] = trailing
    ordered["past_only_low_threshold"] = low_thresholds
    ordered["past_only_high_threshold"] = high_thresholds
    ordered["volatility_regime"] = labels
    ordered["prior_regime_measure_count"] = prior_measure_counts
    ordered["regime_warmup"] = ordered["volatility_regime"].eq("UNCLASSIFIED")
    ordered["regime_classification_reason"] = classification_reasons
    ordered["volatility_lookback"] = config.volatility_lookback
    ordered["volatility_minimum_history"] = config.volatility_minimum_history
    return ordered


def volatility_regime_outputs(
    frame: pd.DataFrame, config: Task04Config
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Repeat weekday descriptive and omnibus analyses inside each regime."""
    classified = assign_past_only_volatility_regime(frame, config)
    stats_frames: list[pd.DataFrame] = []
    test_frames: list[pd.DataFrame] = []
    for regime in ("LOW", "MEDIUM", "HIGH"):
        selected = classified.loc[classified["volatility_regime"].eq(regime)]
        stats_frame = weekday_statistics(
            selected,
            config=config,
            profile=config.primary_coverage_profile,
            analysis_scope=f"volatility_regime_{regime.lower()}",
        )
        stats_frame["volatility_regime"] = regime
        stats_frames.append(stats_frame)
        tests = omnibus_records(
            selected,
            config=config,
            profile=config.primary_coverage_profile,
            analysis_scope=f"volatility_regime_{regime.lower()}",
        )
        tests["volatility_regime"] = regime
        test_frames.append(tests)
    return (
        pd.concat(stats_frames, ignore_index=True),
        pd.concat(test_frames, ignore_index=True),
        classified,
    )


def extreme_event_outputs(frame: pd.DataFrame, config: Task04Config) -> pd.DataFrame:
    """Run reversible winsorised and largest-tail sensitivity comparisons."""
    eligible = eligible_daily(frame)
    low, high = eligible["daily_range_pips"].quantile(list(config.winsorisation_limits))
    tail_threshold = float(
        eligible["daily_range_pips"].quantile(
            1.0 - config.largest_tail_exclusion_fraction
        )
    )
    variants = {
        "primary_raw_distribution": eligible,
        "winsorised_1_99": eligible.assign(
            daily_range_pips=eligible["daily_range_pips"].clip(low, high)
        ),
        "exclude_largest_1_percent": eligible.loc[
            eligible["daily_range_pips"] <= tail_threshold
        ],
    }
    full_order = weekday_order(eligible)
    records: list[dict[str, Any]] = []
    for name, selected in variants.items():
        statistic, p_value, effect = _kruskal_summary(selected, config)
        order = weekday_order(selected)
        records.append(
            {
                "analysis_variant": name,
                "sample_size": len(selected),
                "excluded_observation_count": len(eligible) - len(selected),
                "lower_threshold_pips": float(low)
                if "winsorised" in name
                else math.nan,
                "upper_threshold_pips": (
                    float(high)
                    if "winsorised" in name
                    else tail_threshold
                    if "exclude" in name
                    else math.nan
                ),
                "weekday_order_high_to_low": "|".join(order),
                "rank_correlation_with_primary": rank_correlation(full_order, order),
                "kruskal_statistic": statistic,
                "kruskal_p_value": p_value,
                "epsilon_squared": effect,
                "significant": bool(p_value < config.alpha),
            }
        )
    return pd.DataFrame(records)


def coverage_profile_outputs(
    by_profile: Mapping[str, pd.DataFrame], config: Task04Config
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Generate comparable profile summaries, tests, pairwise rows, and effects."""
    statistics_frames: list[pd.DataFrame] = []
    test_frames: list[pd.DataFrame] = []
    pairwise_frames: list[pd.DataFrame] = []
    effect_frames: list[pd.DataFrame] = []
    comparison_records: list[dict[str, Any]] = []
    primary_order: tuple[str, ...] | None = None
    for profile in (
        config.primary_coverage_profile,
        *config.sensitivity_profiles,
    ):
        selected = eligible_daily(by_profile[profile])
        order = weekday_order(selected)
        if primary_order is None:
            primary_order = order
        statistic_frame = weekday_statistics(
            selected,
            config=config,
            profile=profile,
            analysis_scope="complete_weekday_dates",
        )
        tests = omnibus_records(
            selected,
            config=config,
            profile=profile,
            analysis_scope="complete_weekday_dates",
        )
        pairwise = pairwise_records(
            selected,
            config=config,
            profile=profile,
            analysis_scope="complete_weekday_dates",
        )
        effects = omnibus_effect_records(
            selected,
            config=config,
            profile=profile,
            analysis_scope="complete_weekday_dates",
        )
        statistics_frames.append(statistic_frame)
        test_frames.append(tests)
        if not pairwise.empty:
            pairwise_frames.append(pairwise)
            effect_frames.append(
                pd.DataFrame(
                    {
                        "profile": pairwise["profile"],
                        "analysis_scope": pairwise["analysis_scope"],
                        "comparison": (
                            pairwise["weekday_a"] + " versus " + pairwise["weekday_b"]
                        ),
                        "effect_size_method": "cliffs_delta",
                        "effect_size": pairwise["cliffs_delta_a_minus_b"],
                        "sample_size": (
                            pairwise["sample_size_a"] + pairwise["sample_size_b"]
                        ),
                        "effect_size_magnitude": pairwise["effect_size_magnitude"],
                        "effect_direction": pairwise["effect_direction"],
                    }
                )
            )
        effect_frames.append(effects)
        primary_test = tests.loc[tests["test_name"].eq("kruskal_wallis")].iloc[0]
        epsilon = effects.loc[
            effects["effect_size_method"].eq("epsilon_squared"), "effect_size"
        ].iloc[0]
        comparison_records.append(
            {
                "profile": profile,
                "eligible_daily_observations": len(selected),
                "date_start": selected["utc_date"].min() if not selected.empty else "",
                "date_end": selected["utc_date"].max() if not selected.empty else "",
                "weekday_order_high_to_low": "|".join(order),
                "rank_correlation_with_primary": rank_correlation(
                    primary_order or (), order
                ),
                "kruskal_statistic": primary_test["statistic"],
                "kruskal_p_value": primary_test["p_value"],
                "epsilon_squared": epsilon,
                "significant": primary_test["significant"],
            }
        )
    return (
        pd.concat(statistics_frames, ignore_index=True),
        pd.concat(test_frames, ignore_index=True),
        pd.concat(pairwise_frames, ignore_index=True)
        if pairwise_frames
        else pd.DataFrame(),
        pd.concat(effect_frames, ignore_index=True),
        pd.DataFrame(comparison_records),
    )
