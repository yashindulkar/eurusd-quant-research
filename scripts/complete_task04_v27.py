"""Promote validated v2.7 candidate outputs and create the terminal lifecycle."""

from __future__ import annotations

import argparse
from pathlib import Path

from eurusd_research.config import load_config
from eurusd_research.paths import find_repository_root, project_path
from eurusd_research.research.coverage import _repository_version, build_coverage
from eurusd_research.studies.completion import (
    LifecycleCompletionRequest,
    build_output_digest,
    promote_candidate_outputs,
)
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.integrity import build_task03_row_membership_evidence
from eurusd_research.studies.orchestration import PhaseBStage
from eurusd_research.studies.registry import (
    LifecycleOutputEvidence,
    build_completed_lifecycle,
    read_preregistration,
    validate_registration_lifecycle,
    validate_registration_receipt,
    write_completed_lifecycle,
)


def main(argv: list[str] | None = None) -> int:
    """Complete only from individually validated, fingerprinted Phase B evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("completion_evidence", type=Path)
    parser.add_argument("--root", type=Path)
    arguments = parser.parse_args(argv)
    root = (arguments.root or find_repository_root()).resolve()
    request = LifecycleCompletionRequest.model_validate_json(
        arguments.completion_evidence.read_text(encoding="utf-8")
    )
    progress = request.phase_b_progress
    if not progress.final_outputs_may_be_promoted:
        raise ValueError("Phase B has not completed every pre-promotion stage")
    config = load_task04_config(root)
    registration, _ = read_preregistration(
        project_path(config.preregistration_path, root)
    )
    receipt = validate_registration_receipt(registration, config, root=root)
    research_config = load_config(root)
    task03 = build_task03_row_membership_evidence(
        root,
        build_coverage(
            root=root,
            config=research_config,
            repository_version=_repository_version(
                root,
                ignored_generated_paths=(
                    config.output_directory,
                    config.candidate_output_directory,
                ),
            ),
        ),
        research_config,
    )
    expected = tuple(
        sorted(
            (
                *config.expected_output_files,
                *(f"figures/{x}" for x in config.expected_figure_files),
            )
        )
    )
    figures = tuple(sorted(f"figures/{x}" for x in config.expected_figure_files))
    candidate = project_path(config.candidate_output_directory, root)
    final = project_path(config.output_directory, root)
    candidate_digest = build_output_digest(candidate, expected, figure_paths=figures)
    if candidate_digest.path_plus_bytes_digest != (
        request.deterministic_regeneration_digest
    ):
        raise ValueError("Candidate digest differs from deterministic regeneration")
    output_evidence = LifecycleOutputEvidence(
        production_output_inventory=expected,
        exact_output_paths=expected,
        output_digest=candidate_digest,
        figure_inventory=figures,
        no_extra_output_validation_passed=True,
        output_containment_validation_passed=True,
        validated_candidate_identity_fingerprint=request.validated_candidate_identity.identity_fingerprint,
        baseline_candidate_digest=request.validated_candidate_identity.output_digest.path_plus_bytes_digest,
        final_matches_validated_candidate_identity=True,
        byte_identity_mismatch_count=0,
    )
    promote_candidate_outputs(
        candidate,
        final,
        expected,
        validated_identity=request.validated_candidate_identity,
    )
    progress = progress.advance(PhaseBStage.PROMOTE_FINAL_OUTPUTS)
    if not progress.lifecycle_may_be_created:
        raise AssertionError("Lifecycle creation stage is not yet permitted")
    final_digest = build_output_digest(final, expected, figure_paths=figures)
    if final_digest != candidate_digest:
        raise ValueError("Promoted output digest differs from validated candidate")
    output_evidence = output_evidence.model_copy(update={"output_digest": final_digest})
    lifecycle = build_completed_lifecycle(
        registration,
        config,
        receipt,
        production_state_identifier=request.production_state_identifier,
        descendant_commit_or_working_state=request.descendant_commit_or_working_state,
        output_evidence=output_evidence,
        independent_reconciliation=request.independent_reconciliation,
        completion_gates=request.completion_gates,
        primary_population=request.primary_population,
        primary_statistic=request.primary_statistic,
        primary_p_value=request.primary_p_value,
        primary_effect_size=request.primary_effect_size,
        final_evidence_rating=request.final_evidence_rating,
        task03_execution_context_fingerprint=(task03.execution_context_fingerprint),
        task03_execution_context_variance_observed=(
            task03.execution_context_fingerprint
            != receipt.upstream_evidence.task03.execution_context_fingerprint_at_receipt
        ),
        limitations=request.limitations,
    )
    progress = progress.advance(PhaseBStage.CREATE_COMPLETED_LIFECYCLE)
    lifecycle_path = project_path(config.registration_lifecycle_path, root)
    write_completed_lifecycle(lifecycle, lifecycle_path)
    validate_registration_lifecycle(registration, config, receipt, root=root)
    progress = progress.advance(PhaseBStage.VALIDATE_COMPLETED_LIFECYCLE)
    if not progress.completed:
        raise AssertionError("Phase B completion sequence is incomplete")
    print(
        "Task 04 v2.7 lifecycle: COMPLETED | "
        f"lifecycle_fingerprint={lifecycle.lifecycle_fingerprint}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
