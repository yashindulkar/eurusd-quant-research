"""Fail-closed Task 04 v2.4 completion evidence and output controls.

This module contains no weekday-result calculation.  It defines the evidence
that Phase B must obtain before a candidate study may be promoted and marked
complete.
"""

from __future__ import annotations

import hashlib
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
FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
NonNegativeFinite = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0)]

OUTPUT_DIGEST_ALGORITHM: Literal["task04-path-length-bytes-sha256-v1"] = (
    "task04-path-length-bytes-sha256-v1"
)
INDEPENDENT_RECONCILIATION_IMPLEMENTATION = "task04-independent-csv-reproduction-v1"
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


class WeekdayIndependentStatistics(FrozenEvidence):
    """Independently reproduced primary values for one weekday."""

    weekday: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    sample_size: StrictInt = Field(gt=0)
    contributing_rows: StrictInt = Field(gt=0)
    mean_pips: FiniteFloat
    median_pips: FiniteFloat


class IndependentOmnibusEvidence(FrozenEvidence):
    """Independently reproduced omnibus statistics."""

    kruskal_wallis_h: NonNegativeFinite
    kruskal_wallis_p_value: Annotated[
        float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=1.0)
    ]
    anova_f: NonNegativeFinite
    anova_p_value: Annotated[
        float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=1.0)
    ]
    welch_f: NonNegativeFinite
    welch_p_value: Annotated[
        float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=1.0)
    ]
    brown_forsythe_f: NonNegativeFinite
    brown_forsythe_p_value: Annotated[
        float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=1.0)
    ]
    epsilon_squared: FiniteFloat
    eta_squared: FiniteFloat
    omega_squared: FiniteFloat


class IndependentReconciliationEvidence(FrozenEvidence):
    """Deterministic evidence from a path independent of production statistics."""

    schema_version: Literal["task04-independent-reconciliation-v1"]
    implementation_id: Literal["task04-independent-csv-reproduction-v1"]
    raw_sha256: Sha256
    task03_evidence_fingerprint: Sha256
    primary_population: StrictInt = Field(gt=0)
    weekday_statistics: tuple[
        WeekdayIndependentStatistics,
        WeekdayIndependentStatistics,
        WeekdayIndependentStatistics,
        WeekdayIndependentStatistics,
        WeekdayIndependentStatistics,
    ]
    omnibus: IndependentOmnibusEvidence
    pairwise_maximum_absolute_discrepancy: NonNegativeFinite
    bootstrap_maximum_absolute_discrepancy: NonNegativeFinite
    robustness_population_maximum_absolute_discrepancy: NonNegativeFinite
    regime_maximum_absolute_discrepancy: NonNegativeFinite
    output_inventory_reconciled: StrictBool
    absolute_tolerance: NonNegativeFinite
    relative_tolerance: NonNegativeFinite
    maximum_numerical_discrepancy: NonNegativeFinite
    passed: StrictBool
    artifact_fingerprint: Sha256

    @model_validator(mode="after")
    def validate_reconciliation(self) -> IndependentReconciliationEvidence:
        expected_weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
        if tuple(item.weekday for item in self.weekday_statistics) != expected_weekdays:
            raise ValueError("Independent weekday evidence must use canonical order")
        if sum(item.sample_size for item in self.weekday_statistics) != (
            self.primary_population
        ):
            raise ValueError("Independent weekday populations do not reconcile")
        if self.passed and (
            not self.output_inventory_reconciled
            or self.maximum_numerical_discrepancy > self.absolute_tolerance
        ):
            raise ValueError("Independent reconciliation pass contradicts evidence")
        value = self.model_dump(mode="json")
        fingerprint = value.pop("artifact_fingerprint")
        if canonical_digest(value) != fingerprint:
            raise ValueError("Independent reconciliation fingerprint is invalid")
        return self


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
) -> None:
    """Atomically promote one validated candidate directory on one filesystem."""
    build_output_digest(candidate_directory, expected_paths)
    if final_directory.exists() or final_directory.is_symlink():
        raise FileExistsError("Final Task 04 output directory already exists")
    final_directory.parent.mkdir(parents=True, exist_ok=True)
    if candidate_directory.stat().st_dev != final_directory.parent.stat().st_dev:
        raise RuntimeError("Candidate promotion must remain on one filesystem")
    os.replace(candidate_directory, final_directory)
