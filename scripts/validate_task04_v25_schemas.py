"""Validate v2.5 registration and governance schemas without creating evidence."""

from __future__ import annotations

from eurusd_research.paths import find_repository_root, project_path
from eurusd_research.studies.completion import (
    CompletionGateEvidence,
    IndependentReconciliationEvidence,
    LifecycleCompletionRequest,
)
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.registry import (
    Task04RegistrationLifecycle,
    Task04RegistrationReceipt,
    assert_registration_matches_config,
    read_preregistration,
)


def main() -> int:
    root = find_repository_root()
    config = load_task04_config(root)
    registration, _ = read_preregistration(
        project_path(config.preregistration_path, root)
    )
    assert_registration_matches_config(registration, config)
    models = (
        Task04RegistrationReceipt,
        Task04RegistrationLifecycle,
        CompletionGateEvidence,
        IndependentReconciliationEvidence,
        LifecycleCompletionRequest,
    )
    for model in models:
        schema = model.model_json_schema()
        if schema.get("additionalProperties") is not False:
            raise ValueError(f"{model.__name__} does not reject unknown fields")
    if registration.status != "PREREGISTERED":
        raise ValueError("v2.5 registration is not PREREGISTERED")
    print("Task 04 v2.5 governance schemas: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
