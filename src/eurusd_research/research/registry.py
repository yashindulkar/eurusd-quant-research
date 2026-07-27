"""Canonical coverage-rule registry and aggregation semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Aggregation = Literal["all", "any"]


@dataclass(frozen=True, slots=True)
class CoverageRule:
    """One descriptive flag with a stable identifier and propagation rule."""

    rule_id: str
    description: str
    audit_source: str
    aggregation: Aggregation

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-compatible registry entry."""
        return asdict(self)


RULES: dict[str, CoverageRule] = {
    "raw_available": CoverageRule(
        "COV-ROW-001",
        "The registered raw source row is present.",
        "raw file joined by physical row and timestamp",
        "all",
    ),
    "schema_valid": CoverageRule(
        "COV-ROW-002",
        "RAW-DQ-001 reports mandatory schema and row-count reconciliation.",
        "schema_results",
        "all",
    ),
    "timestamp_valid": CoverageRule(
        "COV-ROW-003",
        "RAW-DQ-001 reports valid, ordered, UTC-aware, on-grid timestamps.",
        "timestamp_results",
        "all",
    ),
    "ohlc_valid": CoverageRule(
        "COV-ROW-004",
        "RAW-DQ-001 reports no OHLC invariant violation.",
        "ohlc_results",
        "all",
    ),
    "duplicate_free": CoverageRule(
        "COV-ROW-005",
        "RAW-DQ-001 reports no duplicate primary timestamp.",
        "duplicate_results",
        "all",
    ),
    "cadence_valid": CoverageRule(
        "COV-ROW-006",
        "The incoming observed interval is exactly M15; the first row is "
        "vacuously true.",
        "timestamp_gaps.csv: timestamp_after",
        "all",
    ),
    "weekly_gap_boundary": CoverageRule(
        "COV-ROW-007",
        "The row is either boundary endpoint of an audited likely-weekly-closure gap.",
        "timestamp_gaps.csv: likely_weekly_closure",
        "any",
    ),
    "long_nonweekly_gap_boundary": CoverageRule(
        "COV-ROW-008",
        "The row is either boundary endpoint of an audited long non-weekly gap.",
        "timestamp_gaps.csv: long_nonweekly_gap",
        "any",
    ),
    "nonweekend_gap_boundary": CoverageRule(
        "COV-ROW-009",
        "The row is either boundary endpoint of an audited non-weekend intraday gap.",
        "timestamp_gaps.csv: non_weekend_intraday",
        "any",
    ),
    "unclassified_gap_boundary": CoverageRule(
        "COV-ROW-010",
        "The row is either boundary endpoint of an audited unclassified gap.",
        "timestamp_gaps.csv: unclassified",
        "any",
    ),
    "continuity_impaired_period": CoverageRule(
        "COV-PERIOD-001",
        "The row belongs to a RAW-DQ-001 continuity-impaired UTC month.",
        "monthly_coverage.csv: continuity_impaired_month",
        "any",
    ),
    "affected_period_2023": CoverageRule(
        "COV-PERIOD-002",
        "The row is within the inclusive audited concentrated-2023 bounds.",
        "continuity_investigation_2023.concentrated_2023_period",
        "any",
    ),
    "partial_boundary_year": CoverageRule(
        "COV-PERIOD-003",
        "The row belongs to an audited incomplete first or final UTC year.",
        "partial_period_results",
        "any",
    ),
    "partial_boundary_month": CoverageRule(
        "COV-PERIOD-004",
        "The row belongs to an audited boundary UTC month.",
        "monthly_coverage.csv: boundary_month",
        "any",
    ),
    "research_eligible_default": CoverageRule(
        "COV-ELIG-001",
        "All structural quality flags pass; coverage warnings remain included.",
        "COV-ROW-001 through COV-ROW-005",
        "all",
    ),
    "requires_sensitivity_analysis": CoverageRule(
        "COV-ELIG-002",
        "At least one boundary, continuity, affected-period, or non-weekly gap "
        "condition applies.",
        "COV-ROW-008 through COV-ROW-010 and COV-PERIOD-001 through COV-PERIOD-004",
        "any",
    ),
}

FLAG_COLUMNS = tuple(RULES)
QUALITY_FLAGS = (
    "raw_available",
    "schema_valid",
    "timestamp_valid",
    "ohlc_valid",
    "duplicate_free",
)
SENSITIVITY_FLAGS = (
    "long_nonweekly_gap_boundary",
    "nonweekend_gap_boundary",
    "unclassified_gap_boundary",
    "continuity_impaired_period",
    "affected_period_2023",
    "partial_boundary_year",
    "partial_boundary_month",
)


def serialized_rule_registry() -> dict[str, dict[str, str]]:
    """Return stable rule metadata in declaration order."""
    return {flag: rule.to_dict() for flag, rule in RULES.items()}
