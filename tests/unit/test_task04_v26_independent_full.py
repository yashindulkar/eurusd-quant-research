from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from eurusd_research.paths import find_repository_root
from eurusd_research.studies.completion import ComponentDiscrepancy
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.independent_daily import (
    _one_profile,
    _schedule,
    rebuild_daily_profiles,
)
from eurusd_research.studies.independent_inventory import (
    InventoryInspection,
    InventoryRecord,
    inspect_output_inventory,
)
from eurusd_research.studies.independent_rating import (
    IndependentRating,
    RatingDecision,
    reconstruct_rating,
)
from eurusd_research.studies.independent_reconciliation import (
    _compare_rating_summary,
    _population_table,
    build_independent_reconciliation,
    compare_frames,
)
from eurusd_research.studies.independent_robustness import (
    annual_tables,
    chronological_tables,
    coverage_profile_tables,
    extreme_table,
    regime_tables,
)
from eurusd_research.studies.independent_statistics import (
    descriptive_table,
    holm_adjust,
    omnibus_table,
    pairwise_table,
)
from eurusd_research.studies.reconciliation_schema import DAILY_PROFILE_OUTPUT_COLUMNS

ROOT = find_repository_root()
HISTORICAL = ROOT / "reports/research/task04_daily_range_weekday"


@pytest.fixture(scope="module")
def config():
    return load_task04_config(ROOT)


@pytest.fixture(scope="module")
def historical_primary() -> pd.DataFrame:
    daily = pd.read_csv(HISTORICAL / "daily_observations.csv")
    selected = daily.loc[daily["primary_profile_eligible"]].copy()
    selected["analysis_eligible"] = True
    return selected


def test_independent_modules_do_not_import_task04_production_implementations() -> None:
    forbidden = {
        "eurusd_research.studies.daily_aggregation",
        "eurusd_research.studies.statistics",
        "eurusd_research.studies.robustness",
        "eurusd_research.studies.task04",
    }
    for name in (
        "independent_daily.py",
        "independent_statistics.py",
        "independent_robustness.py",
        "independent_rating.py",
        "independent_inventory.py",
        "independent_reconciliation.py",
    ):
        tree = ast.parse((ROOT / "src/eurusd_research/studies" / name).read_text())
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert not (forbidden & imported), name


