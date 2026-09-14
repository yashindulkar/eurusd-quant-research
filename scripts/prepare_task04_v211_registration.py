"""Create the v2.11 pre-anchor registration and executable configuration."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, cast

import yaml

from eurusd_research.paths import find_repository_root
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.integrity import (
    read_source_dependency_manifest,
    read_task03_row_membership_evidence,
)
from eurusd_research.studies.registry import (
    assert_registration_matches_config,
    locked_design_fingerprint,
    read_preregistration,
)


def _atomic_yaml(path: Path, value: object) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(yaml.safe_dump(value, sort_keys=False, allow_unicode=False))
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _registered_paths(source_paths: tuple[str, ...]) -> list[str]:
    return sorted(
        {
            *source_paths,
            "configs/task04_daily_range_weekday.yaml",
            "reports/audits/monthly_coverage.csv",
            "reports/audits/raw_data_quality_audit.json",
            "reports/audits/raw_dataset_manifest.json",
            "reports/audits/timestamp_gaps.csv",
            "reports/coverage/coverage_profiles.csv",
            "reports/coverage/coverage_summary.json",
            "reports/coverage/coverage_summary.md",
            "reports/coverage/date_flag_counts.csv",
            "reports/coverage/month_flag_counts.csv",
            "reports/coverage/row_flag_counts.csv",
            "studies/task03_task04_v2.11_evidence.json",
            "studies/task04_daily_range_weekday.v2.11.yaml",
            "studies/task04_development_baseline.json",
            "studies/task04_v2.11_environment_lock.json",
            "studies/task04_v2.11_source_manifest.json",
            "studies/task04_v2.10_stopped_attempt.json",
        }
    )


def main() -> int:
    root = find_repository_root()
    source = read_source_dependency_manifest(
        root / "studies/task04_v2.11_source_manifest.json"
    )
    task03 = read_task03_row_membership_evidence(
        root / "studies/task03_task04_v2.11_evidence.json"
    )
    environment_path = root / "studies/task04_v2.11_environment_lock.json"
    environment_sha = hashlib.sha256(environment_path.read_bytes()).hexdigest()
    base = cast(
        dict[str, Any],
        yaml.safe_load(
            (root / "studies/task04_daily_range_weekday.v2.10.yaml").read_text(
                encoding="utf-8"
            )
        ),
    )
    base.update(
        {
            "registration_version": "2.11",
            "method_version": "range-weekday-registered-replication-v2.11",
            "implementation_version": "task04-daily-range-weekday-v2.11",
            "source_dependency_manifest_fingerprint": (
                source.dependency_manifest_fingerprint
            ),
            "environment_lock_fingerprint": environment_sha,
        }
    )
    task03_dependency = base["task_03_dependency"]
    task03_dependency.pop("row_membership_evidence_path", None)
    task03_dependency.pop("row_membership_evidence_fingerprint", None)
    task03_dependency.pop("coverage_summary_file_fingerprint", None)
    task03_dependency.update(
        {
            "evidence_path": "studies/task03_task04_v2.11_evidence.json",
            "coverage_summary_stable_fingerprint": (
                task03.stable_artifacts.stable_output_sha256[
                    "reports/coverage/coverage_summary.json"
                ]
            ),
            "evidence_layer_schema_version": task03.schema_version,
            "scientific_membership_fingerprint": (
                task03.scientific_membership_fingerprint
            ),
            "stable_artifact_fingerprint": task03.stable_artifact_fingerprint,
            "execution_context_variance_policy": (
                task03.execution_context.context_variance_policy
            ),
        }
    )
    base["expected_outputs"]["directory"] = (
        "reports/research/task04_daily_range_weekday_v2.11"
    )
    paths = _registered_paths(tuple(item.path for item in source.entries))
    base["repository_lineage"].update(
        {
            "registration_receipt_path": (
                "studies/task04_daily_range_weekday.v2.11.receipt.json"
            ),
            "registration_lifecycle_path": (
                "studies/task04_daily_range_weekday.v2.11.lifecycle.json"
            ),
            "source_manifest_path": "studies/task04_v2.11_source_manifest.json",
            "environment_lock_path": "studies/task04_v2.11_environment_lock.json",
            "registered_path_inventory": paths,
            "dirty_state_policy": (
                "Every registered path must be tracked and byte-identical to its "
                "v2.11 anchor blob. Post-anchor receipt, candidate, reconciliation, "
                "lifecycle, and final outputs remain outside the registered tree."
            ),
        }
    )
    base["deviation_policy"]["rule"] = (
        "Any post-anchor scientific or interpretive change requires a new "
        "registration version and Git anchor. "
        "The v2.11 deviation list is locked empty and is not appendable."
    )
    governance = base["production_governance"]
    governance.update(
        {
            "receipt_schema_version": "task04-registration-receipt-v6",
            "lifecycle_schema_version": "task04-registration-lifecycle-v6",
            "candidate_output_directory": "reports/research/.task04_v2.11_candidate",
            "final_output_directory": (
                "reports/research/task04_daily_range_weekday_v2.11"
            ),
            "validated_candidate_identity_path": (
                "studies/task04_v2.11_validated_candidate_identity.json"
            ),
            "independent_reconciliation_path": (
                "studies/task04_v2.11_independent_reconciliation.json"
            ),
            "standalone_completion_evidence_policy": (
                "REOPEN_STRICTLY_VALIDATE_AND_MATCH_LIFECYCLE_CONTEXT_AND_FINAL_BYTES"
            ),
            "independent_rating_reconciliation_policy": (
                "COMPARE_EVERY_REGISTERED_PRODUCTION_RATING_SUMMARY_FIELD"
            ),
            "reporting_interpretation_policy": (
                "NON_SIGNIFICANCE_IS_NON_DETECTION_NOT_ABSENCE_OR_EQUIVALENCE"
            ),
            "validation_segment_label_policy": (
                "CHRONOLOGICALLY_RESERVED_NOT_HISTORICALLY_UNSEEN"
            ),
            "dependence_reporting_policy": (
                "NOMINAL_PRECISION_NOT_DEPENDENCE_ROBUST_NO_DIRECTIONAL_CLAIM"
            ),
            "lifecycle_state_integration_tests": [
                "PRE_RECEIPT",
                "POST_RECEIPT_PRE_CANDIDATE",
                "CANDIDATE",
                "POST_PROMOTION_PRE_LIFECYCLE",
                "COMPLETED",
            ],
            "receipt_existence_policy": (
                "ABSENT_BEFORE_CREATION_REQUIRED_AFTER_CREATION"
            ),
            "pre_receipt_fixture_isolation_policy": (
                "REGISTERED_ANCHOR_PATHS_PLUS_RAW_ONLY_NO_AMBIENT_RUNTIME"
            ),
            "candidate_identity_schema_version": (
                "task04-validated-candidate-identity-v1"
            ),
            "candidate_identity_establishment_stage": (
                "AFTER_TWELVE_COMPONENT_RECONCILIATION"
            ),
            "candidate_identity_immutability_policy": (
                "WRITE_ONCE_NO_AUTOMATIC_REBASELINE"
            ),
            "candidate_identity_comparison_policy": (
                "CURRENT_PATH_SIZE_SHA256_AND_DIGEST_MUST_EQUAL_VALIDATED_BASELINE"
            ),
            "promotion_identity_policy": (
                "FINAL_BYTES_MUST_EQUAL_VALIDATED_CANDIDATE_BASELINE"
            ),
            "task03_evidence_layer_schema_version": task03.schema_version,
            "task03_scientific_membership_policy": (
                "EXACT_ROW_DATE_ALGEBRA_BOUNDARY_AND_RAW_IDENTITY_REQUIRED"
            ),
            "task03_stable_artifact_policy": (
                "CANONICAL_CONTENT_EXCLUDING_REGISTERED_EXECUTION_CONTEXT_REQUIRED"
            ),
            "task03_execution_context_policy": (
                task03.execution_context.context_variance_policy
            ),
            "task03_material_mismatch_policy": (
                "SCIENTIFIC_OR_STABLE_ARTIFACT_MISMATCH_FAILS_BEFORE_AGGREGATION"
            ),
        }
    )
    registration_path = root / "studies/task04_daily_range_weekday.v2.11.yaml"
    _atomic_yaml(registration_path, base)

    active = cast(
        dict[str, Any],
        yaml.safe_load(
            (root / "configs/task04_daily_range_weekday.yaml").read_text(
                encoding="utf-8"
            )
        ),
    )
    active.pop("task03_row_membership_evidence_path", None)
    active.pop("required_task03_row_membership_fingerprint", None)
    active.pop("required_coverage_summary_sha256", None)
    active.update(
        {
            "registration_version": "2.11",
            "method_version": "range-weekday-registered-replication-v2.11",
            "implementation_version": "task04-daily-range-weekday-v2.11",
            "receipt_schema_version": "task04-registration-receipt-v6",
            "lifecycle_schema_version": "task04-registration-lifecycle-v6",
            "preregistration_path": "studies/task04_daily_range_weekday.v2.11.yaml",
            "registration_receipt_path": (
                "studies/task04_daily_range_weekday.v2.11.receipt.json"
            ),
            "registration_lifecycle_path": (
                "studies/task04_daily_range_weekday.v2.11.lifecycle.json"
            ),
            "source_dependency_manifest_path": (
                "studies/task04_v2.11_source_manifest.json"
            ),
            "environment_lock_path": "studies/task04_v2.11_environment_lock.json",
            "task03_evidence_path": "studies/task03_task04_v2.11_evidence.json",
            "task03_evidence_layer_schema_version": task03.schema_version,
            "task03_execution_context_variance_policy": (
                task03.execution_context.context_variance_policy
            ),
            "lifecycle_state_integration_tests": [
                "PRE_RECEIPT",
                "POST_RECEIPT_PRE_CANDIDATE",
                "CANDIDATE",
                "POST_PROMOTION_PRE_LIFECYCLE",
                "COMPLETED",
            ],
            "receipt_existence_policy": (
                "ABSENT_BEFORE_CREATION_REQUIRED_AFTER_CREATION"
            ),
            "pre_receipt_fixture_isolation_policy": (
                "REGISTERED_ANCHOR_PATHS_PLUS_RAW_ONLY_NO_AMBIENT_RUNTIME"
            ),
            "task03_scientific_membership_policy": (
                "EXACT_ROW_DATE_ALGEBRA_BOUNDARY_AND_RAW_IDENTITY_REQUIRED"
            ),
            "task03_stable_artifact_policy": (
                "CANONICAL_CONTENT_EXCLUDING_REGISTERED_EXECUTION_CONTEXT_REQUIRED"
            ),
            "task03_material_mismatch_policy": (
                "SCIENTIFIC_OR_STABLE_ARTIFACT_MISMATCH_FAILS_BEFORE_AGGREGATION"
            ),
            "output_directory": "reports/research/task04_daily_range_weekday_v2.11",
            "candidate_output_directory": "reports/research/.task04_v2.11_candidate",
            "validated_candidate_identity_path": (
                "studies/task04_v2.11_validated_candidate_identity.json"
            ),
            "independent_reconciliation_path": (
                "studies/task04_v2.11_independent_reconciliation.json"
            ),
            "standalone_completion_evidence_policy": (
                "REOPEN_STRICTLY_VALIDATE_AND_MATCH_LIFECYCLE_CONTEXT_AND_FINAL_BYTES"
            ),
            "independent_rating_reconciliation_policy": (
                "COMPARE_EVERY_REGISTERED_PRODUCTION_RATING_SUMMARY_FIELD"
            ),
            "reporting_interpretation_policy": (
                "NON_SIGNIFICANCE_IS_NON_DETECTION_NOT_ABSENCE_OR_EQUIVALENCE"
            ),
            "validation_segment_label_policy": (
                "CHRONOLOGICALLY_RESERVED_NOT_HISTORICALLY_UNSEEN"
            ),
            "dependence_reporting_policy": (
                "NOMINAL_PRECISION_NOT_DEPENDENCE_ROBUST_NO_DIRECTIONAL_CLAIM"
            ),
            "required_source_dependency_manifest_fingerprint": (
                source.dependency_manifest_fingerprint
            ),
            "required_environment_lock_fingerprint": environment_sha,
            "required_task03_scientific_membership_fingerprint": (
                task03.scientific_membership_fingerprint
            ),
            "required_task03_stable_artifact_fingerprint": (
                task03.stable_artifact_fingerprint
            ),
            "required_coverage_summary_stable_sha256": (
                task03.stable_artifacts.stable_output_sha256[
                    "reports/coverage/coverage_summary.json"
                ]
            ),
        }
    )
    _atomic_yaml(root / "configs/task04_daily_range_weekday.yaml", active)
    config = load_task04_config(root)
    registration, _ = read_preregistration(registration_path)
    assert_registration_matches_config(registration, config)
    print(
        "Task 04 v2.11 preregistration: ANCHOR_READY | "
        f"semantic={locked_design_fingerprint(registration)} | "
        f"registered_paths={len(paths)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
