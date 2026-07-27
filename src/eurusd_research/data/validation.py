"""Small validation primitives; a complete dataset audit is intentionally deferred."""

from __future__ import annotations

from collections.abc import Sequence


class SchemaMismatchError(ValueError):
    """Raised when observed CSV columns differ from configured expectations."""


def validate_columns(observed: Sequence[str], expected: Sequence[str]) -> None:
    """Require exact column names and order for lineage registration."""
    if tuple(observed) != tuple(expected):
        raise SchemaMismatchError(
            f"CSV columns do not match expected schema. "
            f"Observed={list(observed)!r}; expected={list(expected)!r}"
        )
