"""Explicit v2.9 Phase B stage ordering and filesystem lifecycle states.

The stage controller is intentionally result-agnostic.  It prevents candidate
generation from being conflated with terminal lifecycle completion.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import ConfigDict, Field

from eurusd_research.config import StrictModel


class PhaseBStage(StrEnum):
    VALIDATE_ANCHOR = "validate_anchor"
    CREATE_RECEIPT = "create_receipt"
    VALIDATE_RECEIPT = "validate_receipt"
    VALIDATE_PRE_GENERATION_DEPENDENCIES = "validate_pre_generation_dependencies"
    GENERATE_CANDIDATE_OUTPUTS = "generate_candidate_outputs"
    VALIDATE_CANDIDATE_OUTPUTS = "validate_candidate_outputs"
    INDEPENDENT_POPULATION_RECONCILIATION = "independent_population_reconciliation"
    INDEPENDENT_STATISTICAL_REPRODUCTION = "independent_statistical_reproduction"
    DETERMINISTIC_REGENERATION = "deterministic_regeneration"
    FIGURE_VALIDATION = "figure_validation"
    RUN_REQUIRED_QUALITY_GATES = "run_required_quality_gates"
    PROMOTE_FINAL_OUTPUTS = "promote_final_outputs"
    CREATE_COMPLETED_LIFECYCLE = "create_completed_lifecycle"
    VALIDATE_COMPLETED_LIFECYCLE = "validate_completed_lifecycle"


PHASE_B_SEQUENCE = tuple(PhaseBStage)


class PhaseBFilesystemState(StrEnum):
    """Permitted externally observable Phase B evidence states."""

    PRE_RECEIPT = "PRE_RECEIPT"
    POST_RECEIPT_PRE_CANDIDATE = "POST_RECEIPT_PRE_CANDIDATE"
    CANDIDATE = "CANDIDATE"
    POST_PROMOTION_PRE_LIFECYCLE = "POST_PROMOTION_PRE_LIFECYCLE"
    COMPLETED = "COMPLETED"


def classify_phase_b_filesystem_state(
    *,
    receipt_path: Path,
    lifecycle_path: Path,
    candidate_directory: Path,
    final_directory: Path,
) -> PhaseBFilesystemState:
    """Classify one valid lifecycle state without assuming receipt absence globally."""
    present = (
        receipt_path.exists(),
        lifecycle_path.exists(),
        candidate_directory.exists(),
        final_directory.exists(),
    )
    states = {
        (False, False, False, False): PhaseBFilesystemState.PRE_RECEIPT,
        (True, False, False, False): (PhaseBFilesystemState.POST_RECEIPT_PRE_CANDIDATE),
        (True, False, True, False): PhaseBFilesystemState.CANDIDATE,
        (True, False, False, True): (
            PhaseBFilesystemState.POST_PROMOTION_PRE_LIFECYCLE
        ),
        (True, True, False, True): PhaseBFilesystemState.COMPLETED,
    }
    try:
        return states[present]
    except KeyError as error:
        raise ValueError(
            "Invalid Task 04 lifecycle filesystem state: "
            f"receipt={present[0]}, lifecycle={present[1]}, "
            f"candidate={present[2]}, final={present[3]}"
        ) from error


class PhaseBProgress(StrictModel):
    """Immutable evidence that Phase B advances one stage at a time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    completed_stages: tuple[PhaseBStage, ...] = Field(default=())

    def advance(self, stage: PhaseBStage) -> PhaseBProgress:
        index = len(self.completed_stages)
        if index >= len(PHASE_B_SEQUENCE) or PHASE_B_SEQUENCE[index] != stage:
            expected = (
                "NONE" if index >= len(PHASE_B_SEQUENCE) else PHASE_B_SEQUENCE[index]
            )
            raise ValueError(f"Invalid Phase B transition; expected {expected}")
        return PhaseBProgress(completed_stages=(*self.completed_stages, stage))

    @property
    def final_outputs_may_be_promoted(self) -> bool:
        return self.completed_stages == PHASE_B_SEQUENCE[:11]

    @property
    def lifecycle_may_be_created(self) -> bool:
        return self.completed_stages == PHASE_B_SEQUENCE[:12]

    @property
    def completed(self) -> bool:
        return self.completed_stages == PHASE_B_SEQUENCE
