from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from tests.helpers import EXPECTED_COLUMNS

from eurusd_research.config import DataConfig, load_config
from eurusd_research.data.audit import (
    ANNUAL_COVERAGE_COLUMNS,
    COUNT_DISTRIBUTION_COLUMNS,
    EXTREME_MOVEMENT_COLUMNS,
    MONTHLY_COVERAGE_COLUMNS,
    OHLC_VIOLATION_COLUMNS,
    _coverage_tables,
    _internal_consistency,
    _warning_list,
    _weekly_boundaries,
    run_raw_data_audit,
)
from eurusd_research.data.gaps import (
    GAP_COLUMNS,
    build_gap_table,
    expand_missing_timestamps,
)
from eurusd_research.data.registry import (
    DatasetManifest,
    sha256_file,
    write_registration,
)
from eurusd_research.data.reporting import (
    normalize_audit_result,
    render_markdown_report,
    write_audit_outputs,
)
from eurusd_research.paths import find_repository_root

FIXED_AUDIT_TIME = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


def _base_rows() -> list[list[str]]:
    return [
        ["2024-01-05T21:30:00Z", "1.1000", "1.1010", "1.0990", "1.1005", "15", "feed"],
        ["2024-01-05T21:45:00Z", "1.1005", "1.1015", "1.1000", "1.1010", "14", "feed"],
        ["2024-01-07T22:00:00Z", "1.1020", "1.1030", "1.1010", "1.1025", "12", "feed"],
        ["2024-01-07T22:15:00Z", "1.1025", "1.1030", "1.1020", "1.1025", "15", "feed"],
        ["2024-01-08T10:00:00Z", "1.1025", "1.1025", "1.1025", "1.1025", "1", "feed"],
        ["2024-01-08T10:15:00Z", "1.1025", "1.1040", "1.1020", "1.1030", "15", "feed"],
    ]


