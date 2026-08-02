"""Validate the Task 04 preregistration without calculating study results."""

from __future__ import annotations

from eurusd_research.config import load_config
from eurusd_research.paths import find_repository_root, project_path
from eurusd_research.research.coverage import build_coverage
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.dependencies import validate_task04_dependencies
from eurusd_research.studies.integrity import (
    validate_source_dependency_manifest,
    validate_task03_row_membership,
)
from eurusd_research.studies.registry import (
    assert_registration_matches_config,
    locked_design_fingerprint,
    read_preregistration,
)


def main() -> int:
    """Print a bounded validation receipt."""
    root = find_repository_root()
    config = load_task04_config(root)
    registration, _raw = read_preregistration(
        project_path(config.preregistration_path, root)
    )
    assert_registration_matches_config(registration, config)
    validate_task04_dependencies(root, config)
    validate_source_dependency_manifest(
        root, config.required_source_dependency_manifest_fingerprint
    )
    repository_config = load_config(root)
    coverage = build_coverage(
        root=root,
        config=repository_config,
        repository_version="git-anchor-pending",
    )
    validate_task03_row_membership(
        root,
        coverage,
        repository_config,
        expected_scientific_fingerprint=(
            config.required_task03_scientific_membership_fingerprint
        ),
        expected_stable_artifact_fingerprint=(
            config.required_task03_stable_artifact_fingerprint
        ),
    )
    if project_path(config.registration_receipt_path, root).exists():
        raise ValueError("v2.7 receipt already exists; this is not pre-anchor state")
    if project_path(config.registration_lifecycle_path, root).exists():
        raise ValueError("v2.7 lifecycle already exists before anchoring")
    if project_path(config.output_directory, root).exists():
        raise ValueError("v2.7 production output directory exists before anchoring")
    if project_path(config.candidate_output_directory, root).exists():
        raise ValueError("v2.7 candidate output directory exists before anchoring")
    print(
        f"Task 04 preregistration: PASS | status={registration.status} | "
        f"registration_version={registration.registration_version} | "
        f"locked_design_sha256={locked_design_fingerprint(registration)} | "
        "receipt=ANCHOR_COMMIT_REQUIRED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