def test_full_reconciliation_orchestration_calculates_every_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config
) -> None:
    """Exercise the full fail-closed orchestration with independent fixtures."""
    from eurusd_research.studies import independent_reconciliation as module

    profiles = (
        "DEFAULT_RESEARCH",
        "STRICT_CONTINUITY",
        "SENSITIVITY_FULL",
        "SENSITIVITY_2023",
    )
    daily_record = {
        "utc_date": "2020-01-06",
        "weekday_number": 0,
        "weekday_name": "Monday",
        "daily_open": 1.0,
        "daily_high": 1.001,
        "daily_low": 1.0,
        "daily_close": 1.001,
        "daily_range_price": 0.001,
        "daily_range_pips": 10.0,
        "first_timestamp_utc": "2020-01-06T00:00:00Z",
        "last_timestamp_utc": "2020-01-06T00:15:00Z",
        "observed_m15_rows": 2,
        "expected_m15_rows": 2,
        "observed_coverage_ratio": 1.0,
        "first_expected_interval_present": True,
        "last_expected_interval_present": True,
        "continuous_expected_grid": True,
        "is_weekday": True,
        "is_weekend_date": False,
        "is_boundary_date": False,
        "is_partial_daily_observation": False,
        "analysis_eligible": True,
        "exclusion_reasons": "",
        "first_raw_row_number": 1,
        "last_raw_row_number": 2,
        "contributing_raw_row_count": 2,
        "contributing_rows_sha256": "a" * 64,
        "expected_schedule_source": "fixture",
        "zero_contribution": False,
        "nonzero_partial": False,
        "incomplete": False,
        "complete": True,
        "dataset_version": "fixture",
        "raw_sha256": "b" * 64,
        "audit_fingerprint": "c" * 64,
        "coverage_fingerprint": "d" * 64,
        "coverage_config_fingerprint": "e" * 64,
        "task04_config_fingerprint": "f" * 64,
        "preregistration_fingerprint": "1" * 64,
        "method_id": "RANGE-WEEKDAY-001",
        "method_version": "range-weekday-registered-replication-v2.9",
        "repository_version": "fixture",
    }
    frames = {
        profile: pd.DataFrame(
            [
                {
                    **daily_record,
                    "profile": profile,
                }
            ],
            columns=DAILY_PROFILE_OUTPUT_COLUMNS,
        )
        for profile in profiles
    }
    population = pd.DataFrame(
        [{"profile": "RAW", "metric": "total_raw_rows", "weekday": "", "value": 1}]
    )
    weekday = pd.DataFrame(
        [
            {
                "profile": profile,
                "analysis_scope": "full_eligible_sample",
                "weekday_name": "Monday",
                "sample_size": 1,
            }
            for profile in profiles
        ]
    )
    omnibus = pd.DataFrame(
        [
            {
                "profile": profile,
                "analysis_scope": "full_eligible_sample",
                "test_name": "kruskal_wallis",
                "statistic": 1.0,
                "p_value": 0.1,
                "significant": False,
            }
            for profile in profiles
        ]
    )
    effects = pd.DataFrame(
        [
            {
                "profile": profile,
                "analysis_scope": "full_eligible_sample",
                "comparison": "Monday-Friday",
                "effect_size_method": "epsilon_squared",
                "effect_size": 0.01,
            }
            for profile in profiles
        ]
    )
    pairwise = pd.DataFrame(
        [
            {
                "profile": "DEFAULT_RESEARCH",
                "analysis_scope": "full_eligible_sample",
                "weekday_a": "Monday",
                "weekday_b": "Tuesday",
                "p_value": 0.5,
            }
        ]
    )
    periods = pd.DataFrame(
        [
            {"analysis_period": name, "value": float(index)}
            for index, name in enumerate(
                (
                    "full_eligible_sample",
                    "pre_2020",
                    "covid_era",
                    "post_2021",
                    "development_70",
                    "validation_30",
                )
            )
        ]
    )
    split = periods.loc[
        periods["analysis_period"].isin(("development_70", "validation_30"))
    ].reset_index(drop=True)
    annual_statistics = pd.DataFrame(
        [{"year": 2020, "weekday_name": "Monday", "median": 10.0}]
    )
    annual_tests = pd.DataFrame([{"year": 2020, "p_value": 0.1}])
    regime_statistics = pd.DataFrame(
        [
            {"volatility_regime": regime, "weekday_name": "Monday", "median": 10.0}
            for regime in ("LOW", "MEDIUM", "HIGH")
        ]
    )
    regime_tests = pd.DataFrame(
        [
            {
                "volatility_regime": regime,
                "test_name": "kruskal_wallis",
                "p_value": 0.1,
            }
            for regime in ("LOW", "MEDIUM", "HIGH")
        ]
    )
    lineage = pd.DataFrame(
        [
            {
                "utc_date": "2020-01-06",
                "profile": "DEFAULT_RESEARCH",
                "daily_range_pips": 10.0,
                "lagged_trailing_median_range_pips": None,
                "prior_regime_measure_count": 0,
                "past_only_low_threshold": None,
                "past_only_high_threshold": None,
                "volatility_regime": "WARMUP",
                "regime_warmup": True,
                "regime_classification_reason": "insufficient_history",
                "volatility_lookback": 180,
                "volatility_minimum_history": 180,
                "dataset_version": "fixture",
                "raw_sha256": "b" * 64,
                "audit_fingerprint": "c" * 64,
                "coverage_fingerprint": "d" * 64,
                "coverage_config_fingerprint": "e" * 64,
                "task04_config_fingerprint": "f" * 64,
                "preregistration_fingerprint": "1" * 64,
                "method_id": "RANGE-WEEKDAY-001",
                "method_version": "range-weekday-registered-replication-v2.9",
                "repository_version": "fixture",
            }
        ]
    )
    extreme = pd.DataFrame(
        [{"analysis_variant": "primary_raw_distribution", "sample_size": 1}]
    )

    monkeypatch.setattr(
        module,
        "rebuild_daily_profiles",
        lambda *_args, **_kwargs: (
            frames,
            pd.DataFrame([{"utc_date": "2020-01-06"}]),
            pd.DataFrame({profile: [True] for profile in profiles}),
            "a" * 64,
            "b" * 64,
        ),
    )
    monkeypatch.setattr(module, "_population_table", lambda *_args: population)
    monkeypatch.setattr(
        module,
        "coverage_profile_tables",
        lambda *_args: (weekday, omnibus, pairwise, effects),
    )
    monkeypatch.setattr(module, "chronological_tables", lambda *_args: (periods, split))
    monkeypatch.setattr(
        module,
        "annual_tables",
        lambda *_args: (annual_statistics, annual_tests),
    )
    monkeypatch.setattr(
        module,
        "regime_tables",
        lambda *_args: (regime_statistics, regime_tests, lineage),
    )
    monkeypatch.setattr(module, "extreme_table", lambda *_args: extreme)
    monkeypatch.setattr(
        module,
        "weekday_order",
        lambda *_args: ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"),
    )
    monkeypatch.setattr(
        module,
        "reconstruct_rating",
        lambda **_kwargs: IndependentRating(
            "MODERATE",
            "MODERATE",
            "MODERATE",
            (
                RatingDecision(
                    "primary_significance", "alpha=0.05", "p=0.01", True, "pass"
                ),
            ),
            (),
            {"rating": "MODERATE"},
        ),
    )
    record = InventoryRecord("artifact.csv", 1, "c" * 64, True, False, 1, True)
    monkeypatch.setattr(
        module,
        "inspect_output_inventory",
        lambda *_args: InventoryInspection(
            ("artifact.csv",),
            ("artifact.csv",),
            (),
            (),
            (),
            (),
            (record,),
            "d" * 64,
        ),
    )

    output = tmp_path / "candidate"
    output.mkdir()
    population.to_csv(output / "population_reconciliation.csv", index=False)
    pd.concat(frames.values(), ignore_index=True).to_csv(
        output / "daily_profile_observations.csv", index=False
    )
    weekday.to_csv(output / "weekday_statistics.csv", index=False)
    omnibus.to_csv(output / "omnibus_tests.csv", index=False)
    pairwise.to_csv(output / "pairwise_tests.csv", index=False)
    effects.to_csv(output / "effect_sizes.csv", index=False)
    periods.to_csv(output / "period_robustness.csv", index=False)
    split.to_csv(output / "chronological_split_results.csv", index=False)
    annual_statistics.to_csv(output / "yearly_statistics.csv", index=False)
    annual_tests.to_csv(output / "yearly_omnibus_tests.csv", index=False)
    regime_statistics.to_csv(output / "volatility_regime_statistics.csv", index=False)
    regime_tests.to_csv(output / "volatility_regime_tests.csv", index=False)
    lineage.to_csv(output / "volatility_regime_lineage.csv", index=False)
    extreme.to_csv(output / "extreme_event_sensitivity.csv", index=False)
    (output / "study_summary.json").write_text(
        '{"evidence_rating":{"rating":"MODERATE"}}\n', encoding="utf-8"
    )

    evidence = build_independent_reconciliation(
        ROOT,
        output,
        config=config,
        anchor_commit="1" * 40,
        receipt_fingerprint="2" * 64,
        production_output_digest="3" * 64,
        absolute_tolerance=1e-10,
        relative_tolerance=1e-10,
    )
    assert evidence.baseline_establishment_eligible, [
        (name, getattr(evidence, name).model_dump())
        for name in evidence.checked_components
        if not getattr(evidence, name).passed
    ]
    assert not evidence.passed
    assert evidence.missing_evidence == ("validated_candidate_identity",)
    assert evidence.checked_components == (
        "source_population",
        "daily_aggregation",
        "descriptive_statistics",
        "primary_inference",
        "pairwise_analysis",
        "chronological_analysis",
        "fixed_period_analysis",
        "annual_analysis",
        "volatility_regime_analysis",
        "extreme_event_analysis",
        "evidence_rating",
        "output_inventory",
    )
    assert all(getattr(evidence, name).passed for name in evidence.checked_components)


