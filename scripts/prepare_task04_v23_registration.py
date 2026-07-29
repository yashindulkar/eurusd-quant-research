"""Create the standalone v2.3 pre-anchor registration and active configuration."""

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


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping: {path}")
    return cast(dict[str, Any], value)


def _registered_paths(root: Path, source_entries: tuple[object, ...]) -> list[str]:
    source_paths = [cast(Any, entry).path for entry in source_entries]
    evidence_paths = [
        "configs/task04_daily_range_weekday.yaml",
        "studies/task04_daily_range_weekday.v2.3.yaml",
        "studies/task04_v2.3_source_manifest.json",
        "studies/task04_v2.3_environment_lock.json",
        "studies/task03_task04_v2.3_mask_evidence.json",
        "studies/task04_development_baseline.json",
        "reports/audits/raw_dataset_manifest.json",
        "reports/audits/raw_data_quality_audit.json",
        "reports/audits/timestamp_gaps.csv",
        "reports/audits/monthly_coverage.csv",
        "reports/coverage/coverage_summary.json",
        "reports/coverage/coverage_summary.md",
        "reports/coverage/coverage_profiles.csv",
        "reports/coverage/row_flag_counts.csv",
        "reports/coverage/date_flag_counts.csv",
        "reports/coverage/month_flag_counts.csv",
    ]
    return sorted(set((*source_paths, *evidence_paths)))


