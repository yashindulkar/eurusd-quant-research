"""Create the v2.4 pre-anchor registration and executable configuration."""

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
    paths = {
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
        "studies/task03_task04_v2.4_mask_evidence.json",
        "studies/task04_daily_range_weekday.v2.4.yaml",
        "studies/task04_development_baseline.json",
        "studies/task04_v2.4_environment_lock.json",
        "studies/task04_v2.4_source_manifest.json",
    }
    return sorted(paths)


def _completion_gates() -> list[str]:
    return [
        "receipt_validated",
        "anchor_ancestry_validated",
        "registered_path_integrity_validated",
        "raw_identity_validated",
        "task02_validated",
        "task03_exact_membership_validated",
        "configuration_reconciled",
        "dependency_closure_validated",
        "candidate_inventory_validated",
        "population_reconciliation_passed",
        "independent_statistical_reproduction_passed",
        "maximum_numerical_discrepancy_within_tolerance",
        "deterministic_regeneration_passed",
        "exact_output_digest_reproduced",
        "figures_validated",
        "absolute_path_scan_passed",
        "non_finite_scan_passed",
        "volatile_output_scan_passed",
        "symlink_non_regular_scan_passed",
        "ruff_passed",
        "mypy_passed",
        "unit_tests_passed",
        "integration_tests_passed",
        "branch_coverage_passed",
        "raw_checksum_unchanged",
        "raw_mtime_unchanged",
        "deviation_policy_satisfied",
    ]


