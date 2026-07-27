from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from eurusd_research.data.registry import sha256_file
from eurusd_research.paths import find_repository_root
from eurusd_research.research.coverage import generate_coverage


@pytest.mark.integration
def test_production_coverage_task02_integration_determinism_and_immutability(
    tmp_path: Path,
) -> None:
    root = find_repository_root()
    raw = root / "data/raw/EURUSD_M15_UTC.csv"
    before = (sha256_file(raw), raw.stat().st_mtime_ns)
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"

    first = generate_coverage(root, first_directory)
    second = generate_coverage(root, second_directory)

    assert before == (sha256_file(raw), raw.stat().st_mtime_ns)
    assert first.lineage.raw_sha256 == before[0]
    assert first.lineage == second.lineage
    assert first.summary == second.summary
    assert set(first.flags_by_level) == {"row", "date", "month", "year", "dataset"}
    assert len(first.flags_by_level["row"]) == 406_945
    assert first.summary["continuity_impaired_months"] == [
        "2023-02",
        "2023-03",
        "2023-04",
        "2023-05",
        "2023-06",
        "2023-07",
    ]
    assert first.summary["affected_period_2023"]["first_timestamp_before"] == (
        "2023-01-27T10:45:00Z"
    )
    row_profiles = first.profile_masks_by_level["row"]
    assert row_profiles["FULL_DATASET"].all()
    assert row_profiles["DEFAULT_RESEARCH"].all()
    assert (
        row_profiles["STRICT_CONTINUITY"] | row_profiles["SENSITIVITY_FULL"]
    ).equals(row_profiles["DEFAULT_RESEARCH"])
    assert not (
        row_profiles["STRICT_CONTINUITY"] & row_profiles["SENSITIVITY_FULL"]
    ).any()
    assert not (
        row_profiles["SENSITIVITY_2023"] & ~row_profiles["SENSITIVITY_FULL"]
    ).any()
    assert int(row_profiles["SENSITIVITY_2023"].sum()) == 9_258
    assert int(row_profiles["SENSITIVITY_FULL"].sum()) == 46_468
    structural_flags = [
        "raw_available",
        "schema_valid",
        "timestamp_valid",
        "ohlc_valid",
        "duplicate_free",
    ]
    assert (
        first.flags_by_level["row"]
        .loc[row_profiles["DEFAULT_RESEARCH"], structural_flags]
        .all(axis=None)
    )
    assert int(first.flags_by_level["month"]["continuity_impaired_period"].sum()) == 6
    assert first.lineage.repository_version.endswith(("+clean", "+dirty"))
    assert len(first.lineage.audit_gap_table_sha256) == 64
    assert len(first.lineage.audit_monthly_table_sha256) == 64
    sensitivity = first.summary["sensitivity_analysis"]
    assert sensitivity["union_row_count"] == 46_468
    assert (
        sum(
            record["row_count"]
            for record in sensitivity["mutually_exclusive_combinations"]
        )
        == 46_468
    )

    expected_files = {
        "coverage_summary.json",
        "coverage_summary.md",
        "row_flag_counts.csv",
        "date_flag_counts.csv",
        "month_flag_counts.csv",
        "coverage_profiles.csv",
    }
    assert {path.name for path in first_directory.iterdir()} == expected_files
    for filename in expected_files:
        assert (first_directory / filename).read_bytes() == (
            second_directory / filename
        ).read_bytes()
    loaded = json.loads(
        (first_directory / "coverage_summary.json").read_text(encoding="utf-8")
    )
    assert loaded["task_02_relationship"]["duplicates_audit_logic"] is False


@pytest.mark.integration
def test_coverage_cli_writes_requested_directory(tmp_path: Path) -> None:
    root = find_repository_root()
    output = tmp_path / "cli-output"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "eurusd_research.research",
            "--root",
            str(root),
            "--output-directory",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Coverage: COVERAGE-001 | rows=406945" in result.stdout
    assert (output / "coverage_summary.md").is_file()