def main() -> int:
    """Prepare v2.3 design files and validate them without creating a receipt."""
    root = find_repository_root()
    active_config_path = root / "configs" / "task04_daily_range_weekday.yaml"
    historical_config_path = root / "configs" / "task04_daily_range_weekday.v2.2.yaml"
    if not historical_config_path.exists():
        _atomic_text(
            historical_config_path,
            active_config_path.read_text(encoding="utf-8"),
        )

    source_manifest = read_source_dependency_manifest(
        root / "studies" / "task04_v2.3_source_manifest.json"
    )
    task03_evidence = read_task03_row_membership_evidence(
        root / "studies" / "task03_task04_v2.3_mask_evidence.json"
    )
    environment_path = root / "studies" / "task04_v2.3_environment_lock.json"
    environment_sha256 = hashlib.sha256(environment_path.read_bytes()).hexdigest()
    registered_paths = _registered_paths(root, source_manifest.entries)

    config = _read_yaml(historical_config_path)
    config.update(
        {
            "registration_version": "2.3",
            "method_version": "range-weekday-registered-replication-v2.3",
            "implementation_version": "task04-daily-range-weekday-v2.3",
            "receipt_schema_version": "task04-registration-receipt-v2",
            "preregistration_path": ("studies/task04_daily_range_weekday.v2.3.yaml"),
            "registration_receipt_path": (
                "studies/task04_daily_range_weekday.v2.3.receipt.json"
            ),
            "registration_lifecycle_path": (
                "studies/task04_daily_range_weekday.v2.3.lifecycle.json"
            ),
            "source_dependency_manifest_path": (
                "studies/task04_v2.3_source_manifest.json"
            ),
            "environment_lock_path": ("studies/task04_v2.3_environment_lock.json"),
            "task03_row_membership_evidence_path": (
                "studies/task03_task04_v2.3_mask_evidence.json"
            ),
            "output_directory": ("reports/research/task04_daily_range_weekday_v2.3"),
            "required_source_dependency_manifest_fingerprint": (
                source_manifest.dependency_manifest_fingerprint
            ),
            "required_environment_lock_fingerprint": environment_sha256,
            "required_task03_row_membership_fingerprint": (
                task03_evidence.evidence_fingerprint
            ),
        }
    )
    config.pop("required_registration_receipt_fingerprint", None)
    config["evidence_rating"].update(
        {
            "minimum_regime_sample": 100,
            "high_regime_significance_role": "contextual_only",
        }
    )
    _atomic_text(
        active_config_path,
        yaml.safe_dump(config, sort_keys=False, allow_unicode=False),
    )

    registration = _read_yaml(root / "studies" / "task04_daily_range_weekday.yaml")
    registration.update(
        {
            "registration_version": "2.3",
            "method_version": "range-weekday-registered-replication-v2.3",
            "status": "PREREGISTERED",
            "implementation_version": "task04-daily-range-weekday-v2.3",
            "source_dependency_manifest_fingerprint": (
                source_manifest.dependency_manifest_fingerprint
            ),
            "environment_lock_fingerprint": environment_sha256,
            "deviation_policy": {
                "model": "NEW_REGISTRATION_VERSION_REQUIRED",
                "post_anchor_scientific_changes_permitted": False,
                "same_version_append_only_ledger_supported": False,
                "rule": (
                    "Any post-anchor scientific or interpretive change requires "
                    "a new registration version and a new Git anchor. The v2.3 "
                    "deviation list is locked empty and is not appendable."
                ),
            },
            "preregistration_deviations": [],
        }
    )
    registration["task_03_dependency"].update(
        {
            "architecture": "DESIGN_B_REBUILD_AND_RECONCILE_EXACTLY",
            "row_membership_evidence_path": (
                "studies/task03_task04_v2.3_mask_evidence.json"
            ),
            "row_membership_evidence_fingerprint": (
                task03_evidence.evidence_fingerprint
            ),
        }
    )
    registration["expected_outputs"]["directory"] = (
        "reports/research/task04_daily_range_weekday_v2.3"
    )
    thresholds = registration["evidence_rating"]["thresholds"]
    thresholds.update(
        {
            "minimum_regime_sample": 100,
            "high_regime_significance_role": "contextual_only",
        }
    )
    registration["evidence_rating"].update(
        {
            "required_periods": [
                "full_eligible_sample",
                "pre_2020",
                "covid_era",
                "post_2021",
                "development_70",
                "validation_30",
            ],
            "required_regimes": ["LOW", "MEDIUM", "HIGH"],
            "required_evidence_artifacts": [
                "coverage_profile_comparison.csv",
                "weekday_statistics.csv",
                "period_robustness.csv",
                "yearly_omnibus_tests.csv",
                "volatility_regime_statistics.csv",
                "volatility_regime_tests.csv",
                "extreme_event_sensitivity.csv",
            ],
            "missing_evidence_policy": (
                "Any missing, empty, malformed, non-finite, contradictory, or "
                "sample-insufficient required evidence produces INSUFFICIENT."
            ),
        }
    )
    registration["evidence_rating"]["logic"] = (
        registration["evidence_rating"]["logic"]
        + " Every required evidence artifact must be present, structurally "
        "complete, finite, and sample-sufficient. HIGH-regime significance is "
        "contextual evidence only; its finite omnibus result and population are "
        "nevertheless required for a rating above INSUFFICIENT."
    )
    registration["repository_lineage"] = {
        "baseline_head": "5773f7b28fc53e972bf77eb015187620a32ab2ec",
        "development_baseline_path": "studies/task04_development_baseline.json",
        "registration_receipt_path": (
            "studies/task04_daily_range_weekday.v2.3.receipt.json"
        ),
        "registration_lifecycle_path": (
            "studies/task04_daily_range_weekday.v2.3.lifecycle.json"
        ),
        "source_manifest_path": "studies/task04_v2.3_source_manifest.json",
        "environment_lock_path": "studies/task04_v2.3_environment_lock.json",
        "raw_path": "data/raw/EURUSD_M15_UTC.csv",
        "manifest_path": "reports/audits/raw_dataset_manifest.json",
        "task_02_result_path": "reports/audits/raw_data_quality_audit.json",
        "task_03_result_path": "reports/coverage/coverage_summary.json",
        "registered_path_inventory": registered_paths,
        "dirty_state_policy": (
            "Every registered path must be tracked and byte-identical to the "
            "anchor blob before generation. Additional files inside the declared "
            "source scope are forbidden by manifest reconciliation. Generated "
            "v2.3 outputs and the post-anchor receipt/lifecycle are outside the "
            "anchor tree; unrelated documentation-only dirt is permitted and "
            "reported by Git."
        ),
    }
    v23_path = root / "studies" / "task04_daily_range_weekday.v2.3.yaml"
    _atomic_text(
        v23_path,
        yaml.safe_dump(registration, sort_keys=False, allow_unicode=False),
    )

    validated_config = load_task04_config(root)
    validated_registration, _ = read_preregistration(v23_path)
    assert_registration_matches_config(validated_registration, validated_config)
    print(
        "Task 04 v2.3 preregistration: ANCHOR_READY | "
        f"semantic={locked_design_fingerprint(validated_registration)} | "
        f"registered_paths={len(registered_paths)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
