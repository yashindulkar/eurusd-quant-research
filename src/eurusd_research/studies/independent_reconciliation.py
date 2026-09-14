"""Complete independent raw-to-evidence reconciliation for Task 04 v2.11.

This orchestration module imports no Task 04 production aggregation,
statistics, robustness, rating, or inventory implementation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from eurusd_research.studies.completion import (
    INDEPENDENT_RECONCILIATION_IMPLEMENTATION,
    RECONCILIATION_COMPONENTS,
    CandidateByteIdentityEvidence,
    ComponentDiscrepancy,
    ComponentName,
    IndependentReconciliationEvidence,
    ValidatedCandidateIdentity,
)
from eurusd_research.studies.configuration import Task04Config
from eurusd_research.studies.independent_daily import PROFILES, rebuild_daily_profiles
from eurusd_research.studies.independent_inventory import (
    compare_output_to_validated_identity,
    inspect_output_inventory,
)
from eurusd_research.studies.independent_rating import reconstruct_rating
from eurusd_research.studies.independent_robustness import (
    annual_tables,
    chronological_tables,
    coverage_profile_tables,
    extreme_table,
    regime_tables,
)
from eurusd_research.studies.independent_statistics import weekday_order
from eurusd_research.studies.integrity import canonical_digest
from eurusd_research.studies.reconciliation_schema import (
    DAILY_PROFILE_SCHEMA,
    REGIME_LINEAGE_OUTPUT_SCHEMA,
    canonical_registered_output_paths,
    load_candidate_csv,
    project_registered_regime_lineage,
    schema_from_expected,
)


@dataclass(frozen=True, slots=True)
class FrameComparison:
    """Calculated field-level comparison evidence."""

    checked_rows: int
    checked_fields: int
    absolute: dict[str, float]
    relative: dict[str, float]
    categorical_mismatches: int
    membership_mismatches: int
    examples: tuple[str, ...]
    missing: tuple[str, ...]


def compare_frames(
    expected: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    keys: tuple[str, ...],
    label: str,
) -> FrameComparison:
    """Compare all expected columns with stable key and null semantics."""
    missing_columns = tuple(sorted(set(expected.columns).difference(actual.columns)))
    if missing_columns:
        return FrameComparison(0, 0, {}, {}, 0, len(expected), (), missing_columns)
    expected_ordered = expected.sort_values(list(keys), kind="stable").reset_index(
        drop=True
    )
    actual_ordered = (
        actual.loc[:, expected.columns]
        .sort_values(list(keys), kind="stable")
        .reset_index(drop=True)
    )
    if len(expected_ordered) != len(actual_ordered):
        return FrameComparison(
            min(len(expected_ordered), len(actual_ordered)),
            0,
            {},
            {},
            0,
            abs(len(expected_ordered) - len(actual_ordered)),
            (f"{label}:row_count:{len(expected_ordered)}!={len(actual_ordered)}",),
            (),
        )
    examples: list[str] = []
    membership = 0
    for key in keys:
        left = expected_ordered[key].astype(str).fillna("<NULL>")
        right = actual_ordered[key].astype(str).fillna("<NULL>")
        count = int((left != right).sum())
        membership += count
        if count and len(examples) < 20:
            examples.append(f"{label}:{key}:membership_mismatches={count}")
    absolute: dict[str, float] = {}
    relative: dict[str, float] = {}
    categorical = 0
    for column in expected.columns:
        if column in keys:
            continue
        left_numeric = pd.to_numeric(expected_ordered[column], errors="coerce")
        right_numeric = pd.to_numeric(actual_ordered[column], errors="coerce")
        numeric = bool(
            expected_ordered[column].dtype.kind in "iufc"
            or actual_ordered[column].dtype.kind in "iufc"
        )
        if numeric:
            left_values = left_numeric.to_numpy(float)
            right_values = right_numeric.to_numpy(float)
            null_mismatch = np.isnan(left_values) != np.isnan(right_values)
            finite = np.isfinite(left_values) & np.isfinite(right_values)
            differences = np.abs(left_values[finite] - right_values[finite])
            denominators = np.maximum(np.abs(left_values[finite]), np.finfo(float).eps)
            absolute[f"{label}.{column}"] = float(differences.max(initial=0.0))
            relative[f"{label}.{column}"] = float(
                (differences / denominators).max(initial=0.0)
            )
            null_count = int(null_mismatch.sum())
            categorical += null_count
            if null_count and len(examples) < 20:
                examples.append(f"{label}:{column}:null_mismatches={null_count}")
        else:
            left_values = expected_ordered[column].fillna("<NULL>").astype(str)
            right_values = actual_ordered[column].fillna("<NULL>").astype(str)
            count = int((left_values != right_values).sum())
            categorical += count
            if count and len(examples) < 20:
                examples.append(f"{label}:{column}:categorical_mismatches={count}")
    return FrameComparison(
        len(expected_ordered),
        len(expected_ordered) * len(expected.columns),
        absolute,
        relative,
        categorical,
        membership,
        tuple(examples),
        (),
    )


def _merge_comparisons(*values: FrameComparison) -> FrameComparison:
    return FrameComparison(
        sum(item.checked_rows for item in values),
        sum(item.checked_fields for item in values),
        {key: value for item in values for key, value in item.absolute.items()},
        {key: value for item in values for key, value in item.relative.items()},
        sum(item.categorical_mismatches for item in values),
        sum(item.membership_mismatches for item in values),
        tuple(example for item in values for example in item.examples)[:20],
        tuple(missing for item in values for missing in item.missing),
    )


def _flatten_rating(value: object, prefix: str = "") -> dict[str, object]:
    """Flatten every rating-summary leaf for field-by-field reconciliation."""
    if isinstance(value, dict):
        return {
            key: leaf
            for name in sorted(value)
            for key, leaf in _flatten_rating(
                value[name], f"{prefix}.{name}" if prefix else str(name)
            ).items()
        }
    if isinstance(value, list):
        return {
            key: leaf
            for index, item in enumerate(value)
            for key, leaf in _flatten_rating(item, f"{prefix}[{index}]").items()
        }
    return {prefix: value}


def _compare_rating_summary(
    expected: dict[str, object], actual: object
) -> FrameComparison:
    """Compare every independently reconstructed production rating field."""
    if not isinstance(actual, dict):
        return FrameComparison(0, 0, {}, {}, 1, 0, (), ("evidence_rating",))
    left = _flatten_rating(expected)
    right = _flatten_rating(actual)
    missing = tuple(sorted(set(left) - set(right)))
    extra = tuple(sorted(set(right) - set(left)))
    examples: list[str] = []
    absolute: dict[str, float] = {}
    relative: dict[str, float] = {}
    categorical = 0
    for field in sorted(set(left) & set(right)):
        left_value = left[field]
        right_value = right[field]
        if (
            isinstance(left_value, (int, float))
            and not isinstance(left_value, bool)
            and isinstance(right_value, (int, float))
            and not isinstance(right_value, bool)
        ):
            difference = abs(float(left_value) - float(right_value))
            absolute[f"evidence_rating.{field}"] = difference
            relative[f"evidence_rating.{field}"] = difference / max(
                abs(float(left_value)), np.finfo(float).eps
            )
        elif type(left_value) is not type(right_value) or left_value != right_value:
            categorical += 1
            if len(examples) < 20:
                examples.append(
                    f"evidence_rating:{field}:{left_value!r}!={right_value!r}"
                )
    if missing:
        examples.append(f"evidence_rating:missing={list(missing)}")
    if extra:
        examples.append(f"evidence_rating:extra={list(extra)}")
    return FrameComparison(
        1,
        len(left),
        absolute,
        relative,
        categorical,
        len(missing) + len(extra),
        tuple(examples[:20]),
        missing,
    )


def _component(
    name: ComponentName,
    comparison: FrameComparison,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
    inventory_mismatches: int = 0,
    unsupported_claims: tuple[str, ...] = (),
) -> ComponentDiscrepancy:
    maximum_absolute = max([0.0, *comparison.absolute.values()])
    maximum_relative = max([0.0, *comparison.relative.values()])
    passed = bool(
        comparison.checked_rows > 0
        and comparison.checked_fields > 0
        and maximum_absolute <= absolute_tolerance
        and maximum_relative <= relative_tolerance
        and comparison.categorical_mismatches == 0
        and comparison.membership_mismatches == 0
        and inventory_mismatches == 0
        and not comparison.missing
        and not unsupported_claims
    )
    return ComponentDiscrepancy(
        component=name,
        status="PASS" if passed else "FAIL",
        checked_row_count=comparison.checked_rows,
        checked_field_count=comparison.checked_fields,
        absolute_discrepancy_by_field=comparison.absolute,
        relative_discrepancy_by_field=comparison.relative,
        maximum_absolute_discrepancy=maximum_absolute,
        maximum_relative_discrepancy=maximum_relative,
        categorical_mismatch_count=comparison.categorical_mismatches,
        membership_mismatch_count=comparison.membership_mismatches,
        inventory_mismatch_count=inventory_mismatches,
        mismatch_examples=comparison.examples,
        missing_evidence=comparison.missing,
        unsupported_claims=unsupported_claims,
        passed=passed,
    )


def _population_table(
    frames: dict[str, pd.DataFrame],
    row_flags: pd.DataFrame,
    masks: pd.DataFrame,
    config: Task04Config,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = [
        {
            "profile": "RAW",
            "metric": "total_raw_rows",
            "weekday": "",
            "value": len(row_flags),
        }
    ]
    sensitivity = [
        "long_nonweekly_gap_boundary",
        "nonweekend_gap_boundary",
        "unclassified_gap_boundary",
        "continuity_impaired_period",
        "affected_period_2023",
        "partial_boundary_year",
        "partial_boundary_month",
    ]
    mixed = row_flags.groupby("utc_date")[sensitivity].nunique().gt(1).any(axis=1)
    audited_dates = set(
        row_flags.loc[row_flags["affected_period_2023"], "utc_date"].astype(str)
    )
    for profile, frame in frames.items():
        eligible = frame.loc[frame["analysis_eligible"]]
        metrics = {
            "profile_source_rows": int(masks[profile].sum()),
            "total_observed_utc_dates": len(frame),
            "monday_friday_utc_dates": int(frame["is_weekday"].sum()),
            "weekend_utc_dates": int(frame["is_weekend_date"].sum()),
            "complete_dates": int(frame["complete"].sum()),
            "incomplete_dates": int(frame["incomplete"].sum()),
            "excluded_boundary_dates": int(frame["is_boundary_date"].sum()),
            "zero_contribution_dates": int(frame["zero_contribution"].sum()),
            "task03_profile_ineligible_dates": int(frame["zero_contribution"].sum()),
            "nonzero_partial_dates": int(frame["nonzero_partial"].sum()),
            "dates_excluded_for_insufficient_contributing_observations": int(
                (
                    frame["observed_m15_rows"]
                    < config.daily_completeness.minimum_daily_rows
                ).sum()
            ),
            "dates_included_in_analysis": len(eligible),
            "dates_with_mixed_sensitivity_conditions": int(
                mixed.loc[mixed.index.isin(frame["utc_date"])].sum()
            ),
            "dates_affected_by_audited_2023_interval": int(
                frame["utc_date"].isin(audited_dates).sum()
            ),
        }
        if (
            metrics["incomplete_dates"]
            != metrics["zero_contribution_dates"] + metrics["nonzero_partial_dates"]
        ):
            raise ValueError(
                f"Independent completeness reconciliation failed: {profile}"
            )
        records.extend(
            {"profile": profile, "metric": metric, "weekday": "", "value": value}
            for metric, value in metrics.items()
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
    return pd.DataFrame(records)


def build_independent_reconciliation(
    root: Path,
    output_directory: Path,
    *,
    config: Task04Config,
    anchor_commit: str,
    receipt_fingerprint: str,
    production_output_digest: str,
    absolute_tolerance: float,
    relative_tolerance: float,
    validated_candidate_identity: ValidatedCandidateIdentity | None = None,
) -> IndependentReconciliationEvidence:
    """Reconstruct every registered evidence component and compare outputs."""
    frames, row_flags, masks, raw_sha, task03_fingerprint = rebuild_daily_profiles(
        root, config
    )
    population_expected = _population_table(frames, row_flags, masks, config)
    population_actual = load_candidate_csv(
        output_directory / "population_reconciliation.csv",
        schema_from_expected(
            population_expected,
            empty_string_columns=("weekday",),
        ),
    )
    source_comparison = compare_frames(
        population_expected,
        population_actual,
        keys=("profile", "metric", "weekday"),
        label="population",
    )

    independent_daily = pd.concat(frames.values(), ignore_index=True)
    independent_daily["is_partial_daily_observation"] = independent_daily["incomplete"]
    for column in ("first_timestamp_utc", "last_timestamp_utc"):
        independent_daily[column] = pd.to_datetime(
            independent_daily[column], utc=True
        ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    daily_actual = load_candidate_csv(
        output_directory / "daily_profile_observations.csv",
        DAILY_PROFILE_SCHEMA,
    )
    daily_comparison = compare_frames(
        independent_daily,
        daily_actual,
        keys=("profile", "utc_date"),
        label="daily",
    )

    weekday_expected, omnibus_expected, pairwise_expected, effects_expected = (
        coverage_profile_tables(frames, config)
    )
    weekday_actual = load_candidate_csv(
        output_directory / "weekday_statistics.csv",
        schema_from_expected(weekday_expected),
    )
    omnibus_actual = load_candidate_csv(
        output_directory / "omnibus_tests.csv",
        schema_from_expected(omnibus_expected),
    )
    pairwise_actual = load_candidate_csv(
        output_directory / "pairwise_tests.csv",
        schema_from_expected(pairwise_expected),
    )
    effects_actual = load_candidate_csv(
        output_directory / "effect_sizes.csv",
        schema_from_expected(effects_expected),
    )
    descriptive_comparison = compare_frames(
        weekday_expected,
        weekday_actual,
        keys=("profile", "analysis_scope", "weekday_name"),
        label="weekday_statistics",
    )
    inference_comparison = _merge_comparisons(
        compare_frames(
            omnibus_expected,
            omnibus_actual,
            keys=("profile", "analysis_scope", "test_name"),
            label="omnibus",
        ),
        compare_frames(
            effects_expected,
            effects_actual,
            keys=(
                "profile",
                "analysis_scope",
                "comparison",
                "effect_size_method",
            ),
            label="effects",
        ),
    )
    pairwise_comparison = compare_frames(
        pairwise_expected,
        pairwise_actual,
        keys=("profile", "analysis_scope", "weekday_a", "weekday_b"),
        label="pairwise",
    )

    primary = frames[config.primary_coverage_profile]
    periods_expected, split_expected = chronological_tables(primary, config)
    periods_actual = load_candidate_csv(
        output_directory / "period_robustness.csv",
        schema_from_expected(periods_expected),
    )
    split_actual = load_candidate_csv(
        output_directory / "chronological_split_results.csv",
        schema_from_expected(split_expected),
    )
    chronological_comparison = compare_frames(
        split_expected, split_actual, keys=("analysis_period",), label="chronological"
    )
    fixed_expected = periods_expected.loc[
        periods_expected["analysis_period"].isin(
            ["full_eligible_sample", "pre_2020", "covid_era", "post_2021"]
        )
    ]
    fixed_actual = periods_actual.loc[
        periods_actual["analysis_period"].isin(fixed_expected["analysis_period"])
    ]
    fixed_comparison = compare_frames(
        fixed_expected, fixed_actual, keys=("analysis_period",), label="fixed_period"
    )

    annual_statistics_expected, annual_tests_expected = annual_tables(primary, config)
    annual_comparison = _merge_comparisons(
        compare_frames(
            annual_statistics_expected,
            load_candidate_csv(
                output_directory / "yearly_statistics.csv",
                schema_from_expected(annual_statistics_expected),
            ),
            keys=("year", "weekday_name"),
            label="annual_statistics",
        ),
        compare_frames(
            annual_tests_expected,
            load_candidate_csv(
                output_directory / "yearly_omnibus_tests.csv",
                schema_from_expected(annual_tests_expected),
            ),
            keys=("year",),
            label="annual_tests",
        ),
    )

    regime_statistics_expected, regime_tests_expected, lineage_expected = regime_tables(
        primary, config
    )
    lineage_actual = load_candidate_csv(
        output_directory / "volatility_regime_lineage.csv",
        REGIME_LINEAGE_OUTPUT_SCHEMA,
    )
    lineage_expected = project_registered_regime_lineage(lineage_expected)
    lineage_actual = project_registered_regime_lineage(lineage_actual)
    regime_comparison = _merge_comparisons(
        compare_frames(
            regime_statistics_expected,
            load_candidate_csv(
                output_directory / "volatility_regime_statistics.csv",
                schema_from_expected(regime_statistics_expected),
            ),
            keys=("volatility_regime", "weekday_name"),
            label="regime_statistics",
        ),
        compare_frames(
            regime_tests_expected,
            load_candidate_csv(
                output_directory / "volatility_regime_tests.csv",
                schema_from_expected(regime_tests_expected),
            ),
            keys=("volatility_regime", "test_name"),
            label="regime_tests",
        ),
        compare_frames(
            lineage_expected,
            lineage_actual,
            keys=("utc_date", "profile"),
            label="regime_lineage",
        ),
    )

    extreme_expected = extreme_table(primary, config)
    extreme_actual = load_candidate_csv(
        output_directory / "extreme_event_sensitivity.csv",
        schema_from_expected(extreme_expected),
    )
    extreme_comparison = compare_frames(
        extreme_expected,
        extreme_actual,
        keys=("analysis_variant",),
        label="extreme_event_analysis",
    )

    primary_order = weekday_order(primary.loc[primary["analysis_eligible"]])
    comparison_records = []
    for profile in PROFILES:
        selected = frames[profile].loc[frames[profile]["analysis_eligible"]]
        tests = omnibus_expected.loc[
            omnibus_expected["profile"].eq(profile)
            & omnibus_expected["test_name"].eq("kruskal_wallis")
        ].iloc[0]
        order = weekday_order(selected)
        from eurusd_research.studies.independent_statistics import rank_correlation

        comparison_records.append(
            {
                "profile": profile,
                "eligible_daily_observations": len(selected),
                "date_start": selected["utc_date"].min(),
                "date_end": selected["utc_date"].max(),
                "weekday_order_high_to_low": "|".join(order),
                "rank_correlation_with_primary": rank_correlation(primary_order, order),
                "kruskal_statistic": tests["statistic"],
                "kruskal_p_value": tests["p_value"],
                "epsilon_squared": effects_expected.loc[
                    effects_expected["profile"].eq(profile)
                    & effects_expected["effect_size_method"].eq("epsilon_squared"),
                    "effect_size",
                ].iloc[0],
                "significant": tests["significant"],
            }
        )
    coverage_expected = pd.DataFrame(comparison_records)
    rating = reconstruct_rating(
        coverage=coverage_expected,
        weekday=weekday_expected,
        periods=periods_expected,
        annual=annual_tests_expected,
        regime_statistics=regime_statistics_expected,
        regime_tests=regime_tests_expected,
        extreme=extreme_expected,
        config=config,
    )
    summary = json.loads((output_directory / "study_summary.json").read_text())
    rating_comparison = _compare_rating_summary(
        rating.production_summary, summary.get("evidence_rating")
    )
    if rating.missing_evidence:
        rating_comparison = FrameComparison(
            rating_comparison.checked_rows,
            rating_comparison.checked_fields,
            rating_comparison.absolute,
            rating_comparison.relative,
            rating_comparison.categorical_mismatches,
            rating_comparison.membership_mismatches,
            rating_comparison.examples,
            rating.missing_evidence,
        )

    inspection = inspect_output_inventory(
        output_directory,
        canonical_registered_output_paths(
            config.expected_output_files,
            config.expected_figure_files,
        ),
    )
    inventory_mismatches = (
        len(inspection.missing_paths)
        + len(inspection.extra_paths)
        + len(inspection.duplicate_normalized_paths)
        + len(inspection.unsafe_paths)
    )
    byte_identity: CandidateByteIdentityEvidence | None = None
    if validated_candidate_identity is not None and inventory_mismatches == 0:
        comparison = compare_output_to_validated_identity(
            output_directory,
            validated_candidate_identity,
            registration_version=config.registration_version,
            method_version=config.method_version,
            anchor_commit=anchor_commit,
            receipt_fingerprint=receipt_fingerprint,
        )
        inventory_mismatches += comparison.mismatch_count
        byte_identity = CandidateByteIdentityEvidence(
            validated_candidate_identity_fingerprint=(
                validated_candidate_identity.identity_fingerprint
            ),
            baseline_candidate_digest=(
                validated_candidate_identity.output_digest.path_plus_bytes_digest
            ),
            current_candidate_digest=(
                comparison.current_output_digest.path_plus_bytes_digest
            ),
            baseline_files=validated_candidate_identity.output_digest.files,
            current_files=comparison.current_output_digest.files,
            missing_paths=comparison.missing_paths,
            extra_paths=comparison.extra_paths,
            size_mismatch_paths=comparison.size_mismatch_paths,
            sha256_mismatch_paths=comparison.sha256_mismatch_paths,
            byte_identity_mismatch_paths=comparison.byte_identity_mismatch_paths,
            digest_mismatch=comparison.digest_mismatch,
            baseline_identity_mismatch=comparison.baseline_identity_mismatch,
            passed=comparison.reconciled,
        )
    inventory_comparison = FrameComparison(
        len(inspection.records),
        max(1, len(inspection.records) * 7),
        {},
        {},
        0,
        0,
        tuple(
            (
                *inspection.missing_paths,
                *inspection.extra_paths,
                *inspection.unsafe_paths,
            )
        )[:20],
        (),
    )

    components = {
        "source_population": _component(
            "source_population",
            source_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "daily_aggregation": _component(
            "daily_aggregation",
            daily_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "descriptive_statistics": _component(
            "descriptive_statistics",
            descriptive_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "primary_inference": _component(
            "primary_inference",
            inference_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "pairwise_analysis": _component(
            "pairwise_analysis",
            pairwise_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "chronological_analysis": _component(
            "chronological_analysis",
            chronological_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "fixed_period_analysis": _component(
            "fixed_period_analysis",
            fixed_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "annual_analysis": _component(
            "annual_analysis",
            annual_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "volatility_regime_analysis": _component(
            "volatility_regime_analysis",
            regime_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "extreme_event_analysis": _component(
            "extreme_event_analysis",
            extreme_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "evidence_rating": _component(
            "evidence_rating",
            rating_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "output_inventory": _component(
            "output_inventory",
            inventory_comparison,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
            inventory_mismatches=inventory_mismatches,
        ),
    }
    missing = tuple(
        value
        for component in components.values()
        for value in component.missing_evidence
    )
    unsupported = tuple(
        value
        for component in components.values()
        for value in component.unsupported_claims
    )
    baseline_eligible = all(item.passed for item in components.values())
    baseline_missing = (
        () if byte_identity is not None else ("validated_candidate_identity",)
    )
    payload: dict[str, Any] = {
        "schema_version": "task04-independent-reconciliation-v3",
        "implementation_id": INDEPENDENT_RECONCILIATION_IMPLEMENTATION,
        "study_id": "TASK-04",
        "registration_version": config.registration_version,
        "method_version": config.method_version,
        "anchor_commit": anchor_commit,
        "receipt_fingerprint": receipt_fingerprint,
        "raw_sha256": raw_sha,
        "task03_evidence_fingerprint": task03_fingerprint,
        "production_output_digest": production_output_digest,
        "baseline_establishment_eligible": baseline_eligible,
        "candidate_byte_identity": (
            None if byte_identity is None else byte_identity.model_dump(mode="json")
        ),
        "tolerance_policy": "ABSOLUTE_AND_RELATIVE_WITH_ZERO_CATEGORICAL_TOLERANCE",
        "checked_components": list(RECONCILIATION_COMPONENTS),
        **{
            name: component.model_dump(mode="json")
            for name, component in components.items()
        },
        "independent_rating_decisions": [
            {
                "dimension": item.dimension,
                "registered_threshold": item.registered_threshold,
                "independent_input": item.independent_input,
                "passed": item.passed,
                "effect_on_rating": item.effect_on_rating,
                "missing_evidence_rule": item.missing_evidence_rule,
            }
            for item in rating.decisions
        ],
        "primary_population": int(primary["analysis_eligible"].sum()),
        "checked_row_count": sum(
            item.checked_row_count for item in components.values()
        ),
        "checked_field_count": sum(
            item.checked_field_count for item in components.values()
        ),
        "categorical_mismatch_count": sum(
            item.categorical_mismatch_count for item in components.values()
        ),
        "membership_mismatch_count": sum(
            item.membership_mismatch_count for item in components.values()
        ),
        "inventory_mismatch_count": sum(
            item.inventory_mismatch_count for item in components.values()
        ),
        "missing_evidence": list((*missing, *baseline_missing)),
        "unsupported_claims": list(unsupported),
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "maximum_numerical_discrepancy": max(
            item.maximum_absolute_discrepancy for item in components.values()
        ),
        "passed": all(item.passed for item in components.values())
        and byte_identity is not None
        and byte_identity.passed
        and not missing
        and not unsupported,
    }
    return IndependentReconciliationEvidence.model_validate(
        {**payload, "artifact_fingerprint": canonical_digest(payload)}
    )