def main() -> int:
    root = find_repository_root()
    source = read_source_dependency_manifest(
        root / "studies" / "task04_v2.4_source_manifest.json"
    )
    task03 = read_task03_row_membership_evidence(
        root / "studies" / "task03_task04_v2.4_mask_evidence.json"
    )
    environment_path = root / "studies" / "task04_v2.4_environment_lock.json"
    environment_sha = hashlib.sha256(environment_path.read_bytes()).hexdigest()
    base = cast(
        dict[str, Any],
        yaml.safe_load(
            (root / "studies" / "task04_daily_range_weekday.v2.3.yaml").read_text(
                encoding="utf-8"
            )
        ),
    )
    base.update(
        {
            "registration_version": "2.4",
            "method_version": "range-weekday-registered-replication-v2.4",
            "implementation_version": "task04-daily-range-weekday-v2.4",
            "source_dependency_manifest_fingerprint": (
                source.dependency_manifest_fingerprint
            ),
            "environment_lock_fingerprint": environment_sha,
        }
    )
    base["task_03_dependency"].update(
        {
            "row_membership_evidence_path": (
                "studies/task03_task04_v2.4_mask_evidence.json"
            ),
            "row_membership_evidence_fingerprint": task03.evidence_fingerprint,
        }
    )
    base["expected_outputs"]["directory"] = (
        "reports/research/task04_daily_range_weekday_v2.4"
    )
    paths = _registered_paths(tuple(item.path for item in source.entries))
    base["repository_lineage"].update(
        {
            "registration_receipt_path": (
                "studies/task04_daily_range_weekday.v2.4.receipt.json"
            ),
            "registration_lifecycle_path": (
                "studies/task04_daily_range_weekday.v2.4.lifecycle.json"
            ),
            "source_manifest_path": "studies/task04_v2.4_source_manifest.json",
            "environment_lock_path": "studies/task04_v2.4_environment_lock.json",
            "registered_path_inventory": paths,
            "dirty_state_policy": (
                "Every registered path must be tracked and byte-identical to its "
                "v2.4 anchor blob. Additional files in the declared source scope "
                "are forbidden. Candidate outputs, receipt, lifecycle, and final "
                "outputs are post-anchor evidence outside the registered tree."
            ),
        }
    )
    base["deviation_policy"]["rule"] = (
        "Any post-anchor scientific or interpretive change requires a new "
        "registration version and Git anchor. The v2.4 deviation list is locked "
        "empty and is not appendable."
    )
    base["production_governance"] = {
        "receipt_schema_version": "task04-registration-receipt-v3",
        "lifecycle_schema_version": "task04-registration-lifecycle-v3",
        "completion_sequence": [
            "validate_anchor",
            "create_receipt",
            "validate_receipt",
            "validate_pre_generation_dependencies",
            "generate_candidate_outputs",
            "validate_candidate_outputs",
            "independent_population_reconciliation",
            "independent_statistical_reproduction",
            "deterministic_regeneration",
            "figure_validation",
            "run_required_quality_gates",
            "promote_final_outputs",
            "create_completed_lifecycle",
            "validate_completed_lifecycle",
        ],
        "candidate_output_directory": "reports/research/.task04_v2.4_candidate",
        "final_output_directory": ("reports/research/task04_daily_range_weekday_v2.4"),
        "candidate_outputs_are_completed_evidence": False,
        "output_digest_algorithm": "task04-path-length-bytes-sha256-v1",
        "independent_reconciliation_implementation": (
            "task04-independent-csv-reproduction-v1"
        ),
        "maximum_numerical_discrepancy_tolerance": 1e-10,
        "minimum_branch_coverage_percent": 90.0,
        "required_completion_gates": _completion_gates(),
        "promotion_policy": (
            "VALIDATE_CANDIDATE_THEN_ATOMICALLY_PROMOTE_ON_ONE_FILESYSTEM"
        ),
        "failure_policy": ("FAILED_CANDIDATES_NEVER_CREATE_A_COMPLETED_LIFECYCLE"),
        "anchor_ancestry_policy": (
            "COMPLETION_STATE_MUST_EQUAL_OR_DESCEND_FROM_ANCHOR"
        ),
    }
    registration_path = root / "studies" / "task04_daily_range_weekday.v2.4.yaml"
    _atomic_yaml(registration_path, base)

    active = cast(
        dict[str, Any],
        yaml.safe_load(
            (root / "configs" / "task04_daily_range_weekday.yaml").read_text(
                encoding="utf-8"
            )
        ),
    )
    active.update(
        {
            "registration_version": "2.4",
            "method_version": "range-weekday-registered-replication-v2.4",
            "implementation_version": "task04-daily-range-weekday-v2.4",
            "receipt_schema_version": "task04-registration-receipt-v3",
            "lifecycle_schema_version": "task04-registration-lifecycle-v3",
            "preregistration_path": registration_path.relative_to(root).as_posix(),
            "registration_receipt_path": (
                "studies/task04_daily_range_weekday.v2.4.receipt.json"
            ),
            "registration_lifecycle_path": (
                "studies/task04_daily_range_weekday.v2.4.lifecycle.json"
            ),
            "source_dependency_manifest_path": (
                "studies/task04_v2.4_source_manifest.json"
            ),
            "environment_lock_path": "studies/task04_v2.4_environment_lock.json",
            "task03_row_membership_evidence_path": (
                "studies/task03_task04_v2.4_mask_evidence.json"
            ),
            "output_directory": ("reports/research/task04_daily_range_weekday_v2.4"),
            "candidate_output_directory": ("reports/research/.task04_v2.4_candidate"),
            "completion_sequence": base["production_governance"]["completion_sequence"],
            "candidate_outputs_are_completed_evidence": False,
            "output_digest_algorithm": "task04-path-length-bytes-sha256-v1",
            "independent_reconciliation_implementation": (
                "task04-independent-csv-reproduction-v1"
            ),
            "maximum_numerical_discrepancy_tolerance": 1e-10,
            "minimum_branch_coverage_percent": 90.0,
            "candidate_failure_policy": (
                "FAILED_CANDIDATES_NEVER_CREATE_A_COMPLETED_LIFECYCLE"
            ),
            "promotion_policy": (
                "VALIDATE_CANDIDATE_THEN_ATOMICALLY_PROMOTE_ON_ONE_FILESYSTEM"
            ),
            "required_completion_gates": _completion_gates(),
            "anchor_ancestry_policy": (
                "COMPLETION_STATE_MUST_EQUAL_OR_DESCEND_FROM_ANCHOR"
            ),
            "required_source_dependency_manifest_fingerprint": (
                source.dependency_manifest_fingerprint
            ),
            "required_environment_lock_fingerprint": environment_sha,
            "required_task03_row_membership_fingerprint": task03.evidence_fingerprint,
        }
    )
    _atomic_yaml(root / "configs" / "task04_daily_range_weekday.yaml", active)
    config = load_task04_config(root)
    registration, _ = read_preregistration(registration_path)
    assert_registration_matches_config(registration, config)
    print(
        "Task 04 v2.4 preregistration: ANCHOR_READY | "
        f"semantic={locked_design_fingerprint(registration)} | "
        f"registered_paths={len(paths)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
