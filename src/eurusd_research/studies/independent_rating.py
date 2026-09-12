"""Result-independent reconstruction of the registered Task 04 evidence rating."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from eurusd_research.studies.configuration import Task04Config
from eurusd_research.studies.independent_statistics import WEEKDAYS, rank_correlation


@dataclass(frozen=True, slots=True)
class RatingDecision:
    """One traceable registered rating dimension."""

    dimension: str
    registered_threshold: str
    independent_input: str
    passed: bool
    effect_on_rating: str
    missing_evidence_rule: str = "INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class IndependentRating:
    """Independent rating result and its dimension-by-dimension decisions."""

    rating: str
    uncapped_rating: str
    cap: str
    decisions: tuple[RatingDecision, ...]
    missing_evidence: tuple[str, ...]
    production_summary: dict[str, Any]


def reconstruct_rating(
    *,
    coverage: pd.DataFrame,
    weekday: pd.DataFrame,
    periods: pd.DataFrame,
    annual: pd.DataFrame,
    regime_statistics: pd.DataFrame,
    regime_tests: pd.DataFrame,
    extreme: pd.DataFrame,
    config: Task04Config,
) -> IndependentRating:
    """Evaluate every registered rating dimension without production code."""
    required = {
        "coverage": coverage,
        "weekday": weekday,
        "periods": periods,
        "annual": annual,
        "regime_statistics": regime_statistics,
        "regime_tests": regime_tests,
        "extreme": extreme,
    }
    missing = tuple(sorted(name for name, table in required.items() if table.empty))
    if missing:
        return IndependentRating(
            "INSUFFICIENT", "INSUFFICIENT", "MODERATE", (), missing, {}
        )
    primary = coverage.loc[coverage["profile"].eq(config.primary_coverage_profile)]
    primary_stats = weekday.loc[weekday["profile"].eq(config.primary_coverage_profile)]
    sufficient_years = annual.loc[annual["sufficient_for_inference"]]
    primary_regime = regime_tests.loc[regime_tests["test_name"].eq("kruskal_wallis")]
    required_sets = (
        (
            "coverage profiles",
            set(coverage["profile"]),
            {
                config.primary_coverage_profile,
                "STRICT_CONTINUITY",
                "SENSITIVITY_FULL",
                "SENSITIVITY_2023",
            },
        ),
        ("weekdays", set(primary_stats["weekday_name"]), set(WEEKDAYS)),
        (
            "periods",
            set(periods["analysis_period"]),
            {
                "full_eligible_sample",
                "pre_2020",
                "covid_era",
                "post_2021",
                "development_70",
                "validation_30",
            },
        ),
        (
            "regimes",
            set(primary_regime["volatility_regime"]),
            {"LOW", "MEDIUM", "HIGH"},
        ),
    )
    missing_structure = [
        name
        for name, actual, expected in required_sets
        if not expected.issubset(actual)
    ]
    numeric_tables = (
        (primary, ("kruskal_p_value", "epsilon_squared")),
        (
            primary_stats,
            ("sample_size", "median", "median_ci_lower", "median_ci_upper"),
        ),
        (periods, ("rank_correlation_with_full", "kruskal_p_value")),
        (sufficient_years, ("kruskal_p_value", "epsilon_squared")),
        (regime_statistics, ("sample_size", "median")),
        (primary_regime, ("sample_size", "statistic", "p_value")),
        (extreme, ("rank_correlation_with_primary", "kruskal_p_value")),
    )
    nonfinite = []
    for table, columns in numeric_tables:
        if table.empty or any(column not in table for column in columns):
            nonfinite.append("missing numeric evidence")
        elif not np.isfinite(table.loc[:, list(columns)].to_numpy(float)).all():
            nonfinite.append("non-finite numeric evidence")
    if missing_structure or nonfinite or sufficient_years.empty:
        errors_set = {*missing_structure, *nonfinite}
        if sufficient_years.empty:
            errors_set.add("sufficient years")
        errors = tuple(sorted(errors_set))
        return IndependentRating(
            "INSUFFICIENT", "INSUFFICIENT", "MODERATE", (), errors, {}
        )
    if (
        primary_regime["sample_size"] < config.evidence_rating.minimum_regime_sample
    ).any():
        return IndependentRating(
            "INSUFFICIENT",
            "INSUFFICIENT",
            "MODERATE",
            (),
            ("insufficient regime population",),
            {},
        )
    primary_row = primary.iloc[0]
    period_index = periods.set_index("analysis_period")
    development = tuple(
        str(period_index.loc["development_70", "weekday_order_high_to_low"]).split("|")
    )
    validation = tuple(
        str(period_index.loc["validation_30", "weekday_order_high_to_low"]).split("|")
    )
    validation_agreement = rank_correlation(development, validation)
    strict_agreement = float(
        coverage.set_index("profile").loc[
            "STRICT_CONTINUITY", "rank_correlation_with_primary"
        ]
    )
    extreme_agreement = float(
        extreme.loc[
            ~extreme["analysis_variant"].eq("primary_raw_distribution"),
            "rank_correlation_with_primary",
        ].min()
    )
    widths = (
        primary_stats["median_ci_upper"] - primary_stats["median_ci_lower"]
    ) / primary_stats["median"].abs()
    maximum_width = float(widths.max())
    minimum_n = int(primary_stats["sample_size"].min())
    thresholds = config.evidence_rating
    moderate_values = (
        (
            "primary_significance",
            config.alpha,
            float(primary_row["kruskal_p_value"]),
            float(primary_row["kruskal_p_value"]) < config.alpha,
        ),
        (
            "primary_effect_magnitude",
            thresholds.moderate_minimum_epsilon_squared,
            float(primary_row["epsilon_squared"]),
            float(primary_row["epsilon_squared"])
            >= thresholds.moderate_minimum_epsilon_squared,
        ),
        (
            "ci_precision",
            thresholds.moderate_maximum_median_ci_relative_width,
            maximum_width,
            maximum_width <= thresholds.moderate_maximum_median_ci_relative_width,
        ),
        (
            "primary_sample",
            thresholds.minimum_primary_weekday_sample,
            minimum_n,
            minimum_n >= thresholds.minimum_primary_weekday_sample,
        ),
        (
            "chronological_validation",
            thresholds.minimum_rank_correlation,
            validation_agreement,
            validation_agreement >= thresholds.minimum_rank_correlation,
        ),
        (
            "required_profile_concordance",
            thresholds.minimum_rank_correlation,
            strict_agreement,
            strict_agreement >= thresholds.minimum_rank_correlation,
        ),
        (
            "extreme_event_stability",
            thresholds.minimum_rank_correlation,
            extreme_agreement,
            extreme_agreement >= thresholds.minimum_rank_correlation,
        ),
    )
    decisions = [
        RatingDecision(
            name, str(threshold), str(value), passed, "required for MODERATE"
        )
        for name, threshold, value, passed in moderate_values
    ]
    full_order = tuple(str(primary_row["weekday_order_high_to_low"]).split("|"))
    stable_year_fraction = float(
        np.mean(
            [
                rank_correlation(full_order, tuple(str(order).split("|")))
                >= thresholds.minimum_rank_correlation
                for order in sufficient_years["weekday_order_high_to_low"]
            ]
        )
    )
    fixed_minimum = float(
        period_index.loc[
            ["pre_2020", "covid_era", "post_2021"], "rank_correlation_with_full"
        ].min()
    )
    regime_orders = []
    for _, selected in regime_statistics.groupby("volatility_regime", sort=False):
        medians = selected.set_index("weekday_name")["median"]
        regime_orders.append(
            tuple(
                sorted(
                    WEEKDAYS,
                    key=lambda day: (-float(medians[day]), WEEKDAYS.index(day)),
                )
            )
        )
    regime_minimum = min(rank_correlation(full_order, order) for order in regime_orders)
    diagnostic = coverage.loc[
        coverage["profile"].isin(["SENSITIVITY_FULL", "SENSITIVITY_2023"]),
        "rank_correlation_with_primary",
    ].fillna(1.0)
    strong_values = (
        (
            "strong_effect",
            thresholds.strong_minimum_epsilon_squared,
            float(primary_row["epsilon_squared"]),
            float(primary_row["epsilon_squared"])
            >= thresholds.strong_minimum_epsilon_squared,
        ),
        (
            "strong_ci_precision",
            thresholds.strong_maximum_median_ci_relative_width,
            maximum_width,
            maximum_width <= thresholds.strong_maximum_median_ci_relative_width,
        ),
        (
            "annual_stability",
            thresholds.strong_minimum_stable_year_fraction,
            stable_year_fraction,
            stable_year_fraction >= thresholds.strong_minimum_stable_year_fraction,
        ),
        (
            "fixed_period_stability",
            thresholds.minimum_rank_correlation,
            fixed_minimum,
            fixed_minimum >= thresholds.minimum_rank_correlation,
        ),
        (
            "regime_stability",
            thresholds.minimum_rank_correlation,
            regime_minimum,
            regime_minimum >= thresholds.minimum_rank_correlation,
        ),
        (
            "diagnostic_profile_evidence",
            thresholds.minimum_rank_correlation,
            float(diagnostic.min()),
            bool((diagnostic >= thresholds.minimum_rank_correlation).all()),
        ),
    )
    decisions.extend(
        RatingDecision(name, str(threshold), str(value), passed, "required for STRONG")
        for name, threshold, value, passed in strong_values
    )
    moderate_pass = all(
        item.passed
        for item in decisions
        if item.effect_on_rating == "required for MODERATE"
    )
    strong_pass = all(
        item.passed
        for item in decisions
        if item.effect_on_rating == "required for STRONG"
    )
    uncapped = (
        "STRONG"
        if moderate_pass and strong_pass
        else "MODERATE"
        if moderate_pass
        else "WEAK"
    )
    order = ("INSUFFICIENT", "WEAK", "MODERATE", "STRONG")
    cap = thresholds.unresolved_timestamp_semantics_maximum_rating
    rating = (
        cap
        if config.timestamp_semantics_status == "UNRESOLVED"
        and order.index(uncapped) > order.index(cap)
        else uncapped
    )
    decisions.append(
        RatingDecision(
            "timestamp_resolution",
            cap,
            config.timestamp_semantics_status,
            config.timestamp_semantics_status != "UNRESOLVED",
            "caps maximum rating",
        )
    )
    moderate_checks = {
        "primary_significant": moderate_values[0][3],
        "epsilon_squared_meets_moderate_threshold": moderate_values[1][3],
        "median_ci_precision_meets_moderate_threshold": moderate_values[2][3],
        "primary_group_sample_sufficient": moderate_values[3][3],
        "development_validation_rank_correlation_sufficient": moderate_values[4][3],
        "strict_continuity_direction_concordant": moderate_values[5][3],
        "extreme_sensitivity_does_not_reverse_order": moderate_values[6][3],
    }
    development_significant = bool(
        period_index.loc["development_70", "kruskal_p_value"] < config.alpha
    )
    validation_significant = bool(
        period_index.loc["validation_30", "kruskal_p_value"] < config.alpha
    )
    required_profile_concordance = bool(
        strict_agreement >= thresholds.minimum_rank_correlation
    )
    diagnostic_profile_concordance = bool(
        (diagnostic >= thresholds.minimum_rank_correlation).all()
    )
    fixed_correlations = [
        float(period_index.loc[name, "rank_correlation_with_full"])
        for name in ("pre_2020", "covid_era", "post_2021")
    ]
    regime_correlations = [
        rank_correlation(full_order, order) for order in regime_orders
    ]
    strong_checks = {
        "epsilon_squared_meets_strong_threshold": strong_values[0][3],
        "development_significant": development_significant,
        "validation_significant": validation_significant,
        "median_ci_precision_meets_strong_threshold": strong_values[1][3],
        "sufficient_year_stability_meets_threshold": strong_values[2][3],
        "all_fixed_periods_directionally_stable": strong_values[3][3],
        "all_regimes_directionally_stable": strong_values[4][3],
        "required_coverage_profiles_directionally_concordant": (
            required_profile_concordance
        ),
        "timestamp_semantics_resolved": config.timestamp_semantics_status
        != "UNRESOLVED",
    }
    if thresholds.diagnostic_profile_disagreement_blocks_strong:
        strong_checks["diagnostic_coverage_profiles_directionally_concordant"] = (
            diagnostic_profile_concordance
        )
    summary: dict[str, Any] = {
        "rating": rating,
        "moderate_checks": moderate_checks,
        "strong_checks": strong_checks,
        "development_validation_rank_correlation": validation_agreement,
        "sufficient_year_stable_fraction": stable_year_fraction,
        "fixed_period_rank_correlations": fixed_correlations,
        "regime_rank_correlations": regime_correlations,
        "extreme_event_minimum_rank_correlation": extreme_agreement,
        "maximum_primary_median_ci_relative_width": maximum_width,
        "minimum_primary_weekday_sample": minimum_n,
        "required_profile_concordance": required_profile_concordance,
        "diagnostic_profile_concordance": diagnostic_profile_concordance,
        "diagnostic_profile_disagreement_blocks_strong": (
            thresholds.diagnostic_profile_disagreement_blocks_strong
        ),
        "high_regime_significance_role": thresholds.high_regime_significance_role,
        "high_regime_kruskal_p_value": float(
            primary_regime.set_index("volatility_regime").loc["HIGH", "p_value"]
        ),
        "timestamp_semantics_status": config.timestamp_semantics_status,
        "timestamp_semantics_rating_cap": cap,
        "thresholds": thresholds.model_dump(mode="json"),
        "logic_source": "studies/task04_daily_range_weekday.yaml",
    }
    return IndependentRating(rating, uncapped, cap, tuple(decisions), (), summary)
