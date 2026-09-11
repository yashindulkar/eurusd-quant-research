from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from eurusd_research.config import load_config
from eurusd_research.paths import find_repository_root
from eurusd_research.research.coverage import build_coverage
from eurusd_research.research.models import CoverageResult
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.integrity import (
    build_source_dependency_manifest,
    build_task03_row_membership_evidence,
    read_source_dependency_manifest,
    read_task03_row_membership_evidence,
    validate_task03_row_membership,
)


def _coverage() -> tuple[Path, CoverageResult]:
    root = find_repository_root()
    config = load_config(root)
    return (
        root,
        build_coverage(
            root=root,
            config=config,
            repository_version="integrity-test",
        ),
    )


def test_live_task03_row_membership_matches_pinned_evidence() -> None:
    root, coverage = _coverage()
    config = load_config(root)
    task_config = load_task04_config(root)
    evidence = validate_task03_row_membership(
        root,
        coverage,
        config,
        expected_scientific_fingerprint=(
            task_config.required_task03_scientific_membership_fingerprint
        ),
        expected_stable_artifact_fingerprint=(
            task_config.required_task03_stable_artifact_fingerprint
        ),
    )
    counts = {item.profile: item.row_included for item in evidence.profiles}
    assert counts == {
        "DEFAULT_RESEARCH": 406945,
        "STRICT_CONTINUITY": 360477,
        "SENSITIVITY_FULL": 46468,
        "SENSITIVITY_2023": 9258,
    }


def test_dependency_manifest_covers_representative_execution_closure() -> None:
    root = find_repository_root()
    manifest = read_source_dependency_manifest(
        root / "studies" / "task04_v2.8_source_manifest.json"
    )
    paths = {entry.path for entry in manifest.entries}
    assert {
        "src/eurusd_research/research/eligibility.py",
        "src/eurusd_research/research/coverage.py",
        "src/eurusd_research/config.py",
        "src/eurusd_research/paths.py",
        "src/eurusd_research/studies/daily_aggregation.py",
        "src/eurusd_research/studies/statistics.py",
        "src/eurusd_research/studies/robustness.py",
        "src/eurusd_research/studies/configuration.py",
        "src/eurusd_research/studies/dependencies.py",
        "src/eurusd_research/studies/reconciliation_schema.py",
        "tests/unit/test_task04_v26_governance.py",
        "Makefile",
        "pyproject.toml",
        "studies/task04_v2.8_environment_lock.json",
    }.issubset(paths)


