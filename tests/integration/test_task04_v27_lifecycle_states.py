from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from eurusd_research.studies.completion import (
    RECONCILIATION_COMPONENTS,
    OutputDigestEvidence,
    ValidatedCandidateIdentity,
    build_output_digest,
    promote_candidate_outputs,
)
from eurusd_research.studies.independent_inventory import (
    compare_output_to_validated_identity,
)
from eurusd_research.studies.integrity import canonical_digest
from eurusd_research.studies.orchestration import (
    PHASE_B_SEQUENCE,
    PhaseBFilesystemState,
    PhaseBProgress,
    PhaseBStage,
    classify_phase_b_filesystem_state,
)


def _paths(root: Path) -> tuple[Path, Path, Path, Path]:
    return (
        root / "receipt.json",
        root / "lifecycle.json",
        root / "candidate",
        root / "final",
    )


def _state(root: Path) -> PhaseBFilesystemState:
    receipt, lifecycle, candidate, final = _paths(root)
    return classify_phase_b_filesystem_state(
        receipt_path=receipt,
        lifecycle_path=lifecycle,
        candidate_directory=candidate,
        final_directory=final,
    )


def _identity(output_digest: OutputDigestEvidence) -> ValidatedCandidateIdentity:
    digest = output_digest.model_dump(mode="json")
    payload = {
        "schema_version": "task04-validated-candidate-identity-v1",
        "registration_version": "2.10",
        "method_version": "range-weekday-registered-replication-v2.10",
        "anchor_commit": "a" * 40,
        "receipt_fingerprint": "b" * 64,
        "establishment_stage": "AFTER_TWELVE_COMPONENT_RECONCILIATION",
        "output_digest": digest,
    }
    return ValidatedCandidateIdentity.model_validate(
        {**payload, "identity_fingerprint": canonical_digest(payload)}
    )


@pytest.mark.integration
def test_phase_b_filesystem_states_are_explicit_and_receipt_aware(
    tmp_path: Path,
) -> None:
    receipt, lifecycle, candidate, final = _paths(tmp_path)
    assert _state(tmp_path) == PhaseBFilesystemState.PRE_RECEIPT

    receipt.write_text('{"status":"PREREGISTERED"}\n', encoding="utf-8")
    assert _state(tmp_path) == PhaseBFilesystemState.POST_RECEIPT_PRE_CANDIDATE

    candidate.mkdir()
    assert _state(tmp_path) == PhaseBFilesystemState.CANDIDATE

    candidate.rename(final)
    assert _state(tmp_path) == PhaseBFilesystemState.POST_PROMOTION_PRE_LIFECYCLE

    lifecycle.write_text('{"status":"COMPLETED"}\n', encoding="utf-8")
    assert _state(tmp_path) == PhaseBFilesystemState.COMPLETED

    candidate.mkdir()
    with pytest.raises(ValueError, match="Invalid Task 04 lifecycle"):
        _state(tmp_path)


@pytest.mark.integration
def test_full_simulated_phase_b_sequence_is_state_safe_and_non_mutating(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "isolated-repository"
    repository.mkdir()
    receipt, lifecycle, candidate, final = _paths(repository)
    expected = ("study_summary.json", "figures/figure_01.png")
    figures = ("figures/figure_01.png",)
    progress = PhaseBProgress()

    assert _state(repository) == PhaseBFilesystemState.PRE_RECEIPT
    progress = progress.advance(PhaseBStage.VALIDATE_ANCHOR)
    receipt.write_text('{"validated":true}\n', encoding="utf-8")
    progress = progress.advance(PhaseBStage.CREATE_RECEIPT)
    progress = progress.advance(PhaseBStage.VALIDATE_RECEIPT)
    assert _state(repository) == PhaseBFilesystemState.POST_RECEIPT_PRE_CANDIDATE

    progress = progress.advance(PhaseBStage.VALIDATE_PRE_GENERATION_DEPENDENCIES)
    (candidate / "figures").mkdir(parents=True)
    (candidate / "study_summary.json").write_text(
        json.dumps({"classification": "CANDIDATE"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (candidate / "figures/figure_01.png").write_bytes(b"deterministic-png-fixture")
    progress = progress.advance(PhaseBStage.GENERATE_CANDIDATE_OUTPUTS)
    candidate_digest = build_output_digest(candidate, expected, figure_paths=figures)
    identity = _identity(candidate_digest)
    progress = progress.advance(PhaseBStage.VALIDATE_CANDIDATE_OUTPUTS)
    assert _state(repository) == PhaseBFilesystemState.CANDIDATE

    checked_components: dict[str, bool] = {
        name: True for name in RECONCILIATION_COMPONENTS
    }
    assert len(checked_components) == 12 and all(checked_components.values())
    progress = progress.advance(PhaseBStage.INDEPENDENT_POPULATION_RECONCILIATION)
    progress = progress.advance(PhaseBStage.INDEPENDENT_STATISTICAL_REPRODUCTION)

    regenerated = repository / "regenerated"
    shutil.copytree(candidate, regenerated)
    regenerated_digest = build_output_digest(
        regenerated, expected, figure_paths=figures
    )
    assert regenerated_digest == candidate_digest
    progress = progress.advance(PhaseBStage.DETERMINISTIC_REGENERATION)
    assert (candidate / "figures/figure_01.png").read_bytes()
    progress = progress.advance(PhaseBStage.FIGURE_VALIDATION)
    progress = progress.advance(PhaseBStage.RUN_REQUIRED_QUALITY_GATES)
    assert progress.final_outputs_may_be_promoted

    figure = candidate / "figures/figure_01.png"
    original = figure.read_bytes()
    figure.write_bytes(original + b"x")
    comparison = compare_output_to_validated_identity(
        candidate,
        identity,
        registration_version="2.10",
        method_version="range-weekday-registered-replication-v2.10",
        anchor_commit="a" * 40,
        receipt_fingerprint="b" * 64,
    )
    assert not comparison.reconciled
    with pytest.raises(ValueError, match="validated baseline"):
        promote_candidate_outputs(
            candidate, final, expected, validated_identity=identity
        )
    figure.write_bytes(original)

    promote_candidate_outputs(candidate, final, expected, validated_identity=identity)
    progress = progress.advance(PhaseBStage.PROMOTE_FINAL_OUTPUTS)
    assert _state(repository) == PhaseBFilesystemState.POST_PROMOTION_PRE_LIFECYCLE
    assert progress.lifecycle_may_be_created

    lifecycle.write_text(
        json.dumps(
            {
                "status": "COMPLETED",
                "output_digest": candidate_digest.path_plus_bytes_digest,
                "components": sorted(checked_components),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    progress = progress.advance(PhaseBStage.CREATE_COMPLETED_LIFECYCLE)
    progress = progress.advance(PhaseBStage.VALIDATE_COMPLETED_LIFECYCLE)
    assert progress.completed
    assert _state(repository) == PhaseBFilesystemState.COMPLETED


@pytest.mark.integration
@pytest.mark.parametrize("stage", PHASE_B_SEQUENCE[1:])
def test_simulated_phase_b_cannot_cross_a_failed_or_skipped_stage(
    stage: PhaseBStage,
) -> None:
    with pytest.raises(ValueError, match="Invalid Phase B transition"):
        PhaseBProgress().advance(stage)
