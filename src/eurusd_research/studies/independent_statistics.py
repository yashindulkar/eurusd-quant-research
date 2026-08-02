"""Independent statistical formulas used only by Task 04 reconciliation."""

from __future__ import annotations

import hashlib
import itertools
import math
import warnings
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.oneway import anova_oneway

from eurusd_research.studies.configuration import Task04Config

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def derived_seed(base: int, label: str) -> int:
    """Derive the registered deterministic bootstrap seed."""
    return int.from_bytes(
        hashlib.sha256(f"{base}:{label}".encode()).digest()[:8], "big"
    )


def bootstrap_interval(
    values: np.ndarray,
    *,
    median: bool,
    seed: int,
    resamples: int,
    confidence_level: float,
) -> tuple[float, float]:
    """Independent iid percentile interval with NumPy linear quantiles."""
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size == 0:
        return math.nan, math.nan
    function = np.median if median else np.mean
    if clean.size == 1 or np.all(clean == clean[0]):
        value = float(function(clean))
        return value, value
    generator = np.random.default_rng(seed)
    values_out = np.empty(resamples, dtype=float)
    for index in range(resamples):
        sample = clean[generator.integers(0, clean.size, clean.size)]
        values_out[index] = float(function(sample))
    tail = (1.0 - confidence_level) / 2.0
    bounds = np.quantile(values_out, [tail, 1.0 - tail], method="linear")
    return float(bounds[0]), float(bounds[1])


def descriptive_values(
    values: np.ndarray,
    *,
    full_median: float,
    label: str,
    config: Task04Config,
) -> dict[str, int | float]:
    """Calculate every preregistered descriptive field independently."""
    source = np.asarray(values, dtype=float)
    missing = int((~np.isfinite(source)).sum())
    clean = source[np.isfinite(source)]
    if clean.size == 0:
        raise ValueError(f"Independent descriptive group is empty: {label}")
    quantiles = np.quantile(
        clean, [0.01, 0.05, 0.10, 0.25, 0.75, 0.90, 0.95, 0.99], method="linear"
    )
    mean = float(np.mean(clean))
    median = float(np.median(clean))
    variance = float(np.var(clean, ddof=1)) if clean.size > 1 else 0.0
    standard_deviation = math.sqrt(variance)
    if clean.size >= 3 and not np.all(clean == clean[0]):
        skewness = float(stats.skew(clean, bias=False))
        kurtosis = float(stats.kurtosis(clean, fisher=True, bias=False))
        qq_correlation = float(stats.probplot(clean, dist="norm", fit=True)[1][2])
    else:
        skewness, kurtosis, qq_correlation = 0.0, 0.0, 1.0
    mean_ci = bootstrap_interval(
        clean,
        median=False,
        seed=derived_seed(config.bootstrap_seed, f"{label}:mean"),
        resamples=config.bootstrap_resamples,
        confidence_level=config.confidence_level,
    )
    median_ci = bootstrap_interval(
        clean,
        median=True,
        seed=derived_seed(config.bootstrap_seed, f"{label}:median"),
        resamples=config.bootstrap_resamples,
        confidence_level=config.confidence_level,
    )
    return {
        "sample_size": int(clean.size),
        "missing_count": missing,
        "mean": mean,
        "median": median,
        "standard_deviation": standard_deviation,
        "variance": variance,
        "minimum": float(clean.min()),
        "maximum": float(clean.max()),
        "percentile_1": float(quantiles[0]),
        "percentile_5": float(quantiles[1]),
        "percentile_10": float(quantiles[2]),
        "percentile_25": float(quantiles[3]),
        "percentile_75": float(quantiles[4]),
        "percentile_90": float(quantiles[5]),
        "percentile_95": float(quantiles[6]),
        "percentile_99": float(quantiles[7]),
        "interquartile_range": float(quantiles[4] - quantiles[3]),
        "median_absolute_deviation": float(np.median(np.abs(clean - median))),
        "coefficient_of_variation": standard_deviation / mean
        if not np.isclose(mean, 0.0)
        else math.nan,
        "skewness": skewness,
        "excess_kurtosis": kurtosis,
        "mean_ci_lower": mean_ci[0],
        "mean_ci_upper": mean_ci[1],
        "median_ci_lower": median_ci[0],
        "median_ci_upper": median_ci[1],
        "proportion_above_full_sample_median": float(np.mean(clean > full_median)),
        "qq_plot_correlation": qq_correlation,
    }