def test_v29_scientific_design_is_identical_to_v28() -> None:
    v28 = yaml.safe_load(
        (ROOT / "studies/task04_daily_range_weekday.v2.8.yaml").read_text()
    )
    v29 = yaml.safe_load(
        (ROOT / "studies/task04_daily_range_weekday.v2.9.yaml").read_text()
    )
    scientific_fields = (
        "research_question",
        "primary_null_hypothesis",
        "primary_alternative_hypothesis",
        "secondary_hypotheses",
        "primary_outcome",
        "unit_of_analysis",
        "calendar_definition",
        "weekday_definition",
        "timestamp_semantics",
        "primary_coverage_profile",
        "sensitivity_profiles",
        "daily_completeness_rule",
        "boundary_period_policy",
        "descriptive_statistics",
        "statistical_conventions",
        "primary_statistical_test",
        "post_hoc_test",
        "multiple_testing_correction",
        "effect_size_measures",
        "confidence_interval_method",
        "normality_diagnostic",
        "variance_diagnostic",
        "robustness_analyses",
        "volatility_regime_definition",
        "chronological_stability_design",
        "missing_data_policy",
        "exclusion_policy",
        "deterministic_seed_policy",
        "evidence_rating",
        "known_limitations",
        "prohibited_analyses",
    )
    assert {field: v29[field] for field in scientific_fields} == {
        field: v28[field] for field in scientific_fields
    }


