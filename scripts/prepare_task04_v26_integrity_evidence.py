"""Prepare pre-result v2.6 dependency evidence without Task 04 calculation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path

from eurusd_research.config import load_config
from eurusd_research.paths import find_repository_root
from eurusd_research.research.coverage import build_coverage
from eurusd_research.studies.integrity import (
    ENVIRONMENT_LOCK_SCHEMA_VERSION,
    build_source_dependency_manifest,
    build_task03_row_membership_evidence,
)

RUNTIME_DISTRIBUTIONS = (
    "matplotlib",
    "numpy",
    "pandas",
    "pyarrow",
    "pydantic",
    "PyYAML",
    "scipy",
    "statsmodels",
)


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _environment_lock() -> dict[str, object]:
    return {
        "schema_version": ENVIRONMENT_LOCK_SCHEMA_VERSION,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "dependencies": {
            distribution: importlib.metadata.version(distribution)
            for distribution in RUNTIME_DISTRIBUTIONS
        },
        "policy": (
            "Exact versions for the registered v2.6 candidate-generation and "
            "completion workflow; package constraints remain in pyproject.toml."
        ),
    }


def main() -> int:
    """Write only pre-anchor integrity evidence."""
    root = find_repository_root()
    environment_path = root / "studies" / "task04_v2.6_environment_lock.json"
    _atomic_json(environment_path, _environment_lock())
    repository_config = load_config(root)
    coverage = build_coverage(
        root=root,
        config=repository_config,
        repository_version="v2.6-git-anchor-pending",
    )
    task03_evidence = build_task03_row_membership_evidence(
        root, coverage, repository_config
    )
    task03_path = root / "studies" / "task03_task04_v2.6_mask_evidence.json"
    _atomic_json(task03_path, task03_evidence.model_dump(mode="json"))
    source_manifest = build_source_dependency_manifest(root)
    source_path = root / "studies" / "task04_v2.6_source_manifest.json"
    _atomic_json(source_path, source_manifest.model_dump(mode="json"))
    print(
        "Task 04 v2.6 pre-anchor evidence: PREPARED | "
        f"environment={hashlib.sha256(environment_path.read_bytes()).hexdigest()} | "
        f"source={source_manifest.dependency_manifest_fingerprint} | "
        f"task03={task03_evidence.evidence_fingerprint}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
