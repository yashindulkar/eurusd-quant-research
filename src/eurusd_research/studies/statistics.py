"""Transparent descriptive and inferential statistics for Task 04."""

from __future__ import annotations

import hashlib
import itertools
import math
import warnings
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.oneway import anova_oneway

from eurusd_research.studies.configuration import Task04Config


def _seed(base_seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{base_seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def bootstrap_interval(
    values: np.ndarray,
    statistic: Callable[[np.ndarray], float],
    *,
    confidence_level: float,
    resamples: int,
    seed: int,
) -> tuple[float, float]:
    """Deterministic iid percentile-bootstrap interval."""
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size == 0:
        return math.nan, math.nan
    if clean.size == 1 or np.all(clean == clean[0]):
        value = float(statistic(clean))
        return value, value
    generator = np.random.default_rng(seed)
    estimates = np.empty(resamples, dtype=float)
    for index in range(resamples):
        sample = clean[generator.integers(0, clean.size, clean.size)]
        estimates[index] = statistic(sample)
    tail = (1.0 - confidence_level) / 2.0
    low, high = np.quantile(estimates, [tail, 1.0 - tail])
    return float(low), float(high)


def descriptive_record(
    values: Sequence[float] | np.ndarray,
    *,
    full_sample_median: float,
    config: Task04Config,
    label: str,
) -> dict[str, Any]:
    """Calculate the complete preregistered descriptive-statistics set."""
    array = np.asarray(values, dtype=float)
    missing = int((~np.isfinite(array)).sum())
    clean = array[np.isfinite(array)]
    if clean.size == 0:
        return {
            "sample_size": 0,
            "missing_count": missing,
            **{
                name: math.nan
                for name in (
                    "mean",
                    "median",
                    "standard_deviation",
                    "variance",
                    "minimum",
                    "maximum",
                    "percentile_1",
                    "percentile_5",
                    "percentile_10",
                    "percentile_25",
                    "percentile_75",
                    "percentile_90",
                    "percentile_95",
                    "percentile_99",
                    "interquartile_range",
                    "median_absolute_deviation",
                    "coefficient_of_variation",
                    "skewness",
                    "excess_kurtosis",
                    "mean_ci_lower",
                    "mean_ci_upper",
                    "median_ci_lower",
                    "median_ci_upper",
                    "proportion_above_full_sample_median",
                    "qq_plot_correlation",
                )
            },
        }
    quantiles = np.quantile(clean, [0.01, 0.05, 0.10, 0.25, 0.75, 0.90, 0.95, 0.99])
    mean = float(np.mean(clean))
    median = float(np.median(clean))
    variance = float(np.var(clean, ddof=1)) if clean.size > 1 else 0.0
    standard_deviation = math.sqrt(variance)
    mean_ci = bootstrap_interval(
        clean,
        lambda sample: float(np.mean(sample)),
        confidence_level=config.confidence_level,
        resamples=config.bootstrap_resamples,
        seed=_seed(config.bootstrap_seed, f"{label}:mean"),
    )
    median_ci = bootstrap_interval(
        clean,
        lambda sample: float(np.median(sample)),
        confidence_level=config.confidence_level,
        resamples=config.bootstrap_resamples,
        seed=_seed(config.bootstrap_seed, f"{label}:median"),
    )
    if clean.size >= 3 and not np.all(clean == clean[0]):
        skewness = float(stats.skew(clean, bias=False))
        kurtosis = float(stats.kurtosis(clean, fisher=True, bias=False))
        qq_correlation = float(stats.probplot(clean, dist="norm", fit=True)[1][2])
    else:
        skewness = 0.0
        kurtosis = 0.0
        qq_correlation = 1.0
    return {
        "sample_size": int(clean.size),
        "missing_count": missing,
        "mean": mean,
        "median": median,
        "standard_deviation": standard_deviation,
        "variance": variance,
        "minimum": float(np.min(clean)),
        "maximum": float(np.max(clean)),
        "percentile_1": float(quantiles[0]),
        "percentile_5": float(quantiles[1]),
        "percentile_10": float(quantiles[2]),
        "percentile_25": float(quantiles[3]),
        "percentile_75": float(quantiles[4]),
        "percentile_90": float(quantiles[5]),
        "percentile_95": float(quantiles[6]),
        "percentile_99": float(quantiles[7]),
        "interquartile_range": float(quantiles[4] - quantiles[3]),
        "median_absolute_deviation": float(np.median(np.abs(clean - np.median(clean)))),
        "coefficient_of_variation": (
            standard_deviation / mean if not np.isclose(mean, 0.0) else math.nan
        ),
        "skewness": skewness,
        "excess_kurtosis": kurtosis,
        "mean_ci_lower": mean_ci[0],
        "mean_ci_upper": mean_ci[1],
        "median_ci_lower": median_ci[0],
        "median_ci_upper": median_ci[1],
        "proportion_above_full_sample_median": float(
            np.mean(clean > full_sample_median)
        ),
        "qq_plot_correlation": qq_correlation,
    }


def weekday_statistics(
    frame: pd.DataFrame,
    *,
    config: Task04Config,
    profile: str,
    analysis_scope: str,
) -> pd.DataFrame:
    """Describe every weekday in stable calendar order."""
    full_median = float(frame["daily_range_pips"].median())
    date_min = frame["utc_date"].min() if not frame.empty else ""
    date_max = frame["utc_date"].max() if not frame.empty else ""
    records = []
    for weekday in config.weekday_inclusion:
        values = frame.loc[
            frame["weekday_name"].eq(weekday), "daily_range_pips"
        ].to_numpy(dtype=float)
        records.append(
            {
                "profile": profile,
                "analysis_scope": analysis_scope,
                "weekday_name": weekday,
                **descriptive_record(
                    values,
                    full_sample_median=full_median,
                    config=config,
                    label=f"{profile}:{analysis_scope}:{weekday}",
                ),
                "study_date_start": date_min,
                "study_date_end": date_max,
            }
        )
    return pd.DataFrame.from_records(records)


def epsilon_squared(statistic: float, sample_size: int, groups: int) -> float:
    """Kruskal-Wallis epsilon-squared, clipped to its feasible range."""
    if sample_size <= groups:
        return math.nan
    return float(np.clip((statistic - groups + 1) / (sample_size - groups), 0.0, 1.0))


def _anova_effects(groups: Sequence[np.ndarray]) -> tuple[float, float]:
    clean = [np.asarray(group, dtype=float) for group in groups if len(group)]
    sample_size = sum(len(group) for group in clean)
    group_count = len(clean)
    if group_count < 2 or sample_size <= group_count:
        return math.nan, math.nan
    grand = float(np.mean(np.concatenate(clean)))
    between = sum(len(group) * (float(np.mean(group)) - grand) ** 2 for group in clean)
    within = sum(float(np.sum((group - np.mean(group)) ** 2)) for group in clean)
    total = between + within
    eta = between / total if total else 0.0
    mean_square_within = within / (sample_size - group_count)
    omega_denominator = total + mean_square_within
    omega = (
        (between - (group_count - 1) * mean_square_within) / omega_denominator
        if omega_denominator
        else 0.0
    )
    return float(np.clip(eta, 0.0, 1.0)), float(np.clip(omega, 0.0, 1.0))


def _valid_groups(
    frame: pd.DataFrame, weekdays: Iterable[str]
) -> tuple[list[str], list[np.ndarray]]:
    names: list[str] = []
    groups: list[np.ndarray] = []
    for weekday in weekdays:
        values = frame.loc[
            frame["weekday_name"].eq(weekday), "daily_range_pips"
        ].dropna()
        if not values.empty:
            names.append(weekday)
            groups.append(values.to_numpy(dtype=float))
    return names, groups


def omnibus_records(
    frame: pd.DataFrame,
    *,
    config: Task04Config,
    profile: str,
    analysis_scope: str,
) -> pd.DataFrame:
    """Run all preregistered omnibus and diagnostic comparisons."""
    names, groups = _valid_groups(frame, config.weekday_inclusion)
    sample_size = sum(len(group) for group in groups)
    if len(groups) < 2:
        return pd.DataFrame.from_records(
            [
                {
                    "profile": profile,
                    "analysis_scope": analysis_scope,
                    "test_name": name,
                    "test_role": role,
                    "statistic": math.nan,
                    "p_value": math.nan,
                    "numerator_degrees_of_freedom": math.nan,
                    "denominator_degrees_of_freedom": math.nan,
                    "sample_size": sample_size,
                    "group_count": len(groups),
                    "significant": False,
                }
                for name, role in (
                    ("kruskal_wallis", "primary"),
                    ("one_way_anova", "complementary"),
                    ("welch_anova", "complementary"),
                    ("brown_forsythe_levene", "diagnostic"),
                )
            ]
        )
    all_constant = all(np.all(group == group[0]) for group in groups)
    same_constant = all_constant and len({float(group[0]) for group in groups}) == 1
    if same_constant:
        kruskal_statistic, kruskal_p = 0.0, 1.0
    else:
        kruskal_statistic, kruskal_p = stats.kruskal(*groups)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        anova = stats.f_oneway(*groups)
        levene = stats.levene(*groups, center="median")
        welch = anova_oneway(groups, use_var="unequal")
    values = (
        (
            "kruskal_wallis",
            "primary",
            float(kruskal_statistic),
            float(kruskal_p),
            len(groups) - 1,
            math.nan,
        ),
        (
            "one_way_anova",
            "complementary",
            float(np.nan_to_num(anova.statistic, nan=0.0)),
            float(np.nan_to_num(anova.pvalue, nan=1.0)),
            len(groups) - 1,
            sample_size - len(groups),
        ),
        (
            "welch_anova",
            "complementary",
            float(np.nan_to_num(welch.statistic, nan=0.0)),
            float(np.nan_to_num(welch.pvalue, nan=1.0)),
            float(welch.df_num),
            float(welch.df_denom),
        ),
        (
            "brown_forsythe_levene",
            "diagnostic",
            float(np.nan_to_num(levene.statistic, nan=0.0)),
            float(np.nan_to_num(levene.pvalue, nan=1.0)),
            len(groups) - 1,
            sample_size - len(groups),
        ),
    )
    return pd.DataFrame.from_records(
        [
            {
                "profile": profile,
                "analysis_scope": analysis_scope,
                "test_name": name,
                "test_role": role,
                "statistic": statistic,
                "p_value": p_value,
                "numerator_degrees_of_freedom": numerator_degrees,
                "denominator_degrees_of_freedom": denominator_degrees,
                "sample_size": sample_size,
                "group_count": len(groups),
                "groups_present": "|".join(names),
                "significant": bool(p_value < config.alpha),
            }
            for (
                name,
                role,
                statistic,
                p_value,
                numerator_degrees,
                denominator_degrees,
            ) in values
        ]
    )


def omnibus_effect_records(
    frame: pd.DataFrame,
    *,
    config: Task04Config,
    profile: str,
    analysis_scope: str,
) -> pd.DataFrame:
    """Calculate nonparametric and parametric omnibus effect sizes."""
    _, groups = _valid_groups(frame, config.weekday_inclusion)
    sample_size = sum(len(group) for group in groups)
    if len(groups) < 2:
        effects = (
            ("epsilon_squared", math.nan),
            ("eta_squared", math.nan),
            ("omega_squared", math.nan),
        )
    else:
        same_constant = all(np.all(group == groups[0][0]) for group in groups)
        statistic = 0.0 if same_constant else float(stats.kruskal(*groups).statistic)
        eta, omega = _anova_effects(groups)
        effects = (
            ("epsilon_squared", epsilon_squared(statistic, sample_size, len(groups))),
            ("eta_squared", eta),
            ("omega_squared", omega),
        )
    return pd.DataFrame.from_records(
        [
            {
                "profile": profile,
                "analysis_scope": analysis_scope,
                "comparison": "Monday-Friday",
                "effect_size_method": method,
                "effect_size": value,
                "sample_size": sample_size,
            }
            for method, value in effects
        ]
    )


def holm_adjust(p_values: Sequence[float]) -> np.ndarray:
    """Holm family-wise p-value adjustment with stable monotonicity."""
    values = np.asarray(p_values, dtype=float)
    if values.size == 0:
        return values
    order = np.argsort(values, kind="stable")
    adjusted_sorted = np.empty(values.size, dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        candidate = (values.size - rank) * values[index]
        running = max(running, candidate)
        adjusted_sorted[rank] = min(running, 1.0)
    adjusted = np.empty(values.size, dtype=float)
    adjusted[order] = adjusted_sorted
    return adjusted


def cliffs_delta(group_a: np.ndarray, group_b: np.ndarray) -> float:
    """Cliff's delta with A-minus-B direction and tie support."""
    if group_a.size == 0 or group_b.size == 0:
        return math.nan
    statistic = stats.mannwhitneyu(
        group_a, group_b, alternative="two-sided", method="asymptotic"
    ).statistic
    return float(2.0 * statistic / (group_a.size * group_b.size) - 1.0)


def _dunn_unadjusted(
    arrays: Sequence[np.ndarray], pairs: Sequence[tuple[int, int]]
) -> list[float]:
    pooled = np.concatenate(arrays)
    ranks = stats.rankdata(pooled, method="average")
    counts = np.array([len(array) for array in arrays], dtype=int)
    ends = np.cumsum(counts)
    starts = np.r_[0, ends[:-1]]
    mean_ranks = np.array(
        [
            float(np.mean(ranks[start:end]))
            for start, end in zip(starts, ends, strict=True)
        ]
    )
    _, tie_counts = np.unique(pooled, return_counts=True)
    tie_term = float(np.sum(tie_counts**3 - tie_counts))
    sample_size = pooled.size
    variance = sample_size * (sample_size + 1) / 12.0
    if sample_size > 1:
        variance -= tie_term / (12.0 * (sample_size - 1))
    output = []
    for first, second in pairs:
        standard_error = math.sqrt(
            variance * (1.0 / counts[first] + 1.0 / counts[second])
        )
        if np.isclose(standard_error, 0.0):
            output.append(1.0)
            continue
        z_value = (mean_ranks[first] - mean_ranks[second]) / standard_error
        output.append(float(2.0 * stats.norm.sf(abs(z_value))))
    return output


def _effect_magnitude(value: float) -> str:
    absolute = abs(value)
    if absolute < 0.147:
        return "negligible"
    if absolute < 0.330:
        return "small"
    if absolute < 0.474:
        return "medium"
    return "large"


def pairwise_records(
    frame: pd.DataFrame,
    *,
    config: Task04Config,
    profile: str,
    analysis_scope: str,
) -> pd.DataFrame:
    """Run all ten Dunn comparisons and associated robust effects."""
    names, arrays = _valid_groups(frame, config.weekday_inclusion)
    if len(names) != len(config.weekday_inclusion):
        return pd.DataFrame()
    pairs = list(itertools.combinations(range(len(names)), 2))
    raw_p = _dunn_unadjusted(arrays, pairs)
    adjusted = holm_adjust(raw_p)
    records: list[dict[str, Any]] = []
    for position, (first, second) in enumerate(pairs):
        a = arrays[first]
        b = arrays[second]
        median_difference = float(np.median(a) - np.median(b))
        mean_difference = float(np.mean(a) - np.mean(b))
        generator = np.random.default_rng(
            _seed(
                config.bootstrap_seed,
                f"{profile}:{analysis_scope}:{names[first]}:{names[second]}",
            )
        )
        bootstrap = np.empty(config.bootstrap_resamples, dtype=float)
        for index in range(config.bootstrap_resamples):
            sample_a = a[generator.integers(0, a.size, a.size)]
            sample_b = b[generator.integers(0, b.size, b.size)]
            bootstrap[index] = np.median(sample_a) - np.median(sample_b)
        tail = (1.0 - config.confidence_level) / 2.0
        ci = np.quantile(bootstrap, [tail, 1.0 - tail])
        delta = cliffs_delta(a, b)
        records.append(
            {
                "profile": profile,
                "analysis_scope": analysis_scope,
                "weekday_a": names[first],
                "weekday_b": names[second],
                "sample_size_a": len(a),
                "sample_size_b": len(b),
                "median_a": float(np.median(a)),
                "median_b": float(np.median(b)),
                "median_difference_a_minus_b": median_difference,
                "mean_difference_a_minus_b": mean_difference,
                "relative_median_difference": (
                    median_difference / float(np.median(b))
                    if not np.isclose(np.median(b), 0.0)
                    else math.nan
                ),
                "unadjusted_p_value": raw_p[position],
                "holm_adjusted_p_value": float(adjusted[position]),
                "significant": bool(adjusted[position] < config.alpha),
                "cliffs_delta_a_minus_b": delta,
                "effect_size_magnitude": _effect_magnitude(delta),
                "effect_direction": (
                    f"{names[first]}>{names[second]}"
                    if delta > 0
                    else f"{names[first]}<{names[second]}"
                    if delta < 0
                    else "no_direction"
                ),
                "median_difference_ci_lower": float(ci[0]),
                "median_difference_ci_upper": float(ci[1]),
                "study_date_start": frame["utc_date"].min(),
                "study_date_end": frame["utc_date"].max(),
            }
        )
    return pd.DataFrame.from_records(records)
