"""Versioned Task 04 registration, receipt, and lifecycle controls."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import ConfigDict, Field, StrictInt, model_validator

from eurusd_research.config import StrictModel
from eurusd_research.studies.completion import (
    CompletionGateEvidence,
    IndependentReconciliationEvidence,
    OutputDigestEvidence,
    build_output_digest,
)
from eurusd_research.studies.configuration import Task04Config
from eurusd_research.studies.dependencies import validate_task04_dependencies
from eurusd_research.studies.git_anchor import (
    assert_anchor_lineage,
    commit_tree_id,
    registered_path_tree_fingerprint,
    resolve_commit,
)
from eurusd_research.studies.integrity import (
    read_task03_row_membership_evidence,
    validate_source_dependency_manifest,
)
from eurusd_research.studies.registration_models import Task04PreregistrationV28

MUTABLE_REGISTRATION_FIELDS = ("status",)
RECEIPT_SCHEMA_VERSION = "task04-registration-receipt-v5"
LIFECYCLE_SCHEMA_VERSION = "task04-registration-lifecycle-v5"
CANONICALIZATION_VERSION = "task04-canonical-json-v1"


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


Task04Preregistration = Task04PreregistrationV28


LOCKED_FIELDS = tuple(
    field
    for field in Task04Preregistration.model_fields
    if field not in MUTABLE_REGISTRATION_FIELDS
)


class ReceiptSection(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RegisteredBlobIdentity(ReceiptSection):
    path: str = Field(min_length=1)
    git_blob_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReceiptIdentity(ReceiptSection):
    receipt_schema_version: Literal["task04-registration-receipt-v5"]
    study_id: Literal["TASK-04"]
    registration_version: Literal["2.8"]
    method_id: Literal["RANGE-WEEKDAY-001"]
    method_version: Literal["range-weekday-registered-replication-v2.8"]
    registration_file_path: Literal["studies/task04_daily_range_weekday.v2.8.yaml"]
    receipt_file_path: Literal["studies/task04_daily_range_weekday.v2.8.receipt.json"]
    registration_classification: Literal[
        "correctively registered replication of the developed Task 04 analysis"
    ]
    non_first_look_disclosure: str = Field(min_length=1)
    registration_status_at_anchoring: Literal["PREREGISTERED"]


class ReceiptGitAnchor(ReceiptSection):
    anchor_commit_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    anchor_tree_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    anchor_parent_commit_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    branch_at_registration: str = Field(min_length=1)
    anchor_reachability_policy: Literal["ANCHOR_MUST_REMAIN_REACHABLE"]
    descendant_validation_policy: Literal[
        "CURRENT_STATE_MUST_EQUAL_OR_DESCEND_FROM_ANCHOR"
    ]
    registered_path_tree_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_path_inventory: tuple[str, ...] = Field(min_length=1)
    registered_blob_identities: tuple[RegisteredBlobIdentity, ...] = Field(min_length=1)
    repository_dirty_state_policy: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> ReceiptGitAnchor:
        paths = tuple(self.registered_path_inventory)
        blobs = tuple(item.path for item in self.registered_blob_identities)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("Registered receipt paths must be unique and sorted")
        if blobs != paths:
            raise ValueError("Registered blobs must exactly match path inventory")
        return self


class ReceiptScientificExecutableDesign(ReceiptSection):
    semantic_design_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    executable_configuration_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_tree_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_lock_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_dependency_lock_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    timestamp_assumption: Literal["AS_SUPPLIED_TIMESTAMP_LABEL_DATE"]
    unresolved_timestamp_limitation: str = Field(min_length=1)
    maximum_evidence_rating_cap: Literal["MODERATE"]
    deviation_policy: Literal["NEW_REGISTRATION_VERSION_REQUIRED"]
    expected_production_output_inventory: tuple[str, ...] = Field(min_length=1)
    expected_figure_inventory: tuple[str, ...] = Field(min_length=8, max_length=8)
    validated_candidate_identity_path: Literal[
        "studies/task04_v2.8_validated_candidate_identity.json"
    ]
    candidate_identity_schema_version: Literal["task04-validated-candidate-identity-v1"]
    candidate_identity_establishment_stage: Literal[
        "AFTER_TWELVE_COMPONENT_RECONCILIATION"
    ]
    candidate_identity_immutability_policy: Literal[
        "WRITE_ONCE_NO_AUTOMATIC_REBASELINE"
    ]
    candidate_identity_comparison_policy: Literal[
        "CURRENT_PATH_SIZE_SHA256_AND_DIGEST_MUST_EQUAL_VALIDATED_BASELINE"
    ]


class ReceiptRawEvidence(ReceiptSection):
    path: Literal["data/raw/EURUSD_M15_UTC.csv"]
    dataset_version: Literal["sha256:b2a41310927aa9a9"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReceiptTask02Evidence(ReceiptSection):
    schema_version: Literal["raw-data-quality-audit-v2"]
    audit_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    readiness_status: Literal["PASS, CONDITIONALLY_READY"]


class ReceiptTask03ProfileCounts(ReceiptSection):
    default_research_rows: StrictInt = Field(gt=0)
    strict_continuity_rows: StrictInt = Field(gt=0)
    sensitivity_full_rows: StrictInt = Field(gt=0)
    sensitivity_2023_rows: StrictInt = Field(gt=0)
    observed_dates: StrictInt = Field(gt=0)
    default_research_dates: StrictInt = Field(gt=0)
    strict_continuity_dates: StrictInt = Field(gt=0)
    sensitivity_full_dates: StrictInt = Field(gt=0)
    sensitivity_2023_dates: StrictInt = Field(gt=0)


class ReceiptTask03Evidence(ReceiptSection):
    schema_version: Literal["task03-layered-evidence-v1"]
    method_version: Literal["research-coverage-v1"]
    coverage_stable_artifact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_membership_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    stable_artifact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_context_fingerprint_at_receipt: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_context_variance_policy: Literal[
        "INFORMATIONAL_IF_SCIENTIFIC_AND_STABLE_ARTIFACT_IDENTITIES_MATCH"
    ]
    exact_row_membership_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    exact_date_membership_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_counts: ReceiptTask03ProfileCounts
    algebra_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReceiptUpstreamEvidence(ReceiptSection):
    raw_dataset: ReceiptRawEvidence
    task02: ReceiptTask02Evidence
    task03: ReceiptTask03Evidence


class ReceiptIntegrity(ReceiptSection):
    canonicalization_version: Literal["task04-canonical-json-v1"]
    field_inventory: tuple[str, ...] = Field(min_length=1)
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_mutable_fields_after_anchoring: tuple[str, ...] = Field(max_length=0)


class Task04RegistrationReceipt(StrictModel):
    """Immutable pre-result identity of the v2.8 registered replication."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: ReceiptIdentity
    git_anchor: ReceiptGitAnchor
    scientific_and_executable_design: ReceiptScientificExecutableDesign
    upstream_evidence: ReceiptUpstreamEvidence
    integrity: ReceiptIntegrity
    receipt_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class LifecycleIdentity(ReceiptSection):
    lifecycle_schema_version: Literal["task04-registration-lifecycle-v5"]
    study_id: Literal["TASK-04"]
    registration_version: Literal["2.8"]
    method_id: Literal["RANGE-WEEKDAY-001"]
    method_version: Literal["range-weekday-registered-replication-v2.8"]
    lifecycle_file_path: Literal[
        "studies/task04_daily_range_weekday.v2.8.lifecycle.json"
    ]
    status: Literal["COMPLETED"]
    receipt_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    anchor_commit_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    anchor_tree_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    anchor_parent_commit_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    registration_classification: Literal[
        "correctively registered replication of the developed Task 04 analysis"
    ]


