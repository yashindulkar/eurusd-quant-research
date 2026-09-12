from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from eurusd_research.studies.completion import (
    CandidateByteIdentityEvidence,
    OutputDigestEvidence,
    ValidatedCandidateIdentity,
    build_output_digest,
    promote_candidate_outputs,
    read_validated_candidate_identity,
    write_validated_candidate_identity,
)
from eurusd_research.studies.independent_inventory import (
    CandidateIdentityComparison,
    compare_output_to_validated_identity,
    inspect_output_inventory,
)
from eurusd_research.studies.integrity import canonical_digest
from eurusd_research.studies.registry import LifecycleOutputEvidence

EXPECTED = ("report.json", "report.md", "table.csv", "figures/figure.png")
FIGURES = ("figures/figure.png",)


def _candidate(root: Path) -> Path:
    candidate = root / "candidate"
    (candidate / "figures").mkdir(parents=True)
    (candidate / "report.json").write_bytes(b'{"value":1}\n')
    (candidate / "report.md").write_bytes(b"# Report\n")
    (candidate / "table.csv").write_bytes(b"name,value\na,1\n")
    (candidate / "figures/figure.png").write_bytes(b"png-fixture-bytes")
    return candidate


def _identity(
    digest: OutputDigestEvidence,
    *,
    version: str = "2.9",
    anchor: str = "a" * 40,
    receipt: str = "b" * 64,
) -> ValidatedCandidateIdentity:
    payload = {
        "schema_version": "task04-validated-candidate-identity-v1",
        "registration_version": version,
        "method_version": f"range-weekday-registered-replication-v{version}",
        "anchor_commit": anchor,
        "receipt_fingerprint": receipt,
        "establishment_stage": "AFTER_TWELVE_COMPONENT_RECONCILIATION",
        "output_digest": digest.model_dump(mode="json"),
    }
    return ValidatedCandidateIdentity.model_validate(
        {**payload, "identity_fingerprint": canonical_digest(payload)}
    )


def _compare(candidate: Path, identity: ValidatedCandidateIdentity):
    return compare_output_to_validated_identity(
        candidate,
        identity,
        registration_version="2.9",
        method_version="range-weekday-registered-replication-v2.9",
        anchor_commit="a" * 40,
        receipt_fingerprint="b" * 64,
    )


def _comparison_evidence(
    comparison: CandidateIdentityComparison, identity: ValidatedCandidateIdentity
) -> CandidateByteIdentityEvidence:
    return CandidateByteIdentityEvidence(
        validated_candidate_identity_fingerprint=identity.identity_fingerprint,
        baseline_candidate_digest=identity.output_digest.path_plus_bytes_digest,
        current_candidate_digest=comparison.current_output_digest.path_plus_bytes_digest,
        baseline_files=identity.output_digest.files,
        current_files=comparison.current_output_digest.files,
        missing_paths=comparison.missing_paths,
        extra_paths=comparison.extra_paths,
        size_mismatch_paths=comparison.size_mismatch_paths,
        sha256_mismatch_paths=comparison.sha256_mismatch_paths,
        byte_identity_mismatch_paths=comparison.byte_identity_mismatch_paths,
        digest_mismatch=comparison.digest_mismatch,
        baseline_identity_mismatch=comparison.baseline_identity_mismatch,
        passed=comparison.reconciled,
    )


