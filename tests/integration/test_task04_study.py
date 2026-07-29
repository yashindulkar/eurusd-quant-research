from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from scipy import stats

from eurusd_research.data.registry import sha256_file
from eurusd_research.paths import find_repository_root
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.dependencies import (
    validate_task04_dependencies,
)
from eurusd_research.studies.task04 import generate_task04_study


@pytest.mark.integration
def test_task04_v23_stops_before_calculation_without_anchor_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = find_repository_root()
    raw = root / "data/raw/EURUSD_M15_UTC.csv"
    before = (sha256_file(raw), raw.stat().st_mtime_ns)
    output = tmp_path / "task04"
    called = False

    def forbidden_calculation(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("Task 04 calculation crossed the anchor boundary")

    monkeypatch.setattr(
        "eurusd_research.studies.task04.aggregate_daily_profiles",
        forbidden_calculation,
    )
    with pytest.raises(FileNotFoundError, match="receipt not found"):
        generate_task04_study(root, output)
    assert not called
    assert not output.exists()
    assert before == (sha256_file(raw), raw.stat().st_mtime_ns)


@pytest.mark.integration
def test_v22_historical_numerical_evidence_remains_unchanged() -> None:
    root = find_repository_root()
    output = root / "reports" / "research" / "task04_daily_range_weekday"
    summary = json.loads((output / "study_summary.json").read_text(encoding="utf-8"))
    assert summary["study"]["registration_version"] == "2.2"
    assert summary["population"]["raw_rows"] == 406_945
    assert summary["population"]["primary_eligible_dates"] == 4_127
    assert summary["evidence_rating"]["rating"] == "MODERATE"
    daily = pd.read_csv(output / "daily_observations.csv")
    assert len(daily) == daily["utc_date"].nunique() == 5_146
    assert tuple(daily["weekday_name"].drop_duplicates().head(5)) != ()
    assert daily["raw_sha256"].eq(summary["raw_checksum_before"]).all()
    primary = daily.loc[daily["primary_profile_eligible"]]
    groups = [
        primary.loc[primary["weekday_name"].eq(weekday), "daily_range_pips"].to_numpy()
        for weekday in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
    ]
    recomputed = stats.kruskal(*groups)
    assert recomputed.statistic == pytest.approx(
        summary["primary_result"]["kruskal_statistic"],
        rel=1e-14,
    )
    assert recomputed.pvalue == pytest.approx(
        summary["primary_result"]["kruskal_p_value"],
        rel=1e-14,
    )
    population = pd.read_csv(output / "population_reconciliation.csv")
    profile_rows = population.loc[
        population["metric"].eq("profile_source_rows")
    ].set_index("profile")["value"]
    assert profile_rows.to_dict() == {
        "DEFAULT_RESEARCH": 406_945,
        "STRICT_CONTINUITY": 360_477,
        "SENSITIVITY_FULL": 46_468,
        "SENSITIVITY_2023": 9_258,
    }
    zero_dates = population.loc[
        population["metric"].eq("zero_contribution_dates")
    ].set_index("profile")["value"]
    assert zero_dates.to_dict() == {
        "DEFAULT_RESEARCH": 0,
        "STRICT_CONTINUITY": 621,
        "SENSITIVITY_FULL": 4_465,
        "SENSITIVITY_2023": 4_990,
    }
    for prefix in (
        "default_research",
        "strict_continuity",
        "sensitivity_full",
        "sensitivity_2023",
    ):
        assert daily[f"{prefix}_observed_m15_rows"].notna().all()
        assert len(daily[f"{prefix}_observed_m15_rows"]) == 5_146
    strict_zero = daily["strict_continuity_observed_m15_rows"].eq(0)
    assert int(strict_zero.sum()) == 621
    assert daily.loc[strict_zero, "strict_continuity_daily_range_pips"].isna().all()
    assert len(pd.read_csv(output / "pairwise_tests.csv")) == 40
    effects = pd.read_csv(output / "effect_sizes.csv")
    assert {"epsilon_squared", "eta_squared", "omega_squared", "cliffs_delta"}.issubset(
        set(effects["effect_size_method"])
    )
    split = pd.read_csv(output / "chronological_split_results.csv")
    assert {
        "significant_pairs",
        "primary_significant_pairs_retained",
    }.issubset(split.columns)
    figures = sorted((output / "figures").glob("*.png"))
    assert len(figures) == 8
    assert all(path.stat().st_size > 10_000 for path in figures)
    assert summary["raw_checksum_before"] == summary["raw_checksum_after"]
    regimes = pd.read_csv(output / "volatility_regime_lineage.csv")
    assert len(regimes) == 4_127
    assert int(regimes["regime_warmup"].sum()) == 180
    assert regimes.loc[~regimes["regime_warmup"], "utc_date"].iloc[0] == "2010-09-14"
    assert (
        regimes["method_version"].eq("range-weekday-registered-replication-v2.2").all()
    )
    degrees = pd.read_csv(output / "omnibus_tests.csv")
    primary_welch = degrees.loc[
        degrees["profile"].eq("DEFAULT_RESEARCH")
        & degrees["test_name"].eq("welch_anova")
    ].iloc[0]
    assert primary_welch["denominator_degrees_of_freedom"] > 0


@pytest.mark.integration
def test_task04_dependency_validation_fails_closed() -> None:
    root = find_repository_root()
    config = load_task04_config(root)
    coverage_summary, raw_manifest = validate_task04_dependencies(root, config)
    assert coverage_summary["lineage"]["raw_sha256"] == config.required_raw_sha256
    assert raw_manifest["sha256"] == config.required_raw_sha256
    stale = config.model_copy(update={"required_coverage_summary_sha256": "b" * 64})
    with pytest.raises(ValueError, match="coverage summary fingerprint is stale"):
        validate_task04_dependencies(root, stale)

    missing = config.model_copy(
        update={"coverage_summary_path": Path("reports/coverage/missing.json")}
    )
    with pytest.raises(FileNotFoundError):
        validate_task04_dependencies(root, missing)

    mutations = (
        (
            {"required_raw_manifest_sha256": "b" * 64},
            "raw manifest fingerprint",
        ),
        ({"required_raw_sha256": "b" * 64}, "raw SHA-256"),
        (
            {"required_task02_audit_fingerprint": "b" * 64},
            "Task 02 audit fingerprint",
        ),
        (
            {"primary_coverage_profile": "ABSENT_PROFILE"},
            "lacks a required profile",
        ),
        (
            {"required_source_dependency_manifest_fingerprint": "b" * 64},
            "source dependency manifest",
        ),
        (
            {"required_environment_lock_fingerprint": "b" * 64},
            "environment lock",
        ),
        (
            {"required_task03_row_membership_fingerprint": "b" * 64},
            "row-membership evidence",
        ),
    )
    for update, message in mutations:
        with pytest.raises(ValueError, match=message):
            validate_task04_dependencies(root, config.model_copy(update=update))
