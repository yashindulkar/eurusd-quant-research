"""Versioned Task 04 registration, receipt, and lifecycle controls."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import ConfigDict, Field, model_validator

from eurusd_research.config import StrictModel
from eurusd_research.studies.configuration import Task04Config
from eurusd_research.studies.dependencies import validate_task04_dependencies
from eurusd_research.studies.git_anchor import (
    assert_anchor_lineage,
    commit_tree_id,
    registered_path_tree_fingerprint,
    resolve_commit,
)
from eurusd_research.studies.integrity import validate_source_dependency_manifest
from eurusd_research.studies.registration_models import Task04PreregistrationV23

MUTABLE_REGISTRATION_FIELDS = ("status",)
RECEIPT_SCHEMA_VERSION = "task04-registration-receipt-v2"
LIFECYCLE_SCHEMA_VERSION = "task04-registration-lifecycle-v2"


class PreregistrationDeviation(StrictModel):
    """Deterministic, versioned disclosure of a post-anchor design deviation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    deviation_id: str = Field(pattern=r"^TASK-04-R22-D[0-9]{3}$")
    registration_version: Literal["2.2"]
    affected_field: str = Field(min_length=1)
    original_value_or_fingerprint: Any
    revised_value: Any
    reason: str = Field(min_length=1)
    classification: Literal["PRIMARY", "SECONDARY", "ADMINISTRATIVE"]
    interpretation_affected: Literal["PRIMARY", "SECONDARY", "NONE"]
    approval_mechanism: str = Field(min_length=1)
    consequence: str = Field(min_length=1)
    lineage_reference: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_canonical_values(self) -> PreregistrationDeviation:
        try:
            json.dumps(
                {
                    "original": self.original_value_or_fingerprint,
                    "revised": self.revised_value,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Task 04 deviation values must be finite JSON values"
            ) from error
        return self


Task04Preregistration = Task04PreregistrationV23


LOCKED_FIELDS = tuple(
    field
    for field in Task04Preregistration.model_fields
    if field not in MUTABLE_REGISTRATION_FIELDS
)


class Task04RegistrationReceipt(StrictModel):
    """Immutable pre-result identity of the registered replication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_schema_version: Literal["task04-registration-receipt-v2"]
    study_id: Literal["TASK-04"]
    registration_version: Literal["2.3"]
    method_id: Literal["RANGE-WEEKDAY-001"]
    method_version: Literal["range-weekday-registered-replication-v2.3"]
    registration_status_at_anchoring: Literal["PREREGISTERED"]
    semantic_design_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executable_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task02_audit_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    task03_coverage_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    task03_row_membership_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_tree_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preregistration_anchor_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    preregistration_anchor_tree: str = Field(pattern=r"^[0-9a-f]{40}$")
    registered_path_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_path_inventory: tuple[str, ...] = Field(min_length=1)
    expected_output_inventory: tuple[str, ...] = Field(min_length=1)
    timestamp_operational_assumption: Literal["AS_SUPPLIED_TIMESTAMP_LABEL_DATE"]
    deviation_policy: Literal["NEW_REGISTRATION_VERSION_REQUIRED"]
    repository_dirty_state_policy: str = Field(min_length=1)
    receipt_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class Task04RegistrationLifecycle(StrictModel):
    """Persisted lifecycle history binding completion to the original receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lifecycle_schema_version: Literal["task04-registration-lifecycle-v2"]
    study_id: Literal["TASK-04"]
    registration_version: Literal["2.3"]
    receipt_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preregistration_anchor_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    semantic_design_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executable_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status_history: tuple[Literal["PREREGISTERED", "COMPLETED"], ...]
    current_status: Literal["COMPLETED"]
    lifecycle_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_preregistration(path: Path) -> tuple[Task04Preregistration, bytes]:
    """Read and strictly validate the machine-readable study registration."""
    if not path.is_file():
        raise FileNotFoundError(f"Task 04 preregistration not found: {path}")
    raw = path.read_bytes()
    try:
        value = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise ValueError("Task 04 preregistration is invalid YAML") from error
    if not isinstance(value, dict):
        raise ValueError("Task 04 preregistration must be a mapping")
    return Task04Preregistration.model_validate(value), raw


def normalized_registration(
    registration: Task04Preregistration,
) -> dict[str, Any]:
    """Return the canonical semantic design without controlled lifecycle fields."""
    value = deepcopy(registration.model_dump(mode="json"))
    value.pop("status")
    outputs = cast(dict[str, Any], value["expected_outputs"])
    outputs["files"] = sorted(outputs["files"])
    outputs["figures"] = sorted(outputs["figures"])
    return value


def locked_design_fingerprint(registration: Task04Preregistration) -> str:
    """Fingerprint every semantic field in canonical form."""
    return _canonical_digest(normalized_registration(registration))


def deviation_fingerprint(registration: Task04Preregistration) -> str:
    """Fingerprint the locked empty same-version deviation declaration."""
    return _canonical_digest(list(registration.preregistration_deviations))


def executable_configuration_contract(config: Task04Config) -> dict[str, Any]:
    """Canonical executable design derived only from settings actually consumed."""
    return {
        "identity": {
            "study_id": config.study_id,
            "registration_version": config.registration_version,
            "method_id": config.method_id,
            "method_version": config.method_version,
            "implementation_version": config.implementation_version,
        },
        "data": {
            "raw_checksum": config.required_raw_sha256,
            "raw_manifest_sha256": config.required_raw_manifest_sha256,
            "task02_audit_fingerprint": config.required_task02_audit_fingerprint,
            "task03_coverage_fingerprint": config.required_coverage_summary_sha256,
            "task03_row_membership_fingerprint": (
                config.required_task03_row_membership_fingerprint
            ),
            "source_dependency_manifest_fingerprint": (
                config.required_source_dependency_manifest_fingerprint
            ),
            "environment_lock_fingerprint": (
                config.required_environment_lock_fingerprint
            ),
        },
        "calendar": {
            "timezone": config.timezone,
            "pip_size": config.pip_size,
            "weekday_inclusion": list(config.weekday_inclusion),
            "timestamp_semantics_status": config.timestamp_semantics_status,
            "timestamp_operational_assumption": (
                config.timestamp_operational_assumption
            ),
        },
        "coverage": {
            "primary_profile": config.primary_coverage_profile,
            "sensitivity_profiles": list(config.sensitivity_profiles),
            "daily_completeness": config.daily_completeness.model_dump(mode="json"),
        },
        "statistics": {
            "minimum_yearly_weekday_sample": config.minimum_yearly_weekday_sample,
            "alpha": config.alpha,
            "multiple_testing_method": config.multiple_testing_method,
            "primary_omnibus_test": config.primary_omnibus_test,
            "post_hoc_test": config.post_hoc_test,
            "effect_size_methods": list(config.effect_size_methods),
            "confidence_level": config.confidence_level,
            "bootstrap_seed": config.bootstrap_seed,
            "bootstrap_resamples": config.bootstrap_resamples,
            "quantile_method": config.quantile_method,
            "variance_convention": config.variance_convention,
            "mad_convention": config.mad_convention,
        },
        "robustness": {
            "chronological_split_fraction": config.chronological_split_fraction,
            "period_boundaries": config.period_boundaries.model_dump(mode="json"),
            "volatility_lookback": config.volatility_lookback,
            "volatility_minimum_history": config.volatility_minimum_history,
            "regime_quantiles": list(config.regime_quantiles),
            "winsorisation_limits": list(config.winsorisation_limits),
            "largest_tail_exclusion_fraction": (config.largest_tail_exclusion_fraction),
        },
        "evidence_rating": config.evidence_rating.model_dump(mode="json"),
        "outputs": {
            "directory": config.output_directory.as_posix(),
            "files": sorted(config.expected_output_files),
            "figures": sorted(config.expected_figure_files),
        },
        "figures": config.figure_settings.model_dump(mode="json"),
    }


def registration_execution_contract(
    registration: Task04Preregistration,
) -> dict[str, Any]:
    """Map registered definitions to the same canonical executable contract."""
    required_profiles = list(registration.sensitivity_profiles.required)
    diagnostic_profiles = list(registration.sensitivity_profiles.diagnostic)
    completeness = registration.daily_completeness_rule
    confidence = registration.confidence_interval_method
    chronological = registration.chronological_stability_design
    regimes = registration.volatility_regime_definition
    exclusions = registration.exclusion_policy
    conventions = registration.statistical_conventions
    outputs = registration.expected_outputs
    return {
        "identity": {
            "study_id": registration.study_id,
            "registration_version": registration.registration_version,
            "method_id": registration.method_id,
            "method_version": registration.method_version,
            "implementation_version": registration.implementation_version,
        },
        "data": {
            "raw_checksum": registration.raw_checksum,
            "raw_manifest_sha256": registration.raw_manifest_sha256,
            "task02_audit_fingerprint": (
                registration.task_02_dependency.normalized_result_fingerprint
            ),
            "task03_coverage_fingerprint": (
                registration.task_03_dependency.coverage_summary_file_fingerprint
            ),
            "task03_row_membership_fingerprint": (
                registration.task_03_dependency.row_membership_evidence_fingerprint
            ),
            "source_dependency_manifest_fingerprint": (
                registration.source_dependency_manifest_fingerprint
            ),
            "environment_lock_fingerprint": (registration.environment_lock_fingerprint),
        },
        "calendar": {
            "timezone": registration.calendar_definition.timezone,
            "pip_size": registration.primary_outcome.pip_size,
            "weekday_inclusion": list(registration.weekday_definition.primary_weekdays),
            "timestamp_semantics_status": (
                registration.timestamp_semantics.authoritative_status
            ),
            "timestamp_operational_assumption": (
                registration.timestamp_semantics.operational_assumption
            ),
        },
        "coverage": {
            "primary_profile": registration.primary_coverage_profile,
            "sensitivity_profiles": required_profiles + diagnostic_profiles,
            "daily_completeness": {
                "minimum_coverage_ratio": completeness.minimum_coverage_ratio,
                "minimum_daily_rows": completeness.minimum_daily_rows,
                "require_first_expected_interval": (
                    completeness.require_first_expected_interval
                ),
                "require_last_expected_interval": (
                    completeness.require_last_expected_interval
                ),
                "exclude_partial_days": (
                    completeness.partial_days_in_primary_analysis is False
                ),
                "exclude_dataset_boundary_dates": (
                    completeness.exclude_dataset_boundary_dates
                ),
            },
        },
        "statistics": {
            "minimum_yearly_weekday_sample": (
                chronological.minimum_per_weekday_per_year
            ),
            "alpha": registration.primary_statistical_test.alpha,
            "multiple_testing_method": (
                registration.multiple_testing_correction.implementation_id
            ),
            "primary_omnibus_test": (
                registration.primary_statistical_test.implementation_id
            ),
            "post_hoc_test": registration.post_hoc_test.implementation_id,
            "effect_size_methods": list(
                registration.effect_size_measures.implementation_ids
            ),
            "confidence_level": confidence.confidence_level,
            "bootstrap_seed": confidence.seed,
            "bootstrap_resamples": confidence.resamples,
            "quantile_method": conventions.quantile_method,
            "variance_convention": conventions.variance_convention,
            "mad_convention": conventions.mad_convention,
        },
        "robustness": {
            "chronological_split_fraction": chronological.development_fraction,
            "period_boundaries": chronological.period_boundaries.model_dump(
                mode="json"
            ),
            "volatility_lookback": regimes.lookback_eligible_weekdays,
            "volatility_minimum_history": regimes.minimum_prior_regime_measures,
            "regime_quantiles": [
                regimes.low_quantile,
                regimes.high_quantile,
            ],
            "winsorisation_limits": list(exclusions.winsorisation_limits),
            "largest_tail_exclusion_fraction": (
                exclusions.largest_tail_exclusion_fraction
            ),
        },
        "evidence_rating": registration.evidence_rating.thresholds.model_dump(
            mode="json"
        ),
        "outputs": {
            "directory": outputs.directory,
            "files": sorted(outputs.files),
            "figures": sorted(outputs.figures),
        },
        "figures": outputs.figure_settings.model_dump(mode="json"),
    }


def executable_configuration_fingerprint(config: Task04Config) -> str:
    """Fingerprint the complete executable contract, excluding receipt identity."""
    return _canonical_digest(executable_configuration_contract(config))


def assert_registration_matches_config(
    registration: Task04Preregistration, config: Task04Config
) -> None:
    """Fail closed when any registered and executable definition disagrees."""
    registered = registration_execution_contract(registration)
    executable = executable_configuration_contract(config)
    if registered != executable:
        differing = sorted(
            key for key in registered if registered.get(key) != executable.get(key)
        )
        raise ValueError(
            "Preregistration and executable configuration disagree: "
            + ", ".join(differing)
        )


def _expected_inventory(config: Task04Config) -> tuple[str, ...]:
    return tuple(
        sorted(
            (
                *config.expected_output_files,
                *(f"figures/{name}" for name in config.expected_figure_files),
            )
        )
    )


def _receipt_payload(receipt: Task04RegistrationReceipt) -> dict[str, Any]:
    value = receipt.model_dump(mode="json")
    value.pop("receipt_fingerprint")
    return value


def _lifecycle_payload(lifecycle: Task04RegistrationLifecycle) -> dict[str, Any]:
    value = lifecycle.model_dump(mode="json")
    value.pop("lifecycle_fingerprint")
    return value


def build_registration_receipt(
    registration: Task04Preregistration,
    config: Task04Config,
    *,
    root: Path,
    anchor_commit: str | None = None,
) -> Task04RegistrationReceipt:
    """Build a deterministic receipt for an already committed design anchor."""
    if registration.status != "PREREGISTERED":
        raise ValueError("A registration receipt can only anchor PREREGISTERED status")
    assert_registration_matches_config(registration, config)
    validate_task04_dependencies(root, config)
    source_manifest = validate_source_dependency_manifest(
        root, config.required_source_dependency_manifest_fingerprint
    )
    environment_path = root / config.environment_lock_path
    environment_sha256 = _sha256_file(environment_path)
    if environment_sha256 != config.required_environment_lock_fingerprint:
        raise ValueError("Task 04 environment lock fingerprint is stale")
    anchor = anchor_commit or resolve_commit(root)
    registered_paths = registration.repository_lineage.registered_path_inventory
    tree_id = commit_tree_id(root, anchor)
    registered_tree = registered_path_tree_fingerprint(root, anchor, registered_paths)
    assert_anchor_lineage(
        root,
        anchor_commit=anchor,
        anchor_tree=tree_id,
        paths=registered_paths,
        registered_tree_fingerprint=registered_tree,
    )
    payload: dict[str, Any] = {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "study_id": registration.study_id,
        "registration_version": registration.registration_version,
        "method_id": registration.method_id,
        "method_version": registration.method_version,
        "registration_status_at_anchoring": registration.status,
        "semantic_design_sha256": locked_design_fingerprint(registration),
        "executable_configuration_sha256": executable_configuration_fingerprint(config),
        "dependency_lock_sha256": (
            config.required_source_dependency_manifest_fingerprint
        ),
        "environment_lock_sha256": environment_sha256,
        "raw_dataset_sha256": config.required_raw_sha256,
        "raw_manifest_sha256": config.required_raw_manifest_sha256,
        "task02_audit_fingerprint": config.required_task02_audit_fingerprint,
        "task03_coverage_fingerprint": config.required_coverage_summary_sha256,
        "task03_row_membership_fingerprint": (
            config.required_task03_row_membership_fingerprint
        ),
        "source_tree_fingerprint": source_manifest.source_tree_fingerprint,
        "preregistration_anchor_commit": anchor,
        "preregistration_anchor_tree": tree_id,
        "registered_path_tree_sha256": registered_tree,
        "registered_path_inventory": registered_paths,
        "expected_output_inventory": _expected_inventory(config),
        "timestamp_operational_assumption": (config.timestamp_operational_assumption),
        "deviation_policy": registration.deviation_policy.model,
        "repository_dirty_state_policy": (
            registration.repository_lineage.dirty_state_policy
        ),
    }
    return Task04RegistrationReceipt.model_validate(
        {**payload, "receipt_fingerprint": _canonical_digest(payload)}
    )


def write_registration_receipt(receipt: Task04RegistrationReceipt, path: Path) -> None:
    """Persist a receipt once; refuse to replace an existing anchor."""
    if path.exists():
        raise FileExistsError(f"Task 04 registration receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(
            receipt.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_registration_receipt(path: Path) -> Task04RegistrationReceipt:
    """Read and independently validate a receipt and its self-fingerprint."""
    if not path.is_file():
        raise FileNotFoundError(f"Task 04 registration receipt not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Task 04 registration receipt is malformed") from error
    receipt = Task04RegistrationReceipt.model_validate(value)
    if _canonical_digest(_receipt_payload(receipt)) != receipt.receipt_fingerprint:
        raise ValueError("Task 04 registration receipt fingerprint is invalid")
    return receipt


def validate_registration_receipt(
    registration: Task04Preregistration,
    config: Task04Config,
    *,
    root: Path,
) -> Task04RegistrationReceipt:
    """Bind current registration/configuration/dependencies to the original receipt."""
    assert_registration_matches_config(registration, config)
    receipt_path = root / config.registration_receipt_path
    receipt = read_registration_receipt(receipt_path)
    expected = build_registration_receipt(
        registration,
        config,
        root=root,
        anchor_commit=receipt.preregistration_anchor_commit,
    )
    assert_registration_receipt_matches(
        receipt, expected, registration=registration, config=config
    )
    return receipt


def assert_registration_receipt_matches(
    receipt: Task04RegistrationReceipt,
    expected: Task04RegistrationReceipt,
    *,
    registration: Task04Preregistration,
    config: Task04Config,
) -> None:
    """Validate receipt content independently of its storage location."""
    checks = {
        "receipt schema": receipt.receipt_schema_version
        == config.receipt_schema_version,
        "study": receipt.study_id == registration.study_id,
        "registration version": receipt.registration_version
        == registration.registration_version,
        "method": (
            receipt.method_id == registration.method_id
            and receipt.method_version == registration.method_version
        ),
        "semantic design": receipt.semantic_design_sha256
        == expected.semantic_design_sha256,
        "executable configuration": receipt.executable_configuration_sha256
        == expected.executable_configuration_sha256,
        "dependency lock": receipt.dependency_lock_sha256
        == expected.dependency_lock_sha256,
        "environment lock": receipt.environment_lock_sha256
        == expected.environment_lock_sha256,
        "raw dataset": receipt.raw_dataset_sha256 == config.required_raw_sha256,
        "raw manifest": receipt.raw_manifest_sha256
        == config.required_raw_manifest_sha256,
        "Task 02": receipt.task02_audit_fingerprint
        == config.required_task02_audit_fingerprint,
        "Task 03": receipt.task03_coverage_fingerprint
        == config.required_coverage_summary_sha256,
        "Task 03 row membership": receipt.task03_row_membership_fingerprint
        == config.required_task03_row_membership_fingerprint,
        "source tree": receipt.source_tree_fingerprint
        == expected.source_tree_fingerprint,
        "anchor commit": receipt.preregistration_anchor_commit
        == expected.preregistration_anchor_commit,
        "anchor tree": receipt.preregistration_anchor_tree
        == expected.preregistration_anchor_tree,
        "registered path tree": receipt.registered_path_tree_sha256
        == expected.registered_path_tree_sha256,
        "registered path inventory": receipt.registered_path_inventory
        == expected.registered_path_inventory,
        "output inventory": receipt.expected_output_inventory
        == _expected_inventory(config),
        "timestamp assumption": receipt.timestamp_operational_assumption
        == config.timestamp_operational_assumption,
        "deviation policy": receipt.deviation_policy
        == registration.deviation_policy.model,
        "dirty-state policy": receipt.repository_dirty_state_policy
        == registration.repository_lineage.dirty_state_policy,
        "receipt fingerprint": receipt.receipt_fingerprint
        == expected.receipt_fingerprint,
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise ValueError(
            "Task 04 registration receipt validation failed: " + ", ".join(failed)
        )


def _write_lifecycle(
    registration: Task04Preregistration,
    config: Task04Config,
    receipt: Task04RegistrationReceipt,
    path: Path,
) -> Task04RegistrationLifecycle:
    if path.exists():
        raise FileExistsError("Task 04 registration lifecycle already exists")
    payload: dict[str, Any] = {
        "lifecycle_schema_version": LIFECYCLE_SCHEMA_VERSION,
        "study_id": registration.study_id,
        "registration_version": registration.registration_version,
        "receipt_fingerprint": receipt.receipt_fingerprint,
        "preregistration_anchor_commit": receipt.preregistration_anchor_commit,
        "semantic_design_sha256": locked_design_fingerprint(registration),
        "executable_configuration_sha256": executable_configuration_fingerprint(config),
        "status_history": ["PREREGISTERED", "COMPLETED"],
        "current_status": "COMPLETED",
    }
    lifecycle = Task04RegistrationLifecycle.model_validate(
        {**payload, "lifecycle_fingerprint": _canonical_digest(payload)}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            lifecycle.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return lifecycle


def validate_registration_lifecycle(
    registration: Task04Preregistration,
    config: Task04Config,
    receipt: Task04RegistrationReceipt,
    *,
    root: Path,
) -> Task04RegistrationLifecycle:
    """Validate completion while keeping the anchored registration unchanged."""
    path = root / config.registration_lifecycle_path
    if not path.is_file():
        raise FileNotFoundError("Completed Task 04 registration lifecycle is missing")
    validate_registration_receipt(registration, config, root=root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Task 04 registration lifecycle is malformed") from error
    lifecycle = Task04RegistrationLifecycle.model_validate(value)
    if _canonical_digest(_lifecycle_payload(lifecycle)) != (
        lifecycle.lifecycle_fingerprint
    ):
        raise ValueError("Task 04 registration lifecycle fingerprint is invalid")
    checks = (
        lifecycle.receipt_fingerprint == receipt.receipt_fingerprint,
        lifecycle.preregistration_anchor_commit
        == receipt.preregistration_anchor_commit,
        lifecycle.semantic_design_sha256 == locked_design_fingerprint(registration),
        lifecycle.executable_configuration_sha256
        == executable_configuration_fingerprint(config),
        lifecycle.status_history == ("PREREGISTERED", "COMPLETED"),
        lifecycle.current_status == "COMPLETED",
    )
    if not all(checks):
        raise ValueError("Task 04 completed lifecycle does not match registration")
    return lifecycle


def preregistration_record(
    registration: Task04Preregistration,
    raw: bytes,
    config: Task04Config,
    *,
    root: Path,
) -> dict[str, Any]:
    """Create a registry record validated against the immutable receipt."""
    receipt = validate_registration_receipt(registration, config, root=root)
    lifecycle_path = root / config.registration_lifecycle_path
    completed = lifecycle_path.is_file()
    if completed:
        validate_registration_lifecycle(registration, config, receipt, root=root)
    return {
        "study_id": registration.study_id,
        "registration_version": registration.registration_version,
        "method_id": registration.method_id,
        "method_version": registration.method_version,
        "title": registration.title,
        "status": "COMPLETED" if completed else "PREREGISTERED",
        "registration_classification": registration.registration_classification,
        "preregistration_file_sha256": hashlib.sha256(raw).hexdigest(),
        "locked_design_sha256": locked_design_fingerprint(registration),
        "executable_configuration_sha256": (
            executable_configuration_fingerprint(config)
        ),
        "registration_receipt_fingerprint": receipt.receipt_fingerprint,
        "locked_fields": list(LOCKED_FIELDS),
        "deviation_count": len(registration.preregistration_deviations),
        "deviation_ledger_sha256": deviation_fingerprint(registration),
        "preregistration_path": config.preregistration_path.as_posix(),
        "registration_receipt_path": config.registration_receipt_path.as_posix(),
        "registration_lifecycle_path": config.registration_lifecycle_path.as_posix(),
    }


def assert_locked_fields_unchanged(
    before: Task04Preregistration, after: Task04Preregistration
) -> None:
    """Reject mutation of any semantic field across lifecycle transition."""
    if locked_design_fingerprint(before) != locked_design_fingerprint(after):
        raise ValueError("Locked preregistration fields changed after registration")


def transition_to_completed(
    path: Path,
    *,
    config: Task04Config,
    root: Path,
) -> Task04Preregistration:
    """Persist completion without rewriting the committed registration."""
    before, _raw = read_preregistration(path)
    receipt = validate_registration_receipt(before, config, root=root)
    lifecycle_path = root / config.registration_lifecycle_path
    if lifecycle_path.exists():
        validate_registration_lifecycle(before, config, receipt, root=root)
        return before
    _write_lifecycle(before, config, receipt, lifecycle_path)
    validate_registration_lifecycle(before, config, receipt, root=root)
    return before
