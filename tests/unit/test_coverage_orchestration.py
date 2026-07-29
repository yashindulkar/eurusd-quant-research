from __future__ import annotations

import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from eurusd_research.config import CoverageConfig, load_config
from eurusd_research.data.registry import DatasetManifest, read_manifest
from eurusd_research.paths import find_repository_root
from eurusd_research.research.coverage import (
    _load_evidence,
    _read_json,
    _repository_version,
    _stable_digest,
    _validate_audit_contract,
    render_coverage_markdown,
)


def _production_contract() -> tuple[
    dict[str, Any],
    DatasetManifest,
    pd.DataFrame,
    pd.DataFrame,
    Any,
]:
    root = find_repository_root()
    config = load_config(root)
    audit = _read_json(root / config.coverage.audit_result_path)
    manifest = read_manifest(root / config.data.registered_manifest_path)
    gaps = pd.read_csv(root / config.coverage.audit_gap_table_path)
    monthly = pd.read_csv(root / config.coverage.audit_monthly_table_path)
    return audit, manifest, gaps, monthly, config


def test_audit_contract_accepts_consistent_task02_evidence() -> None:
    audit, manifest, gaps, monthly, config = _production_contract()
    _validate_audit_contract(audit, manifest, gaps, monthly, config)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda a, g, m: g.drop(columns="timestamp_before"), "gap artifact"),
        (lambda a, g, m: m.drop(columns="month"), "monthly artifact"),
        (
            lambda a, g, m: a["audit_metadata"].update(
                {"audit_method_version": "old-audit"}
            ),
            "method version",
        ),
        (
            lambda a, g, m: a["audit_metadata"]["effective_thresholds"].update(
                {"cadence_minutes": 30}
            ),
            "thresholds",
        ),
        (
            lambda a, g, m: a["dataset_identity"].update({"sha256_after": "b" * 64}),
            "SHA-256",
        ),
        (
            lambda a, g, m: a["dataset_identity"].update(
                {"dataset_version": "sha256:" + "b" * 16}
            ),
            "dataset version",
        ),
        (
            lambda a, g, m: a["dataset_identity"].update(
                {"raw_unchanged_during_audit": False}
            ),
            "identity reconciliation",
        ),
        (lambda a, g, m: a.update({"failures": ["fatal"]}), "fatal findings"),
        (
            lambda a, g, m: a["final_readiness_assessment"].update(
                {"state": "NOT_READY"}
            ),
            "readiness",
        ),
        (
            lambda a, g, m: a["schema_results"].update({"row_count": 1}),
            "row identity",
        ),
        (
            lambda a, g, m: a["timestamp_results"].update(
                {"last_timestamp": "2020-01-01T00:00:00Z"}
            ),
            "timestamp bounds",
        ),
        (
            lambda a, g, m: a["audit_metadata"].update(
                {"audit_timestamp_utc": "2000-01-01T00:00:00Z"}
            ),
            "predates",
        ),
        (
            lambda a, g, m: a["gap_summary"].update({"gap_count": 1}),
            "gap artifact count",
        ),
        (
            lambda a, g, m: g.assign(
                preliminary_category=g["preliminary_category"].mask(
                    g.index == 0, "unclassified"
                )
            ),
            "gap categories",
        ),
        (
            lambda a, g, m: a["gap_summary"].update(
                {"estimated_missing_m15_timestamps": 1}
            ),
            "missing-timestamp total",
        ),
        (
            lambda a, g, m: a["partial_period_results"].update(
                {"continuity_impaired_months": []}
            ),
            "continuity-impaired months",
        ),
        (
            lambda a, g, m: a["partial_period_results"].update({"boundary_months": []}),
            "boundary months",
        ),
        (
            lambda a, g, m: m.drop(index=1).reset_index(drop=True),
            "monthly artifact row count",
        ),
        (
            lambda a, g, m: m.assign(bar_count=m["bar_count"].mask(m.index == 0, 1)),
            "monthly artifact is stale",
        ),
        (
            lambda a, g, m: a["continuity_investigation_2023"].update(
                {"concentrated_2023_period": None}
            ),
            "no computed 2023",
        ),
        (
            lambda a, g, m: a["continuity_investigation_2023"][
                "concentrated_2023_period"
            ].update({"first_timestamp_before": "2000-01-01T00:00:00Z"}),
            "affected-period bounds",
        ),
    ],
)
def test_audit_contract_rejects_inconsistent_or_stale_evidence(
    mutation: Any, message: str
) -> None:
    audit, manifest, gaps, monthly, config = _production_contract()
    audit = deepcopy(audit)
    changed = mutation(audit, gaps.copy(), monthly.copy())
    selected_gaps = (
        changed
        if isinstance(changed, pd.DataFrame)
        and tuple(changed.columns) == tuple(gaps.columns)
        and "monthly" not in message
        else gaps
    )
    selected_monthly = (
        changed
        if isinstance(changed, pd.DataFrame)
        and (tuple(changed.columns) == tuple(monthly.columns) or "monthly" in message)
        else monthly
    )
    if "gap artifact" in message and isinstance(changed, pd.DataFrame):
        selected_gaps = changed
    with pytest.raises(ValueError, match=message):
        _validate_audit_contract(
            audit, manifest, selected_gaps, selected_monthly, config
        )


