"""Authoritative Task 01-03 dependency validation for Task 04."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from eurusd_research.config import load_config
from eurusd_research.data.registry import read_manifest, sha256_file
from eurusd_research.paths import project_path
from eurusd_research.studies.configuration import Task04Config
from eurusd_research.studies.integrity import (
    read_source_dependency_manifest,
    read_task03_row_membership_evidence,
    stable_coverage_artifact_sha256,
)


def _stable_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Task 04 dependency is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Task 04 dependency must be a JSON object: {path}")
    return cast(dict[str, Any], value)


def validate_task04_dependencies(
    root: Path, task_config: Task04Config
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate raw, manifest, Task 02, and Task 03 identities fail-closed."""
    repository_config = load_config(root)
    manifest_path = project_path(repository_config.data.registered_manifest_path, root)
    if sha256_file(manifest_path) != task_config.required_raw_manifest_sha256:
        raise ValueError("Task 04 raw manifest fingerprint is stale")
    manifest = read_manifest(manifest_path)
    raw_path = project_path(repository_config.data.raw_dataset_path, root)
    if sha256_file(raw_path) != task_config.required_raw_sha256:
        raise ValueError("Task 04 raw SHA-256 differs from the registered value")
    if manifest.sha256 != task_config.required_raw_sha256:
        raise ValueError("Task 04 raw manifest checksum is incompatible")
    coverage_path = project_path(task_config.coverage_summary_path, root)
    coverage_summary = _read_json(coverage_path)
    lineage = coverage_summary.get("lineage", {})
    expected = {
        "raw_sha256": task_config.required_raw_sha256,
        "coverage_method_id": repository_config.coverage.method_id,
        "coverage_method_version": repository_config.coverage.method_version,
        "coverage_config_sha256": _stable_digest(
            repository_config.coverage.model_dump(mode="json")
        ),
        "audit_result_content_sha256": (
            repository_config.coverage.required_audit_result_content_sha256
        ),
        "audit_gap_table_sha256": (
            repository_config.coverage.required_audit_gap_table_sha256
        ),
        "audit_monthly_table_sha256": (
            repository_config.coverage.required_audit_monthly_table_sha256
        ),
    }
    if (
        repository_config.coverage.required_audit_result_content_sha256
        != task_config.required_task02_audit_fingerprint
    ):
        raise ValueError("Task 04 Task 02 audit fingerprint is stale")
    for field, expected_value in expected.items():
        if lineage.get(field) != expected_value:
            raise ValueError(f"Task 03 coverage lineage mismatch: {field}")
    profiles = {
        row["profile"]
        for row in coverage_summary.get("coverage_profiles", [])
        if row.get("level") == "row"
    }
    required_profiles = {
        task_config.primary_coverage_profile,
        *task_config.sensitivity_profiles,
    }
    if not required_profiles.issubset(profiles):
        raise ValueError("Task 03 coverage summary lacks a required profile")
    source_manifest = read_source_dependency_manifest(
        project_path(task_config.source_dependency_manifest_path, root)
    )
    if (
        source_manifest.dependency_manifest_fingerprint
        != task_config.required_source_dependency_manifest_fingerprint
    ):
        raise ValueError("Task 04 source dependency manifest is stale")
    environment_path = project_path(task_config.environment_lock_path, root)
    if sha256_file(environment_path) != (
        task_config.required_environment_lock_fingerprint
    ):
        raise ValueError("Task 04 environment lock is stale")
    mask_evidence = read_task03_row_membership_evidence(
        project_path(task_config.task03_evidence_path, root)
    )
    summary_relative = task_config.coverage_summary_path.as_posix()
    registered_summary_sha = mask_evidence.stable_artifacts.stable_output_sha256.get(
        summary_relative
    )
    if (
        registered_summary_sha is None
        or registered_summary_sha != task_config.required_coverage_summary_stable_sha256
        or stable_coverage_artifact_sha256(coverage_path) != registered_summary_sha
    ):
        raise ValueError("Task 03 stable coverage-summary fingerprint is stale")
    if mask_evidence.scientific_membership_fingerprint != (
        task_config.required_task03_scientific_membership_fingerprint
    ):
        raise ValueError("Task 03 scientific-membership evidence is stale")
    if mask_evidence.stable_artifact_fingerprint != (
        task_config.required_task03_stable_artifact_fingerprint
    ):
        raise ValueError("Task 03 stable-artifact evidence is stale")
    if (
        mask_evidence.scientific_membership.raw_sha256
        != task_config.required_raw_sha256
        or mask_evidence.scientific_membership.task03_method_id
        != repository_config.coverage.method_id
        or mask_evidence.task03_method_version
        != repository_config.coverage.method_version
    ):
        raise ValueError("Task 03 scientific evidence lineage is incompatible")
    return coverage_summary, manifest.to_dict()
