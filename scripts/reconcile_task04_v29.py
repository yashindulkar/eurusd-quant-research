"""Build full independent Task 04 v2.9 reconciliation evidence after generation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from eurusd_research.paths import find_repository_root, project_path
from eurusd_research.studies.completion import (
    build_output_digest,
    build_validated_candidate_identity,
    write_validated_candidate_identity,
)
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.independent_inventory import inspect_output_inventory
from eurusd_research.studies.independent_reconciliation import (
    build_independent_reconciliation,
)
from eurusd_research.studies.registry import (
    read_preregistration,
    validate_registration_receipt,
)


def _write_once(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"Independent reconciliation evidence exists: {path}")
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    root = (arguments.root or find_repository_root()).resolve()
    config = load_task04_config(root)
    registration, _ = read_preregistration(
        project_path(config.preregistration_path, root)
    )
    receipt = validate_registration_receipt(registration, config, root=root)
    candidate = project_path(config.candidate_output_directory, root)
    expected = tuple(
        sorted(
            (
                *config.expected_output_files,
                *(f"figures/{name}" for name in config.expected_figure_files),
            )
        )
    )
    inventory = inspect_output_inventory(candidate, expected)
    if not inventory.reconciled:
        raise RuntimeError("Independent candidate inventory inspection failed")
    figures = tuple(sorted(f"figures/{name}" for name in config.expected_figure_files))
    output_digest = build_output_digest(candidate, expected, figure_paths=figures)
    preliminary = build_independent_reconciliation(
        root,
        candidate,
        config=config,
        anchor_commit=receipt.git_anchor.anchor_commit_id,
        receipt_fingerprint=receipt.receipt_fingerprint,
        production_output_digest=inventory.path_plus_bytes_digest,
        absolute_tolerance=config.maximum_numerical_discrepancy_tolerance,
        relative_tolerance=config.maximum_numerical_discrepancy_tolerance,
    )
    if not preliminary.baseline_establishment_eligible:
        raise RuntimeError("Candidate failed before baseline identity establishment")
    identity = build_validated_candidate_identity(preliminary, output_digest)
    identity_path = project_path(config.validated_candidate_identity_path, root)
    write_validated_candidate_identity(identity, identity_path)
    evidence = build_independent_reconciliation(
        root,
        candidate,
        config=config,
        anchor_commit=receipt.git_anchor.anchor_commit_id,
        receipt_fingerprint=receipt.receipt_fingerprint,
        production_output_digest=inventory.path_plus_bytes_digest,
        absolute_tolerance=config.maximum_numerical_discrepancy_tolerance,
        relative_tolerance=config.maximum_numerical_discrepancy_tolerance,
        validated_candidate_identity=identity,
    )
    if not evidence.passed:
        raise RuntimeError("Independent reconciliation failed closed")
    path = arguments.output or project_path(
        config.independent_reconciliation_path, root
    )
    _write_once(path, evidence.model_dump(mode="json"))
    print(
        "Task 04 v2.9 independent reconciliation: PASS | "
        f"fingerprint={evidence.artifact_fingerprint}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