def _write_csv(
    path: Path,
    rows: list[list[str]],
    columns: tuple[str, ...] = EXPECTED_COLUMNS,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def _config(root: Path, path: Path, rows: list[list[str]]) -> tuple[DataConfig, Path]:
    base = load_config(find_repository_root()).data
    checksum = sha256_file(path)
    manifest_path = root / "reports" / "manifest.json"
    manifest = DatasetManifest(
        logical_dataset_name="fixture",
        relative_file_path=path.relative_to(root).as_posix(),
        file_size_bytes=path.stat().st_size,
        sha256=checksum,
        row_count=len(rows),
        detected_columns=tuple(
            next(csv.reader(path.open(encoding="utf-8", newline="")))
        ),
        first_timestamp=rows[0][0] if rows else "",
        last_timestamp=rows[-1][0] if rows else "",
        registration_timestamp_utc="2026-01-01T00:00:00Z",
        dataset_version=f"sha256:{checksum[:16]}",
    )
    write_registration(manifest, manifest_path)
    config = base.model_copy(
        update={
            "raw_dataset_path": path.relative_to(root),
            "dataset_logical_name": "fixture",
            "registered_manifest_path": manifest_path.relative_to(root),
            "expected_dataset_version": manifest.dataset_version,
        }
    )
    return config, manifest_path


def _audit(
    tmp_path: Path,
    rows: list[list[str]] | None = None,
    columns: tuple[str, ...] = EXPECTED_COLUMNS,
) -> tuple[Any, dict[str, pd.DataFrame], Path]:
    selected = rows or _base_rows()
    path = tmp_path / "data" / "raw" / "fixture.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(path, selected, columns)
    config, manifest_path = _config(tmp_path, path, selected)
    result, tables = run_raw_data_audit(
        path,
        config,
        repository_root=tmp_path,
        manifest_path=manifest_path,
        audit_timestamp=FIXED_AUDIT_TIME,
    )
    return result, tables, path


def test_valid_dataset_audit_and_required_diagnostics(tmp_path: Path) -> None:
    result, tables, _ = _audit(tmp_path)
    assert not result.failures
    assert result.schema_results["mandatory_schema_satisfied"]
    assert result.timestamp_results["parsed_timezone_aware"]
    assert result.timestamp_results["off_15_minute_grid_count"] == 0
    assert result.ohlc_results["flat_candle_count"] == 1
    assert result.ohlc_results["zero_body_candle_count"] == 2
    assert result.gap_summary["category_counts"] == {
        "likely_weekly_closure": 1,
        "unclassified": 1,
    }
    assert result.count_field_results["bounded_1_to_15_percentage"] == 100
    assert result.source_results["unique_non_null_values"] == ["feed"]
    assert result.final_readiness_assessment["state"] == "CONDITIONALLY_READY"
    assert set(tables) == {
        "timestamp_gaps.csv",
        "annual_coverage.csv",
        "monthly_coverage.csv",
        "ohlc_violations.csv",
        "extreme_price_movements.csv",
        "count_field_distribution.csv",
    }
    assert list(tables["ohlc_violations.csv"].columns)


def test_extra_and_missing_columns_fail_clearly(tmp_path: Path) -> None:
    rows = _base_rows()
    extra_columns = (*EXPECTED_COLUMNS, "extra")
    extra_rows = [[*row, "x"] for row in rows]
    extra, _, path = _audit(tmp_path, extra_rows, extra_columns)
    assert extra.schema_results["unexpected_columns"] == ["extra"]
    assert extra.final_readiness_assessment["state"] == "NOT_READY"

    missing_path = tmp_path / "missing.csv"
    missing_columns = EXPECTED_COLUMNS[:-1]
    missing_rows = [row[:-1] for row in rows]
    _write_csv(missing_path, missing_rows, missing_columns)
    config, manifest_path = _config(tmp_path, missing_path, missing_rows)
    missing, tables = run_raw_data_audit(
        missing_path,
        config,
        repository_root=tmp_path,
        manifest_path=manifest_path,
        audit_timestamp=FIXED_AUDIT_TIME,
    )
    assert missing.schema_results["missing_expected_columns"] == ["source"]
    assert missing.final_readiness_assessment["state"] == "NOT_READY"
    expected_schemas = {
        "timestamp_gaps.csv": GAP_COLUMNS,
        "annual_coverage.csv": ANNUAL_COVERAGE_COLUMNS,
        "monthly_coverage.csv": MONTHLY_COVERAGE_COLUMNS,
        "ohlc_violations.csv": OHLC_VIOLATION_COLUMNS,
        "extreme_price_movements.csv": EXTREME_MOVEMENT_COLUMNS,
        "count_field_distribution.csv": COUNT_DISTRIBUTION_COLUMNS,
    }
    for filename, expected in expected_schemas.items():
        assert tables[filename].empty
        assert tuple(tables[filename].columns) == expected
    assert path.exists()


@pytest.mark.parametrize(
    ("timestamp", "failure_fragment", "field", "expected"),
    [
        ("invalid", "unparseable", "unparseable_count", 1),
        (
            "2024-01-08T10:30:00",
            "explicit timezone",
            "source_values_without_explicit_timezone_count",
            1,
        ),
        (
            "2024-01-08T10:17:00Z",
            "off the M15 grid",
            "off_15_minute_grid_count",
            1,
        ),
    ],
)
def test_invalid_naive_and_off_grid_timestamps(
    tmp_path: Path,
    timestamp: str,
    failure_fragment: str,
    field: str,
    expected: int,
) -> None:
    rows = _base_rows()
    rows[-1][0] = timestamp
    result, _, _ = _audit(tmp_path, rows)
    assert result.timestamp_results[field] == expected
    assert any(failure_fragment in failure for failure in result.failures)


def test_duplicate_and_out_of_order_timestamps(tmp_path: Path) -> None:
    rows = _base_rows()
    rows[-1][0] = rows[-2][0]
    duplicate, _, _ = _audit(tmp_path, rows)
    assert duplicate.duplicate_results["duplicate_primary_timestamp_row_count"] == 2
    assert duplicate.timestamp_results["zero_length_interval_count"] == 1

    rows = _base_rows()
    rows[-1][0] = "2024-01-04T10:15:00Z"
    unordered, _, _ = _audit(tmp_path, rows)
    assert not unordered.timestamp_results["chronologically_ordered"]
    assert unordered.timestamp_results["backward_interval_count"] == 1


def test_numeric_ohlc_and_count_failures_are_reported(tmp_path: Path) -> None:
    rows = _base_rows()
    rows[0][1] = ""
    rows[1][2] = "inf"
    rows[2][3] = "-1"
    rows[3][2] = "1.0"
    rows[3][3] = "1.2"
    rows[4][5] = "-1"
    rows[5][5] = "2.5"
    result, tables, _ = _audit(tmp_path, rows)
    assert result.missing_value_results["open"]["empty_string_count"] == 1
    assert result.missing_value_results["high"]["positive_infinity_count"] == 1
    assert result.ohlc_results["combined_invalid_ohlc_count"] >= 4
    assert result.count_field_results["below_zero_count"] == 1
    assert result.count_field_results["non_integer_count"] == 1
    assert len(tables["ohlc_violations.csv"]) >= 4
    assert result.final_readiness_assessment["state"] == "NOT_READY"


def test_source_label_validation(tmp_path: Path) -> None:
    rows = _base_rows()
    rows[1][6] = " feed "
    rows[2][6] = "FEED"
    rows[3][6] = ""
    result, _, _ = _audit(tmp_path, rows)
    assert result.source_results["leading_or_trailing_whitespace_count"] == 1
    assert result.source_results["empty_count"] == 1
    assert result.source_results["casefold_collision_groups"] == {
        "feed": ["FEED", "feed"]
    }
    assert result.source_results["source_change_count"] >= 3


def test_serialisation_is_strict_and_calculations_deterministic(
    tmp_path: Path,
) -> None:
    first, tables, raw_path = _audit(tmp_path)
    before = raw_path.read_bytes()
    output = tmp_path / "reports"
    write_audit_outputs(first, tables, output)
    assert raw_path.read_bytes() == before
    loaded = json.loads(
        (output / "raw_data_quality_audit.json").read_text(encoding="utf-8")
    )
    assert loaded["dataset_identity"]["checksum_matches_manifest"]
    assert "# Raw Dataset Quality Audit" in (
        output / "raw_data_quality_report.md"
    ).read_text(encoding="utf-8")
    assert "CONDITIONALLY_READY" in render_markdown_report(first)
    assert "Rows: 6" in render_markdown_report(first)
    for filename in tables:
        assert (output / filename).is_file()

    config, manifest_path = _config(tmp_path, raw_path, _base_rows())
    os.utime(
        raw_path, ns=(raw_path.stat().st_atime_ns, raw_path.stat().st_mtime_ns + 10)
    )
    second, second_tables = run_raw_data_audit(
        raw_path,
        config,
        repository_root=tmp_path,
        manifest_path=manifest_path,
        audit_timestamp=datetime(2026, 7, 28, tzinfo=UTC),
    )
    assert normalize_audit_result(first.to_dict()) == normalize_audit_result(
        second.to_dict()
    )
    second_output = tmp_path / "reports-second"
    write_audit_outputs(second, second_tables, second_output)
    assert (output / "raw_data_quality_report.md").read_bytes() == (
        second_output / "raw_data_quality_report.md"
    ).read_bytes()
    for filename in tables:
        assert (output / filename).read_bytes() == (
            second_output / filename
        ).read_bytes()


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("sha256", "a" * 64, "SHA-256"),
        ("row_count", 999, "row counts"),
        ("file_size_bytes", 999, "sizes"),
        ("first_timestamp", "2024-01-01T00:00:00Z", "boundaries"),
        ("detected_columns", list(reversed(EXPECTED_COLUMNS)), "column names"),
    ],
)
def test_manifest_file_disagreements_are_fatal(
    tmp_path: Path, field: str, value: object, fragment: str
) -> None:
    _, _, raw_path = _audit(tmp_path)
    config, manifest_path = _config(tmp_path, raw_path, _base_rows())
    content = json.loads(manifest_path.read_text(encoding="utf-8"))
    content[field] = value
    if field == "sha256":
        content["dataset_version"] = "sha256:" + "a" * 16
        config = config.model_copy(
            update={"expected_dataset_version": content["dataset_version"]}
        )
    manifest_path.write_text(json.dumps(content), encoding="utf-8")
    result, _ = run_raw_data_audit(
        raw_path,
        config,
        repository_root=tmp_path,
        manifest_path=manifest_path,
        audit_timestamp=FIXED_AUDIT_TIME,
    )
    assert result.final_readiness_assessment["state"] == "NOT_READY"
    assert any(fragment in failure for failure in result.failures)