def descriptive_table(
    frame: pd.DataFrame, config: Task04Config, profile: str, scope: str
) -> pd.DataFrame:
    """Build the complete weekday descriptive table."""
    full_median = float(frame["daily_range_pips"].median())
    records: list[dict[str, Any]] = []
    for weekday in WEEKDAYS:
        values = frame.loc[
            frame["weekday_name"].eq(weekday), "daily_range_pips"
        ].to_numpy(float)
        records.append(
            {
                "profile": profile,
                "analysis_scope": scope,
                "weekday_name": weekday,
                **descriptive_values(
                    values,
                    full_median=full_median,
                    label=f"{profile}:{scope}:{weekday}",
                    config=config,
                ),
                "study_date_start": frame["utc_date"].min(),
                "study_date_end": frame["utc_date"].max(),
            }
        )
    return pd.DataFrame(records)


def _groups(frame: pd.DataFrame) -> tuple[list[str], list[np.ndarray]]:
    names: list[str] = []
    groups: list[np.ndarray] = []
    for weekday in WEEKDAYS:
        values = (
            frame.loc[frame["weekday_name"].eq(weekday), "daily_range_pips"]
            .dropna()
            .to_numpy(float)
        )
        if values.size:
            names.append(weekday)
            groups.append(values)
    return names, groups


def _epsilon(statistic: float, sample_size: int, group_count: int) -> float:
    return float(
        np.clip((statistic - group_count + 1) / (sample_size - group_count), 0.0, 1.0)
    )


def _anova_effects(groups: Sequence[np.ndarray]) -> tuple[float, float]:
    pooled = np.concatenate(groups)
    grand = float(pooled.mean())
    between = sum(len(group) * (float(group.mean()) - grand) ** 2 for group in groups)
    within = sum(float(np.sum((group - group.mean()) ** 2)) for group in groups)
    total = between + within
    mse = within / (len(pooled) - len(groups))
    eta = between / total if total else 0.0
    omega = (between - (len(groups) - 1) * mse) / (total + mse) if total + mse else 0.0
    return float(np.clip(eta, 0.0, 1.0)), float(np.clip(omega, 0.0, 1.0))


