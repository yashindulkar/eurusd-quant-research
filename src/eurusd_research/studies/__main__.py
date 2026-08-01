"""CLI for registered-replication Task 04 generation and validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from eurusd_research.paths import find_repository_root
from eurusd_research.studies.task04 import generate_task04_study


def main(argv: list[str] | None = None) -> int:
    """Generate Task 04 candidate outputs without completing the lifecycle."""
    parser = argparse.ArgumentParser(
        description="Generate candidate UTC-weekday daily-range evidence"
    )
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--output-directory", type=Path)
    arguments = parser.parse_args(argv)
    root = (arguments.root or find_repository_root()).resolve()
    result = generate_task04_study(root, arguments.output_directory)
    primary = result.summary["primary_result"]
    print(
        f"Task 04: {result.summary['study']['status']} | "
        f"dates={result.summary['population']['primary_eligible_dates']} | "
        f"p={primary['kruskal_p_value']:.6g} | "
        f"evidence={result.summary['evidence_rating']['rating']}"
    )
    print(result.output_directory / "study_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