def test_pinned_task03_evidence_tamper_fails_self_validation(
    tmp_path: Path,
) -> None:
    root = find_repository_root()
    value = json.loads(
        (root / "studies" / "task03_task04_v2.8_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    value["scientific_membership"]["profiles"][0]["row_membership_sha256"] = "f" * 64
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        read_task03_row_membership_evidence(path)


def test_equal_count_different_membership_and_row_order_change_are_detected() -> None:
    root, coverage = _coverage()
    config = load_config(root)
    baseline = build_task03_row_membership_evidence(root, coverage, config)

    masks = {
        level: frame.copy(deep=True)
        for level, frame in coverage.profile_masks_by_level.items()
    }
    selected = masks["row"]["STRICT_CONTINUITY"].copy()
    included = selected[selected].index[0]
    excluded = selected[~selected].index[0]
    selected.loc[included] = False
    selected.loc[excluded] = True
    masks["row"]["STRICT_CONTINUITY"] = selected
    changed = CoverageResult(
        coverage.lineage,
        coverage.flags_by_level,
        masks,
        coverage.summary,
    )
    changed_evidence = build_task03_row_membership_evidence(root, changed, config)
    assert (
        changed_evidence.profiles[1].row_included == baseline.profiles[1].row_included
    )
    assert (
        changed_evidence.profiles[1].row_membership_sha256
        != baseline.profiles[1].row_membership_sha256
    )

    date_selected = masks["date"]["STRICT_CONTINUITY"].copy()
    date_included = date_selected[date_selected].index[0]
    date_excluded = date_selected[~date_selected].index[0]
    date_selected.loc[date_included] = False
    date_selected.loc[date_excluded] = True
    masks["date"]["STRICT_CONTINUITY"] = date_selected
    date_changed = CoverageResult(
        coverage.lineage,
        coverage.flags_by_level,
        masks,
        coverage.summary,
    )
    date_evidence = build_task03_row_membership_evidence(root, date_changed, config)
    assert date_evidence.profiles[1].date_included == baseline.profiles[1].date_included
    assert (
        date_evidence.profiles[1].date_membership_sha256
        != baseline.profiles[1].date_membership_sha256
    )

    reordered_flags = {
        level: frame.copy(deep=True) for level, frame in coverage.flags_by_level.items()
    }
    reordered_masks = {
        level: frame.copy(deep=True)
        for level, frame in coverage.profile_masks_by_level.items()
    }
    reordered_flags["row"] = reordered_flags["row"].iloc[::-1].reset_index(drop=True)
    reordered_masks["row"] = reordered_masks["row"].iloc[::-1].reset_index(drop=True)
    reordered = CoverageResult(
        coverage.lineage,
        reordered_flags,
        reordered_masks,
        coverage.summary,
    )
    reordered_evidence = build_task03_row_membership_evidence(root, reordered, config)
    assert (
        reordered_evidence.scientific_membership_fingerprint
        != baseline.scientific_membership_fingerprint
    )


def test_task03_execution_context_is_separate_from_scientific_identity() -> None:
    root, coverage = _coverage()
    config = load_config(root)
    baseline = build_task03_row_membership_evidence(root, coverage, config)
    changed_context = CoverageResult(
        replace(coverage.lineage, repository_version="git:other+dirty"),
        coverage.flags_by_level,
        coverage.profile_masks_by_level,
        coverage.summary,
    )
    current = build_task03_row_membership_evidence(root, changed_context, config)
    assert current.scientific_membership == baseline.scientific_membership
    assert current.stable_artifacts == baseline.stable_artifacts
    assert current.execution_context != baseline.execution_context

    task_config = load_task04_config(root)
    validated = validate_task03_row_membership(
        root,
        changed_context,
        config,
        expected_scientific_fingerprint=(
            task_config.required_task03_scientific_membership_fingerprint
        ),
        expected_stable_artifact_fingerprint=(
            task_config.required_task03_stable_artifact_fingerprint
        ),
    )
    assert validated.execution_context == current.execution_context


def test_task03_stable_artifact_change_is_not_treated_as_context(
    tmp_path: Path,
) -> None:
    root, coverage = _coverage()
    config = load_config(root)
    baseline = build_task03_row_membership_evidence(root, coverage, config)
    (tmp_path / "reports").mkdir()
    shutil.copytree(root / "reports/coverage", tmp_path / "reports/coverage")
    artifact = tmp_path / "reports/coverage/row_flag_counts.csv"
    artifact.write_bytes(artifact.read_bytes() + b"\n")
    changed = build_task03_row_membership_evidence(tmp_path, coverage, config)
    assert changed.scientific_membership == baseline.scientific_membership
    assert changed.stable_artifacts != baseline.stable_artifacts


def test_task03_layer_models_reject_schema_raw_and_algebra_mutations() -> None:
    root, coverage = _coverage()
    config = load_config(root)
    evidence = build_task03_row_membership_evidence(root, coverage, config)
    for field, replacement in (
        ("raw_sha256", "f" * 64),
        ("coverage_schema_version", "changed-schema"),
        ("strict_subset_default", False),
        ("boundary_classification_sha256", "e" * 64),
    ):
        values = evidence.scientific_membership.model_dump(mode="python")
        values[field] = replacement
        with pytest.raises(ValueError, match="fingerprint"):
            type(evidence.scientific_membership).model_validate(values)


def _minimal_source_scope(root: Path) -> None:
    (root / "src" / "eurusd_research").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "configs").mkdir()
    (root / "studies").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "eurusd_research" / "__init__.py").write_text(
        '"""fixture"""\n', encoding="utf-8"
    )
    (root / "scripts" / "run.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname='fixture'\n", encoding="utf-8"
    )
    (root / "Makefile").write_text("check:\n\t@true\n", encoding="utf-8")
    for name in ("project.yaml", "data.yaml", "coverage.yaml", "sessions.yaml"):
        (root / "configs" / name).write_text("{}\n", encoding="utf-8")
    (root / "studies" / "task04_v2.8_environment_lock.json").write_text(
        json.dumps({"schema_version": "fixture"}) + "\n",
        encoding="utf-8",
    )


def test_source_manifest_detects_mutation_and_added_untracked_source(
    tmp_path: Path,
) -> None:
    _minimal_source_scope(tmp_path)
    baseline = build_source_dependency_manifest(tmp_path)
    source = tmp_path / "src" / "eurusd_research" / "__init__.py"
    source.write_text('"""changed"""\n', encoding="utf-8")
    changed = build_source_dependency_manifest(tmp_path)
    assert changed.dependency_manifest_fingerprint != (
        baseline.dependency_manifest_fingerprint
    )
    source.write_text('"""fixture"""\n', encoding="utf-8")
    (source.parent / "untracked_dependency.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )
    added = build_source_dependency_manifest(tmp_path)
    assert added.dependency_manifest_fingerprint != (
        baseline.dependency_manifest_fingerprint
    )


def test_mask_failure_occurs_before_primary_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, coverage = _coverage()
    config = load_config(root)
    called = False

    def primary_calculation() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "eurusd_research.studies.integrity.build_task03_row_membership_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("live mask mismatch")
        ),
    )
    with pytest.raises(ValueError, match="live mask mismatch"):
        validate_task03_row_membership(
            root,
            coverage,
            config,
            expected_scientific_fingerprint=load_task04_config(
                root
            ).required_task03_scientific_membership_fingerprint,
            expected_stable_artifact_fingerprint=load_task04_config(
                root
            ).required_task03_stable_artifact_fingerprint,
        )
        primary_calculation()
    assert not called