def test_independent_daily_aggregation_uses_mask_before_ohlc_and_retains_zero_date(
    config,
) -> None:
    timestamps = pd.to_datetime(
        ["2020-01-06T00:00:00Z", "2020-01-06T00:15:00Z"], utc=True
    )
    raw = pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "utc_date": ["2020-01-06", "2020-01-06"],
            "open": [1.10, 9.0],
            "high": [1.11, 9.5],
            "low": [1.09, 0.1],
            "close": [1.105, 9.2],
            "raw_row_number": [2, 3],
        }
    )
    schedule = pd.DataFrame(
        {
            "utc_date": ["2020-01-06", "2020-01-07"],
            "expected_first_timestamp_utc": [
                timestamps[0],
                pd.Timestamp("2020-01-07", tz="UTC"),
            ],
            "expected_last_timestamp_utc": [
                timestamps[0],
                pd.Timestamp("2020-01-07", tz="UTC"),
            ],
            "expected_m15_rows": [1, 1],
            "expected_schedule_source": ["synthetic", "synthetic"],
        }
    )
    result = _one_profile(
        raw,
        pd.Series([True, False]),
        schedule,
        "DEFAULT_RESEARCH",
        config,
    ).set_index("utc_date")
    assert result.loc["2020-01-06", "daily_high"] == 1.11
    assert result.loc["2020-01-06", "daily_low"] == 1.09
    assert result.loc["2020-01-06", "daily_range_pips"] == pytest.approx(200.0)
    assert bool(result.loc["2020-01-07", "zero_contribution"])
    assert pd.isna(result.loc["2020-01-07", "daily_open"])


def test_independent_source_population_rebuilds_from_raw_and_exact_masks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config
) -> None:
    from eurusd_research.studies import independent_daily as module

    raw_path = tmp_path / "data/raw/EURUSD_M15_UTC.csv"
    raw_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "timestamp_utc": [
                "2020-01-06T00:00:00Z",
                "2020-01-07T00:00:00Z",
            ],
            "open": [1.10, 1.20],
            "high": [1.11, 1.21],
            "low": [1.09, 1.19],
            "close": [1.105, 1.205],
        }
    ).to_csv(raw_path, index=False)
    gaps_path = tmp_path / "reports/audits/timestamp_gaps.csv"
    gaps_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "preliminary_category": ["likely_weekly_closure"],
            "timestamp_before": ["2020-01-10T21:45:00Z"],
            "timestamp_after": ["2020-01-12T22:00:00Z"],
        }
    ).to_csv(gaps_path, index=False)
    masks = pd.DataFrame(
        {
            "DEFAULT_RESEARCH": [True, True],
            "STRICT_CONTINUITY": [True, True],
            "SENSITIVITY_FULL": [False, False],
            "SENSITIVITY_2023": [False, False],
        }
    )
    flags = pd.DataFrame(
        {
            "utc_date": ["2020-01-06", "2020-01-07"],
            "affected_period_2023": [False, False],
        }
    )
    coverage = SimpleNamespace(
        profile_masks_by_level={"row": masks}, flags_by_level={"row": flags}
    )
    evidence = SimpleNamespace(
        observed_row_count=2,
        observed_date_count=2,
        scientific_membership_fingerprint="b" * 64,
    )
    monkeypatch.setattr(module, "sha256_file", lambda _path: config.required_raw_sha256)
    monkeypatch.setattr(module, "load_config", lambda _root: object())
    monkeypatch.setattr(module, "build_coverage", lambda **_kwargs: coverage)
    monkeypatch.setattr(
        module, "validate_task03_row_membership", lambda *_args, **_kwargs: evidence
    )

    frames, returned_flags, returned_masks, raw_sha, task03_sha = (
        rebuild_daily_profiles(
            tmp_path, config, profiles=("DEFAULT_RESEARCH", "STRICT_CONTINUITY")
        )
    )
    assert tuple(frames) == ("DEFAULT_RESEARCH", "STRICT_CONTINUITY")
    assert all(len(frame) == 2 for frame in frames.values())
    assert returned_flags.equals(flags)
    assert returned_masks.equals(masks)
    assert raw_sha == config.required_raw_sha256
    assert task03_sha == "b" * 64


