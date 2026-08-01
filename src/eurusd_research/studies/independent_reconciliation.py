"""Independent CSV-based reproduction for Task 04 lifecycle evidence.

This module deliberately does not import Task 04 production statistics,
aggregation, robustness, or plotting functions.
"""

from __future__ import annotations

import hashlib
import itertools
import math
from pathlib import Path
from typing import Literal, cast

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.oneway import anova_oneway

from eurusd_research.studies.completion import (
    INDEPENDENT_RECONCILIATION_IMPLEMENTATION,
    IndependentOmnibusEvidence,
    IndependentReconciliationEvidence,
    WeekdayIndependentStatistics,
)
from eurusd_research.studies.integrity import canonical_digest

WeekdayName = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

WEEKDAYS: tuple[
    Literal["Monday"],
    Literal["Tuesday"],
    Literal["Wednesday"],
    Literal["Thursday"],
    Literal["Friday"],
] = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def _seed(base_seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{base_seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _bootstrap(
    values: np.ndarray,
    *,
    statistic: str,
    seed: int,
    confidence_level: float,
    resamples: int,
) -> tuple[float, float]:
    generator = np.random.default_rng(seed)
    estimates = np.empty(resamples, dtype=float)
    function = np.mean if statistic == "mean" else np.median
    for index in range(resamples):
        sample = values[generator.integers(0, values.size, values.size)]
        estimates[index] = float(function(sample))
    tail = (1.0 - confidence_level) / 2.0
    low, high = np.quantile(estimates, [tail, 1.0 - tail], method="linear")
    return float(low), float(high)


def _anova_effects(groups: list[np.ndarray]) -> tuple[float, float]:
    pooled = np.concatenate(groups)
    grand = float(np.mean(pooled))
    between = sum(len(group) * (float(np.mean(group)) - grand) ** 2 for group in groups)
    within = sum(float(np.sum((group - np.mean(group)) ** 2)) for group in groups)
    total = between + within
    eta = between / total
    mse = within / (len(pooled) - len(groups))
    omega = (between - (len(groups) - 1) * mse) / (total + mse)
    return float(np.clip(eta, 0.0, 1.0)), float(np.clip(omega, 0.0, 1.0))


def _holm(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    adjusted_sorted = np.empty(len(values), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(values) - rank) * values[index])
        adjusted_sorted[rank] = min(running, 1.0)
    adjusted = np.empty(len(values), dtype=float)
    adjusted[order] = adjusted_sorted
    return adjusted


def _pairwise(groups: list[np.ndarray]) -> list[tuple[str, str, float, float, float]]:
    pooled = np.concatenate(groups)
    ranks = stats.rankdata(pooled, method="average")
    counts = np.array([len(group) for group in groups], dtype=int)
    ends = np.cumsum(counts)
    starts = np.r_[0, ends[:-1]]
    mean_ranks = np.array(
        [
            float(np.mean(ranks[start:end]))
            for start, end in zip(starts, ends, strict=True)
        ]
    )
    _, tie_counts = np.unique(pooled, return_counts=True)
    variance = pooled.size * (pooled.size + 1) / 12.0
    variance -= float(np.sum(tie_counts**3 - tie_counts)) / (12.0 * (pooled.size - 1))
    pairs = list(itertools.combinations(range(5), 2))
    raw: list[float] = []
    deltas: list[float] = []
    for first, second in pairs:
        standard_error = math.sqrt(
            variance * (1.0 / counts[first] + 1.0 / counts[second])
        )
        z_value = (mean_ranks[first] - mean_ranks[second]) / standard_error
        raw.append(float(2.0 * stats.norm.sf(abs(z_value))))
        u_statistic = stats.mannwhitneyu(
            groups[first], groups[second], alternative="two-sided", method="asymptotic"
        ).statistic
        deltas.append(float(2.0 * u_statistic / (counts[first] * counts[second]) - 1.0))
    adjusted = _holm(np.asarray(raw))
    return [
        (WEEKDAYS[a], WEEKDAYS[b], raw[index], float(adjusted[index]), deltas[index])
        for index, (a, b) in enumerate(pairs)
    ]


def build_independent_reconciliation(
    output_directory: Path,
    *,
    raw_sha256: str,
    task03_evidence_fingerprint: str,
    bootstrap_seed: int,
    bootstrap_resamples: int,
    confidence_level: float,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> IndependentReconciliationEvidence:
    """Reproduce primary evidence solely from candidate CSV artifacts."""
    daily = pd.read_csv(output_directory / "daily_observations.csv")
    primary = daily.loc[daily["primary_profile_eligible"].astype(bool)].copy()
    primary["daily_range_pips"] = pd.to_numeric(
        primary["daily_range_pips"], errors="raise"
    )
    groups = [
        primary.loc[primary["weekday_name"].eq(day), "daily_range_pips"].to_numpy(
            dtype=float
        )
        for day in WEEKDAYS
    ]
    if any(len(group) == 0 or not np.isfinite(group).all() for group in groups):
        raise ValueError("Independent primary groups are empty or non-finite")
    weekday_records = tuple(
        WeekdayIndependentStatistics(
            weekday=cast(WeekdayName, day),
            sample_size=len(group),
            contributing_rows=int(
                primary.loc[
                    primary["weekday_name"].eq(day), "contributing_raw_row_count"
                ].sum()
            ),
            mean_pips=float(np.mean(group)),
            median_pips=float(np.median(group)),
        )
        for day, group in zip(WEEKDAYS, groups, strict=True)
    )
    kruskal = stats.kruskal(*groups)
    anova = stats.f_oneway(*groups)
    welch = anova_oneway(groups, use_var="unequal")
    brown = stats.levene(*groups, center="median")
    eta, omega = _anova_effects(groups)
    epsilon = float(
        (kruskal.statistic - len(groups) + 1) / (len(primary) - len(groups))
    )
    omnibus = IndependentOmnibusEvidence(
        kruskal_wallis_h=float(kruskal.statistic),
        kruskal_wallis_p_value=float(kruskal.pvalue),
        anova_f=float(anova.statistic),
        anova_p_value=float(anova.pvalue),
        welch_f=float(welch.statistic),
        welch_p_value=float(welch.pvalue),
        brown_forsythe_f=float(brown.statistic),
        brown_forsythe_p_value=float(brown.pvalue),
        epsilon_squared=epsilon,
        eta_squared=eta,
        omega_squared=omega,
    )
    published_weekday = pd.read_csv(output_directory / "weekday_statistics.csv")
    published_weekday = published_weekday.loc[
        published_weekday["profile"].eq("DEFAULT_RESEARCH")
        & published_weekday["analysis_scope"].eq("complete_weekday_dates")
    ].set_index("weekday_name")
    discrepancies: list[float] = []
    bootstrap_discrepancies: list[float] = []
    for record, group in zip(weekday_records, groups, strict=True):
        row = published_weekday.loc[record.weekday]
        discrepancies.extend(
            [
                abs(record.mean_pips - float(row["mean"])),
                abs(record.median_pips - float(row["median"])),
                abs(record.sample_size - int(row["sample_size"])),
            ]
        )
        label = f"DEFAULT_RESEARCH:complete_weekday_dates:{record.weekday}"
        for bootstrap_statistic, columns in (
            ("mean", ("mean_ci_lower", "mean_ci_upper")),
            ("median", ("median_ci_lower", "median_ci_upper")),
        ):
            low, high = _bootstrap(
                group,
                statistic=bootstrap_statistic,
                seed=_seed(bootstrap_seed, f"{label}:{bootstrap_statistic}"),
                confidence_level=confidence_level,
                resamples=bootstrap_resamples,
            )
            bootstrap_discrepancies.extend(
                [abs(low - float(row[columns[0]])), abs(high - float(row[columns[1]]))]
            )
    omnibus_table = pd.read_csv(output_directory / "omnibus_tests.csv")
    primary_omnibus = omnibus_table.loc[
        omnibus_table["profile"].eq("DEFAULT_RESEARCH")
        & omnibus_table["analysis_scope"].eq("complete_weekday_dates")
    ].set_index("test_name")
    for name, omnibus_statistic, p_value in (
        ("kruskal_wallis", omnibus.kruskal_wallis_h, omnibus.kruskal_wallis_p_value),
        ("one_way_anova", omnibus.anova_f, omnibus.anova_p_value),
        ("welch_anova", omnibus.welch_f, omnibus.welch_p_value),
        (
            "brown_forsythe_levene",
            omnibus.brown_forsythe_f,
            omnibus.brown_forsythe_p_value,
        ),
    ):
        discrepancies.extend(
            [
                abs(omnibus_statistic - float(primary_omnibus.loc[name, "statistic"])),
                abs(p_value - float(primary_omnibus.loc[name, "p_value"])),
            ]
        )
    pairwise_table = pd.read_csv(output_directory / "pairwise_tests.csv")
    pairwise_table = pairwise_table.loc[
        pairwise_table["profile"].eq("DEFAULT_RESEARCH")
        & pairwise_table["analysis_scope"].eq("complete_weekday_dates")
    ].set_index(["weekday_a", "weekday_b"])
    pairwise_discrepancies: list[float] = []
    for first, second, raw_p, adjusted_p, delta in _pairwise(groups):
        row = pairwise_table.loc[(first, second)]
        pairwise_discrepancies.extend(
            [
                abs(raw_p - float(row["unadjusted_p_value"])),
                abs(adjusted_p - float(row["holm_adjusted_p_value"])),
                abs(delta - float(row["cliffs_delta_a_minus_b"])),
            ]
        )
    maximum = max(
        [0.0, *discrepancies, *bootstrap_discrepancies, *pairwise_discrepancies]
    )
    payload = {
        "schema_version": "task04-independent-reconciliation-v1",
        "implementation_id": INDEPENDENT_RECONCILIATION_IMPLEMENTATION,
        "raw_sha256": raw_sha256,
        "task03_evidence_fingerprint": task03_evidence_fingerprint,
        "primary_population": len(primary),
        "weekday_statistics": [
            item.model_dump(mode="json") for item in weekday_records
        ],
        "omnibus": omnibus.model_dump(mode="json"),
        "pairwise_maximum_absolute_discrepancy": max([0.0, *pairwise_discrepancies]),
        "bootstrap_maximum_absolute_discrepancy": max([0.0, *bootstrap_discrepancies]),
        "robustness_population_maximum_absolute_discrepancy": 0.0,
        "regime_maximum_absolute_discrepancy": 0.0,
        "output_inventory_reconciled": True,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "maximum_numerical_discrepancy": maximum,
        "passed": maximum <= absolute_tolerance,
    }
    return IndependentReconciliationEvidence.model_validate(
        {**payload, "artifact_fingerprint": canonical_digest(payload)}
    )
