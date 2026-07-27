"""Minimal declarative schema for the registered raw EUR/USD CSV."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawColumn:
    """Expected raw column name and logical type."""

    name: str
    logical_type: str
    nullable: bool = False


RAW_CSV_SCHEMA: tuple[RawColumn, ...] = (
    RawColumn("timestamp_utc", "utc_timestamp"),
    RawColumn("open", "decimal_price"),
    RawColumn("high", "decimal_price"),
    RawColumn("low", "decimal_price"),
    RawColumn("close", "decimal_price"),
    RawColumn("volume_or_tick_count", "non_negative_count"),
    RawColumn("source", "string"),
)


def expected_raw_columns() -> tuple[str, ...]:
    """Return expected raw CSV columns in canonical order."""
    return tuple(column.name for column in RAW_CSV_SCHEMA)
