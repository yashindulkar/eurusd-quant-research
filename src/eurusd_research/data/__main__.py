"""Command-line entry point for the registered raw-data audit."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from eurusd_research.config import load_config
from eurusd_research.data.audit import run_raw_data_audit
from eurusd_research.data.reporting import write_audit_outputs
from eurusd_research.logging_utils import configure_logging
from eurusd_research.paths import find_repository_root, project_path

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run the configured audit; return nonzero only for fatal findings."""
    parser = argparse.ArgumentParser(description="Audit the registered raw dataset")
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--output-directory", type=Path)
    arguments = parser.parse_args(argv)
    configure_logging()
    root = (arguments.root or find_repository_root()).resolve()
    config = load_config(root)
    raw_path = project_path(config.data.raw_dataset_path, root)
    output_directory = arguments.output_directory or project_path(
        config.project.report_directories.audits, root
    )
    result, tables = run_raw_data_audit(
        raw_path,
        config.data,
        repository_root=root,
        manifest_path=project_path(config.data.registered_manifest_path, root),
    )
    write_audit_outputs(result, tables, output_directory)
    assessment = result.final_readiness_assessment
    print(
        f"Raw audit: {assessment['state']} | "
        f"rows={result.schema_results.get('row_count', 0)} | "
        f"gaps={result.gap_summary.get('gap_count', 0)} | "
        f"failures={len(result.failures)} | warnings={len(result.warnings)}"
    )
    print(output_directory / "raw_data_quality_report.md")
    if result.failures:
        LOGGER.error("Fatal audit findings: %s", "; ".join(result.failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