class LifecycleProductionState(ReceiptSection):
    production_state_identifier: str = Field(min_length=1)
    production_source_tree_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    descendant_commit_or_working_state: str = Field(min_length=1)
    descends_from_anchor: Literal[True]
    registered_anchor_paths_unchanged: Literal[True]
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task02_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    task03_scientific_membership_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    task03_stable_artifact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    task03_execution_context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    task03_execution_context_variance_observed: bool
    task03_scientific_validation_passed: Literal[True]
    task03_stable_artifact_validation_passed: Literal[True]
    task03_execution_context_classified: Literal[True]
    executable_configuration_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class LifecycleOutputEvidence(ReceiptSection):
    production_output_inventory: tuple[str, ...] = Field(min_length=1)
    exact_output_paths: tuple[str, ...] = Field(min_length=1)
    output_digest: OutputDigestEvidence
    figure_inventory: tuple[str, ...] = Field(min_length=8, max_length=8)
    no_extra_output_validation_passed: Literal[True]
    output_containment_validation_passed: Literal[True]
    validated_candidate_identity_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_matches_validated_candidate_identity: Literal[True]
    byte_identity_mismatch_count: Literal[0]

    @model_validator(mode="after")
    def validate_output_identity(self) -> LifecycleOutputEvidence:
        expected = tuple(sorted(self.production_output_inventory))
        if self.exact_output_paths != expected:
            raise ValueError("Lifecycle exact output paths disagree with inventory")
        if tuple(item.relative_path for item in self.output_digest.files) != expected:
            raise ValueError("Lifecycle file hashes disagree with inventory")
        if not set(self.figure_inventory).issubset(set(expected)):
            raise ValueError("Lifecycle figure inventory is not an output subset")
        if self.output_digest.path_plus_bytes_digest != self.baseline_candidate_digest:
            raise ValueError("Lifecycle final digest differs from candidate baseline")
        return self


