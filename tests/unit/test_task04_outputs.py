from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from eurusd_research.paths import find_repository_root
from eurusd_research.studies.configuration import load_task04_config
from eurusd_research.studies.registry import read_preregistration
from eurusd_research.studies.task04 import (
    _atomic_text,
    _deviation_frame,
    _markdown_report,
    _validate_deviation_reconciliation,
    _validate_existing_output_scope,
    _validate_written_outputs,
    _write_csv,
)


def _write_inventory(directory: Path) -> None:
    config = load_task04_config()
    directory.mkdir()
    for name in config.expected_output_files:
        (directory / name).write_text("fixture\n", encoding="utf-8")
    figures = directory / "figures"
    figures.mkdir()
    for name in config.expected_figure_files:
        (figures / name).write_bytes(b"fixture")


def test_exact_output_inventory_accepts_only_registered_paths(tmp_path: Path) -> None:
    config = load_task04_config()
    output = tmp_path / "output"
    _write_inventory(output)
    _validate_existing_output_scope(output, config)
    _validate_written_outputs(output, config)

    missing = output / config.expected_output_files[0]
    missing.unlink()
    with pytest.raises(RuntimeError, match="missing"):
        _validate_written_outputs(output, config)
    missing.write_text("fixture\n", encoding="utf-8")

    missing_figure = output / "figures" / config.expected_figure_files[0]
    missing_figure.unlink()
    with pytest.raises(RuntimeError, match="missing"):
        _validate_written_outputs(output, config)
    missing_figure.write_bytes(b"fixture")

    extra = output / "stale.csv"
    extra.write_text("stale\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        _validate_existing_output_scope(output, config)
    with pytest.raises(RuntimeError, match="unexpected"):
        _validate_written_outputs(output, config)


def test_output_inventory_rejects_link_and_non_regular_file_attacks(
    tmp_path: Path,
) -> None:
    config = load_task04_config()

    inside = tmp_path / "inside"
    _write_inventory(inside)
    target = inside / config.expected_output_files[0]
    target.unlink()
    target.symlink_to(inside / config.expected_output_files[1])
    with pytest.raises(RuntimeError, match="symbolic"):
        _validate_written_outputs(inside, config)

    outside = tmp_path / "outside"
    _write_inventory(outside)
    external = tmp_path / "external.txt"
    external.write_text("external\n", encoding="utf-8")
    outside_target = outside / config.expected_output_files[0]
    outside_target.unlink()
    outside_target.symlink_to(external)
    with pytest.raises(RuntimeError, match="symbolic"):
        _validate_written_outputs(outside, config)

    parent_link = tmp_path / "parent-link"
    parent_link.mkdir()
    for name in config.expected_output_files:
        (parent_link / name).write_text("fixture\n", encoding="utf-8")
    real_figures = tmp_path / "real-figures"
    real_figures.mkdir()
    for name in config.expected_figure_files:
        (real_figures / name).write_bytes(b"fixture")
    (parent_link / "figures").symlink_to(real_figures, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symbolic"):
        _validate_written_outputs(parent_link, config)

    broken = tmp_path / "broken"
    _write_inventory(broken)
    broken_target = broken / config.expected_output_files[0]
    broken_target.unlink()
    broken_target.symlink_to(tmp_path / "absent")
    with pytest.raises(RuntimeError, match="symbolic"):
        _validate_written_outputs(broken, config)

    hardlinked = tmp_path / "hardlinked"
    _write_inventory(hardlinked)
    hardlink_target = hardlinked / config.expected_output_files[0]
    hardlink_target.unlink()
    os.link(hardlinked / config.expected_output_files[1], hardlink_target)
    with pytest.raises(RuntimeError, match="hard links"):
        _validate_written_outputs(hardlinked, config)

    fifo = tmp_path / "fifo"
    _write_inventory(fifo)
    fifo_target = fifo / config.expected_output_files[0]
    fifo_target.unlink()
    os.mkfifo(fifo_target)
    with pytest.raises(RuntimeError, match="not a regular"):
        _validate_written_outputs(fifo, config)

    directory = tmp_path / "directory"
    _write_inventory(directory)
    directory_target = directory / config.expected_output_files[0]
    directory_target.unlink()
    directory_target.mkdir()
    with pytest.raises(RuntimeError, match="missing"):
        _validate_written_outputs(directory, config)


def test_same_version_deviation_output_is_locked_empty() -> None:
    config = load_task04_config()
    registration, _ = read_preregistration(config.preregistration_path)
    frame = _deviation_frame(registration)
    assert frame.empty
    assert not registration.deviation_policy.post_anchor_scientific_changes_permitted
    assert not registration.deviation_policy.same_version_append_only_ledger_supported
    _validate_deviation_reconciliation(registration, frame, [])


def test_markdown_and_atomic_writers_use_historical_evidence_fixture(
    tmp_path: Path,
) -> None:
    """Render a report fixture without generating a v2.3 study."""
    historical = (
        find_repository_root() / "reports" / "research" / "task04_daily_range_weekday"
    )
    summary = json.loads(
        (historical / "study_summary.json").read_text(encoding="utf-8")
    )
    tables = {
        name: pd.read_csv(historical / name)
        for name in (
            "population_reconciliation.csv",
            "weekday_statistics.csv",
            "pairwise_tests.csv",
            "preregistration_deviations.csv",
        )
    }
    report = _markdown_report(summary, tables)
    assert report.startswith("# Daily Range Behaviour by Weekday")
    assert "Registration deviations\n\nNone." in report

    nonempty = tables.copy()
    nonempty["preregistration_deviations.csv"] = pd.DataFrame(
        [
            {
                "deviation_id": "fixture-only",
                "affected_field": "fixture",
                "classification": "TEST",
                "reason": "cover report rendering",
                "consequence": "none",
                "lineage_reference": "unit-test",
            }
        ]
    )
    assert "`fixture-only`" in _markdown_report(summary, nonempty)

    text_path = tmp_path / "nested" / "report.md"
    _atomic_text(text_path, report)
    assert text_path.read_text(encoding="utf-8") == report
    csv_path = tmp_path / "nested" / "table.csv"
    _write_csv(csv_path, tables["weekday_statistics.csv"].head(2))
    assert len(pd.read_csv(csv_path)) == 2
