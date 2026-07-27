from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.conftest import EXPECTED_COLUMNS

from eurusd_research.data.registry import (
    read_manifest,
    register_raw_dataset,
    sha256_file,
    write_registration,
)
from eurusd_research.data.validation import SchemaMismatchError


def test_sha256_is_reproducible(tiny_raw_csv: Path) -> None:
    first = sha256_file(tiny_raw_csv, chunk_size=7)
    second = sha256_file(tiny_raw_csv, chunk_size=1024)
    assert first == second
    assert len(first) == 64


def test_sha256_rejects_invalid_chunk_size(tiny_raw_csv: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        sha256_file(tiny_raw_csv, chunk_size=0)


def test_missing_file_errors_are_useful(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"
    with pytest.raises(FileNotFoundError, match="Raw dataset not found"):
        sha256_file(missing)


def test_register_raw_dataset(tiny_raw_csv: Path, tmp_path: Path) -> None:
    registered_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    result = register_raw_dataset(
        path=tiny_raw_csv,
        repository_root=tmp_path,
        logical_name="fixture",
        expected_columns=EXPECTED_COLUMNS,
        timestamp_column="timestamp_utc",
        registered_at=registered_at,
    )
    assert result.row_count == 2
    assert result.first_timestamp == "2020-01-01T00:00:00Z"
    assert result.last_timestamp == "2020-01-01T00:15:00Z"
    assert result.registration_timestamp_utc == "2026-01-02T03:04:05Z"
    assert result.dataset_version == f"sha256:{result.sha256[:16]}"
    assert result.file_size_bytes == tiny_raw_csv.stat().st_size


def test_registration_requires_repository_file(
    tiny_raw_csv: Path, tmp_path: Path
) -> None:
    other_root = tmp_path / "other"
    other_root.mkdir()
    with pytest.raises(ValueError, match="inside the repository"):
        register_raw_dataset(
            path=tiny_raw_csv,
            repository_root=other_root,
            logical_name="fixture",
            expected_columns=EXPECTED_COLUMNS,
            timestamp_column="timestamp_utc",
        )


def test_registration_rejects_wrong_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("timestamp_utc,close\n2020-01-01T00:00:00Z,1.0\n")
    with pytest.raises(SchemaMismatchError, match="do not match"):
        register_raw_dataset(
            path=path,
            repository_root=tmp_path,
            logical_name="bad",
            expected_columns=EXPECTED_COLUMNS,
            timestamp_column="timestamp_utc",
        )


def test_write_registration_json(tiny_raw_csv: Path, tmp_path: Path) -> None:
    registration = register_raw_dataset(
        path=tiny_raw_csv,
        repository_root=tmp_path,
        logical_name="fixture",
        expected_columns=EXPECTED_COLUMNS,
        timestamp_column="timestamp_utc",
    )
    output = tmp_path / "reports" / "manifest.json"
    assert write_registration(registration, output)
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["sha256"] == registration.sha256
    assert not output.with_suffix(".json.tmp").exists()
    before = output.read_bytes()
    later = registration.model_copy(
        update={"registration_timestamp_utc": "2099-01-01T00:00:00Z"}
    )
    assert not write_registration(later, output)
    assert output.read_bytes() == before
    assert read_manifest(output) == registration


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sha256", "bad"),
        ("row_count", 0),
        ("file_size_bytes", 0),
        ("detected_columns", []),
    ],
)
def test_manifest_rejects_malformed_required_fields(
    tmp_path: Path, field: str, value: object
) -> None:
    manifest = tmp_path / "manifest.json"
    content = {
        "logical_dataset_name": "fixture",
        "relative_file_path": "data/raw/file.csv",
        "file_size_bytes": 10,
        "sha256": "a" * 64,
        "row_count": 1,
        "detected_columns": list(EXPECTED_COLUMNS),
        "first_timestamp": "2020-01-01T00:00:00Z",
        "last_timestamp": "2020-01-01T00:00:00Z",
        "registration_timestamp_utc": "2026-01-01T00:00:00Z",
        "dataset_version": "sha256:" + "a" * 16,
    }
    content[field] = value
    manifest.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match=r"malformed|version"):
        read_manifest(manifest)


def test_missing_and_invalid_json_manifest_fail(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        read_manifest(tmp_path / "missing.json")
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable"):
        read_manifest(path)
