from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from tests.helpers import EXPECTED_COLUMNS

from eurusd_research.config import load_config
from eurusd_research.data.registry import register_raw_dataset
from eurusd_research.paths import find_repository_root, project_path


@pytest.mark.integration
def test_configured_directories_exist() -> None:
    root = find_repository_root()
    config = load_config(root)
    assert project_path(config.project.report_directories.audits, root).is_dir()
    assert project_path(config.data.raw_dataset_path, root).parent.is_dir()


@pytest.mark.integration
def test_registration_is_read_only(tiny_raw_csv: Path, tmp_path: Path) -> None:
    before = (tiny_raw_csv.stat().st_size, tiny_raw_csv.stat().st_mtime_ns)
    register_raw_dataset(
        path=tiny_raw_csv,
        repository_root=tmp_path,
        logical_name="fixture",
        expected_columns=EXPECTED_COLUMNS,
        timestamp_column="timestamp_utc",
    )
    after = (tiny_raw_csv.stat().st_size, tiny_raw_csv.stat().st_mtime_ns)
    assert after == before


@pytest.mark.integration
def test_environment_validation_script() -> None:
    root = find_repository_root()
    result = subprocess.run(
        [sys.executable, "scripts/validate_environment.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Environment validation: PASS" in result.stdout