def test_independent_schedule_uses_audited_friday_and_sunday_boundaries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reports/audits/timestamp_gaps.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "preliminary_category": ["likely_weekly_closure"],
            "timestamp_before": ["2020-01-10T21:45:00Z"],
            "timestamp_after": ["2020-01-12T22:00:00Z"],
        }
    ).to_csv(path, index=False)
    dates = pd.DatetimeIndex(pd.to_datetime(["2020-01-10", "2020-01-12"]))
    result = _schedule(tmp_path, dates).set_index("utc_date")
    assert result.loc["2020-01-10", "expected_m15_rows"] == 88
    assert result.loc["2020-01-12", "expected_m15_rows"] == 8


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("raw_count", "raw population"),
        ("unordered", "timestamps are not ordered"),
        ("date_count", "observed-date count"),
        ("strict_not_default", "STRICT is not a DEFAULT subset"),
        ("strict_overlap", "STRICT overlaps SENSITIVITY_FULL"),
        ("union", "union SENSITIVITY_FULL differs"),
        ("sensitivity_subset", "not a sensitivity subset"),
        ("unknown_profile", "Unknown independent coverage profiles"),
    ],
)
def test_independent_source_population_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config,
    defect: str,
    message: str,
) -> None:
    from eurusd_research.studies import independent_daily as module

    raw_path = tmp_path / "data/raw/EURUSD_M15_UTC.csv"
    raw_path.parent.mkdir(parents=True)
    timestamps = ["2020-01-06T00:00:00Z", "2020-01-07T00:00:00Z"]
    if defect == "unordered":
        timestamps.reverse()
    pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "open": [1.1, 1.2],
            "high": [1.11, 1.21],
            "low": [1.09, 1.19],
            "close": [1.105, 1.205],
        }
    ).to_csv(raw_path, index=False)
    gaps_path = tmp_path / "reports/audits/timestamp_gaps.csv"
    gaps_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "preliminary_category": ["likely_weekly_closure"],
            "timestamp_before": ["2020-01-10T21:45:00Z"],
            "timestamp_after": ["2020-01-12T22:00:00Z"],
        }
    ).to_csv(gaps_path, index=False)
    default = [True, True]
    strict = [True, True]
    sensitivity = [False, False]
    sensitivity_2023 = [False, False]
    if defect == "strict_not_default":
        default, strict = [False, True], [True, True]
    elif defect == "strict_overlap":
        sensitivity = [True, False]
    elif defect == "union":
        strict = [True, False]
    elif defect == "sensitivity_subset":
        sensitivity_2023 = [True, False]
    masks = pd.DataFrame(
        {
            "DEFAULT_RESEARCH": default,
            "STRICT_CONTINUITY": strict,
            "SENSITIVITY_FULL": sensitivity,
            "SENSITIVITY_2023": sensitivity_2023,
        }
    )
    coverage = SimpleNamespace(
        profile_masks_by_level={"row": masks},
        flags_by_level={"row": pd.DataFrame({"utc_date": timestamps})},
    )
    evidence = SimpleNamespace(
        observed_row_count=3 if defect == "raw_count" else 2,
        observed_date_count=3 if defect == "date_count" else 2,
        evidence_fingerprint="b" * 64,
    )
    monkeypatch.setattr(module, "sha256_file", lambda _path: config.required_raw_sha256)
    monkeypatch.setattr(module, "load_config", lambda _root: object())
    monkeypatch.setattr(module, "build_coverage", lambda **_kwargs: coverage)
    monkeypatch.setattr(
        module, "validate_task03_row_membership", lambda *_args, **_kwargs: evidence
    )
    profiles = ("NOT_A_PROFILE",) if defect == "unknown_profile" else ()
    kwargs = {"profiles": profiles} if profiles else {}
    with pytest.raises(ValueError, match=message):
        rebuild_daily_profiles(tmp_path, config, **kwargs)


def test_frame_comparison_records_missing_membership_and_value_defects() -> None:
    expected = pd.DataFrame(
        [{"key": "A", "number": 1.0, "category": "x", "nullable": np.nan}]
    )
    assert compare_frames(
        expected,
        pd.DataFrame([{"key": "A"}]),
        keys=("key",),
        label="missing",
    ).missing
    assert (
        compare_frames(
            expected,
            pd.concat([expected, expected]),
            keys=("key",),
            label="rows",
        ).membership_mismatches
        == 1
    )
    changed = expected.copy()
    changed.loc[0, ["key", "number", "category", "nullable"]] = ["B", 2.0, "y", 1.0]
    comparison = compare_frames(expected, changed, keys=("key",), label="changed")
    assert comparison.membership_mismatches == 1
    assert comparison.categorical_mismatches == 2
    assert comparison.absolute["changed.number"] == 1.0