def test_missing_task02_artifact_fails_closed() -> None:
    root = find_repository_root()
    config = load_config(root)
    coverage = config.coverage.model_copy(
        update={"audit_gap_table_path": Path("reports/audits/missing.csv")}
    )
    changed = config.model_copy(update={"coverage": coverage})
    with pytest.raises(FileNotFoundError):
        _load_evidence(root, changed)


def test_stale_task02_fingerprint_fails_closed() -> None:
    root = find_repository_root()
    config = load_config(root)
    coverage = config.coverage.model_copy(
        update={"required_audit_gap_table_sha256": "b" * 64}
    )
    changed = config.model_copy(update={"coverage": coverage})
    with pytest.raises(ValueError, match="gap artifact fingerprint is stale"):
        _load_evidence(root, changed)


def test_json_reader_and_digest(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text('{"b": 2, "a": 1}', encoding="utf-8")
    assert _read_json(valid) == {"a": 1, "b": 2}
    assert _stable_digest({"a": 1, "b": 2}) == _stable_digest({"b": 2, "a": 1})

    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        _read_json(invalid)
    invalid.write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable"):
        _read_json(invalid)


def test_repository_version_reports_clean_and_dirty_state(tmp_path: Path) -> None:
    missing = tmp_path / "not-a-repository"
    missing.mkdir()
    with pytest.raises(ValueError, match="cannot be resolved"):
        _repository_version(missing)

    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    tracked = repository / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    assert _repository_version(repository).endswith("+clean")
    (repository / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    assert _repository_version(repository).endswith("+dirty")


def test_repository_version_ignores_only_generated_outputs(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    output_directory = repository / "reports" / "coverage"
    output_directory.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    output = output_directory / "coverage_summary.json"
    output.write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )

    output.write_text('{"lineage": "refreshed"}\n', encoding="utf-8")
    assert _repository_version(
        repository, ignored_generated_paths=(Path("reports/coverage"),)
    ).endswith("+clean")

    (repository / "source.py").write_text("changed = True\n", encoding="utf-8")
    assert _repository_version(
        repository, ignored_generated_paths=(Path("reports/coverage"),)
    ).endswith("+dirty")


def test_markdown_includes_lineage_and_sensitivity_reconciliation() -> None:
    summary = {
        "lineage": {
            "dataset_version": "sha256:a",
            "raw_sha256": "a",
            "audit_method_version": "audit",
            "audit_result_content_sha256": "b",
            "audit_gap_table_sha256": "c",
            "audit_monthly_table_sha256": "d",
            "coverage_method_id": "COVERAGE-001",
            "coverage_method_version": "v1",
            "repository_version": "git:e+dirty",
        },
        "eligibility_status_counts": {"fully_eligible": 2},
        "affected_period_2023": {
            "first_timestamp_before": "start",
            "last_timestamp_after": "end",
        },
        "continuity_impaired_months": ["2023-02"],
        "sensitivity_analysis": {
            "contributing_rules": [
                {
                    "flag": "affected_period_2023",
                    "rule_id": "COV-PERIOD-002",
                    "row_count": 1,
                    "unique_only_row_count": 1,
                }
            ]
        },
        "coverage_profiles": [
            {
                "profile": "FULL",
                "level": "row",
                "included_units": 2,
                "excluded_units": 0,
                "included_percentage": 100.0,
            }
        ],
        "level_semantics": {"row": "one row"},
    }
    markdown = render_coverage_markdown(summary)
    assert "# Research Coverage" in markdown
    assert "git:e+dirty" in markdown
    assert "`affected_period_2023`" in markdown
    assert "| FULL | 2 | 0 | 100.000000 |" in markdown


def test_coverage_config_validation_and_portability() -> None:
    config = load_config(find_repository_root())
    assert config.coverage.method_id == "COVERAGE-001"
    assert config.coverage.required_audit_method_version == (
        "raw-data-quality-audit-v2"
    )
    assert len(config.coverage.required_audit_result_content_sha256) == 64
    assert "STRICT_CONTINUITY" in config.coverage.profiles
    invalid_profile = config.coverage.profiles["FULL_DATASET"].model_dump(mode="python")
    invalid_profile.update(
        {
            "require_all": ("raw_available",),
            "exclude_any": ("raw_available",),
        }
    )
    with pytest.raises(ValueError, match="must not repeat"):
        type(config.coverage.profiles["FULL_DATASET"]).model_validate(invalid_profile)

    values = config.coverage.model_dump(mode="python")
    values["output_directory"] = Path("/absolute/output")
    with pytest.raises(ValueError, match="repository-relative"):
        CoverageConfig.model_validate(values)
