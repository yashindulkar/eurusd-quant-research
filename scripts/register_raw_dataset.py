#!/usr/bin/env python3
"""Register the configured immutable raw dataset without modifying it."""

from __future__ import annotations

import logging

from eurusd_research.config import load_config
from eurusd_research.data.registry import register_raw_dataset, write_registration
from eurusd_research.logging_utils import configure_logging
from eurusd_research.paths import find_repository_root, project_path

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Register the configured dataset and write its audit manifest."""
    configure_logging()
    root = find_repository_root()
    config = load_config(root)
    raw_path = project_path(config.data.raw_dataset_path, root)
    output_path = project_path(
        config.project.report_directories.audits / "raw_dataset_manifest.json",
        root,
    )
    registration = register_raw_dataset(
        path=raw_path,
        repository_root=root,
        logical_name="eurusd_m15_utc",
        expected_columns=config.data.expected_columns,
        timestamp_column=config.data.timestamp_column,
    )
    write_registration(registration, output_path)
    LOGGER.info(
        "Registered %s (%d rows, %s)",
        registration.relative_file_path,
        registration.row_count,
        registration.dataset_version,
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
