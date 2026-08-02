"""Independent chronological, annual, regime, and extreme-event calculations."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from eurusd_research.studies.configuration import Task04Config
from eurusd_research.studies.independent_statistics import (
    WEEKDAYS,
    descriptive_table,
    omnibus_table,
    pairwise_table,
    rank_correlation,
    weekday_order,
)


def eligible(frame: pd.DataFrame) -> pd.DataFrame:
    """Select inferentially eligible dates in stable UTC order."""
    return (
        frame.loc[frame["analysis_eligible"]]
        .sort_values("utc_date", kind="stable")
        .reset_index(drop=True)
    )


def _kruskal(frame: pd.DataFrame, alpha: float) -> tuple[float, float, float, bool]:
    groups = [
        frame.loc[frame["weekday_name"].eq(day), "daily_range_pips"].to_numpy(float)
        for day in WEEKDAYS
    ]
    groups = [group for group in groups if group.size]
    if len(groups) < 2:
        return math.nan, math.nan, math.nan, False
    same = all(np.all(group == groups[0][0]) for group in groups)
    h_value, p_value = (0.0, 1.0) if same else stats.kruskal(*groups)
    sample_size = sum(map(len, groups))
    epsilon = float(
        np.clip(
            (float(h_value) - len(groups) + 1) / (sample_size - len(groups)), 0.0, 1.0
        )
    )
    return float(h_value), float(p_value), epsilon, bool(p_value < alpha)


def _period_record(
    name: str, frame: pd.DataFrame, full_order: tuple[str, ...], config: Task04Config
) -> dict[str, Any]:
    order = weekday_order(frame)
    medians = frame.groupby("weekday_name")["daily_range_pips"].median()
    h_value, p_value, epsilon, significant = _kruskal(frame, config.alpha)
    return {
        "analysis_period": name,
        "date_start": frame["utc_date"].min() if not frame.empty else "",
        "date_end": frame["utc_date"].max() if not frame.empty else "",
        "sample_size": len(frame),
        "weekday_order_high_to_low": "|".join(order),
        "rank_correlation_with_full": rank_correlation(full_order, order),
        "kruskal_statistic": h_value,
        "kruskal_p_value": p_value,
        "epsilon_squared": epsilon,
        "significant": significant,
        **{
            f"{day.lower()}_median_pips": float(medians.get(day, math.nan))
            for day in WEEKDAYS
        },
    }


def chronological_tables(
    frame: pd.DataFrame, config: Task04Config
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Independently construct fixed periods and protected 70/30 split."""
    ordered = eligible(frame)
    dates = pd.to_datetime(ordered["utc_date"], utc=True)
    bounds = config.period_boundaries
    split = math.floor(len(ordered) * config.chronological_split_fraction)
    periods = {
        "full_eligible_sample": ordered,
        "pre_2020": ordered.loc[
            dates < pd.Timestamp(bounds.pre_2020_end_exclusive, tz="UTC")
        ],
        "covid_era": ordered.loc[
            dates.between(
                pd.Timestamp(bounds.covid_start_inclusive, tz="UTC"),
                pd.Timestamp(bounds.covid_end_inclusive, tz="UTC"),
                inclusive="both",
            )
        ],
        "post_2021": ordered.loc[
            dates >= pd.Timestamp(bounds.post_2021_start_inclusive, tz="UTC")
        ],
        "development_70": ordered.iloc[:split],
        "validation_30": ordered.iloc[split:],
    }
    full_order = weekday_order(ordered)
    records = [
        _period_record(name, value, full_order, config)
        for name, value in periods.items()
    ]
    full_pairs = pairwise_table(
        ordered, config, config.primary_coverage_profile, "full_eligible_sample"
    )
    primary_labels = set(full_pairs.loc[full_pairs["significant"], "effect_direction"])
    split_rows: list[dict[str, Any]] = []
    for name in ("development_70", "validation_30"):
        pairs = pairwise_table(
            periods[name], config, config.primary_coverage_profile, name
        )
        labels = tuple(pairs.loc[pairs["significant"], "effect_direction"].astype(str))
        record = next(item for item in records if item["analysis_period"] == name)
        split_rows.append(
            {
                **record,
                "significant_pairwise_count": int(pairs["significant"].sum()),
                "significant_pairs": "|".join(labels),
                "primary_significant_pairs_retained": len(set(labels) & primary_labels),
                "primary_significant_pair_count": len(primary_labels),
            }
        )
    return pd.DataFrame(records), pd.DataFrame(split_rows)


