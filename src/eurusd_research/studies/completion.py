"""Fail-closed Task 04 v2.9 completion evidence and output controls.

This module contains no weekday-result calculation.  It defines the evidence
that Phase B must obtain before a candidate study may be promoted and marked
complete.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StrictBool, StrictInt, model_validator

from eurusd_research.config import StrictModel
from eurusd_research.studies.integrity import (
    assert_regular_contained_file,
    canonical_digest,
)
from eurusd_research.studies.orchestration import PHASE_B_SEQUENCE, PhaseBProgress

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
GitCommit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
NonNegativeFinite = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0)]
ComponentName = Literal[
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
]

OUTPUT_DIGEST_ALGORITHM: Literal["task04-path-length-bytes-sha256-v1"] = (
    "task04-path-length-bytes-sha256-v1"
)
INDEPENDENT_RECONCILIATION_IMPLEMENTATION = "task04-independent-full-reproduction-v2"
CANDIDATE_IDENTITY_SCHEMA_VERSION = "task04-validated-candidate-identity-v1"
RECONCILIATION_COMPONENTS = (
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
COMPLETION_BOOLEAN_FIELDS = (
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
)


class FrozenEvidence(StrictModel):
    """Immutable unknown-key-rejecting completion evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class OutputFileHash(FrozenEvidence):
    """Identity of one registered regular output file."""

    relative_path: str = Field(min_length=1)
    size_bytes: StrictInt = Field(ge=0)
    sha256: Sha256
    category: Literal["TABLE_OR_REPORT", "FIGURE"]

    @model_validator(mode="after")
    def validate_path(self) -> OutputFileHash:
        path = Path(self.relative_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in self.relative_path
            or path.as_posix() != self.relative_path
        ):
            raise ValueError("Output evidence paths must be safe and relative")
        return self