def test_manifest_config_disagreement_is_fatal(tmp_path: Path) -> None:
    _, _, raw_path = _audit(tmp_path)
    config, manifest_path = _config(tmp_path, raw_path, _base_rows())
    config = config.model_copy(update={"dataset_logical_name": "different"})
    result, _ = run_raw_data_audit(
        raw_path,
        config,
        repository_root=tmp_path,
        manifest_path=manifest_path,
        audit_timestamp=FIXED_AUDIT_TIME,
    )
    assert "Manifest/config logical dataset identifiers disagree" in result.failures


def test_missing_manifest_is_fatal_and_preserves_warning_context(
    tmp_path: Path,
) -> None:
    _, _, raw_path = _audit(tmp_path)
    config, _ = _config(tmp_path, raw_path, _base_rows())
    result, tables = run_raw_data_audit(
        raw_path,
        config,
        repository_root=tmp_path,
        manifest_path=tmp_path / "missing-manifest.json",
        audit_timestamp=FIXED_AUDIT_TIME,
    )
    assert result.final_readiness_assessment["state"] == "NOT_READY"
    assert any("not found" in failure for failure in result.failures)
    assert result.warnings
    assert all(frame.empty for frame in tables.values())


def test_missing_timestamp_period_allocation_and_month_classifications() -> None:
    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2020-04-30T23:30:00Z",
                "2020-05-01T00:30:00Z",
                "2020-05-15T00:00:00Z",
                "2020-06-01T00:00:00Z",
                "2020-06-01T00:15:00Z",
            ],
            utc=True,
        )
    )
    gaps = build_gap_table(
        timestamps,
        cadence_minutes=15,
        weekly_minimum_minutes=10_000,
        large_gap_minimum_minutes=720,
    )
    missing = expand_missing_timestamps(gaps, 15)
    annual, monthly, _ = _coverage_tables(
        timestamps,
        gaps,
        missing,
        pd.Series([15] * len(timestamps)),
        0.75,
        1,
    )
    assert annual["estimated_missing_m15_timestamps_in_period"].sum() == len(missing)
    assert monthly["estimated_missing_m15_timestamps_in_period"].sum() == len(missing)
    april = monthly.set_index("month").loc["2020-04"]
    may = monthly.set_index("month").loc["2020-05"]
    assert april["boundary_month"]
    assert april["continuity_impaired_month"]
    assert may["continuity_impaired_month"]
    assert "nonweekend_gaps" in may["classification_reasons"]


