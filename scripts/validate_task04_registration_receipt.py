"""Independently validate the Task 04 registration receipt and lifecycle."""

from __future__ import annotations

from eurusd_research.paths import find_repository_root, project_path
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.registry import (
    read_preregistration,
    validate_registration_lifecycle,
    validate_registration_receipt,
)


def main() -> int:
    """Validate receipt identity and completed lifecycle when applicable."""
    root = find_repository_root()
    config = load_task04_config(root)
    registration, _ = read_preregistration(
        project_path(config.preregistration_path, root)
    )
    receipt = validate_registration_receipt(registration, config, root=root)
    lifecycle = "NOT_YET_COMPLETED"
    if project_path(config.registration_lifecycle_path, root).is_file():
        validated = validate_registration_lifecycle(
            registration, config, receipt, root=root
        )
        lifecycle = validated.lifecycle_fingerprint
    effective_status = (
        "COMPLETED" if lifecycle != "NOT_YET_COMPLETED" else "PREREGISTERED"
    )
    print(
        "Task 04 registration receipt: PASS | "
        f"status={effective_status} | "
        f"receipt_fingerprint={receipt.receipt_fingerprint} | "
        f"lifecycle={lifecycle}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
