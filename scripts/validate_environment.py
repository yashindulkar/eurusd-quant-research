#!/usr/bin/env python3
"""Validate the runtime, package dependencies, configuration, and directories."""

from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path

from eurusd_research.config import load_config
from eurusd_research.paths import find_repository_root, project_path

MINIMUM_PYTHON = (3, 11)
MAXIMUM_PYTHON = (3, 14)
REQUIRED_DISTRIBUTIONS = (
    "matplotlib",
    "numpy",
    "pandas",
    "pyarrow",
    "pydantic",
    "PyYAML",
    "scipy",
    "statsmodels",
)


def main() -> int:
    """Run environment checks and return a process exit status."""
    errors: list[str] = []
    version = sys.version_info[:3]
    print(f"Python: {'.'.join(map(str, version))}")
    if not (MINIMUM_PYTHON <= version < MAXIMUM_PYTHON):
        errors.append("Python must be >=3.11 and <3.14")

    root = find_repository_root(Path(__file__))
    print(f"Repository root: {root}")
    config = load_config(root)
    print(f"Configuration: valid ({config.project.instrument})")

    for distribution in REQUIRED_DISTRIBUTIONS:
        try:
            installed = importlib.metadata.version(distribution)
            print(f"Dependency {distribution}: {installed}")
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"Missing dependency: {distribution}")

    required_directories = (
        "data/raw",
        "data/interim",
        "data/processed",
        "data/external",
        "reports/figures",
        "reports/tables",
        "reports/audits",
        "reports/coverage",
    )
    for relative in required_directories:
        path = project_path(relative, root)
        if not path.is_dir():
            errors.append(f"Missing directory: {relative}")
    print(f"Required directories: {len(required_directories)} checked")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Environment validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