def test_independent_population_reconciliation_calculates_every_metric(config) -> None:
    profiles = (
        "DEFAULT_RESEARCH",
        "STRICT_CONTINUITY",
        "SENSITIVITY_FULL",
        "SENSITIVITY_2023",
    )
    frames = {
        profile: pd.DataFrame(
            {
                "utc_date": ["2020-01-06", "2020-01-11"],
                "analysis_eligible": [True, False],
                "is_weekday": [True, False],
                "is_weekend_date": [False, True],
                "complete": [True, False],
                "incomplete": [False, True],
                "is_boundary_date": [False, True],
                "zero_contribution": [False, True],
                "nonzero_partial": [False, False],
                "observed_m15_rows": [96, 0],
                "weekday_name": ["Monday", "Saturday"],
            }
        )
        for profile in profiles
    }
    masks = pd.DataFrame({profile: [True, False] for profile in profiles})
    sensitivity_columns = (
        "long_nonweekly_gap_boundary",
        "nonweekend_gap_boundary",
        "unclassified_gap_boundary",
        "continuity_impaired_period",
        "affected_period_2023",
        "partial_boundary_year",
        "partial_boundary_month",
    )
    row_flags = pd.DataFrame(
        {
            "utc_date": ["2020-01-06", "2020-01-11"],
            **{
                column: [column == "affected_period_2023", False]
                for column in sensitivity_columns
            },
        }
    )
    result = _population_table(frames, row_flags, masks, config)
    default = result.loc[result["profile"].eq("DEFAULT_RESEARCH")]
    metrics = default.loc[default["weekday"].eq("")].set_index("metric")["value"]
    assert metrics["complete_dates"] == 1
    assert metrics["incomplete_dates"] == 1
    assert metrics["zero_contribution_dates"] == 1
    assert metrics["nonzero_partial_dates"] == 0
    assert metrics["dates_included_in_analysis"] == 1
    monday = default.loc[
        default["metric"].eq("contributing_m15_rows_by_weekday")
        & default["weekday"].eq("Monday"),
        "value",
    ].iloc[0]
    assert monday == 96


def test_full_descriptive_primary_reproduction(config, historical_primary) -> None:
    expected = descriptive_table(
        historical_primary, config, "DEFAULT_RESEARCH", "complete_weekday_dates"
    )
    actual = pd.read_csv(HISTORICAL / "weekday_statistics.csv")
    actual = actual.loc[actual["profile"].eq("DEFAULT_RESEARCH")]
    comparison = compare_frames(
        expected,
        actual,
        keys=("profile", "analysis_scope", "weekday_name"),
        label="descriptive",
    )
    assert comparison.categorical_mismatches == 0
    assert max(comparison.absolute.values(), default=0.0) < 2e-13


def test_primary_inference_and_pairwise_reproduction(
    config, historical_primary
) -> None:
    tests, effects = omnibus_table(
        historical_primary, config, "DEFAULT_RESEARCH", "complete_weekday_dates"
    )
    published_tests = pd.read_csv(HISTORICAL / "omnibus_tests.csv")
    published_tests = published_tests.loc[
        published_tests["profile"].eq("DEFAULT_RESEARCH")
    ]
    test_comparison = compare_frames(
        tests,
        published_tests,
        keys=("profile", "analysis_scope", "test_name"),
        label="omnibus",
    )
    assert max(test_comparison.absolute.values(), default=0.0) < 2e-13
    _, _, _, all_effects = coverage_profile_tables(
        {
            profile: historical_primary
            for profile in (
                "DEFAULT_RESEARCH",
                "STRICT_CONTINUITY",
                "SENSITIVITY_FULL",
                "SENSITIVITY_2023",
            )
        },
        config,
    )
    effects = all_effects.loc[all_effects["profile"].eq("DEFAULT_RESEARCH")]
    published_effects = pd.read_csv(HISTORICAL / "effect_sizes.csv")
    published_effects = published_effects.loc[
        published_effects["profile"].eq("DEFAULT_RESEARCH")
    ]
    effect_comparison = compare_frames(
        effects,
        published_effects,
        keys=("profile", "analysis_scope", "comparison", "effect_size_method"),
        label="effects",
    )
    assert effect_comparison.categorical_mismatches == 0
    assert effect_comparison.membership_mismatches == 0
    assert max(effect_comparison.absolute.values(), default=0.0) < 2e-13
    pairwise = pairwise_table(
        historical_primary, config, "DEFAULT_RESEARCH", "complete_weekday_dates"
    )
    published_pairs = pd.read_csv(HISTORICAL / "pairwise_tests.csv")
    published_pairs = published_pairs.loc[
        published_pairs["profile"].eq("DEFAULT_RESEARCH")
    ]
    pair_comparison = compare_frames(
        pairwise,
        published_pairs,
        keys=("profile", "analysis_scope", "weekday_a", "weekday_b"),
        label="pairwise",
    )
    assert pair_comparison.categorical_mismatches == 0
    assert max(pair_comparison.absolute.values(), default=0.0) < 2e-13


