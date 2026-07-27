"""Typed, JSON-safe result models for the raw-data quality audit."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd


def json_safe(value: Any) -> Any:
    """Recursively convert scientific Python values to strict JSON values."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@dataclass(slots=True)
class AuditResult:
    """Bounded main audit result; detailed records are written separately."""

    audit_metadata: dict[str, Any]
    dataset_identity: dict[str, Any]
    schema_results: dict[str, Any]
    timestamp_results: dict[str, Any]
    duplicate_results: dict[str, Any]
    missing_value_results: dict[str, Any]
    ohlc_results: dict[str, Any]
    price_precision_results: dict[str, Any]
    count_field_results: dict[str, Any]
    source_results: dict[str, Any]
    gap_summary: dict[str, Any]
    continuity_investigation_2023: dict[str, Any]
    calendar_coverage: dict[str, Any]
    partial_period_results: dict[str, Any]
    weekly_boundary_results: dict[str, Any]
    movement_diagnostics: dict[str, Any]
    internal_consistency_results: dict[str, Any]
    annual_coverage: list[dict[str, Any]]
    monthly_coverage: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    unresolved_assumptions: list[str] = field(default_factory=list)
    final_readiness_assessment: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the result into deterministic, strict-JSON-compatible data."""
        return cast(dict[str, Any], json_safe(asdict(self)))
