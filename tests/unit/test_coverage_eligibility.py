from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from eurusd_research.config import CoverageProfileConfig
from eurusd_research.research.eligibility import (
    aggregate_flags,
    apply_profile,
    build_profile_masks,
    build_row_flags,
    validate_canonical_profile_algebra,
)
from eurusd_research.research.models import CoverageLineage
from eurusd_research.research.registry import FLAG_COLUMNS, serialized_rule_registry


def _lineage() -> CoverageLineage:
    return CoverageLineage(
        dataset_logical_name="fixture",
        dataset_version="sha256:0123456789abcdef",
        raw_sha256="0" * 64,
        audit_method_version="raw-data-quality-audit-v2",
        audit_result_content_sha256="1" * 64,
        audit_result_path="reports/audits/audit.json",
        audit_gap_table_sha256="4" * 64,
        audit_gap_table_path="reports/audits/gaps.csv",
        audit_monthly_table_sha256="5" * 64,
        audit_monthly_table_path="reports/audits/monthly.csv",
        coverage_method_id="COVERAGE-001",
        coverage_method_version="research-coverage-v1",
        coverage_config_sha256="2" * 64,
        repository_version="git:" + "3" * 40,
    )


def _audit(row_count: int = 4, *, valid: bool = True) -> dict[str, Any]:
    return {
        "schema_results": {
            "mandatory_schema_satisfied": valid,
            "row_count": row_count,
            "row_count_matches_manifest": valid,
        },
        "timestamp_results": {
            "successful_parsing_count": row_count,
            "source_values_with_explicit_timezone_count": row_count,
            "unparseable_count": 0,
            "off_15_minute_grid_count": 0,
            "chronologically_ordered": valid,
        },
        "ohlc_results": {"combined_invalid_ohlc_count": 0 if valid else 1},
        "duplicate_results": {
            "duplicate_primary_timestamp_row_count": 0 if valid else 2
        },
        "partial_period_results": {
            "incomplete_first_year": False,
            "first_year": 2023,
            "incomplete_final_year": False,
            "final_year": 2023,
        },
        "continuity_investigation_2023": {
            "concentrated_2023_period": {
                "first_timestamp_before": "2023-02-01T00:00:00Z",
                "last_timestamp_after": "2023-02-01T00:30:00Z",
            }
        },
    }


def _evidence() -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    timestamps = pd.Series(
        [
            "2023-01-31T23:45:00Z",
            "2023-02-01T00:00:00Z",
            "2023-02-01T00:15:00Z",
            "2023-03-01T00:00:00Z",
        ],
        dtype="string",
    )
    gaps = pd.DataFrame(
        [
            {
                "timestamp_before": timestamps.iloc[0],
                "timestamp_after": timestamps.iloc[1],
                "preliminary_category": "likely_weekly_closure",
            },
            {
                "timestamp_before": timestamps.iloc[1],
                "timestamp_after": timestamps.iloc[2],
                "preliminary_category": "non_weekend_intraday",
            },
            {
                "timestamp_before": timestamps.iloc[2],
                "timestamp_after": timestamps.iloc[3],
                "preliminary_category": "long_nonweekly_gap",
            },
        ]
    )
    monthly = pd.DataFrame(
        [
            {
                "month": "2023-01",
                "boundary_month": True,
                "continuity_impaired_month": False,
            },
            {
                "month": "2023-02",
                "boundary_month": False,
                "continuity_impaired_month": True,
            },
            {
                "month": "2023-03",
                "boundary_month": False,
                "continuity_impaired_month": False,
            },
        ]
    )
    return timestamps, gaps, monthly


def test_row_flags_are_audit_backed_reversible_and_lineaged() -> None:
    timestamps, gaps, monthly = _evidence()
    frame = build_row_flags(timestamps, _audit(), gaps, monthly, _lineage())

    assert len(frame) == 4
    assert frame["raw_row_number"].tolist() == [2, 3, 4, 5]
    assert frame["raw_timestamp"].tolist() == timestamps.tolist()
    assert frame["research_eligible_default"].all()
    assert frame["cadence_valid"].tolist() == [True, False, False, False]
    assert frame["weekly_gap_boundary"].tolist() == [True, True, False, False]
    assert frame["nonweekend_gap_boundary"].tolist() == [False, True, True, False]
    assert frame["long_nonweekly_gap_boundary"].tolist() == [
        False,
        False,
        True,
        True,
    ]
    assert frame["continuity_impaired_period"].tolist() == [
        False,
        True,
        True,
        False,
    ]
    assert frame["affected_period_2023"].tolist() == [False, True, True, False]
    assert frame["partial_boundary_month"].tolist() == [True, False, False, False]
    assert frame["requires_sensitivity_analysis"].all()
    assert set(frame["eligibility_status"]) == {"conditionally_eligible"}
    assert frame["dataset_version"].astype(str).unique().tolist() == [
        "sha256:0123456789abcdef"
    ]
    assert tuple(serialized_rule_registry()) == FLAG_COLUMNS