def test_holm_equal_values_and_constant_groups(config) -> None:
    assert np.allclose(holm_adjust([0.01, 0.01, 0.5]), [0.03, 0.03, 0.5])
    frame = pd.DataFrame(
        {
            "utc_date": [f"2020-01-{index + 1:02d}" for index in range(10)],
            "weekday_name": list(
                ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
            )
            * 2,
            "daily_range_pips": np.ones(10),
        }
    )
    tests, _ = omnibus_table(frame, config, "DEFAULT_RESEARCH", "constant")
    primary = tests.set_index("test_name").loc["kruskal_wallis"]
    assert primary["statistic"] == 0.0 and primary["p_value"] == 1.0


def test_all_robustness_tables_reproduce_historical_control(
    config, historical_primary
) -> None:
    periods, split = chronological_tables(historical_primary, config)
    annual, annual_tests = annual_tables(historical_primary, config)
    regime_stats, regime_tests, lineage = regime_tables(historical_primary, config)
    extreme = extreme_table(historical_primary, config)
    comparisons = (
        compare_frames(
            periods,
            pd.read_csv(HISTORICAL / "period_robustness.csv"),
            keys=("analysis_period",),
            label="periods",
        ),
        compare_frames(
            split,
            pd.read_csv(HISTORICAL / "chronological_split_results.csv"),
            keys=("analysis_period",),
            label="split",
        ),
        compare_frames(
            annual,
            pd.read_csv(HISTORICAL / "yearly_statistics.csv"),
            keys=("year", "weekday_name"),
            label="annual",
        ),
        compare_frames(
            annual_tests,
            pd.read_csv(HISTORICAL / "yearly_omnibus_tests.csv"),
            keys=("year",),
            label="annual_tests",
        ),
        compare_frames(
            regime_stats,
            pd.read_csv(HISTORICAL / "volatility_regime_statistics.csv"),
            keys=("volatility_regime", "weekday_name"),
            label="regime_stats",
        ),
        compare_frames(
            regime_tests,
            pd.read_csv(HISTORICAL / "volatility_regime_tests.csv"),
            keys=("volatility_regime", "test_name"),
            label="regime_tests",
        ),
        compare_frames(
            lineage,
            pd.read_csv(HISTORICAL / "volatility_regime_lineage.csv"),
            keys=("utc_date",),
            label="regime_lineage",
        ),
        compare_frames(
            extreme,
            pd.read_csv(HISTORICAL / "extreme_event_sensitivity.csv"),
            keys=("analysis_variant",),
            label="extreme",
        ),
    )
    assert all(item.categorical_mismatches == 0 for item in comparisons)
    assert (
        max(value for item in comparisons for value in [0.0, *item.absolute.values()])
        < 1e-12
    )


def test_independent_rating_reproduces_and_missing_is_insufficient(config) -> None:
    tables = {
        name: pd.read_csv(HISTORICAL / filename)
        for name, filename in {
            "coverage": "coverage_profile_comparison.csv",
            "weekday": "weekday_statistics.csv",
            "periods": "period_robustness.csv",
            "annual": "yearly_omnibus_tests.csv",
            "regime_statistics": "volatility_regime_statistics.csv",
            "regime_tests": "volatility_regime_tests.csv",
            "extreme": "extreme_event_sensitivity.csv",
        }.items()
    }
    result = reconstruct_rating(config=config, **tables)
    assert result.rating == "MODERATE"
    assert result.decisions
    published = json.loads(
        (HISTORICAL / "study_summary.json").read_text(encoding="utf-8")
    )["evidence_rating"]
    full_surface = _compare_rating_summary(result.production_summary, published)
    assert full_surface.checked_fields >= 30
    assert full_surface.categorical_mismatches == 0
    assert full_surface.missing == (
        "high_regime_kruskal_p_value",
        "high_regime_significance_role",
        "thresholds.high_regime_significance_role",
        "thresholds.minimum_regime_sample",
    )
    assert max(full_surface.absolute.values(), default=0.0) < 1e-12
    tables["extreme"] = pd.DataFrame()
    assert reconstruct_rating(config=config, **tables).rating == "INSUFFICIENT"