class OutputDigestEvidence(FrozenEvidence):
    """Canonical path-plus-bytes digest and its per-file audit records."""

    digest_algorithm: Literal["task04-path-length-bytes-sha256-v1"]
    files: tuple[OutputFileHash, ...] = Field(min_length=1)
    inventory_fingerprint: Sha256
    path_plus_bytes_digest: Sha256

    @model_validator(mode="after")
    def validate_inventory(self) -> OutputDigestEvidence:
        paths = tuple(item.relative_path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("Output digest records must be unique and sorted")
        expected_inventory = canonical_digest(list(paths))
        if self.inventory_fingerprint != expected_inventory:
            raise ValueError("Output inventory fingerprint is invalid")
        return self


class ValidatedCandidateIdentity(FrozenEvidence):
    """Immutable identity established only after candidate reconciliation."""

    schema_version: Literal["task04-validated-candidate-identity-v1"]
    registration_version: Literal["2.9"]
    method_version: Literal["range-weekday-registered-replication-v2.9"]
    anchor_commit: GitCommit
    receipt_fingerprint: Sha256
    establishment_stage: Literal["AFTER_TWELVE_COMPONENT_RECONCILIATION"]
    output_digest: OutputDigestEvidence
    identity_fingerprint: Sha256

    @model_validator(mode="after")
    def validate_identity(self) -> ValidatedCandidateIdentity:
        value = self.model_dump(mode="json")
        fingerprint = value.pop("identity_fingerprint")
        if canonical_digest(value) != fingerprint:
            raise ValueError("Validated candidate identity fingerprint is invalid")
        return self


class CandidateByteIdentityEvidence(FrozenEvidence):
    """Calculated comparison of current output bytes to the trusted baseline."""

    validated_candidate_identity_fingerprint: Sha256
    baseline_candidate_digest: Sha256
    current_candidate_digest: Sha256
    baseline_files: tuple[OutputFileHash, ...] = Field(min_length=1)
    current_files: tuple[OutputFileHash, ...] = Field(min_length=1)
    missing_paths: tuple[str, ...]
    extra_paths: tuple[str, ...]
    size_mismatch_paths: tuple[str, ...]
    sha256_mismatch_paths: tuple[str, ...]
    byte_identity_mismatch_paths: tuple[str, ...]
    digest_mismatch: StrictBool
    baseline_identity_mismatch: StrictBool
    passed: StrictBool

    @model_validator(mode="after")
    def validate_comparison(self) -> CandidateByteIdentityEvidence:
        baseline_by_path = {item.relative_path: item for item in self.baseline_files}
        current_by_path = {item.relative_path: item for item in self.current_files}
        if len(baseline_by_path) != len(self.baseline_files):
            raise ValueError("Baseline candidate paths must be unique")
        if len(current_by_path) != len(self.current_files):
            raise ValueError("Current candidate paths must be unique")
        if tuple(baseline_by_path) != tuple(sorted(baseline_by_path)):
            raise ValueError("Baseline candidate paths must be sorted")
        if tuple(current_by_path) != tuple(sorted(current_by_path)):
            raise ValueError("Current candidate paths must be sorted")
        expected_missing = tuple(sorted(set(baseline_by_path) - set(current_by_path)))
        expected_extra = tuple(sorted(set(current_by_path) - set(baseline_by_path)))
        common = sorted(set(baseline_by_path) & set(current_by_path))
        expected_size = tuple(
            path
            for path in common
            if baseline_by_path[path].size_bytes != current_by_path[path].size_bytes
        )
        expected_sha256 = tuple(
            path
            for path in common
            if baseline_by_path[path].sha256 != current_by_path[path].sha256
        )
        if self.missing_paths != expected_missing or self.extra_paths != expected_extra:
            raise ValueError("Candidate path mismatches were not calculated")
        if self.size_mismatch_paths != expected_size:
            raise ValueError("Candidate size mismatches were not calculated")
        if self.sha256_mismatch_paths != expected_sha256:
            raise ValueError("Candidate SHA-256 mismatches were not calculated")
        if self.byte_identity_mismatch_paths != expected_sha256:
            raise ValueError("Candidate byte mismatches must follow calculated hashes")
        if self.digest_mismatch != (
            self.current_candidate_digest != self.baseline_candidate_digest
        ):
            raise ValueError("Candidate digest mismatch flag was not calculated")
        mismatch = bool(
            self.missing_paths
            or self.extra_paths
            or self.size_mismatch_paths
            or self.sha256_mismatch_paths
            or self.byte_identity_mismatch_paths
            or self.digest_mismatch
            or self.baseline_identity_mismatch
        )
        if self.passed == mismatch:
            raise ValueError("Candidate byte-identity pass contradicts mismatches")
        return self


class ComponentDiscrepancy(FrozenEvidence):
    """Calculated discrepancy summary for one independently checked component."""

    component: ComponentName
    status: Literal["PASS", "FAIL", "NOT_CHECKED"]
    checked_row_count: StrictInt = Field(ge=0)
    checked_field_count: StrictInt = Field(ge=0)
    absolute_discrepancy_by_field: dict[str, NonNegativeFinite]
    relative_discrepancy_by_field: dict[str, NonNegativeFinite]
    maximum_absolute_discrepancy: NonNegativeFinite
    maximum_relative_discrepancy: NonNegativeFinite
    categorical_mismatch_count: StrictInt = Field(ge=0)
    membership_mismatch_count: StrictInt = Field(ge=0)
    inventory_mismatch_count: StrictInt = Field(ge=0)
    mismatch_examples: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    passed: StrictBool

    @model_validator(mode="after")
    def validate_component(self) -> ComponentDiscrepancy:
        calculated = self.checked_row_count > 0 and self.checked_field_count > 0
        contradictions = bool(
            self.categorical_mismatch_count
            or self.membership_mismatch_count
            or self.inventory_mismatch_count
            or self.missing_evidence
            or self.unsupported_claims
        )
        if self.status == "NOT_CHECKED" and (self.passed or calculated):
            raise ValueError("Unchecked reconciliation evidence cannot pass")
        expected_pass = self.status == "PASS" and calculated and not contradictions
        if self.passed != expected_pass:
            raise ValueError("Component pass flag contradicts calculated evidence")
        if self.status == "PASS" and (
            self.maximum_absolute_discrepancy
            != max([0.0, *self.absolute_discrepancy_by_field.values()])
            or self.maximum_relative_discrepancy
            != max([0.0, *self.relative_discrepancy_by_field.values()])
        ):
            raise ValueError("Component maxima do not match field discrepancies")
        return self


class IndependentRatingDecision(FrozenEvidence):
    """One independently evaluated registered rating dimension."""

    dimension: str = Field(min_length=1)
    registered_threshold: str = Field(min_length=1)
    independent_input: str = Field(min_length=1)
    passed: StrictBool
    effect_on_rating: str = Field(min_length=1)
    missing_evidence_rule: Literal["INSUFFICIENT"]


class IndependentReconciliationEvidence(FrozenEvidence):
    """Complete deterministic evidence from an independent raw-to-results path."""

    schema_version: Literal["task04-independent-reconciliation-v3"]
    implementation_id: Literal["task04-independent-full-reproduction-v2"]
    study_id: Literal["TASK-04"]
    registration_version: Literal["2.9"]
    method_version: Literal["range-weekday-registered-replication-v2.9"]
    anchor_commit: GitCommit
    receipt_fingerprint: Sha256
    raw_sha256: Sha256
    task03_evidence_fingerprint: Sha256
    production_output_digest: Sha256
    baseline_establishment_eligible: StrictBool
    candidate_byte_identity: CandidateByteIdentityEvidence | None
    tolerance_policy: Literal["ABSOLUTE_AND_RELATIVE_WITH_ZERO_CATEGORICAL_TOLERANCE"]
    checked_components: tuple[str, ...] = Field(min_length=12, max_length=12)
    source_population: ComponentDiscrepancy
    daily_aggregation: ComponentDiscrepancy
    descriptive_statistics: ComponentDiscrepancy
    primary_inference: ComponentDiscrepancy
    pairwise_analysis: ComponentDiscrepancy
    chronological_analysis: ComponentDiscrepancy
    fixed_period_analysis: ComponentDiscrepancy
    annual_analysis: ComponentDiscrepancy
    volatility_regime_analysis: ComponentDiscrepancy
    extreme_event_analysis: ComponentDiscrepancy
    evidence_rating: ComponentDiscrepancy
    output_inventory: ComponentDiscrepancy
    independent_rating_decisions: tuple[IndependentRatingDecision, ...] = Field(
        min_length=1
    )
    primary_population: StrictInt = Field(gt=0)
    checked_row_count: StrictInt = Field(gt=0)
    checked_field_count: StrictInt = Field(gt=0)
    categorical_mismatch_count: StrictInt = Field(ge=0)
    membership_mismatch_count: StrictInt = Field(ge=0)
    inventory_mismatch_count: StrictInt = Field(ge=0)
    missing_evidence: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    absolute_tolerance: NonNegativeFinite
    relative_tolerance: NonNegativeFinite
    maximum_numerical_discrepancy: NonNegativeFinite
    passed: StrictBool
    artifact_fingerprint: Sha256

    @model_validator(mode="after")
    def validate_reconciliation(self) -> IndependentReconciliationEvidence:
        if self.checked_components != RECONCILIATION_COMPONENTS:
            raise ValueError(
                "Independent component inventory is incomplete or reordered"
            )
        components = tuple(getattr(self, name) for name in RECONCILIATION_COMPONENTS)
        if tuple(item.component for item in components) != RECONCILIATION_COMPONENTS:
            raise ValueError("Independent component evidence is misidentified")
        eligible = all(item.passed for item in components)
        if self.baseline_establishment_eligible != eligible:
            raise ValueError("Baseline eligibility contradicts component evidence")
        if self.checked_row_count != sum(item.checked_row_count for item in components):
            raise ValueError("Independent checked-row total is invalid")
        if self.checked_field_count != sum(
            item.checked_field_count for item in components
        ):
            raise ValueError("Independent checked-field total is invalid")
        if self.categorical_mismatch_count != sum(
            item.categorical_mismatch_count for item in components
        ):
            raise ValueError("Categorical mismatch total is invalid")
        if self.membership_mismatch_count != sum(
            item.membership_mismatch_count for item in components
        ):
            raise ValueError("Membership mismatch total is invalid")
        if self.inventory_mismatch_count != sum(
            item.inventory_mismatch_count for item in components
        ):
            raise ValueError("Inventory mismatch total is invalid")
        maximum = max(item.maximum_absolute_discrepancy for item in components)
        if self.candidate_byte_identity is not None:
            byte_identity = self.candidate_byte_identity
            if byte_identity.current_candidate_digest != self.production_output_digest:
                raise ValueError("Current candidate digest was not independently bound")
            if byte_identity.passed != self.output_inventory.passed:
                raise ValueError("Inventory component contradicts byte identity")
            if (
                not byte_identity.passed
                and self.output_inventory.inventory_mismatch_count == 0
            ):
                raise ValueError(
                    "Byte mismatch must increment inventory mismatches count"
                )
        expected_pass = bool(
            all(item.passed for item in components)
            and self.candidate_byte_identity is not None
            and self.candidate_byte_identity.passed
            and not self.missing_evidence
            and not self.unsupported_claims
            and self.categorical_mismatch_count == 0
            and self.membership_mismatch_count == 0
            and self.inventory_mismatch_count == 0
            and maximum <= self.absolute_tolerance
        )
        if self.maximum_numerical_discrepancy != maximum:
            raise ValueError("Overall numerical discrepancy was not calculated")
        if self.passed != expected_pass:
            raise ValueError("Independent reconciliation pass contradicts components")
        value = self.model_dump(mode="json")
        fingerprint = value.pop("artifact_fingerprint")
        if canonical_digest(value) != fingerprint:
            raise ValueError("Independent reconciliation fingerprint is invalid")
        return self


def build_validated_candidate_identity(
    reconciliation: IndependentReconciliationEvidence,
    output_digest: OutputDigestEvidence,
) -> ValidatedCandidateIdentity:
    """Establish a baseline once, only from fully checked preliminary evidence."""
    if reconciliation.candidate_byte_identity is not None or reconciliation.passed:
        raise ValueError("Baseline must be established from preliminary evidence")
    if not reconciliation.baseline_establishment_eligible:
        raise ValueError("Candidate is not eligible for baseline establishment")
    if reconciliation.production_output_digest != output_digest.path_plus_bytes_digest:
        raise ValueError("Preliminary reconciliation digest differs from candidate")
    payload = {
        "schema_version": CANDIDATE_IDENTITY_SCHEMA_VERSION,
        "registration_version": reconciliation.registration_version,
        "method_version": reconciliation.method_version,
        "anchor_commit": reconciliation.anchor_commit,
        "receipt_fingerprint": reconciliation.receipt_fingerprint,
        "establishment_stage": "AFTER_TWELVE_COMPONENT_RECONCILIATION",
        "output_digest": output_digest.model_dump(mode="json"),
    }
    return ValidatedCandidateIdentity.model_validate(
        {**payload, "identity_fingerprint": canonical_digest(payload)}
    )


def write_validated_candidate_identity(
    identity: ValidatedCandidateIdentity, path: Path
) -> None:
    """Persist the baseline exactly once; replacement and automatic rebaseline fail."""
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Validated candidate identity already exists: {path}")
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                identity.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_validated_candidate_identity(path: Path) -> ValidatedCandidateIdentity:
    """Read and fingerprint-validate one prior baseline identity."""
    return ValidatedCandidateIdentity.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def read_independent_reconciliation(
    path: Path,
) -> IndependentReconciliationEvidence:
    """Read and fingerprint-validate standalone reconciliation evidence."""
    return IndependentReconciliationEvidence.model_validate_json(
        path.read_text(encoding="utf-8")
    )


class CompletionGateEvidence(FrozenEvidence):
    """Every individually bound gate required before lifecycle completion."""

    receipt_validated: StrictBool
    anchor_ancestry_validated: StrictBool
    registered_path_integrity_validated: StrictBool
    raw_identity_validated: StrictBool
    task02_validated: StrictBool
    task03_exact_membership_validated: StrictBool
    configuration_reconciled: StrictBool
    dependency_closure_validated: StrictBool
    candidate_inventory_validated: StrictBool
    population_reconciliation_passed: StrictBool
    independent_statistical_reproduction_passed: StrictBool
    deterministic_regeneration_passed: StrictBool
    exact_output_digest_reproduced: StrictBool
    figures_validated: StrictBool
    absolute_path_scan_passed: StrictBool
    non_finite_scan_passed: StrictBool
    volatile_output_scan_passed: StrictBool
    symlink_non_regular_scan_passed: StrictBool
    ruff_passed: StrictBool
    mypy_passed: StrictBool
    unit_tests_passed: StrictBool
    integration_tests_passed: StrictBool
    branch_coverage_passed: StrictBool
    raw_checksum_unchanged: StrictBool
    raw_mtime_unchanged: StrictBool
    deviation_policy_satisfied: StrictBool
    maximum_numerical_discrepancy: NonNegativeFinite
    registered_numerical_tolerance: NonNegativeFinite
    branch_coverage_percent: Annotated[
        float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=100.0)
    ]
    minimum_branch_coverage_percent: Annotated[
        float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=100.0)
    ]

    @model_validator(mode="after")
    def require_every_gate(self) -> CompletionGateEvidence:
        boolean_fields = COMPLETION_BOOLEAN_FIELDS
        failed = [name for name in boolean_fields if not getattr(self, name)]
        if failed:
            raise ValueError("Completion gates failed: " + ", ".join(failed))
        if self.maximum_numerical_discrepancy > self.registered_numerical_tolerance:
            raise ValueError("Numerical discrepancy exceeds registered tolerance")
        if self.branch_coverage_percent < self.minimum_branch_coverage_percent:
            raise ValueError("Branch-aware coverage is below the registered threshold")
        return self


