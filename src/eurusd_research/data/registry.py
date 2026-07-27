"""Streaming raw-dataset identity and metadata registration."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eurusd_research.data.validation import validate_columns


class ManifestError(ValueError):
    """Raised when the authoritative dataset manifest cannot be trusted."""


class DatasetManifest(BaseModel):
    """Strict authoritative identity and observed metadata for one raw file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    logical_dataset_name: str = Field(min_length=1)
    relative_file_path: str = Field(min_length=1)
    file_size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(gt=0)
    detected_columns: tuple[str, ...] = Field(min_length=1)
    first_timestamp: str = Field(min_length=1)
    last_timestamp: str = Field(min_length=1)
    registration_timestamp_utc: str = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^sha256:[0-9a-f]{16}$")

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-compatible mapping."""
        return self.model_dump(mode="json")

    def identity_dict(self) -> dict[str, Any]:
        """Return immutable registration identity, excluding verification time."""
        content = self.to_dict()
        content.pop("registration_timestamp_utc")
        return content


DatasetRegistration = DatasetManifest


def read_manifest(path: Path) -> DatasetManifest:
    """Read and strictly validate the authoritative registration manifest."""
    if not path.is_file():
        raise ManifestError(f"Dataset manifest not found: {path}")
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"Dataset manifest is unreadable: {path}") from error
    try:
        manifest = DatasetManifest.model_validate(value)
    except ValidationError as error:
        raise ManifestError(f"Dataset manifest is malformed: {error}") from error
    if manifest.dataset_version != f"sha256:{manifest.sha256[:16]}":
        raise ManifestError("Dataset manifest version does not match its SHA-256")
    return manifest


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate SHA-256 by streaming fixed-size chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(chunk_size), b""):
                digest.update(chunk)
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Raw dataset not found: {path}") from error
    return digest.hexdigest()


def register_raw_dataset(
    *,
    path: Path,
    repository_root: Path,
    logical_name: str,
    expected_columns: tuple[str, ...],
    timestamp_column: str,
    registered_at: datetime | None = None,
) -> DatasetRegistration:
    """Read metadata from a CSV without altering it."""
    resolved_path = path.resolve()
    resolved_root = repository_root.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("Raw dataset must be inside the repository")
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Raw dataset not found: {resolved_path}")

    stat_before = resolved_path.stat()
    checksum = sha256_file(resolved_path)
    row_count = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None

    with resolved_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        validate_columns(columns, expected_columns)
        for row in reader:
            timestamp = row.get(timestamp_column)
            if row_count == 0:
                first_timestamp = timestamp
            last_timestamp = timestamp
            row_count += 1

    stat_after = resolved_path.stat()
    if (stat_before.st_size, stat_before.st_mtime_ns) != (
        stat_after.st_size,
        stat_after.st_mtime_ns,
    ):
        raise RuntimeError("Raw dataset changed during registration")
    if row_count == 0 or first_timestamp is None or last_timestamp is None:
        raise ValueError("Raw dataset must contain at least one data row")

    registration_time = (registered_at or datetime.now(UTC)).astimezone(UTC)
    return DatasetManifest(
        logical_dataset_name=logical_name,
        relative_file_path=resolved_path.relative_to(resolved_root).as_posix(),
        file_size_bytes=stat_after.st_size,
        sha256=checksum,
        row_count=row_count,
        detected_columns=columns,
        first_timestamp=first_timestamp,
        last_timestamp=last_timestamp,
        registration_timestamp_utc=registration_time.isoformat().replace("+00:00", "Z"),
        dataset_version=f"sha256:{checksum[:16]}",
    )


def write_registration(
    registration: DatasetRegistration,
    output_path: Path,
) -> bool:
    """Write changed identity atomically; preserve bytes for identical identity."""
    if output_path.is_file():
        existing = read_manifest(output_path)
        if existing.identity_dict() == registration.identity_dict():
            return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(registration.to_dict(), handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary_path.replace(output_path)
    return True