def test_sparse_month_without_continuity_and_normal_month() -> None:
    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:15:00Z",
                "2024-01-01T00:30:00Z",
                "2024-01-01T00:45:00Z",
                "2024-02-01T00:00:00Z",
                "2024-03-01T00:00:00Z",
                "2024-03-01T00:15:00Z",
                "2024-03-01T00:30:00Z",
                "2024-03-01T00:45:00Z",
                "2024-04-01T00:00:00Z",
                "2024-04-01T00:15:00Z",
                "2024-04-01T00:30:00Z",
                "2024-04-01T00:45:00Z",
            ],
            utc=True,
        )
    )
    _, monthly, _ = _coverage_tables(
        timestamps,
        pd.DataFrame(columns=GAP_COLUMNS),
        pd.DataFrame(
            columns=["gap_id", "missing_timestamp_utc", "preliminary_category"]
        ),
        pd.Series([15] * len(timestamps)),
        0.75,
        1,
    )
    indexed = monthly.set_index("month")
    assert indexed.loc["2024-02", "sparse_month"]
    assert not indexed.loc["2024-02", "continuity_impaired_month"]
    assert not indexed.loc["2024-03", "partial_observed_month"]


def test_relationship_masks_and_configured_weekly_threshold() -> None:
    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2024-01-05T21:45:00Z",
                "2024-01-07T22:00:00Z",
                "2024-01-08T10:00:00Z",
                "2024-01-08T10:15:00Z",
            ],
            utc=True,
        )
    )
    gaps = build_gap_table(
        timestamps,
        cadence_minutes=15,
        weekly_minimum_minutes=1440,
        large_gap_minimum_minutes=720,
    )
    missing = expand_missing_timestamps(gaps, 15)
    relationships = _internal_consistency(
        pd.Series([1, 2, 14, 15]),
        timestamps,
        gaps,
        missing,
        {
            "first_timestamp_before": "2024-01-08T10:00:00Z",
            "last_timestamp_after": "2024-01-08T10:15:00Z",
        },
        large_gap_minimum_minutes=720,
        low_count_quantile=0.1,
        percentiles=(0.25, 0.5, 0.75),
        boundary_radius_bars=0,
    )
    assert relationships["weekly_boundary_observations"]["subset"]["sample_size"] == 2
    assert relationships["large_gap_observations"]["subset"]["sample_size"] == 3
    assert (
        relationships["computed_2023_affected_period_observations"]["subset"][
            "sample_size"
        ]
        == 2
    )
    assert _weekly_boundaries(timestamps, 15, 1440)["boundary_count"] == 1
    assert _weekly_boundaries(timestamps, 15, 4000)["boundary_count"] == 0
    high_threshold_gaps = build_gap_table(
        timestamps,
        cadence_minutes=15,
        weekly_minimum_minutes=4000,
        large_gap_minimum_minutes=720,
    )
    assert "likely_weekly_closure" not in set(
        high_threshold_gaps["preliminary_category"]
    )
    high_relationships = _internal_consistency(
        pd.Series([1, 2, 14, 15]),
        timestamps,
        high_threshold_gaps,
        expand_missing_timestamps(high_threshold_gaps, 15),
        None,
        large_gap_minimum_minutes=720,
        low_count_quantile=0.1,
        percentiles=(0.25, 0.5, 0.75),
        boundary_radius_bars=0,
    )
    assert (
        high_relationships["weekly_boundary_observations"]["subset"]["sample_size"] == 0
    )


