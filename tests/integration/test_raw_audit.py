from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from tests.helpers import EXPECTED_COLUMNS

from eurusd_research.config import load_config
from eurusd_research.data.audit import run_raw_data_audit
from eurusd_research.data.registry import register_raw_dataset, write_registration
from eurusd_research.paths import find_repository_root


def _cli_repository(tmp_path: Path, *, missing_column: bool = False) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    source_root = find_repository_root()
    shutil.copytree(source_root / "configs", root / "configs")
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    raw = root / "data" / "raw" / "EURUSD_M15_UTC.csv"
    raw.parent.mkdir(parents=True)
    columns = EXPECTED_COLUMNS[:-1] if missing_column else EXPECTED_COLUMNS
    rows = [
        ["2024-01-01T00:00:00Z", "1.1", "1.2", "1.0", "1.15", "15", "fixture"],
        ["2024-01-01T00:15:00Z", "1.15", "1.2", "1.1", "1.18", "14", "fixture"],
    ]
    with raw.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows([row[: len(columns)] for row in rows])
    config_path = root / "configs" / "data.yaml"
    values = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    values["dataset_logical_name"] = "fixture"
    values["timestamp_convention"] = "documented fixture convention"
    values["quote_convention"] = "documented fixture quote"
    values["count_field_semantics"] = "documented fixture count"
    values["upstream_feed_continuity_documented"] = True
    registration = register_raw_dataset(
        path=raw,
        repository_root=root,
        logical_name="fixture",
        expected_columns=tuple(columns),
        timestamp_column="timestamp_utc",
    )
    values["expected_dataset_version"] = registration.dataset_version
    config_path.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
    manifest = root / values["registered_manifest_path"]
    write_registration(registration, manifest)
    return root


def _run_cli(root: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(find_repository_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "eurusd_research.data", "--root", str(root)],
        cwd=find_repository_root(),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


@pytest.mark.integration
def test_real_cli_success_warning_exit_and_outputs(tmp_path: Path) -> None:
    root = _cli_repository(tmp_path)
    raw = root / "data/raw/EURUSD_M15_UTC.csv"
    before = (raw.read_bytes(), raw.stat().st_mtime_ns)
    result = _run_cli(root)
    assert result.returncode == 0
    assert "Raw audit: CONDITIONALLY_READY" in result.stdout
    assert "rows=2" in result.stdout
    output = root / "reports" / "audits"
    assert (output / "raw_data_quality_audit.json").is_file()
    assert (output / "raw_data_quality_report.md").is_file()
    assert (raw.read_bytes(), raw.stat().st_mtime_ns) == before

    data_path = root / "configs" / "data.yaml"
    values = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    values["timestamp_convention"] = None
    data_path.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
    warning = _run_cli(root)
    assert warning.returncode == 0
    assert "CONDITIONALLY_READY" in warning.stdout
    assert "warnings=2" in warning.stdout


@pytest.mark.integration
def test_real_cli_fatal_identity_and_malformed_manifest(tmp_path: Path) -> None:
    root = _cli_repository(tmp_path)
    manifest = root / "reports/audits/raw_dataset_manifest.json"
    content = json.loads(manifest.read_text(encoding="utf-8"))
    content["row_count"] = 3
    manifest.write_text(json.dumps(content), encoding="utf-8")
    mismatch = _run_cli(root)
    assert mismatch.returncode == 1
    assert "failures=1" in mismatch.stdout

    manifest.write_text("{not json", encoding="utf-8")
    malformed = _run_cli(root)
    assert malformed.returncode == 1
    assert "NOT_READY" in malformed.stdout
    assert (
        (root / "reports/audits/timestamp_gaps.csv").read_text().startswith("gap_id,")
    )


@pytest.mark.integration
def test_real_cli_missing_required_column_is_fatal(tmp_path: Path) -> None:
    root = _cli_repository(tmp_path, missing_column=True)
    result = _run_cli(root)
    assert result.returncode == 1
    assert "NOT_READY" in result.stdout
    output = root / "reports/audits"
    assert (output / "ohlc_violations.csv").read_text().startswith("row_number,")


@pytest.mark.integration
def test_production_2023_continuity_and_allocation_reconcile() -> None:
    root = find_repository_root()
    config = load_config(root).data
    result, tables = run_raw_data_audit(
        root / config.raw_dataset_path,
        config,
        repository_root=root,
        manifest_path=root / config.registered_manifest_path,
    )
    assert result.partial_period_results["continuity_impaired_months"] == [
        "2023-02",
        "2023-03",
        "2023-04",
        "2023-05",
        "2023-06",
        "2023-07",
    ]
    period = result.continuity_investigation_2023["concentrated_2023_period"]
    assert period["first_timestamp_before"] == "2023-01-27T10:45:00Z"
    assert period["last_timestamp_after"] == "2023-07-28T20:00:00Z"
    gap_total = int(
        tables["timestamp_gaps.csv"]["estimated_missing_m15_timestamps"].sum()
    )
    assert gap_total == 170_779
    assert (
        tables["annual_coverage.csv"][
            "estimated_missing_m15_timestamps_in_period"
        ].sum()
        == gap_total
    )
    assert (
        tables["monthly_coverage.csv"][
            "estimated_missing_m15_timestamps_in_period"
        ].sum()
        == gap_total
    )