class LifecycleScientificCompletion(ReceiptSection):
    primary_population: StrictInt = Field(gt=0)
    primary_statistic: float = Field(strict=True, allow_inf_nan=False, ge=0.0)
    primary_p_value: float = Field(strict=True, allow_inf_nan=False, ge=0.0, le=1.0)
    primary_effect_size: float = Field(strict=True, allow_inf_nan=False)
    final_evidence_rating: Literal["INSUFFICIENT", "WEAK", "MODERATE", "STRONG"]
    rating_cap: Literal["MODERATE"]
    timestamp_limitation: str = Field(min_length=1)
    required_robustness_evidence_status: Literal["PASS"]
    independent_reconciliation: IndependentReconciliationEvidence
    deterministic_regeneration_status: Literal["PASS"]
    deterministic_regeneration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    figure_validation_status: Literal["PASS"]
    population_reconciliation_status: Literal["PASS"]


class LifecycleGovernance(ReceiptSection):
    final_deviation_policy: Literal["NEW_REGISTRATION_VERSION_REQUIRED"]
    final_deviation_count: Literal[0]
    zero_deviation_declaration: Literal["NO_DEVIATIONS"]
    deviation_ledger_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    limitations: tuple[str, ...] = Field(min_length=1)
    completion_gates: CompletionGateEvidence
    quality_gate_status: Literal["PASS"]
    permitted_future_transition_policy: Literal[
        "COMPLETED_IS_TERMINAL;_CHANGES_REQUIRE_NEW_REGISTRATION_VERSION"
    ]


