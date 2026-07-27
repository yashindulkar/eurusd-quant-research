"""Command-line entry point for research coverage generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from eurusd_research.paths import find_repository_root
from eurusd_research.research.coverage import generate_coverage


def main(argv: list[str] | None = None) -> int:
    """Generate canonical coverage metadata."""
    parser = argparse.ArgumentParser(
        description="Generate Task 02-backed research coverage metadata"
    )
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--output-directory", type=Path)
    arguments = parser.parse_args(argv)
    root = (arguments.root or find_repository_root()).resolve()
    result = generate_coverage(root, arguments.output_directory)
    row_count = len(result.flags_by_level["row"])
    sensitivity_count = int(
        result.flags_by_level["row"]["requires_sensitivity_analysis"].sum()
    )
    print(
        f"Coverage: {result.lineage.coverage_method_id} | rows={row_count} | "
        f"sensitivity_rows={sensitivity_count}"
    )
    destination = arguments.output_directory or (root / "reports" / "coverage")
    print(destination / "coverage_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
