"""Shared test fixtures."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.helpers import EXPECTED_COLUMNS


@pytest.fixture
def tiny_raw_csv(tmp_path: Path) -> Iterator[Path]:
    """Create a two-row raw-like CSV and verify tests leave it unchanged."""
    path = tmp_path / "EURUSD_M15_UTC.csv"
    rows = [
        ("2020-01-01T00:00:00Z", "1.10", "1.11", "1.09", "1.105", "8", "fixture"),
        ("2020-01-01T00:15:00Z", "1.105", "1.12", "1.10", "1.11", "9", "fixture"),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(EXPECTED_COLUMNS)
        writer.writerows(rows)
    before = path.read_bytes()
    yield path
    assert path.read_bytes() == before