def omnibus_table(
    frame: pd.DataFrame, config: Task04Config, profile: str, scope: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Independently calculate registered omnibus tests and effect sizes."""
    names, groups = _groups(frame)
    if len(groups) < 2:
        raise ValueError("Independent omnibus analysis needs at least two groups")
    same = all(np.all(group == groups[0][0]) for group in groups)
    kruskal_h, kruskal_p = (0.0, 1.0) if same else stats.kruskal(*groups)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        anova = stats.f_oneway(*groups)
        welch = anova_oneway(groups, use_var="unequal")
        brown = stats.levene(*groups, center="median")
    n, k = sum(map(len, groups)), len(groups)
    tests = (
        (
            "kruskal_wallis",
            "primary",
            float(kruskal_h),
            float(kruskal_p),
            k - 1,
            math.nan,
        ),
        (
            "one_way_anova",
            "complementary",
            float(np.nan_to_num(anova.statistic)),
            float(np.nan_to_num(anova.pvalue, nan=1.0)),
            k - 1,
            n - k,
        ),
        (
            "welch_anova",
            "complementary",
            float(np.nan_to_num(welch.statistic)),
            float(np.nan_to_num(welch.pvalue, nan=1.0)),
            float(welch.df_num),
            float(welch.df_denom),
        ),
        (
            "brown_forsythe_levene",
            "diagnostic",
            float(np.nan_to_num(brown.statistic)),
            float(np.nan_to_num(brown.pvalue, nan=1.0)),
            k - 1,
            n - k,
        ),
    )
    test_frame = pd.DataFrame(
        [
            {
                "profile": profile,
                "analysis_scope": scope,
                "test_name": name,
                "test_role": role,
                "statistic": statistic,
                "p_value": p_value,
                "numerator_degrees_of_freedom": df_num,
                "denominator_degrees_of_freedom": df_den,
                "sample_size": n,
                "group_count": k,
                "groups_present": "|".join(names),
                "significant": bool(p_value < config.alpha),
            }
            for name, role, statistic, p_value, df_num, df_den in tests
        ]
    )
    eta, omega = _anova_effects(groups)
    effect_frame = pd.DataFrame(
        [
            {
                "profile": profile,
                "analysis_scope": scope,
                "comparison": "Monday-Friday",
                "effect_size_method": method,
                "effect_size": value,
                "sample_size": n,
            }
            for method, value in (
                ("epsilon_squared", _epsilon(float(kruskal_h), n, k)),
                ("eta_squared", eta),
                ("omega_squared", omega),
            )
        ]
    )
    return test_frame, effect_frame


def holm_adjust(values: Sequence[float]) -> np.ndarray:
    """Stable Holm adjustment, including equal p-values."""
    raw = np.asarray(values, dtype=float)
    order = np.argsort(raw, kind="stable")
    adjusted_sorted = np.empty(raw.size)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (raw.size - rank) * raw[index])
        adjusted_sorted[rank] = min(running, 1.0)
    adjusted = np.empty(raw.size)
    adjusted[order] = adjusted_sorted
    return adjusted


def _dunn(
    groups: Sequence[np.ndarray], pairs: Sequence[tuple[int, int]]
) -> list[float]:
    pooled = np.concatenate(groups)
    ranks = stats.rankdata(pooled, method="average")
    counts = np.asarray([len(group) for group in groups])
    ends = np.cumsum(counts)
    starts = np.r_[0, ends[:-1]].astype(int)
    mean_ranks = [
        float(ranks[int(start) : int(end)].mean())
        for start, end in zip(starts, ends, strict=True)
    ]
    _, ties = np.unique(pooled, return_counts=True)
    variance = pooled.size * (pooled.size + 1) / 12.0
    if pooled.size > 1:
        variance -= float(np.sum(ties**3 - ties)) / (12.0 * (pooled.size - 1))
    values: list[float] = []
    for first, second in pairs:
        standard_error = math.sqrt(variance * (1 / counts[first] + 1 / counts[second]))
        if np.isclose(standard_error, 0.0):
            values.append(1.0)
        else:
            z_value = (mean_ranks[first] - mean_ranks[second]) / standard_error
            values.append(float(2.0 * stats.norm.sf(abs(z_value))))
    return values


def _magnitude(delta: float) -> str:
    absolute = abs(delta)
    return (
        "negligible"
        if absolute < 0.147
        else "small"
        if absolute < 0.330
        else "medium"
        if absolute < 0.474
        else "large"
    )


def pairwise_table(
    frame: pd.DataFrame, config: Task04Config, profile: str, scope: str
) -> pd.DataFrame:
    """Independently calculate all registered weekday pairs."""
    names, groups = _groups(frame)
    if names != list(WEEKDAYS):
        raise ValueError("Independent pairwise analysis requires all weekdays")
    pairs = list(itertools.combinations(range(5), 2))
    raw = _dunn(groups, pairs)
    adjusted = holm_adjust(raw)
    records: list[dict[str, Any]] = []
    for position, (first, second) in enumerate(pairs):
        a, b = groups[first], groups[second]
        generator = np.random.default_rng(
            derived_seed(
                config.bootstrap_seed,
                f"{profile}:{scope}:{names[first]}:{names[second]}",
            )
        )
        bootstrap = np.empty(config.bootstrap_resamples)
        for index in range(config.bootstrap_resamples):
            aa = a[generator.integers(0, a.size, a.size)]
            bb = b[generator.integers(0, b.size, b.size)]
            bootstrap[index] = np.median(aa) - np.median(bb)
        tail = (1.0 - config.confidence_level) / 2.0
        ci = np.quantile(bootstrap, [tail, 1.0 - tail], method="linear")
        u_value = stats.mannwhitneyu(
            a, b, alternative="two-sided", method="asymptotic"
        ).statistic
        delta = float(2.0 * u_value / (a.size * b.size) - 1.0)
        median_difference = float(np.median(a) - np.median(b))
        records.append(
            {
                "profile": profile,
                "analysis_scope": scope,
                "weekday_a": names[first],
                "weekday_b": names[second],
                "sample_size_a": a.size,
                "sample_size_b": b.size,
                "median_a": float(np.median(a)),
                "median_b": float(np.median(b)),
                "median_difference_a_minus_b": median_difference,
                "mean_difference_a_minus_b": float(np.mean(a) - np.mean(b)),
                "relative_median_difference": median_difference / float(np.median(b)),
                "unadjusted_p_value": raw[position],
                "holm_adjusted_p_value": float(adjusted[position]),
                "significant": bool(adjusted[position] < config.alpha),
                "cliffs_delta_a_minus_b": delta,
                "effect_size_magnitude": _magnitude(delta),
                "effect_direction": f"{names[first]}>{names[second]}"
                if delta > 0
                else f"{names[first]}<{names[second]}"
                if delta < 0
                else "no_direction",
                "median_difference_ci_lower": float(ci[0]),
                "median_difference_ci_upper": float(ci[1]),
                "study_date_start": frame["utc_date"].min(),
                "study_date_end": frame["utc_date"].max(),
            }
        )
    return pd.DataFrame(records)


def weekday_order(frame: pd.DataFrame) -> tuple[str, ...]:
    """Return median-descending order with calendar tie-breaking."""
    medians = frame.groupby("weekday_name")["daily_range_pips"].median()
    return tuple(
        sorted(
            medians.index,
            key=lambda day: (-float(medians[day]), WEEKDAYS.index(str(day))),
        )
    )


def rank_correlation(first: tuple[str, ...], second: tuple[str, ...]) -> float:
    """Spearman agreement for common weekday orderings."""
    common = [day for day in first if day in second]
    if len(common) < 2:
        return math.nan
    return float(
        stats.spearmanr(
            [first.index(day) for day in common], [second.index(day) for day in common]
        ).statistic
    )
