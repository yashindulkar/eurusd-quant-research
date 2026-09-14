"""Create the Task 04 v2.11 receipt for the committed preregistration anchor."""

from __future__ import annotations

from eurusd_research.paths import find_repository_root, project_path
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.registry import (
    build_registration_receipt,
    read_preregistration,
    write_registration_receipt,
)


def main() -> int:
    """Anchor the registered replication before production result calculation."""
    root = find_repository_root()
    config = load_task04_config(root)
    registration, _ = read_preregistration(
        project_path(config.preregistration_path, root)
    )
    receipt = build_registration_receipt(registration, config, root=root)
    path = project_path(config.registration_receipt_path, root)
    write_registration_receipt(receipt, path)
    print(
        "Task 04 registration receipt: CREATED | "
        f"registration_version={registration.registration_version} | "
        f"receipt_fingerprint={receipt.receipt_fingerprint}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