class LifecycleCompletionRequest(FrozenEvidence):
    """Strict handoff from completed Phase B gates to terminal lifecycle creation."""

    schema_version: Literal["task04-lifecycle-completion-request-v1"]
    phase_b_progress: PhaseBProgress
    production_state_identifier: str = Field(min_length=1)
    descendant_commit_or_working_state: str = Field(min_length=1)
    deterministic_regeneration_digest: Sha256
    validated_candidate_identity: ValidatedCandidateIdentity
    independent_reconciliation: IndependentReconciliationEvidence
    completion_gates: CompletionGateEvidence
    primary_population: StrictInt = Field(gt=0)
    primary_statistic: NonNegativeFinite
    primary_p_value: Annotated[
        float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=1.0)
    ]
    primary_effect_size: FiniteFloat
    final_evidence_rating: Literal["INSUFFICIENT", "WEAK", "MODERATE"]
    limitations: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_pre_promotion_sequence(self) -> LifecycleCompletionRequest:
        if self.phase_b_progress.completed_stages != PHASE_B_SEQUENCE[:11]:
            raise ValueError(
                "Completion request requires every pre-promotion stage in order"
            )
        if not self.independent_reconciliation.passed:
            raise ValueError(
                "Lifecycle completion requires full independent reconciliation"
            )
        byte_identity = self.independent_reconciliation.candidate_byte_identity
        if byte_identity is None or not byte_identity.passed:
            raise ValueError("Lifecycle requires validated candidate byte identity")
        if (
            byte_identity.validated_candidate_identity_fingerprint
            != self.validated_candidate_identity.identity_fingerprint
        ):
            raise ValueError("Reconciliation used a different candidate baseline")
        if (
            self.deterministic_regeneration_digest
            != self.validated_candidate_identity.output_digest.path_plus_bytes_digest
        ):
            raise ValueError("Deterministic digest differs from candidate baseline")
        failed_components = [
            name
            for name in RECONCILIATION_COMPONENTS
            if not getattr(self.independent_reconciliation, name).passed
        ]
        if failed_components:
            raise ValueError(
                "Lifecycle completion has unchecked or failed reconciliation: "
                + ", ".join(failed_components)
            )
        if (
            self.completion_gates.maximum_numerical_discrepancy
            != self.independent_reconciliation.maximum_numerical_discrepancy
        ):
            raise ValueError("Completion gate discrepancy differs from reconciliation")
        return self


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def build_output_digest(
    output_root: Path,
    expected_paths: Iterable[str],
    *,
    figure_paths: Iterable[str] = (),
) -> OutputDigestEvidence:
    """Validate and digest an exact registered output inventory.

    Algorithm v1 sorts UTF-8 relative paths.  For each file it appends the path,
    a NUL byte, the ASCII decimal byte length, a NUL byte, the file bytes, and a
    final NUL byte to one SHA-256 stream.
    """
    expected = tuple(sorted(expected_paths))
    if len(expected) != len(set(expected)):
        raise ValueError("Expected output inventory contains duplicates")
    if output_root.is_symlink() or not output_root.is_dir():
        raise RuntimeError("Output root must be a real directory")
    present = tuple(
        sorted(
            path.relative_to(output_root).as_posix()
            for path in output_root.rglob("*")
            if not path.is_dir()
        )
    )
    if present != expected:
        raise RuntimeError(
            f"Output inventory mismatch; expected={expected}; present={present}"
        )
    figures = set(figure_paths)
    records: list[OutputFileHash] = []
    aggregate = hashlib.sha256()
    for relative in expected:
        path = output_root / relative
        assert_regular_contained_file(path, output_root)
        file_hash, size = _hash_file(path)
        path_bytes = relative.encode("utf-8")
        aggregate.update(path_bytes)
        aggregate.update(b"\0")
        aggregate.update(str(size).encode("ascii"))
        aggregate.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                aggregate.update(chunk)
        aggregate.update(b"\0")
        records.append(
            OutputFileHash(
                relative_path=relative,
                size_bytes=size,
                sha256=file_hash,
                category="FIGURE" if relative in figures else "TABLE_OR_REPORT",
            )
        )
    return OutputDigestEvidence(
        digest_algorithm=OUTPUT_DIGEST_ALGORITHM,
        files=tuple(records),
        inventory_fingerprint=canonical_digest(list(expected)),
        path_plus_bytes_digest=aggregate.hexdigest(),
    )


def promote_candidate_outputs(
    candidate_directory: Path,
    final_directory: Path,
    expected_paths: Iterable[str],
    *,
    validated_identity: ValidatedCandidateIdentity,
) -> None:
    """Atomically promote one validated candidate directory on one filesystem."""
    figures = tuple(
        item.relative_path
        for item in validated_identity.output_digest.files
        if item.category == "FIGURE"
    )
    current = build_output_digest(
        candidate_directory, expected_paths, figure_paths=figures
    )
    if current != validated_identity.output_digest:
        raise ValueError("Candidate bytes differ from validated baseline identity")
    if final_directory.exists() or final_directory.is_symlink():
        raise FileExistsError("Final Task 04 output directory already exists")
    final_directory.parent.mkdir(parents=True, exist_ok=True)
    if candidate_directory.stat().st_dev != final_directory.parent.stat().st_dev:
        raise RuntimeError("Candidate promotion must remain on one filesystem")
    os.replace(candidate_directory, final_directory)