def test_warning_population_and_ordering() -> None:
    empty_gaps = pd.DataFrame(columns=GAP_COLUMNS)
    assert (
        _warning_list(
            gaps=empty_gaps,
            investigation={},
            partial={},
            unresolved=[],
        )
        == []
    )
    warnings = _warning_list(
        gaps=empty_gaps,
        investigation={"materially_different_from_2022_and_2024": True},
        partial={"incomplete_first_year": True},
        unresolved=[
            "Whether timestamp_utc denotes candle open time or candle close time.",
            "The EUR/USD price quote convention.",
        ],
    )
    assert warnings == [
        "COVERAGE: 2023 satisfies the predefined continuity-impairment "
        "materiality rule.",
        "COVERAGE: The first or final observed year is partial.",
        "SEMANTIC: Timestamp convention remains unresolved.",
        "SEMANTIC: Quote convention remains unresolved.",
    ]


def test_price_precision_uses_source_text_digits(tmp_path: Path) -> None:
    rows = _base_rows()
    rows[0][1] = "1.10000"
    rows[1][1] = "1.10001"
    result, _, _ = _audit(tmp_path, rows)
    precision = result.price_precision_results["by_year"]["2024"]["open"]
    assert precision["maximum_source_decimal_places"] == 5
    assert precision["minimum_positive_increment"] == pytest.approx(0.00001)
    assert (
        "binary floating point is not used" in result.price_precision_results["method"]
    )