def annual_tables(
    frame: pd.DataFrame, config: Task04Config
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Independently retain and calculate every calendar year."""
    source = eligible(frame).copy()
    source["year"] = pd.to_datetime(source["utc_date"]).dt.year
    statistics_rows: list[dict[str, Any]] = []
    omnibus_rows: list[dict[str, Any]] = []
    for year, selected in source.groupby("year", sort=True):
        counts = selected["weekday_name"].value_counts()
        sufficient = all(
            int(counts.get(day, 0)) >= config.minimum_yearly_weekday_sample
            for day in WEEKDAYS
        )
        order = weekday_order(selected)
        medians = selected.groupby("weekday_name")["daily_range_pips"].median()
        means = selected.groupby("weekday_name")["daily_range_pips"].mean()
        for day in WEEKDAYS:
            statistics_rows.append(
                {
                    "year": int(year),
                    "weekday_name": day,
                    "sample_size": int(counts.get(day, 0)),
                    "mean": float(means.get(day, math.nan)),
                    "median": float(medians.get(day, math.nan)),
                    "rank_high_to_low": order.index(day) + 1
                    if day in order
                    else math.nan,
                    "is_highest": bool(order and day == order[0]),
                    "is_lowest": bool(order and day == order[-1]),
                    "profile": config.primary_coverage_profile,
                    "sufficient_for_inference": sufficient,
                }
            )
        h_value, p_value, epsilon, significant = _kruskal(selected, config.alpha)
        omnibus_rows.append(
            {
                "year": int(year),
                "sample_size": len(selected),
                "kruskal_statistic": h_value,
                "kruskal_p_value": p_value,
                "epsilon_squared": epsilon,
                "weekday_order_high_to_low": "|".join(order),
                "significant": significant,
                "profile": config.primary_coverage_profile,
                "sufficient_for_inference": sufficient,
            }
        )
    return pd.DataFrame(statistics_rows), pd.DataFrame(omnibus_rows)


def regime_lineage(frame: pd.DataFrame, config: Task04Config) -> pd.DataFrame:
    """Assign every regime from prior outcomes only."""
    source = eligible(frame).copy()
    outcomes = source["daily_range_pips"].astype(float)
    trailing = (
        outcomes.shift(1)
        .rolling(config.volatility_lookback, min_periods=config.volatility_lookback)
        .median()
    )
    labels: list[str] = []
    lows: list[float] = []
    highs: list[float] = []
    counts: list[int] = []
    reasons: list[str] = []
    for index, value in enumerate(trailing):
        prior = trailing.iloc[:index].dropna()
        counts.append(len(prior))
        if pd.isna(value):
            labels.append("UNCLASSIFIED")
            lows.append(math.nan)
            highs.append(math.nan)
            reasons.append("lagged_lookback_not_complete")
        elif len(prior) < config.volatility_minimum_history:
            labels.append("UNCLASSIFIED")
            lows.append(math.nan)
            highs.append(math.nan)
            reasons.append("insufficient_prior_regime_measures")
        else:
            low, high = prior.quantile(list(config.regime_quantiles))
            lows.append(float(low))
            highs.append(float(high))
            labels.append(
                "LOW" if value <= low else "HIGH" if value >= high else "MEDIUM"
            )
            reasons.append("classified_from_past_only_history")
    source["lagged_trailing_median_range_pips"] = trailing
    source["prior_regime_measure_count"] = counts
    source["past_only_low_threshold"] = lows
    source["past_only_high_threshold"] = highs
    source["volatility_regime"] = labels
    source["regime_warmup"] = source["volatility_regime"].eq("UNCLASSIFIED")
    source["regime_classification_reason"] = reasons
    source["volatility_lookback"] = config.volatility_lookback
    source["volatility_minimum_history"] = config.volatility_minimum_history
    return source


def regime_tables(
    frame: pd.DataFrame, config: Task04Config
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Independently calculate date lineage and within-regime evidence."""
    lineage = regime_lineage(frame, config)
    statistic_frames: list[pd.DataFrame] = []
    test_frames: list[pd.DataFrame] = []
    for regime in ("LOW", "MEDIUM", "HIGH"):
        selected = lineage.loc[lineage["volatility_regime"].eq(regime)]
        scope = f"volatility_regime_{regime.lower()}"
        table = descriptive_table(
            selected, config, config.primary_coverage_profile, scope
        )
        table["volatility_regime"] = regime
        tests, _ = omnibus_table(
            selected, config, config.primary_coverage_profile, scope
        )
        tests["volatility_regime"] = regime
        statistic_frames.append(table)
        test_frames.append(tests)
    return (
        pd.concat(statistic_frames, ignore_index=True),
        pd.concat(test_frames, ignore_index=True),
        lineage,
    )


def extreme_table(frame: pd.DataFrame, config: Task04Config) -> pd.DataFrame:
    """Independently apply winsorisation and reversible largest-tail exclusion."""
    source = eligible(frame)
    low, high = source["daily_range_pips"].quantile(list(config.winsorisation_limits))
    tail = float(
        source["daily_range_pips"].quantile(
            1.0 - config.largest_tail_exclusion_fraction
        )
    )
    variants = {
        "primary_raw_distribution": source,
        "winsorised_1_99": source.assign(
            daily_range_pips=source["daily_range_pips"].clip(low, high)
        ),
        "exclude_largest_1_percent": source.loc[source["daily_range_pips"] <= tail],
    }
    full_order = weekday_order(source)
    records: list[dict[str, Any]] = []
    for name, selected in variants.items():
        h_value, p_value, epsilon, significant = _kruskal(selected, config.alpha)
        order = weekday_order(selected)
        records.append(
            {
                "analysis_variant": name,
                "sample_size": len(selected),
                "excluded_observation_count": len(source) - len(selected),
                "lower_threshold_pips": float(low)
                if "winsorised" in name
                else math.nan,
                "upper_threshold_pips": float(high)
                if "winsorised" in name
                else tail
                if "exclude" in name
                else math.nan,
                "weekday_order_high_to_low": "|".join(order),
                "rank_correlation_with_primary": rank_correlation(full_order, order),
                "kruskal_statistic": h_value,
                "kruskal_p_value": p_value,
                "epsilon_squared": epsilon,
                "significant": significant,
            }
        )
    return pd.DataFrame(records)


def coverage_profile_tables(
    frames: dict[str, pd.DataFrame], config: Task04Config
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Independently calculate all profile descriptives, tests, pairs, and effects."""
    statistics: list[pd.DataFrame] = []
    tests: list[pd.DataFrame] = []
    pairs: list[pd.DataFrame] = []
    effects: list[pd.DataFrame] = []
    for profile in (config.primary_coverage_profile, *config.sensitivity_profiles):
        selected = eligible(frames[profile])
        statistics.append(
            descriptive_table(selected, config, profile, "complete_weekday_dates")
        )
        test, effect = omnibus_table(
            selected, config, profile, "complete_weekday_dates"
        )
        tests.append(test)
        pairwise = pairwise_table(selected, config, profile, "complete_weekday_dates")
        pairs.append(pairwise)
        effects.append(
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
        effects.append(effect)
    return (
        pd.concat(statistics, ignore_index=True),
        pd.concat(tests, ignore_index=True),
        pd.concat(pairs, ignore_index=True),
        pd.concat(effects, ignore_index=True),
    )
