"""Validate strict v2.8 registration, receipt, lifecycle, and evidence schemas."""

from __future__ import annotations

from eurusd_research.paths import find_repository_root
from eurusd_research.studies.completion import (
    CompletionGateEvidence,
    IndependentReconciliationEvidence,
    LifecycleCompletionRequest,
)
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.integrity import read_task03_row_membership_evidence
from eurusd_research.studies.registry import (
    Task04RegistrationLifecycle,
    Task04RegistrationReceipt,
    read_preregistration,
)


def main() -> int:
    root = find_repository_root()
    config = load_task04_config(root)
    read_preregistration(root / config.preregistration_path)
    read_task03_row_membership_evidence(root / config.task03_evidence_path)
    for model in (
        Task04RegistrationReceipt,
        Task04RegistrationLifecycle,
        IndependentReconciliationEvidence,
        CompletionGateEvidence,
        LifecycleCompletionRequest,
    ):
        model.model_json_schema()
    print("Task 04 v2.8 governance schemas: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
