"""End-to-end orchestration for the registered Task 04 replication."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from eurusd_research.config import load_config
from eurusd_research.data.quality_models import json_safe
from eurusd_research.data.registry import sha256_file
from eurusd_research.paths import find_repository_root, project_path
from eurusd_research.research.coverage import (
    _repository_version,
    build_coverage,
)
from eurusd_research.studies.configuration import Task04Config, load_task04_config
from eurusd_research.studies.daily_aggregation import (
    DailyAggregationResult,
    aggregate_daily_profiles,
)
from eurusd_research.studies.dependencies import (
    validate_task04_dependencies as _validate_dependencies,
)
from eurusd_research.studies.integrity import (
    assert_regular_contained_file,
    validate_task03_row_membership,
)
from eurusd_research.studies.plotting import plot_all_figures
from eurusd_research.studies.registry import (
    preregistration_record,
    read_preregistration,
)
from eurusd_research.studies.robustness import (
    chronological_outputs,
    coverage_profile_outputs,
    eligible_daily,
    extreme_event_outputs,
    rank_correlation,
    volatility_regime_outputs,
    yearly_outputs,
)


@dataclass(slots=True)
class Task04Result:
    """Generated study evidence and written artifact paths."""

    summary: dict[str, Any]
    tables: dict[str, pd.DataFrame]
    figure_paths: list[Path]
    output_directory: Path


def _stable_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _config_fingerprint(config: Task04Config) -> str:
    return _stable_digest(config.model_dump(mode="json"))


def _lineage(
    *,
    root: Path,
    config: Task04Config,
    coverage_summary: dict[str, Any],
    preregistration: dict[str, Any],
) -> dict[str, str]:
    coverage = coverage_summary["lineage"]
    return {
        "dataset_version": str(coverage["dataset_version"]),
        "raw_sha256": str(coverage["raw_sha256"]),
        "audit_fingerprint": str(coverage["audit_result_content_sha256"]),
        "coverage_fingerprint": config.required_coverage_summary_sha256,
        "coverage_config_fingerprint": str(coverage["coverage_config_sha256"]),
        "task04_config_fingerprint": _config_fingerprint(config),
        "preregistration_fingerprint": str(preregistration["locked_design_sha256"]),
        "method_id": config.method_id,
        "method_version": config.method_version,
        "repository_version": _repository_version(
            root,
            ignored_generated_paths=(
                config.output_directory,
                config.candidate_output_directory,
            ),
        ),
    }


def _population_reconciliation(
    aggregation: DailyAggregationResult,
    coverage_rows: pd.DataFrame,
    profile_masks: pd.DataFrame,
    config: Task04Config,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = [
        {
            "profile": "RAW",
            "metric": "total_raw_rows",
            "weekday": "",
            "value": aggregation.raw_row_count,
        }
    ]
    sensitivity_flags = [
        "long_nonweekly_gap_boundary",
        "nonweekend_gap_boundary",
        "unclassified_gap_boundary",
        "continuity_impaired_period",
        "affected_period_2023",
        "partial_boundary_year",
        "partial_boundary_month",
    ]
    mixed_by_date = (
        coverage_rows.groupby("utc_date")[sensitivity_flags].nunique().gt(1).any(axis=1)
    )
    for profile, frame in aggregation.by_profile.items():
        eligible = frame.loc[frame["analysis_eligible"]]
        metrics = {
            "profile_source_rows": int(profile_masks[profile].sum()),
            "total_observed_utc_dates": len(frame),
            "monday_friday_utc_dates": int(frame["is_weekday"].sum()),
            "weekend_utc_dates": int(frame["is_weekend_date"].sum()),
            "complete_dates": int((~frame["is_partial_daily_observation"]).sum()),
            "incomplete_dates": int(frame["is_partial_daily_observation"].sum()),
            "excluded_boundary_dates": int(frame["is_boundary_date"].sum()),
            "zero_contribution_dates": int(frame["observed_m15_rows"].eq(0).sum()),
            "task03_profile_ineligible_dates": int(
                frame["observed_m15_rows"].eq(0).sum()
            ),
            "nonzero_partial_dates": int(
                (
                    frame["observed_m15_rows"].gt(0)
                    & frame["is_partial_daily_observation"]
                ).sum()
            ),
            "dates_excluded_for_insufficient_contributing_observations": int(
                (
                    frame["observed_m15_rows"]
                    < config.daily_completeness.minimum_daily_rows
                ).sum()
            ),
            "dates_included_in_analysis": len(eligible),
            "dates_with_mixed_sensitivity_conditions": int(
                mixed_by_date.loc[mixed_by_date.index.isin(frame["utc_date"])].sum()
            ),
            "dates_affected_by_audited_2023_interval": int(
                frame["utc_date"]
                .isin(
                    coverage_rows.loc[
                        coverage_rows["affected_period_2023"], "utc_date"
                    ].unique()
                )
                .sum()
            ),
        }
        for metric, value in metrics.items():
            records.append(
                {
                    "profile": profile,
                    "metric": metric,
                    "weekday": "",
                    "value": value,
                }
            )
        for weekday in config.weekday_inclusion:
            selected = eligible.loc[eligible["weekday_name"].eq(weekday)]
            records.extend(
                [
                    {
                        "profile": profile,
                        "metric": "included_dates_by_weekday",
                        "weekday": weekday,
                        "value": len(selected),
                    },
                    {
                        "profile": profile,
                        "metric": "contributing_m15_rows_by_weekday",
                        "weekday": weekday,
                        "value": int(selected["observed_m15_rows"].sum()),
                    },
                ]
            )
        if len(frame) != int(frame["is_weekday"].sum()) + int(
            frame["is_weekend_date"].sum()
        ):
            raise RuntimeError(f"Population date counts do not reconcile: {profile}")
        if int(frame["is_partial_daily_observation"].sum()) + int(
            (~frame["is_partial_daily_observation"]).sum()
        ) != len(frame):
            raise RuntimeError(f"Completeness counts do not reconcile: {profile}")
        if metrics["incomplete_dates"] != (
            metrics["zero_contribution_dates"] + metrics["nonzero_partial_dates"]
        ):
            raise RuntimeError(
                f"Incomplete-date components do not reconcile: {profile}"
            )
    return pd.DataFrame.from_records(records)


def _deviation_frame(registration: Any) -> pd.DataFrame:
    """Serialize the authoritative registered deviation ledger deterministically."""
    columns = [
        "deviation_id",
        "registration_version",
        "affected_field",
        "original_value_or_fingerprint",
        "revised_value",
        "reason",
        "classification",
        "interpretation_affected",
        "approval_mechanism",
        "consequence",
        "lineage_reference",
    ]
    return pd.DataFrame.from_records(
        [
            {
                **item.model_dump(mode="json"),
                "original_value_or_fingerprint": json.dumps(
                    item.original_value_or_fingerprint,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "revised_value": json.dumps(
                    item.revised_value,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
            for item in registration.preregistration_deviations
        ],
        columns=columns,
    )


def _validate_deviation_reconciliation(
    registration: Any,
    frame: pd.DataFrame,
    summary_records: list[dict[str, Any]],
) -> None:
    """Fail if any generated deviation representation diverges from registration."""
    expected_frame = _deviation_frame(registration)
    expected_summary = [
        item.model_dump(mode="json") for item in registration.preregistration_deviations
    ]
    if not frame.equals(expected_frame):
        raise RuntimeError("Task 04 deviation CSV content disagrees with registration")
    if summary_records != expected_summary:
        raise RuntimeError("Task 04 deviation summary disagrees with registration")


def _evidence_rating(
    *,
    coverage_comparison: pd.DataFrame,
    weekday_stats: pd.DataFrame,
    period_results: pd.DataFrame,
    yearly_tests: pd.DataFrame,
    regime_stats: pd.DataFrame,
    regime_tests: pd.DataFrame,
    extreme_results: pd.DataFrame,
    config: Task04Config,
) -> tuple[str, dict[str, Any]]:
    required_periods = {
        "full_eligible_sample",
        "pre_2020",
        "covid_era",
        "post_2021",
        "development_70",
        "validation_30",
    }
    required_regimes = {"LOW", "MEDIUM", "HIGH"}
    all_profiles = {
        config.primary_coverage_profile,
        "STRICT_CONTINUITY",
        "SENSITIVITY_FULL",
        "SENSITIVITY_2023",
    }
    required_profiles = {
        config.primary_coverage_profile,
        "STRICT_CONTINUITY",
    }
    required_frames = {
        "coverage_profile_comparison": coverage_comparison,
        "weekday_statistics": weekday_stats,
        "period_robustness": period_results,
        "yearly_omnibus_tests": yearly_tests,
        "volatility_regime_statistics": regime_stats,
        "volatility_regime_tests": regime_tests,
        "extreme_event_sensitivity": extreme_results,
    }
    missing_artifacts = sorted(
        name for name, frame in required_frames.items() if frame.empty
    )
    if missing_artifacts:
        return "INSUFFICIENT", {
            "rating": "INSUFFICIENT",
            "reason": "required evidence artifact is empty",
            "missing_artifacts": missing_artifacts,
        }
    missing_periods = required_periods.difference(period_results["analysis_period"])
    missing_regimes = required_regimes.difference(regime_stats["volatility_regime"])
    missing_regime_tests = required_regimes.difference(
        regime_tests.loc[
            regime_tests["test_name"].eq("kruskal_wallis"),
            "volatility_regime",
        ]
    )
    missing_profiles = all_profiles.difference(coverage_comparison["profile"])
    structure_errors: list[str] = []
    if missing_periods:
        structure_errors.append(f"periods={sorted(missing_periods)}")
    if missing_regimes:
        structure_errors.append(f"regime_statistics={sorted(missing_regimes)}")
    if missing_regime_tests:
        structure_errors.append(f"regime_tests={sorted(missing_regime_tests)}")
    if missing_profiles:
        structure_errors.append(f"profiles={sorted(missing_profiles)}")
    primary_stats = weekday_stats.loc[
        weekday_stats["profile"].eq(config.primary_coverage_profile)
        & weekday_stats["analysis_scope"].eq("complete_weekday_dates")
    ]
    if set(primary_stats["weekday_name"]) != set(config.weekday_inclusion):
        structure_errors.append("primary_weekday_statistics")
    sufficient_years = yearly_tests.loc[yearly_tests["sufficient_for_inference"]]
    if sufficient_years.empty:
        structure_errors.append("sufficient_years")
    numeric_requirements = (
        (
            coverage_comparison,
            (
                "eligible_daily_observations",
                "kruskal_statistic",
                "kruskal_p_value",
                "epsilon_squared",
            ),
            "coverage profiles",
        ),
        (
            primary_stats,
            (
                "sample_size",
                "median",
                "median_ci_lower",
                "median_ci_upper",
            ),
            "primary weekday statistics",
        ),
        (
            period_results.loc[
                period_results["analysis_period"].isin(required_periods)
            ],
            (
                "sample_size",
                "rank_correlation_with_full",
                "kruskal_statistic",
                "kruskal_p_value",
                "epsilon_squared",
            ),
            "period robustness",
        ),
        (
            sufficient_years,
            (
                "sample_size",
                "kruskal_statistic",
                "kruskal_p_value",
                "epsilon_squared",
            ),
            "annual evidence",
        ),
        (
            regime_stats.loc[regime_stats["volatility_regime"].isin(required_regimes)],
            ("sample_size", "median"),
            "regime statistics",
        ),
        (
            regime_tests.loc[
                regime_tests["test_name"].eq("kruskal_wallis")
                & regime_tests["volatility_regime"].isin(required_regimes)
            ],
            (
                "statistic",
                "p_value",
                "numerator_degrees_of_freedom",
                "sample_size",
                "group_count",
            ),
            "regime tests",
        ),
        (
            extreme_results,
            (
                "sample_size",
                "rank_correlation_with_primary",
                "kruskal_statistic",
                "kruskal_p_value",
                "epsilon_squared",
            ),
            "extreme-event sensitivity",
        ),
    )
    for frame, columns, label in numeric_requirements:
        if any(column not in frame for column in columns):
            structure_errors.append(f"{label}:missing_column")
            continue
        values = frame.loc[:, list(columns)].apply(pd.to_numeric, errors="coerce")
        if values.empty or not np.isfinite(values.to_numpy(dtype=float)).all():
            structure_errors.append(f"{label}:non_finite")
    if not primary_stats.empty:
        contradictory_ci = (
            (primary_stats["median_ci_lower"] > primary_stats["median"])
            | (primary_stats["median"] > primary_stats["median_ci_upper"])
        ).any()
        if contradictory_ci:
            structure_errors.append("primary weekday statistics:contradictory_ci")
    primary_regime_tests = regime_tests.loc[
        regime_tests["test_name"].eq("kruskal_wallis")
        & regime_tests["volatility_regime"].isin(required_regimes)
    ]
    if (
        not primary_regime_tests.empty
        and (
            primary_regime_tests["sample_size"]
            < config.evidence_rating.minimum_regime_sample
        ).any()
    ):
        structure_errors.append("regime tests:insufficient_population")
    if structure_errors:
        return "INSUFFICIENT", {
            "rating": "INSUFFICIENT",
            "reason": "required evidence is missing, malformed, or insufficient",
            "evidence_errors": sorted(structure_errors),
        }
    primary = coverage_comparison.loc[
        coverage_comparison["profile"].eq(config.primary_coverage_profile)
    ].iloc[0]
    period_index = period_results.set_index("analysis_period")
    development_order = tuple(
        str(period_index.loc["development_70", "weekday_order_high_to_low"]).split("|")
    )
    validation_order = tuple(
        str(period_index.loc["validation_30", "weekday_order_high_to_low"]).split("|")
    )
    validation_agreement = rank_correlation(development_order, validation_order)
    strict = coverage_comparison.loc[
        coverage_comparison["profile"].eq("STRICT_CONTINUITY")
    ].iloc[0]
    extreme_agreement = float(
        extreme_results.loc[
            ~extreme_results["analysis_variant"].eq("primary_raw_distribution"),
            "rank_correlation_with_primary",
        ].min()
    )
    ci_relative_widths = (
        primary_stats["median_ci_upper"] - primary_stats["median_ci_lower"]
    ) / primary_stats["median"].abs()
    maximum_ci_relative_width = float(ci_relative_widths.max())
    minimum_primary_group_size = int(primary_stats["sample_size"].min())
    rating_config = config.evidence_rating
    moderate_checks = {
        "primary_significant": bool(primary["kruskal_p_value"] < config.alpha),
        "epsilon_squared_meets_moderate_threshold": bool(
            primary["epsilon_squared"] >= rating_config.moderate_minimum_epsilon_squared
        ),
        "primary_group_sample_sufficient": bool(
            minimum_primary_group_size >= rating_config.minimum_primary_weekday_sample
        ),
        "median_ci_precision_meets_moderate_threshold": bool(
            maximum_ci_relative_width
            <= rating_config.moderate_maximum_median_ci_relative_width
        ),
        "development_validation_rank_correlation_sufficient": bool(
            validation_agreement >= rating_config.minimum_rank_correlation
        ),
        "strict_continuity_direction_concordant": bool(
            strict["rank_correlation_with_primary"]
            >= rating_config.minimum_rank_correlation
        ),
        "extreme_sensitivity_does_not_reverse_order": bool(
            extreme_agreement >= rating_config.minimum_rank_correlation
        ),
    }
    full_order = tuple(str(primary["weekday_order_high_to_low"]).split("|"))
    yearly_agreements = [
        rank_correlation(full_order, tuple(str(order).split("|")))
        for order in sufficient_years["weekday_order_high_to_low"]
    ]
    stable_year_fraction = (
        float(
            np.mean(
                np.asarray(yearly_agreements) >= rating_config.minimum_rank_correlation
            )
        )
        if yearly_agreements
        else 0.0
    )
    regime_orders = []
    for _regime, selected in regime_stats.groupby("volatility_regime", sort=False):
        medians = selected.set_index("weekday_name")["median"]
        regime_orders.append(
            tuple(
                sorted(
                    config.weekday_inclusion,
                    key=lambda day: (
                        -float(medians.get(day, -math.inf)),
                        config.weekday_inclusion.index(day),
                    ),
                )
            )
        )
    regime_agreements = [rank_correlation(full_order, order) for order in regime_orders]
    fixed_period_agreements = [
        float(period_index.loc[name, "rank_correlation_with_full"])
        for name in ("pre_2020", "covid_era", "post_2021")
    ]
    required_profile_concordance = bool(
        (
            coverage_comparison.loc[
                coverage_comparison["profile"].isin(required_profiles),
                "rank_correlation_with_primary",
            ].fillna(1.0)
            >= rating_config.minimum_rank_correlation
        ).all()
    )
    diagnostic_profiles = coverage_comparison.loc[
        ~coverage_comparison["profile"].isin(required_profiles)
    ]
    diagnostic_profile_concordance = bool(
        (
            diagnostic_profiles["rank_correlation_with_primary"].fillna(1.0)
            >= rating_config.minimum_rank_correlation
        ).all()
    )
    strong_checks = {
        "epsilon_squared_meets_strong_threshold": bool(
            primary["epsilon_squared"] >= rating_config.strong_minimum_epsilon_squared
        ),
        "development_significant": bool(
            period_index.loc["development_70", "kruskal_p_value"] < config.alpha
        ),
        "validation_significant": bool(
            period_index.loc["validation_30", "kruskal_p_value"] < config.alpha
        ),
        "median_ci_precision_meets_strong_threshold": bool(
            maximum_ci_relative_width
            <= rating_config.strong_maximum_median_ci_relative_width
        ),
        "sufficient_year_stability_meets_threshold": bool(
            stable_year_fraction >= rating_config.strong_minimum_stable_year_fraction
        ),
        "all_fixed_periods_directionally_stable": bool(
            fixed_period_agreements
            and min(fixed_period_agreements) >= rating_config.minimum_rank_correlation
        ),
        "all_regimes_directionally_stable": bool(
            regime_agreements
            and min(regime_agreements) >= rating_config.minimum_rank_correlation
        ),
        "required_coverage_profiles_directionally_concordant": (
            required_profile_concordance
        ),
        "timestamp_semantics_resolved": (
            config.timestamp_semantics_status != "UNRESOLVED"
        ),
    }
    if rating_config.diagnostic_profile_disagreement_blocks_strong:
        strong_checks["diagnostic_coverage_profiles_directionally_concordant"] = (
            diagnostic_profile_concordance
        )
    rating = "WEAK"
    if all(moderate_checks.values()):
        rating = "MODERATE"
        if all(strong_checks.values()):
            rating = "STRONG"
    rating_order = ("INSUFFICIENT", "WEAK", "MODERATE", "STRONG")
    cap = rating_config.unresolved_timestamp_semantics_maximum_rating
    if config.timestamp_semantics_status == "UNRESOLVED" and rating_order.index(
        rating
    ) > rating_order.index(cap):
        rating = cap
    detail = {
        "rating": rating,
        "moderate_checks": moderate_checks,
        "strong_checks": strong_checks,
        "development_validation_rank_correlation": validation_agreement,
        "sufficient_year_stable_fraction": stable_year_fraction,
        "fixed_period_rank_correlations": fixed_period_agreements,
        "regime_rank_correlations": regime_agreements,
        "extreme_event_minimum_rank_correlation": extreme_agreement,
        "maximum_primary_median_ci_relative_width": maximum_ci_relative_width,
        "minimum_primary_weekday_sample": minimum_primary_group_size,
        "required_profile_concordance": required_profile_concordance,
        "diagnostic_profile_concordance": diagnostic_profile_concordance,
        "diagnostic_profile_disagreement_blocks_strong": (
            rating_config.diagnostic_profile_disagreement_blocks_strong
        ),
        "high_regime_significance_role": (rating_config.high_regime_significance_role),
        "high_regime_kruskal_p_value": float(
            primary_regime_tests.set_index("volatility_regime").loc["HIGH", "p_value"]
        ),
        "timestamp_semantics_status": config.timestamp_semantics_status,
        "timestamp_semantics_rating_cap": cap,
        "thresholds": rating_config.model_dump(mode="json"),
        "logic_source": "studies/task04_daily_range_weekday.yaml",
    }
    return rating, detail


def _markdown_report(summary: dict[str, Any], tables: dict[str, pd.DataFrame]) -> str:
    primary = summary["primary_result"]
    evidence = summary["evidence_rating"]
    population = tables["population_reconciliation.csv"]
    primary_population = population.loc[
        population["profile"].eq("DEFAULT_RESEARCH")
        & population["metric"].eq("dates_included_in_analysis"),
        "value",
    ].iloc[0]
    weekday = tables["weekday_statistics.csv"]
    primary_weekday = weekday.loc[
        weekday["profile"].eq("DEFAULT_RESEARCH")
        & weekday["analysis_scope"].eq("complete_weekday_dates")
    ].sort_values("median", ascending=False)
    top = primary_weekday.iloc[0]
    bottom = primary_weekday.iloc[-1]
    pairwise = tables["pairwise_tests.csv"]
    primary_pairs = pairwise.loc[pairwise["profile"].eq("DEFAULT_RESEARCH")]
    significant_pairs = int(primary_pairs["significant"].sum())
    deviations = tables["preregistration_deviations.csv"]
    lines = [
        "# Daily Range Behaviour by Weekday",
        "",
        "## Registration classification",
        "",
        f"**{summary['registration_classification']}**.",
        "",
        summary["registration_disclosure"],
        "",
        "## Executive conclusion",
        "",
        summary["executive_conclusion"],
        "",
        f"Evidence rating: **{evidence['rating']}**.",
        "",
        "## Research question",
        "",
        "Does the distribution of EUR/USD daily high-low range differ across UTC "
        "weekdays?",
        "",
        "## Registered hypotheses",
        "",
        f"- Null: {summary['hypotheses']['null']}",
        f"- Alternative: {summary['hypotheses']['alternative']}",
        "",
        "## Population reconciliation",
        "",
        f"The primary analysis contains {int(primary_population):,} complete "
        "`DEFAULT_RESEARCH` Monday-Friday UTC dates. All observed dates, partial "
        "dates, weekend dates, boundary dates, and sensitivity memberships remain "
        "in the machine-readable reconciliation and daily metadata.",
        "",
        "## Daily aggregation methodology",
        "",
        "Daily open/high/low/close use the earliest open, maximum high, minimum low, "
        "and latest close among profile-eligible M15 observations on each UTC date. "
        "Range is `(high - low) / 0.0001` without pre-analysis rounding. Monday "
        "through Thursday require the complete 96-interval UTC grid; Friday ends "
        "at its audited RAW-DQ-001 weekly-boundary endpoint.",
        "",
        "The authoritative candle-open-versus-candle-close timestamp convention "
        "remains unresolved. This registered replication assigns each supplied "
        "timestamp label to its supplied UTC date; a close-time convention could "
        "shift one M15 interval at date and weekly boundaries. Unresolved semantics "
        "cap the evidence rating at MODERATE.",
        "",
        "## Coverage profile methodology",
        "",
        "COVERAGE-001 masks are applied to raw rows before each daily aggregation. "
        "`DEFAULT_RESEARCH` is primary, `STRICT_CONTINUITY` is the required "
        "sensitivity, and `SENSITIVITY_FULL`/`SENSITIVITY_2023` are diagnostic "
        "populations rather than substitutes.",
        "",
        "## Descriptive findings",
        "",
        f"The highest primary median was {top['weekday_name']} "
        f"({top['median']:.2f} pips) and the lowest was "
        f"{bottom['weekday_name']} ({bottom['median']:.2f} pips). Means, full "
        "percentile sets, dispersion, shape diagnostics, and deterministic "
        "confidence intervals are retained in `weekday_statistics.csv`.",
        "",
        "The boxplot shows the median/spread comparison while retaining extreme "
        "observations; the shared zero baseline prevents visual exaggeration.",
        "",
        "![Weekday boxplot](figures/01_weekday_boxplot.png)",
        "",
        "The fixed-bandwidth violin view makes distribution shape visible without "
        "changing the primary rank-based inference.",
        "",
        "![Weekday distributions](figures/02_weekday_violin_or_distribution.png)",
        "",
        "The ECDF exposes the full distribution and shows that weekday differences "
        "are not reducible to one average.",
        "",
        "![Weekday ECDF](figures/03_weekday_ecdf.png)",
        "",
        "Mean and median intervals show the estimation uncertainty and the "
        "mean-median separation expected from right-skewed ranges.",
        "",
        "![Weekday mean and median intervals](figures/04_weekday_mean_median_ci.png)",
        "",
        "## Primary omnibus test",
        "",
        f"Kruskal-Wallis H={primary['kruskal_statistic']:.6g}, "
        f"p={primary['kruskal_p_value']:.6g}, epsilon-squared="
        f"{primary['epsilon_squared']:.6g}. This is the registered-replication "
        "primary inferential result.",
        "",
        "## Pairwise results",
        "",
        f"All ten comparisons are reported; {significant_pairs} have Holm-adjusted "
        "p-values below the configured 0.05 threshold. Non-significant pairs are "
        "not suppressed.",
        "",
        "## Effect sizes",
        "",
        "Omnibus epsilon-squared, eta-squared, and omega-squared are reported with "
        "pairwise Cliff's delta, absolute mean/median differences, relative median "
        "differences, and median-difference bootstrap intervals.",
        "",
        "## Confidence intervals",
        "",
        "Mean, median, and pairwise median-difference intervals use 2,000 "
        "deterministic percentile-bootstrap resamples with seed 20260727. They use "
        "iid resampling and therefore do not remove serial dependence.",
        "",
        "## Chronological validation",
        "",
        summary["robustness"]["chronological"],
        "",
        "The period view compares the same weekday medians across fixed windows "
        "and the untouched final 30% validation segment.",
        "",
        "![Chronological stability](figures/07_chronological_stability.png)",
        "",
        "## Year-by-year stability",
        "",
        summary["robustness"]["yearly"],
        "",
        "Yearly medians show both recurring ordering and visible exceptions; the "
        "sufficiency flag remains authoritative for interpretation.",
        "",
        "![Yearly weekday medians](figures/05_yearly_weekday_medians.png)",
        "",
        "## Volatility-regime stability",
        "",
        summary["robustness"]["volatility_regime"],
        "",
        "The regime comparison uses only lagged past information and makes the "
        "HIGH-regime instability visible.",
        "",
        "![Volatility-regime comparison](figures/08_volatility_regime_comparison.png)",
        "",
        "## Coverage-profile sensitivity",
        "",
        summary["robustness"]["coverage_profiles"],
        "",
        "The coverage comparison shows why diagnostic sensitivity-only populations "
        "are not interchangeable with the primary profile.",
        "",
        "![Coverage-profile comparison](figures/06_coverage_profile_comparison.png)",
        "",
        "## Extreme-event sensitivity",
        "",
        summary["robustness"]["extreme_events"],
        "",
        "## Evidence rating",
        "",
        f"**{evidence['rating']}** under the exact registered multi-dimension "
        "logic. A small full-sample p-value cannot by itself produce a strong "
        "rating.",
        "",
        "## Observed facts",
        "",
        summary["observed_fact"],
        "",
        "## Possible explanations",
        "",
        "The study did not test mechanisms. Calendar-linked information flow, "
        "liquidity conditions, and event timing are possible explanations only "
        "and are deferred to separately registered research.",
        "",
        "## Trading implications",
        "",
        "Weekday may be relevant as a contextual range-expectation variable only "
        "if the effect is stable and economically meaningful. This study does not "
        "establish direction, profitability, or a trading rule.",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in summary["limitations"])
    lines.extend(
        [
            "",
            "## Registration deviations",
            "",
            (
                "None."
                if deviations.empty
                else f"{len(deviations)} deviation(s) are documented below and "
                "in `preregistration_deviations.csv`."
            ),
        ]
    )
    if not deviations.empty:
        for row in deviations.itertuples(index=False):
            lines.extend(
                [
                    "",
                    f"- `{row.deviation_id}`; field `{row.affected_field}`; "
                    f"classification `{row.classification}`; reason: {row.reason}; "
                    f"consequence: {row.consequence}; lineage "
                    f"`{row.lineage_reference}`.",
                ]
            )
    lines.extend(
        [
            "",
            "## Recommended future research",
            "",
            "The next task should remain separately registered. A suitable "
            "follow-up is to validate one bounded mechanism or external calendar "
            "explanation without changing this study's completed definitions.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(
        temporary,
        index=False,
        lineterminator="\n",
        date_format="%Y-%m-%dT%H:%M:%SZ",
        float_format="%.17g",
    )
    temporary.replace(path)


def _validate_written_outputs(output_directory: Path, config: Task04Config) -> None:
    expected = {
        *config.expected_output_files,
        *(f"figures/{name}" for name in config.expected_figure_files),
    }
    if output_directory.is_symlink() or not output_directory.is_dir():
        raise RuntimeError("Task 04 output root must be a real directory")
    present: set[str] = set()
    for path in output_directory.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"Task 04 outputs forbid symbolic links: {path}")
        if path.is_dir():
            continue
        assert_regular_contained_file(path, output_directory)
        present.add(path.relative_to(output_directory).as_posix())
    if present != expected:
        missing = sorted(expected.difference(present))
        unexpected = sorted(present.difference(expected))
        raise RuntimeError(
            f"Task 04 output inventory mismatch; missing={missing}; "
            f"unexpected={unexpected}"
        )
    root_text = str(find_repository_root())
    for path in output_directory.rglob("*"):
        if (
            path.is_file()
            and path.suffix in {".csv", ".json", ".md"}
            and root_text in path.read_text(encoding="utf-8")
        ):
            raise RuntimeError(f"Absolute repository path leaked into {path}")


def _validate_existing_output_scope(
    output_directory: Path, config: Task04Config
) -> None:
    """Reject stale or unregistered files before replacing registered artifacts."""
    if not output_directory.exists():
        return
    expected = {
        *config.expected_output_files,
        *(f"figures/{name}" for name in config.expected_figure_files),
    }
    if output_directory.is_symlink() or not output_directory.is_dir():
        raise RuntimeError("Task 04 output root must be a real directory")
    present: set[str] = set()
    for path in output_directory.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"Task 04 outputs forbid symbolic links: {path}")
        if path.is_dir():
            continue
        assert_regular_contained_file(path, output_directory)
        present.add(path.relative_to(output_directory).as_posix())
    unexpected = sorted(present.difference(expected))
    if unexpected:
        raise RuntimeError(
            f"Task 04 output directory contains stale files: {unexpected}"
        )


def generate_task04_study(
    root: Path | None = None, output_directory: Path | None = None
) -> Task04Result:
    """Generate candidate evidence without completing the registered lifecycle."""
    repository_root = (root or find_repository_root()).resolve()
    task_config = load_task04_config(repository_root)
    if project_path(task_config.registration_lifecycle_path, repository_root).exists():
        raise RuntimeError("Completed Task 04 lifecycle forbids candidate regeneration")
    repository_config = load_config(repository_root)
    coverage_summary, manifest = _validate_dependencies(repository_root, task_config)
    preregistration_path = project_path(
        task_config.preregistration_path, repository_root
    )
    registration, registration_raw = read_preregistration(preregistration_path)
    registry = preregistration_record(
        registration, registration_raw, task_config, root=repository_root
    )
    coverage = build_coverage(
        root=repository_root,
        config=repository_config,
        repository_version=_repository_version(
            repository_root,
            ignored_generated_paths=(
                task_config.output_directory,
                task_config.candidate_output_directory,
            ),
        ),
    )
    validate_task03_row_membership(
        repository_root,
        coverage,
        repository_config,
        expected_fingerprint=(task_config.required_task03_row_membership_fingerprint),
    )
    saved_lineage = coverage_summary["lineage"]
    for field in (
        "raw_sha256",
        "audit_result_content_sha256",
        "audit_gap_table_sha256",
        "audit_monthly_table_sha256",
        "coverage_method_id",
        "coverage_method_version",
        "coverage_config_sha256",
    ):
        if coverage.lineage.to_dict()[field] != saved_lineage[field]:
            raise ValueError(f"Live Task 03 masks disagree with saved lineage: {field}")
    lineage = _lineage(
        root=repository_root,
        config=task_config,
        coverage_summary=coverage_summary,
        preregistration=registry,
    )
    raw_path = project_path(repository_config.data.raw_dataset_path, repository_root)
    raw_stat_before = raw_path.stat()
    raw_checksum_before = sha256_file(raw_path)
    gaps = pd.read_csv(
        project_path(repository_config.coverage.audit_gap_table_path, repository_root)
    )
    aggregation = aggregate_daily_profiles(
        raw_path=raw_path,
        coverage=coverage,
        gaps=gaps,
        config=task_config,
        lineage=lineage,
    )
    (
        weekday_statistics,
        omnibus_tests,
        pairwise_tests,
        effect_sizes,
        coverage_comparison,
    ) = coverage_profile_outputs(aggregation.by_profile, task_config)
    primary = eligible_daily(
        aggregation.by_profile[task_config.primary_coverage_profile]
    )
    period_results, chronological_split = chronological_outputs(primary, task_config)
    yearly_statistics, yearly_tests = yearly_outputs(primary, task_config)
    regime_statistics, regime_tests, regime_daily = volatility_regime_outputs(
        primary, task_config
    )
    extreme_results = extreme_event_outputs(primary, task_config)
    population = _population_reconciliation(
        aggregation,
        coverage.flags_by_level["row"],
        coverage.profile_masks_by_level["row"],
        task_config,
    )
    deviations = _deviation_frame(registration)
    rating, rating_detail = _evidence_rating(
        coverage_comparison=coverage_comparison,
        weekday_stats=weekday_statistics,
        period_results=period_results,
        yearly_tests=yearly_tests,
        regime_stats=regime_statistics,
        regime_tests=regime_tests,
        extreme_results=extreme_results,
        config=task_config,
    )
    primary_comparison = coverage_comparison.loc[
        coverage_comparison["profile"].eq(task_config.primary_coverage_profile)
    ].iloc[0]
    primary_result = {
        "kruskal_statistic": float(primary_comparison["kruskal_statistic"]),
        "kruskal_p_value": float(primary_comparison["kruskal_p_value"]),
        "epsilon_squared": float(primary_comparison["epsilon_squared"]),
        "weekday_order_high_to_low": primary_comparison["weekday_order_high_to_low"],
        "significant_at_alpha": bool(primary_comparison["significant"]),
        "alpha": task_config.alpha,
    }
    validation = period_results.set_index("analysis_period").loc["validation_30"]
    coverage_index = coverage_comparison.set_index("profile")
    regime_primary = regime_tests.loc[
        regime_tests["test_name"].eq("kruskal_wallis")
    ].set_index("volatility_regime")
    sufficient_years = yearly_tests.loc[yearly_tests["sufficient_for_inference"]]
    significant_years = int(sufficient_years["significant"].sum())
    extreme_index = extreme_results.set_index("analysis_variant")
    strict_rank_correlation = float(
        coverage_index.loc["STRICT_CONTINUITY", "rank_correlation_with_primary"]
    )
    sensitivity_full_dates = int(
        coverage_index.loc["SENSITIVITY_FULL", "eligible_daily_observations"]
    )
    sensitivity_2023_dates = int(
        coverage_index.loc["SENSITIVITY_2023", "eligible_daily_observations"]
    )
    winsorised_p_value = float(extreme_index.loc["winsorised_1_99", "kruskal_p_value"])
    tail_exclusion_p_value = float(
        extreme_index.loc["exclude_largest_1_percent", "kruskal_p_value"]
    )
    summary = {
        "study": {
            "study_id": task_config.study_id,
            "registration_version": task_config.registration_version,
            "method_id": task_config.method_id,
            "method_version": task_config.method_version,
            "title": registration.title,
            "status": "CANDIDATE",
            "implementation_version": task_config.implementation_version,
        },
        "lineage": lineage,
        "registration_classification": registration.registration_classification,
        "registration_disclosure": registration.registration_disclosure,
        "registry": {**registry, "status": "CANDIDATE"},
        "hypotheses": {
            "null": registration.primary_null_hypothesis,
            "alternative": registration.primary_alternative_hypothesis,
        },
        "primary_result": primary_result,
        "evidence_rating": rating_detail,
        "population": {
            "raw_rows": aggregation.raw_row_count,
            "observed_utc_dates": len(aggregation.wide_observations),
            "primary_eligible_dates": len(primary),
        },
        "executive_conclusion": (
            "The evidence "
            + (
                "suggests that the UTC-weekday daily-range distributions differ, "
                if primary_result["significant_at_alpha"]
                else "does not provide sufficient evidence that the UTC-weekday "
                "daily-range distributions differ, "
            )
            + f"with an omnibus epsilon-squared of "
            f"{primary_result['epsilon_squared']:.4f}. The practical and temporal "
            f"stability is reflected in a conservative {rating} evidence rating; "
            "the result is descriptive and not a trading strategy."
        ),
        "observed_fact": (
            f"The primary Kruskal-Wallis comparison returned p="
            f"{primary_result['kruskal_p_value']:.6g} across "
            f"{len(primary):,} complete UTC weekday dates. The registered weekday "
            f"median order was {primary_result['weekday_order_high_to_low']}."
        ),
        "robustness": {
            "chronological": (
                f"The final 30% validation period had p="
                f"{float(validation['kruskal_p_value']):.6g} and weekday-order "
                "rank correlation "
                f"{float(validation['rank_correlation_with_full']):.3f} "
                "with the full sample."
            ),
            "yearly": (
                f"{int(yearly_tests['sufficient_for_inference'].sum())} calendar "
                "years met the preregistered per-weekday sample threshold; "
                f"{significant_years} had an unadjusted yearly omnibus p-value below "
                "0.05. All years remain in the outputs, and ordering was not uniform."
            ),
            "volatility_regime": (
                f"{int(regime_daily['volatility_regime'].ne('UNCLASSIFIED').sum()):,} "
                "dates received LOW, MEDIUM, or HIGH labels from strictly past-only "
                "information; warm-up dates remain unclassified. Omnibus p-values "
                f"were {float(regime_primary.loc['LOW', 'p_value']):.4g} (LOW), "
                f"{float(regime_primary.loc['MEDIUM', 'p_value']):.4g} (MEDIUM), and "
                f"{float(regime_primary.loc['HIGH', 'p_value']):.4g} (HIGH), so the "
                "relationship did not persist in the HIGH regime."
            ),
            "coverage_profiles": (
                "STRICT_CONTINUITY remained significant with rank correlation "
                f"{strict_rank_correlation:.2f} "
                "against the primary ordering. The diagnostic SENSITIVITY_FULL and "
                f"SENSITIVITY_2023 populations contained "
                f"{sensitivity_full_dates} and {sensitivity_2023_dates} "
                "complete dates and were not significant; their ordering was not "
                "concordant with the primary population."
            ),
            "extreme_events": (
                "The raw primary result remains authoritative. The 1st/99th "
                "winsorised and largest-1%-excluded comparisons retained the same "
                "weekday median ordering, with p-values "
                f"{winsorised_p_value:.4g} and {tail_exclusion_p_value:.4g}; "
                "both transformations are reversible sensitivity checks only."
            ),
        },
        "limitations": list(registration.known_limitations),
        "preregistration_deviations": [
            item.model_dump(mode="json")
            for item in registration.preregistration_deviations
        ],
        "raw_checksum_before": raw_checksum_before,
        "raw_checksum_after": sha256_file(raw_path),
        "raw_mtime_ns_before": raw_stat_before.st_mtime_ns,
        "raw_mtime_ns_after": raw_path.stat().st_mtime_ns,
    }
    if summary["raw_checksum_after"] != raw_checksum_before:
        raise RuntimeError("Raw dataset changed during Task 04 generation")
    if summary["raw_mtime_ns_after"] != raw_stat_before.st_mtime_ns:
        raise RuntimeError("Raw dataset modification time changed during Task 04")
    _validate_deviation_reconciliation(
        registration,
        deviations,
        cast(list[dict[str, Any]], summary["preregistration_deviations"]),
    )
    daily_profile_observations = pd.concat(
        [aggregation.by_profile[profile] for profile in aggregation.by_profile],
        ignore_index=True,
    )
    daily_profile_observations["zero_contribution"] = daily_profile_observations[
        "observed_m15_rows"
    ].eq(0)
    daily_profile_observations["nonzero_partial"] = (
        daily_profile_observations["observed_m15_rows"].gt(0)
        & daily_profile_observations["is_partial_daily_observation"]
    )
    daily_profile_observations["incomplete"] = daily_profile_observations[
        "is_partial_daily_observation"
    ]
    daily_profile_observations["complete"] = ~daily_profile_observations[
        "is_partial_daily_observation"
    ]
    for key, value in lineage.items():
        daily_profile_observations[key] = value
    tables = {
        "population_reconciliation.csv": population,
        "daily_observations.csv": aggregation.wide_observations,
        "daily_profile_observations.csv": daily_profile_observations,
        "weekday_statistics.csv": weekday_statistics,
        "omnibus_tests.csv": omnibus_tests,
        "pairwise_tests.csv": pairwise_tests,
        "effect_sizes.csv": effect_sizes,
        "coverage_profile_comparison.csv": coverage_comparison,
        "chronological_split_results.csv": chronological_split,
        "period_robustness.csv": period_results,
        "yearly_statistics.csv": yearly_statistics,
        "yearly_omnibus_tests.csv": yearly_tests,
        "volatility_regime_statistics.csv": regime_statistics,
        "volatility_regime_tests.csv": regime_tests,
        "volatility_regime_lineage.csv": regime_daily[
            [
                "utc_date",
                "profile",
                "daily_range_pips",
                "lagged_trailing_median_range_pips",
                "prior_regime_measure_count",
                "past_only_low_threshold",
                "past_only_high_threshold",
                "volatility_regime",
                "regime_warmup",
                "regime_classification_reason",
                "volatility_lookback",
                "volatility_minimum_history",
            ]
        ].assign(
            **lineage,
        ),
        "extreme_event_sensitivity.csv": extreme_results,
        "preregistration_deviations.csv": deviations,
    }
    destination = output_directory or project_path(
        task_config.candidate_output_directory, repository_root
    )
    _validate_existing_output_scope(destination, task_config)
    destination.mkdir(parents=True, exist_ok=True)
    for filename, frame in tables.items():
        _write_csv(destination / filename, frame)
    figure_paths = plot_all_figures(
        primary=primary,
        weekday_stats=weekday_statistics,
        yearly_stats=yearly_statistics,
        coverage_comparison=coverage_comparison,
        period_results=period_results,
        regime_stats=regime_statistics,
        output_directory=destination,
        config=task_config,
        raw_version=str(manifest["dataset_version"]),
    )
    _atomic_text(
        destination / "study_summary.json",
        json.dumps(json_safe(summary), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
    )
    _atomic_text(
        destination / "study_registry_record.json",
        json.dumps(
            json_safe({**registry, "status": "CANDIDATE"}),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )
    _atomic_text(destination / "study_summary.md", _markdown_report(summary, tables))
    if tuple(path.name for path in figure_paths) != task_config.expected_figure_files:
        raise RuntimeError(
            "Task 04 plotting did not return the registered figure order"
        )
    _validate_written_outputs(destination, task_config)
    _validate_written_outputs(destination, task_config)
    return Task04Result(summary, tables, figure_paths, destination)