def test_structural_failure_is_explicit_not_silently_removed() -> None:
    timestamps, gaps, monthly = _evidence()
    frame = build_row_flags(
        timestamps, _audit(valid=False), gaps.iloc[0:0], monthly, _lineage()
    )
    assert not frame["research_eligible_default"].any()
    assert set(frame["eligibility_status"]) == {"structurally_ineligible"}
    assert len(frame) == len(timestamps)


def test_row_timestamp_join_failure_is_clear() -> None:
    timestamps, gaps, monthly = _evidence()
    timestamps.iloc[0] = "invalid"
    with pytest.raises(ValueError, match="could not be joined"):
        build_row_flags(timestamps, _audit(), gaps, monthly, _lineage())


def test_level_propagation_semantics() -> None:
    timestamps, gaps, monthly = _evidence()
    rows = build_row_flags(timestamps, _audit(), gaps, monthly, _lineage())
    dates = aggregate_flags(rows, "date", _lineage())
    months = aggregate_flags(rows, "month", _lineage())
    years = aggregate_flags(rows, "year", _lineage())
    dataset = aggregate_flags(rows, "dataset", _lineage())

    assert aggregate_flags(rows, "row", _lineage()) is rows
    february = months.set_index("utc_month").loc["2023-02"]
    assert february["continuity_impaired_period"]
    assert not february["cadence_valid"]
    assert len(dates) == 3
    assert len(years) == 1
    assert dataset.loc[0, "observed_row_count"] == 4
    assert dataset.loc[0, "requires_sensitivity_analysis"]
    with pytest.raises(ValueError, match="Unsupported coverage level"):
        aggregate_flags(rows, "week", _lineage())


def test_profiles_are_consistent_and_configuration_driven() -> None:
    timestamps, gaps, monthly = _evidence()
    rows = build_row_flags(timestamps, _audit(), gaps, monthly, _lineage())
    frames = {
        level: aggregate_flags(rows, level, _lineage())
        for level in ("row", "date", "month", "year", "dataset")
    }
    profiles = {
        "FULL": CoverageProfileConfig(description="all rows"),
        "DEFAULT": CoverageProfileConfig(
            description="valid rows",
            require_all=("research_eligible_default",),
        ),
        "STRICT": CoverageProfileConfig(
            description="unflagged rows",
            require_all=("research_eligible_default",),
            exclude_any=("requires_sensitivity_analysis",),
        ),
        "OVERRIDE_2023": CoverageProfileConfig(
            description="affected only",
            require_any=("affected_period_2023",),
        ),
    }
    masks = build_profile_masks(frames, profiles)

    assert masks["row"]["FULL"].all()
    assert masks["row"]["DEFAULT"].all()
    assert not masks["row"]["STRICT"].any()
    assert masks["row"]["OVERRIDE_2023"].tolist() == [False, True, True, False]
    assert masks["month"]["OVERRIDE_2023"].sum() == 1


def test_canonical_profile_algebra_is_proved_independently_of_dataset() -> None:
    profiles = {
        "DEFAULT_RESEARCH": CoverageProfileConfig(
            description="default",
            require_all=("research_eligible_default",),
        ),
        "STRICT_CONTINUITY": CoverageProfileConfig(
            description="strict",
            require_all=("research_eligible_default",),
            exclude_any=("requires_sensitivity_analysis",),
        ),
        "SENSITIVITY_FULL": CoverageProfileConfig(
            description="sensitivity",
            require_all=(
                "research_eligible_default",
                "requires_sensitivity_analysis",
            ),
        ),
        "SENSITIVITY_2023": CoverageProfileConfig(
            description="2023",
            require_all=(
                "research_eligible_default",
                "requires_sensitivity_analysis",
                "affected_period_2023",
            ),
        ),
    }
    validate_canonical_profile_algebra(profiles)

    broken = dict(profiles)
    broken["SENSITIVITY_2023"] = CoverageProfileConfig(
        description="not necessarily a subset",
        require_all=("research_eligible_default", "affected_period_2023"),
    )
    with pytest.raises(ValueError, match="must be a subset"):
        validate_canonical_profile_algebra(broken)


def test_profile_rejects_unknown_flag() -> None:
    profile = CoverageProfileConfig(
        description="bad override", require_all=("not_a_flag",)
    )
    with pytest.raises(ValueError, match="unknown flags"):
        apply_profile(pd.DataFrame({"raw_available": [True]}), profile)