class Task04RegistrationLifecycle(StrictModel):
    """Terminal completion evidence bound to the original v2.8 receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: LifecycleIdentity
    production_state: LifecycleProductionState
    output_evidence: LifecycleOutputEvidence
    scientific_completion: LifecycleScientificCompletion
    governance: LifecycleGovernance
    lifecycle_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_candidate_to_final_identity(self) -> Task04RegistrationLifecycle:
        reconciliation = self.scientific_completion.independent_reconciliation
        byte_identity = reconciliation.candidate_byte_identity
        if byte_identity is None or not byte_identity.passed:
            raise ValueError("Lifecycle lacks passing candidate byte identity")
        output = self.output_evidence
        if (
            output.validated_candidate_identity_fingerprint
            != byte_identity.validated_candidate_identity_fingerprint
        ):
            raise ValueError("Lifecycle candidate identity fingerprint differs")
        if output.baseline_candidate_digest != byte_identity.baseline_candidate_digest:
            raise ValueError("Lifecycle candidate baseline digest differs")
        if output.output_digest.files != byte_identity.baseline_files:
            raise ValueError("Final per-file hashes differ from candidate baseline")
        if output.output_digest.path_plus_bytes_digest != (
            byte_identity.baseline_candidate_digest
        ):
            raise ValueError("Final digest differs from candidate baseline")
        return self


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
            "task03_coverage_stable_fingerprint": (
                config.required_coverage_summary_stable_sha256
            ),
            "task03_scientific_membership_fingerprint": (
                config.required_task03_scientific_membership_fingerprint
            ),
            "task03_stable_artifact_fingerprint": (
                config.required_task03_stable_artifact_fingerprint
            ),
            "task03_evidence_layer_schema_version": (
                config.task03_evidence_layer_schema_version
            ),
            "task03_execution_context_variance_policy": (
                config.task03_execution_context_variance_policy
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
        "production_governance": {
            "receipt_schema_version": config.receipt_schema_version,
            "lifecycle_schema_version": config.lifecycle_schema_version,
            "candidate_output_directory": config.candidate_output_directory.as_posix(),
            "final_output_directory": config.output_directory.as_posix(),
            "validated_candidate_identity_path": (
                config.validated_candidate_identity_path.as_posix()
            ),
            "completion_sequence": list(config.completion_sequence),
            "candidate_outputs_are_completed_evidence": (
                config.candidate_outputs_are_completed_evidence
            ),
            "lifecycle_state_integration_tests": list(
                config.lifecycle_state_integration_tests
            ),
            "receipt_existence_policy": config.receipt_existence_policy,
            "task03_evidence_layer_schema_version": (
                config.task03_evidence_layer_schema_version
            ),
            "task03_scientific_membership_policy": (
                config.task03_scientific_membership_policy
            ),
            "task03_stable_artifact_policy": config.task03_stable_artifact_policy,
            "task03_execution_context_policy": (
                config.task03_execution_context_variance_policy
            ),
            "task03_material_mismatch_policy": config.task03_material_mismatch_policy,
            "output_digest_algorithm": config.output_digest_algorithm,
            "candidate_identity_schema_version": (
                config.candidate_identity_schema_version
            ),
            "candidate_identity_establishment_stage": (
                config.candidate_identity_establishment_stage
            ),
            "candidate_identity_immutability_policy": (
                config.candidate_identity_immutability_policy
            ),
            "candidate_identity_comparison_policy": (
                config.candidate_identity_comparison_policy
            ),
            "promotion_identity_policy": config.promotion_identity_policy,
            "independent_reconciliation_implementation": (
                config.independent_reconciliation_implementation
            ),
            "candidate_csv_loading_policy": config.candidate_csv_loading_policy,
            "exclusion_reasons_empty_value": config.exclusion_reasons_empty_value,
            "exclusion_reasons_null_policy": config.exclusion_reasons_null_policy,
            "regime_lineage_comparison_fields": list(
                config.regime_lineage_comparison_fields
            ),
            "output_path_convention": config.output_path_convention,
            "figure_path_prefix": config.figure_path_prefix,
            "mismatch_treatment": config.mismatch_treatment,
            "independent_reconciliation_components": list(
                config.independent_reconciliation_components
            ),
            "required_checked_statistics": [
                "complete_daily_profile_fields",
                "full_descriptive_statistics",
                "primary_and_complementary_inference",
                "all_pairwise_statistics",
            ],
            "required_checked_robustness": [
                "chronological_split",
                "fixed_periods",
                "every_calendar_year",
                "past_only_volatility_regimes",
                "winsorisation_and_largest_tail_exclusion",
            ],
            "required_checked_output_evidence": [
                "exact_relative_path_set",
                "regular_file_and_containment",
                "per_file_sha256",
                "canonical_path_plus_bytes_digest",
            ],
            "categorical_mismatch_tolerance": config.categorical_mismatch_tolerance,
            "membership_mismatch_tolerance": config.membership_mismatch_tolerance,
            "inventory_mismatch_tolerance": config.inventory_mismatch_tolerance,
            "unchecked_component_policy": config.unchecked_component_policy,
            "independent_rating_reconstruction_required": (
                config.independent_rating_reconstruction_required
            ),
            "lifecycle_requires_component_level_reconciliation": True,
            "defect_detection_requirement": (
                "EACH_REGISTERED_COMPONENT_MUST_FAIL_ON_TARGETED_MUTATION"
            ),
            "maximum_numerical_discrepancy_tolerance": (
                config.maximum_numerical_discrepancy_tolerance
            ),
            "minimum_branch_coverage_percent": (config.minimum_branch_coverage_percent),
            "failure_policy": config.candidate_failure_policy,
            "promotion_policy": config.promotion_policy,
            "required_completion_gates": list(config.required_completion_gates),
            "anchor_ancestry_policy": config.anchor_ancestry_policy,
        },
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
            "task03_coverage_stable_fingerprint": (
                registration.task_03_dependency.coverage_summary_stable_fingerprint
            ),
            "task03_scientific_membership_fingerprint": (
                registration.task_03_dependency.scientific_membership_fingerprint
            ),
            "task03_stable_artifact_fingerprint": (
                registration.task_03_dependency.stable_artifact_fingerprint
            ),
            "task03_evidence_layer_schema_version": (
                registration.task_03_dependency.evidence_layer_schema_version
            ),
            "task03_execution_context_variance_policy": (
                registration.task_03_dependency.execution_context_variance_policy
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
        "production_governance": (
            registration.production_governance.model_dump(mode="json")
        ),
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


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _registered_blob_identities(
    root: Path, anchor: str, paths: tuple[str, ...]
) -> tuple[RegisteredBlobIdentity, ...]:
    records: list[RegisteredBlobIdentity] = []
    for path in paths:
        line = _git(root, "ls-tree", anchor, "--", path)
        parts = line.split()
        if len(parts) < 4 or parts[1] != "blob":
            raise ValueError(f"Registered anchor path is not a blob: {path}")
        content = subprocess.run(
            ["git", "show", f"{anchor}:{path}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        records.append(
            RegisteredBlobIdentity(
                path=path,
                git_blob_id=parts[2],
                sha256=hashlib.sha256(content).hexdigest(),
            )
        )
    return tuple(records)


RECEIPT_FIELD_INVENTORY = tuple(
    sorted(
        (
            "identity.*",
            "git_anchor.*",
            "scientific_and_executable_design.*",
            "upstream_evidence.raw_dataset.*",
            "upstream_evidence.task02.*",
            "upstream_evidence.task03.*",
            "integrity.canonicalization_version",
            "integrity.field_inventory",
            "integrity.schema_fingerprint",
            "integrity.allowed_mutable_fields_after_anchoring",
        )
    )
)


def build_registration_receipt(
    registration: Task04Preregistration,
    config: Task04Config,
    *,
    root: Path,
    anchor_commit: str | None = None,
    branch_at_registration: str | None = None,
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
    anchor_parent = resolve_commit(root, f"{anchor}^")
    branch = branch_at_registration or _git(root, "branch", "--show-current")
    task03 = read_task03_row_membership_evidence(root / config.task03_evidence_path)
    row_membership = _canonical_digest(
        [
            {"profile": item.profile, "sha256": item.row_membership_sha256}
            for item in task03.profiles
        ]
    )
    date_membership = _canonical_digest(
        [
            {"profile": item.profile, "sha256": item.date_membership_sha256}
            for item in task03.profiles
        ]
    )
    algebra = _canonical_digest(
        {
            "strict_subset_default": (
                task03.scientific_membership.strict_subset_default
            ),
            "strict_disjoint_sensitivity_full": (
                task03.scientific_membership.strict_disjoint_sensitivity_full
            ),
            "strict_union_sensitivity_full_equals_default": (
                task03.scientific_membership.strict_union_sensitivity_full_equals_default
            ),
            "sensitivity_2023_subset_sensitivity_full": (
                task03.scientific_membership.sensitivity_2023_subset_sensitivity_full
            ),
        }
    )
    counts = {item.profile: item.row_included for item in task03.profiles}
    date_counts = {item.profile: item.date_included for item in task03.profiles}
    timestamp_limitation = (
        registration.timestamp_semantics.possible_boundary_consequence
    )
    output_inventory = _expected_inventory(config)
    figures = tuple(sorted(f"figures/{x}" for x in config.expected_figure_files))
    payload: dict[str, Any] = {
        "identity": {
            "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
            "study_id": registration.study_id,
            "registration_version": registration.registration_version,
            "method_id": registration.method_id,
            "method_version": registration.method_version,
            "registration_file_path": config.preregistration_path.as_posix(),
            "receipt_file_path": config.registration_receipt_path.as_posix(),
            "registration_classification": registration.registration_classification,
            "non_first_look_disclosure": registration.registration_disclosure,
            "registration_status_at_anchoring": registration.status,
        },
        "git_anchor": {
            "anchor_commit_id": anchor,
            "anchor_tree_id": tree_id,
            "anchor_parent_commit_id": anchor_parent,
            "branch_at_registration": branch,
            "anchor_reachability_policy": "ANCHOR_MUST_REMAIN_REACHABLE",
            "descendant_validation_policy": (
                "CURRENT_STATE_MUST_EQUAL_OR_DESCEND_FROM_ANCHOR"
            ),
            "registered_path_tree_fingerprint": registered_tree,
            "registered_path_inventory": registered_paths,
            "registered_blob_identities": [
                item.model_dump(mode="json")
                for item in _registered_blob_identities(root, anchor, registered_paths)
            ],
            "repository_dirty_state_policy": (
                registration.repository_lineage.dirty_state_policy
            ),
        },
        "scientific_and_executable_design": {
            "semantic_design_fingerprint": locked_design_fingerprint(registration),
            "executable_configuration_fingerprint": (
                executable_configuration_fingerprint(config)
            ),
            "source_manifest_fingerprint": (
                source_manifest.dependency_manifest_fingerprint
            ),
            "source_tree_fingerprint": source_manifest.source_tree_fingerprint,
            "environment_lock_fingerprint": environment_sha256,
            "package_dependency_lock_fingerprint": _sha256_file(
                root / "pyproject.toml"
            ),
            "timestamp_assumption": config.timestamp_operational_assumption,
            "unresolved_timestamp_limitation": timestamp_limitation,
            "maximum_evidence_rating_cap": (
                registration.timestamp_semantics.evidence_rating_cap
            ),
            "deviation_policy": registration.deviation_policy.model,
            "expected_production_output_inventory": output_inventory,
            "expected_figure_inventory": figures,
            "validated_candidate_identity_path": (
                registration.production_governance.validated_candidate_identity_path
            ),
            "candidate_identity_schema_version": (
                registration.production_governance.candidate_identity_schema_version
            ),
            "candidate_identity_establishment_stage": (
                registration.production_governance.candidate_identity_establishment_stage
            ),
            "candidate_identity_immutability_policy": (
                registration.production_governance.candidate_identity_immutability_policy
            ),
            "candidate_identity_comparison_policy": (
                registration.production_governance.candidate_identity_comparison_policy
            ),
        },
        "upstream_evidence": {
            "raw_dataset": {
                "path": registration.repository_lineage.raw_path,
                "dataset_version": registration.dataset_version,
                "sha256": config.required_raw_sha256,
                "manifest_fingerprint": config.required_raw_manifest_sha256,
            },
            "task02": {
                "schema_version": registration.task_02_dependency.method_version,
                "audit_fingerprint": config.required_task02_audit_fingerprint,
                "readiness_status": "PASS, CONDITIONALLY_READY",
            },
            "task03": {
                "schema_version": task03.schema_version,
                "method_version": task03.task03_method_version,
                "coverage_stable_artifact_fingerprint": (
                    config.required_coverage_summary_stable_sha256
                ),
                "scientific_membership_fingerprint": (
                    task03.scientific_membership_fingerprint
                ),
                "stable_artifact_fingerprint": task03.stable_artifact_fingerprint,
                "execution_context_fingerprint_at_receipt": (
                    task03.execution_context_fingerprint
                ),
                "execution_context_variance_policy": (
                    task03.execution_context.context_variance_policy
                ),
                "exact_row_membership_fingerprint": row_membership,
                "exact_date_membership_fingerprint": date_membership,
                "profile_counts": {
                    "default_research_rows": counts["DEFAULT_RESEARCH"],
                    "strict_continuity_rows": counts["STRICT_CONTINUITY"],
                    "sensitivity_full_rows": counts["SENSITIVITY_FULL"],
                    "sensitivity_2023_rows": counts["SENSITIVITY_2023"],
                    "observed_dates": task03.observed_date_count,
                    "default_research_dates": date_counts["DEFAULT_RESEARCH"],
                    "strict_continuity_dates": date_counts["STRICT_CONTINUITY"],
                    "sensitivity_full_dates": date_counts["SENSITIVITY_FULL"],
                    "sensitivity_2023_dates": date_counts["SENSITIVITY_2023"],
                },
                "algebra_fingerprint": algebra,
            },
        },
        "integrity": {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "field_inventory": RECEIPT_FIELD_INVENTORY,
            "schema_fingerprint": _canonical_digest(
                Task04RegistrationReceipt.model_json_schema()
            ),
            "allowed_mutable_fields_after_anchoring": (),
        },
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
        anchor_commit=receipt.git_anchor.anchor_commit_id,
        branch_at_registration=receipt.git_anchor.branch_at_registration,
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
        "receipt schema": receipt.identity.receipt_schema_version
        == config.receipt_schema_version,
        "study": receipt.identity.study_id == registration.study_id,
        "registration version": receipt.identity.registration_version
        == registration.registration_version,
        "method": receipt.identity.method_id == registration.method_id
        and receipt.identity.method_version == registration.method_version,
        "registration path": receipt.identity.registration_file_path
        == config.preregistration_path.as_posix(),
        "receipt path": receipt.identity.receipt_file_path
        == config.registration_receipt_path.as_posix(),
        "semantic design": receipt.scientific_and_executable_design
        == expected.scientific_and_executable_design,
        "Git anchor": receipt.git_anchor == expected.git_anchor,
        "upstream evidence": receipt.upstream_evidence == expected.upstream_evidence,
        "receipt integrity": receipt.integrity == expected.integrity,
        "receipt fingerprint": receipt.receipt_fingerprint
        == expected.receipt_fingerprint,
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise ValueError(
            "Task 04 registration receipt validation failed: " + ", ".join(failed)
        )


def build_completed_lifecycle(
    registration: Task04Preregistration,
    config: Task04Config,
    receipt: Task04RegistrationReceipt,
    *,
    production_state_identifier: str,
    descendant_commit_or_working_state: str,
    output_evidence: LifecycleOutputEvidence,
    independent_reconciliation: IndependentReconciliationEvidence,
    completion_gates: CompletionGateEvidence,
    primary_population: int,
    primary_statistic: float,
    primary_p_value: float,
    primary_effect_size: float,
    final_evidence_rating: Literal["INSUFFICIENT", "WEAK", "MODERATE", "STRONG"],
    task03_execution_context_fingerprint: str,
    task03_execution_context_variance_observed: bool,
    limitations: tuple[str, ...],
) -> Task04RegistrationLifecycle:
    """Construct terminal lifecycle evidence only after every gate has passed."""
    if not independent_reconciliation.passed:
        raise ValueError("Independent reconciliation did not pass")
    byte_identity = independent_reconciliation.candidate_byte_identity
    if byte_identity is None or not byte_identity.passed:
        raise ValueError("Lifecycle requires candidate baseline byte reconciliation")
    if completion_gates.maximum_numerical_discrepancy != (
        independent_reconciliation.maximum_numerical_discrepancy
    ):
        raise ValueError("Completion and reconciliation discrepancies disagree")
    if final_evidence_rating == "STRONG":
        raise ValueError("Unresolved timestamp semantics cap Task 04 at MODERATE")
    anchor = receipt.git_anchor
    registered_outputs = tuple(
        sorted(
            receipt.scientific_and_executable_design.expected_production_output_inventory
        )
    )
    if output_evidence.exact_output_paths != registered_outputs:
        raise ValueError("Completion output evidence differs from receipt inventory")
    if output_evidence.figure_inventory != tuple(
        sorted(receipt.scientific_and_executable_design.expected_figure_inventory)
    ):
        raise ValueError("Completion figure evidence differs from receipt inventory")
    if (
        output_evidence.validated_candidate_identity_fingerprint
        != byte_identity.validated_candidate_identity_fingerprint
        or output_evidence.baseline_candidate_digest
        != byte_identity.baseline_candidate_digest
    ):
        raise ValueError("Lifecycle and reconciliation use different baselines")
    output_digest = output_evidence.output_digest.path_plus_bytes_digest
    payload: dict[str, Any] = {
        "identity": {
            "lifecycle_schema_version": LIFECYCLE_SCHEMA_VERSION,
            "study_id": registration.study_id,
            "registration_version": registration.registration_version,
            "method_id": registration.method_id,
            "method_version": registration.method_version,
            "lifecycle_file_path": config.registration_lifecycle_path.as_posix(),
            "status": "COMPLETED",
            "receipt_fingerprint": receipt.receipt_fingerprint,
            "anchor_commit_id": anchor.anchor_commit_id,
            "anchor_tree_id": anchor.anchor_tree_id,
            "anchor_parent_commit_id": anchor.anchor_parent_commit_id,
            "registration_classification": registration.registration_classification,
        },
        "production_state": {
            "production_state_identifier": production_state_identifier,
            "production_source_tree_fingerprint": (
                receipt.scientific_and_executable_design.source_tree_fingerprint
            ),
            "descendant_commit_or_working_state": descendant_commit_or_working_state,
            "descends_from_anchor": True,
            "registered_anchor_paths_unchanged": True,
            "raw_sha256": receipt.upstream_evidence.raw_dataset.sha256,
            "task02_fingerprint": receipt.upstream_evidence.task02.audit_fingerprint,
            "task03_scientific_membership_fingerprint": (
                receipt.upstream_evidence.task03.scientific_membership_fingerprint
            ),
            "task03_stable_artifact_fingerprint": (
                receipt.upstream_evidence.task03.stable_artifact_fingerprint
            ),
            "task03_execution_context_fingerprint": (
                task03_execution_context_fingerprint
            ),
            "task03_execution_context_variance_observed": (
                task03_execution_context_variance_observed
            ),
            "task03_scientific_validation_passed": True,
            "task03_stable_artifact_validation_passed": True,
            "task03_execution_context_classified": True,
            "executable_configuration_fingerprint": (
                receipt.scientific_and_executable_design.executable_configuration_fingerprint
            ),
        },
        "output_evidence": output_evidence.model_dump(mode="json"),
        "scientific_completion": {
            "primary_population": primary_population,
            "primary_statistic": primary_statistic,
            "primary_p_value": primary_p_value,
            "primary_effect_size": primary_effect_size,
            "final_evidence_rating": final_evidence_rating,
            "rating_cap": "MODERATE",
            "timestamp_limitation": (
                receipt.scientific_and_executable_design.unresolved_timestamp_limitation
            ),
            "required_robustness_evidence_status": "PASS",
            "independent_reconciliation": independent_reconciliation.model_dump(
                mode="json"
            ),
            "deterministic_regeneration_status": "PASS",
            "deterministic_regeneration_digest": output_digest,
            "figure_validation_status": "PASS",
            "population_reconciliation_status": "PASS",
        },
        "governance": {
            "final_deviation_policy": "NEW_REGISTRATION_VERSION_REQUIRED",
            "final_deviation_count": 0,
            "zero_deviation_declaration": "NO_DEVIATIONS",
            "deviation_ledger_fingerprint": deviation_fingerprint(registration),
            "limitations": limitations,
            "completion_gates": completion_gates.model_dump(mode="json"),
            "quality_gate_status": "PASS",
            "permitted_future_transition_policy": (
                "COMPLETED_IS_TERMINAL;_CHANGES_REQUIRE_NEW_REGISTRATION_VERSION"
            ),
        },
    }
    return Task04RegistrationLifecycle.model_validate(
        {**payload, "lifecycle_fingerprint": _canonical_digest(payload)}
    )


def write_completed_lifecycle(
    lifecycle: Task04RegistrationLifecycle, path: Path
) -> None:
    """Persist one terminal lifecycle; replacement and reversal are forbidden."""
    if path.exists():
        raise FileExistsError("Task 04 registration lifecycle already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                lifecycle.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


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
    expected_paths = _expected_inventory(config)
    actual_output = build_output_digest(
        root / config.output_directory,
        expected_paths,
        figure_paths=(f"figures/{name}" for name in config.expected_figure_files),
    )
    assert_completed_lifecycle_matches(
        lifecycle,
        registration=registration,
        config=config,
        receipt=receipt,
    )
    checks = (
        lifecycle.output_evidence.output_digest == actual_output,
        lifecycle.output_evidence.exact_output_paths == expected_paths,
    )
    if not all(checks):
        raise ValueError("Task 04 completed lifecycle output evidence changed")
    return lifecycle


def assert_completed_lifecycle_matches(
    lifecycle: Task04RegistrationLifecycle,
    *,
    registration: Task04Preregistration,
    config: Task04Config,
    receipt: Task04RegistrationReceipt,
) -> None:
    """Validate terminal identity independently of lifecycle storage and outputs."""
    checks = (
        lifecycle.identity.receipt_fingerprint == receipt.receipt_fingerprint,
        lifecycle.identity.anchor_commit_id == receipt.git_anchor.anchor_commit_id,
        lifecycle.identity.anchor_tree_id == receipt.git_anchor.anchor_tree_id,
        lifecycle.identity.anchor_parent_commit_id
        == receipt.git_anchor.anchor_parent_commit_id,
        lifecycle.identity.registration_version == registration.registration_version,
        lifecycle.identity.method_version == registration.method_version,
        lifecycle.identity.status == "COMPLETED",
        lifecycle.production_state.production_source_tree_fingerprint
        == receipt.scientific_and_executable_design.source_tree_fingerprint,
        lifecycle.production_state.executable_configuration_fingerprint
        == executable_configuration_fingerprint(config),
        lifecycle.production_state.task03_scientific_membership_fingerprint
        == receipt.upstream_evidence.task03.scientific_membership_fingerprint,
        lifecycle.production_state.task03_stable_artifact_fingerprint
        == receipt.upstream_evidence.task03.stable_artifact_fingerprint,
        lifecycle.production_state.task03_scientific_validation_passed,
        lifecycle.production_state.task03_stable_artifact_validation_passed,
        lifecycle.production_state.task03_execution_context_classified,
        lifecycle.production_state.registered_anchor_paths_unchanged,
        lifecycle.production_state.descends_from_anchor,
        lifecycle.governance.final_deviation_count == 0,
        lifecycle.governance.limitations == registration.known_limitations,
        lifecycle.scientific_completion.independent_reconciliation.passed,
        lifecycle.governance.completion_gates.maximum_numerical_discrepancy
        == (
            lifecycle.scientific_completion.independent_reconciliation.maximum_numerical_discrepancy
        ),
        lifecycle.scientific_completion.deterministic_regeneration_digest
        == lifecycle.output_evidence.output_digest.path_plus_bytes_digest,
    )
    if not all(checks):
        raise ValueError("Task 04 completed lifecycle does not match registration")


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
        "status": "COMPLETED" if completed else "CANDIDATE",
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
