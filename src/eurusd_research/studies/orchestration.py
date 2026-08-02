"""Explicit v2.5 Phase B stage ordering.

The stage controller is intentionally result-agnostic.  It prevents candidate
generation from being conflated with terminal lifecycle completion.
"""

from __future__ import annotations

from enum import StrEnum

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