def test_v27_current_only_inventory_reproduces_false_pass(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    baseline = inspect_output_inventory(candidate, EXPECTED)
    (candidate / "figures/figure.png").write_bytes(b"png-fixture-bytesx")
    mutated = inspect_output_inventory(candidate, EXPECTED)
    assert baseline.reconciled and mutated.reconciled
    assert baseline.path_plus_bytes_digest != mutated.path_plus_bytes_digest
    identity = _identity(
        build_output_digest(tmp_path / "candidate", EXPECTED, figure_paths=FIGURES)
    )
    # A fresh self-baseline proves only current state, never absence of mutation.
    assert _compare(candidate, identity).reconciled


@pytest.mark.parametrize(
    ("relative", "mutate"),
    [
        ("figures/figure.png", lambda value: value + b"x"),
        (
            "figures/figure.png",
            lambda value: value[:3] + bytes([value[3] ^ 1]) + value[4:],
        ),
        ("table.csv", lambda value: value.replace(b"a,1", b"a,2")),
        ("report.json", lambda value: value.replace(b"1", b"2")),
        ("table.csv", lambda value: value[:-1]),
        ("report.md", lambda value: value + b"x"),
        ("figures/figure.png", lambda value: b"x" * len(value)),
    ],
)
def test_real_byte_mutations_fail_against_prior_identity(
    tmp_path: Path, relative: str, mutate: Callable[[bytes], bytes]
) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    path = candidate / relative
    original = path.read_bytes()
    path.write_bytes(mutate(original))
    comparison = _compare(candidate, baseline)
    assert not comparison.reconciled
    assert relative in comparison.sha256_mismatch_paths
    assert relative in comparison.byte_identity_mismatch_paths
    assert comparison.digest_mismatch


def test_same_size_replacement_and_restored_mtime_still_fail(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    path = candidate / "figures/figure.png"
    before = path.stat().st_mtime_ns
    path.write_bytes(b"z" * path.stat().st_size)
    path.touch()
    os.utime(path, ns=(before, before))
    comparison = _compare(candidate, baseline)
    assert not comparison.reconciled
    assert not comparison.size_mismatch_paths
    assert comparison.sha256_mismatch_paths == ("figures/figure.png",)


def test_post_validation_mutation_blocks_promotion(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    assert _compare(candidate, baseline).reconciled
    (candidate / "table.csv").write_bytes(b"name,value\na,2\n")
    with pytest.raises(ValueError, match="validated baseline"):
        promote_candidate_outputs(
            candidate,
            tmp_path / "final",
            EXPECTED,
            validated_identity=baseline,
        )


def test_valid_promotion_preserves_exact_baseline(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    final = tmp_path / "final"
    promote_candidate_outputs(candidate, final, EXPECTED, validated_identity=baseline)
    assert (
        build_output_digest(final, EXPECTED, figure_paths=FIGURES)
        == baseline.output_digest
    )


def test_missing_extra_and_renamed_files_fail_structural_inventory(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path)
    (candidate / "table.csv").rename(candidate / "renamed.csv")
    inspected = inspect_output_inventory(candidate, EXPECTED)
    assert inspected.missing_paths == ("table.csv",)
    assert inspected.extra_paths == ("renamed.csv",)
    assert not inspected.reconciled


def test_baseline_is_frozen_and_context_bound(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    with pytest.raises(ValidationError):
        _identity(baseline.output_digest, version="2.7")
    for anchor, receipt, method in (
        (
            "c" * 40,
            "b" * 64,
            "range-weekday-registered-replication-v2.9",
        ),
        (
            "a" * 40,
            "d" * 64,
            "range-weekday-registered-replication-v2.9",
        ),
        ("a" * 40, "b" * 64, "different-method"),
    ):
        comparison = compare_output_to_validated_identity(
            candidate,
            baseline,
            registration_version="2.9",
            method_version=method,
            anchor_commit=anchor,
            receipt_fingerprint=receipt,
        )
        assert comparison.baseline_identity_mismatch
        assert not comparison.reconciled
    with pytest.raises(ValidationError):
        ValidatedCandidateIdentity.model_validate(
            {**baseline.model_dump(mode="python"), "anchor_commit": "c" * 40}
        )


def test_baseline_from_another_run_cannot_self_validate_mutation(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    mutated = tmp_path / "mutated"
    shutil.copytree(candidate, mutated)
    (mutated / "report.json").write_bytes(b'{"value":2}\n')
    self_baseline = _identity(
        build_output_digest(mutated, EXPECTED, figure_paths=FIGURES)
    )
    assert _compare(mutated, self_baseline).reconciled
    assert not _compare(mutated, baseline).reconciled
    assert self_baseline.identity_fingerprint != baseline.identity_fingerprint


def test_baseline_file_is_write_once_and_fingerprint_validated(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    path = tmp_path / "validated-candidate.json"
    write_validated_candidate_identity(baseline, path)
    assert read_validated_candidate_identity(path) == baseline
    with pytest.raises(FileExistsError):
        write_validated_candidate_identity(baseline, path)
    path.write_text(
        path.read_text().replace('"anchor_commit": "a', '"anchor_commit": "c')
    )
    with pytest.raises(ValidationError):
        read_validated_candidate_identity(path)


def test_post_promotion_mutation_blocks_lifecycle_output_evidence(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    final = tmp_path / "final"
    promote_candidate_outputs(candidate, final, EXPECTED, validated_identity=baseline)
    (final / "report.json").write_bytes(b'{"value":2}\n')
    mutated = build_output_digest(final, EXPECTED, figure_paths=FIGURES)
    with pytest.raises(ValidationError, match="final digest"):
        LifecycleOutputEvidence(
            production_output_inventory=tuple(sorted(EXPECTED)),
            exact_output_paths=tuple(sorted(EXPECTED)),
            output_digest=mutated,
            figure_inventory=FIGURES * 8,
            no_extra_output_validation_passed=True,
            output_containment_validation_passed=True,
            validated_candidate_identity_fingerprint=baseline.identity_fingerprint,
            baseline_candidate_digest=baseline.output_digest.path_plus_bytes_digest,
            final_matches_validated_candidate_identity=True,
            byte_identity_mismatch_count=0,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("missing_paths", ("report.json",), "path mismatches"),
        ("extra_paths", ("extra.json",), "path mismatches"),
        ("size_mismatch_paths", ("report.json",), "size mismatches"),
        ("sha256_mismatch_paths", ("report.json",), "SHA-256 mismatches"),
        ("byte_identity_mismatch_paths", ("report.json",), "byte mismatches"),
        ("digest_mismatch", True, "digest mismatch"),
        ("passed", False, "pass contradicts"),
    ],
)
def test_candidate_comparison_rejects_asserted_mismatch_fields(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    comparison = _compare(candidate, baseline)
    values = _comparison_evidence(comparison, baseline).model_dump(mode="python")
    values[field] = value
    with pytest.raises(ValidationError, match=message):
        CandidateByteIdentityEvidence.model_validate(values)


def test_candidate_comparison_rejects_duplicate_and_unsorted_records(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path)
    baseline = _identity(build_output_digest(candidate, EXPECTED, figure_paths=FIGURES))
    comparison = _compare(candidate, baseline)
    valid = _comparison_evidence(comparison, baseline).model_dump(mode="python")
    for field in ("baseline_files", "current_files"):
        duplicate = {**valid, field: (*valid[field], valid[field][0])}
        with pytest.raises(ValidationError, match="paths must be unique"):
            CandidateByteIdentityEvidence.model_validate(duplicate)
        unsorted = {**valid, field: tuple(reversed(valid[field]))}
        with pytest.raises(ValidationError, match="paths must be sorted"):
            CandidateByteIdentityEvidence.model_validate(unsorted)
