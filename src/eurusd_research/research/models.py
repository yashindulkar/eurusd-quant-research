"""Typed containers for coverage evidence, lineage, and generated masks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class CoverageLineage:
    """Stable identity shared by every coverage decision."""

    dataset_logical_name: str
    dataset_version: str
    raw_sha256: str
    audit_method_version: str
    audit_result_content_sha256: str
    audit_result_path: str
    audit_gap_table_sha256: str
    audit_gap_table_path: str
    audit_monthly_table_sha256: str
    audit_monthly_table_path: str
    coverage_method_id: str
    coverage_method_version: str
    coverage_config_sha256: str
    repository_version: str

    def to_dict(self) -> dict[str, str]:
        """Return JSON-compatible lineage."""
        return asdict(self)


@dataclass(slots=True)
class CoverageResult:
    """In-memory flags and profile masks at every supported coverage level."""

    lineage: CoverageLineage
    flags_by_level: dict[str, pd.DataFrame]
    profile_masks_by_level: dict[str, pd.DataFrame]
    summary: dict[str, Any]