@pytest.mark.parametrize(
    "field",
    [
        "daily_open",
        "daily_range_pips",
        "weekday_name",
        "analysis_eligible",
        "mean",
        "percentile_99",
        "median_ci_upper",
        "kruskal_statistic",
        "unadjusted_p_value",
        "holm_adjusted_p_value",
        "cliffs_delta_a_minus_b",
        "chronological_count",
        "fixed_period_boundary",
        "yearly_sufficiency",
        "volatility_regime",
        "regime_threshold",
        "extreme_tail_count",
        "rating_dimension",
    ],
)
def test_field_level_defect_injection_is_detected(field: str) -> None:
    expected = pd.DataFrame({"id": [1, 2], field: [1.0, 2.0]})
    actual = expected.copy()
    actual.loc[0, field] = 9.0
    comparison = compare_frames(expected, actual, keys=("id",), label=field)
    assert (
        comparison.categorical_mismatches
        or max(comparison.absolute.values(), default=0.0) > 0.0
    )


def test_output_inventory_is_calculated_and_detects_path_byte_and_figure_hash(
    tmp_path: Path,
) -> None:
    output = tmp_path / "candidate"
    (output / "figures").mkdir(parents=True)
    (output / "table.csv").write_bytes(b"a")
    (output / "figures/figure.png").write_bytes(b"png")
    expected = ("figures/figure.png", "table.csv")
    first = inspect_output_inventory(output, expected)
    assert first.reconciled
    first_hashes = {item.relative_path: item.sha256 for item in first.records}
    (output / "table.csv").write_bytes(b"b")
    second = inspect_output_inventory(output, expected)
    assert second.path_plus_bytes_digest != first.path_plus_bytes_digest
    assert {item.relative_path: item.sha256 for item in second.records}[
        "table.csv"
    ] != first_hashes["table.csv"]
    (output / "extra.csv").write_bytes(b"x")
    assert not inspect_output_inventory(output, expected).reconciled
    (output / "extra.csv").unlink()
    figure = output / "figures/figure.png"
    figure.write_bytes(b"changed")
    third = inspect_output_inventory(output, expected)
    assert {item.relative_path: item.sha256 for item in third.records}[
        "figures/figure.png"
    ] != first_hashes["figures/figure.png"]


def test_independent_inventory_rejects_symlink_and_hardlink(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    target = output / "target"
    target.write_bytes(b"x")
    link = output / "link"
    link.symlink_to(target)
    inspection = inspect_output_inventory(output, ("link", "target"))
    assert not inspection.reconciled and "link" in inspection.unsafe_paths
    link.unlink()
    hard = output / "hard"
    os.link(target, hard)
    inspection = inspect_output_inventory(output, ("hard", "target"))
    assert not inspection.reconciled


def test_unchecked_component_cannot_default_to_pass() -> None:
    with pytest.raises(ValidationError):
        ComponentDiscrepancy(
            component="daily_aggregation",
            status="NOT_CHECKED",
            checked_row_count=0,
            checked_field_count=0,
            absolute_discrepancy_by_field={},
            relative_discrepancy_by_field={},
            maximum_absolute_discrepancy=0.0,
            maximum_relative_discrepancy=0.0,
            categorical_mismatch_count=0,
            membership_mismatch_count=0,
            inventory_mismatch_count=0,
            mismatch_examples=(),
            missing_evidence=(),
            unsupported_claims=(),
            passed=True,
        )


def test_rating_reconciliation_checks_every_nested_summary_dimension() -> None:
    expected = {
        "rating": "MODERATE",
        "moderate_checks": {"primary_significant": True},
        "strong_checks": {"timestamp_semantics_resolved": False},
        "fixed_period_rank_correlations": [1.0, 0.7, 0.9],
        "thresholds": {"minimum_rank_correlation": 0.6},
    }
    matched = _compare_rating_summary(expected, expected)
    assert matched.checked_fields == 7
    assert not matched.categorical_mismatches
    assert not matched.membership_mismatches
    altered = json.loads(json.dumps(expected))
    altered["moderate_checks"]["primary_significant"] = False
    mismatch = _compare_rating_summary(expected, altered)
    assert mismatch.categorical_mismatches == 1
    missing = json.loads(json.dumps(expected))
    del missing["strong_checks"]["timestamp_semantics_resolved"]
    missing_comparison = _compare_rating_summary(expected, missing)
    assert missing_comparison.membership_mismatches == 1
