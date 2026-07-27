"""Deterministic serialization and computed Markdown reporting for audits."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

import pandas as pd

from eurusd_research.data.quality_models import AuditResult

VOLATILE_RESULT_FIELDS = (
    ("audit_metadata", "audit_timestamp_utc"),
    ("audit_metadata", "elapsed_seconds"),
    ("dataset_identity", "raw_file_modification_timestamp_utc"),
)


def normalize_audit_result(data: dict[str, object]) -> dict[str, object]:
    """Remove documented volatile metadata for deterministic-content tests."""
    normalized = deepcopy(data)
    for section, field in VOLATILE_RESULT_FIELDS:
        section_value = normalized.get(section)
        if isinstance(section_value, dict):
            section_value.pop(field, None)
    return normalized


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def write_audit_outputs(
    result: AuditResult,
    tables: dict[str, pd.DataFrame],
    output_directory: Path,
) -> None:
    """Write bounded JSON, all diagnostic CSVs, and the generated report."""
    output_directory.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(result.to_dict(), indent=2, sort_keys=True, allow_nan=False)
    _atomic_text(output_directory / "raw_data_quality_audit.json", f"{json_text}\n")
    for filename, frame in tables.items():
        temporary = output_directory / f"{filename}.tmp"
        frame.to_csv(
            temporary,
            index=False,
            lineterminator="\n",
            date_format="%Y-%m-%dT%H:%M:%SZ",
        )
        temporary.replace(output_directory / filename)
    _atomic_text(
        output_directory / "raw_data_quality_report.md",
        render_markdown_report(result),
    )


def render_markdown_report(result: AuditResult) -> str:
    """Render an evidence-led report solely from computed audit results."""
    data = result.to_dict()
    identity = data["dataset_identity"]
    schema = data["schema_results"]
    timestamps = data["timestamp_results"]
    duplicates = data["duplicate_results"]
    ohlc = data["ohlc_results"]
    counts = data["count_field_results"]
    gaps = data["gap_summary"]
    investigation = data["continuity_investigation_2023"]
    partial = data["partial_period_results"]
    readiness = data["final_readiness_assessment"]
    source = data["source_results"]
    missing = data["missing_value_results"]
    precision = data["price_precision_results"]
    weekly = data["weekly_boundary_results"]
    movements = data["movement_diagnostics"]
    relationships = data["internal_consistency_results"]
    count_stats = counts.get("summary_statistics", {})
    if not timestamps:
        lines = [
            "# Raw Dataset Quality Audit",
            "",
            "## Audit scope",
            "",
            "The audit stopped on fatal lineage or mandatory-schema validation. "
            "Header-only diagnostic tables were still generated.",
            "",
            "## Readiness assessment",
            "",
            f"**{readiness.get('state')}**",
            "",
            "## Warnings and failures",
            "",
            f"- Warnings: {data['warnings'] or 'None'}",
            f"- Failures: {data['failures'] or 'None'}",
            "",
            "## Unresolved source assumptions",
            "",
        ]
        lines.extend(f"- {item}" for item in data["unresolved_assumptions"])
        return "\n".join(lines) + "\n"
    lines = [
        "# Raw Dataset Quality Audit",
        "",
        "## Audit scope",
        "",
        "This is a strictly read-only technical integrity and coverage audit. It does "
        "not perform market-behaviour, session, signal, or performance analysis.",
        "",
        "## Dataset identity and lineage",
        "",
        f"- Dataset version: `{identity.get('dataset_version')}`",
        f"- File size: {identity.get('file_size_bytes'):,} bytes",
        f"- SHA-256: `{identity.get('sha256_after', identity.get('sha256_before'))}`",
        "- Checksum matches authoritative manifest: "
        f"{identity.get('checksum_matches_manifest')}",
        "- Raw file unchanged during audit: "
        f"{identity.get('raw_unchanged_during_audit')}",
        "",
        "## Confirmed observations",
        "",
        f"- Rows: {schema.get('row_count'):,}; columns: {schema.get('column_count')}.",
        f"- Mandatory schema satisfied: {schema.get('mandatory_schema_satisfied')}.",
        f"- Parsed timestamps: {timestamps.get('successful_parsing_count'):,}; "
        f"unparseable: {timestamps.get('unparseable_count'):,}.",
        f"- Observed bounds: {timestamps.get('first_timestamp')} through "
        f"{timestamps.get('last_timestamp')}.",
        f"- Exact 15-minute intervals: "
        f"{timestamps.get('exact_15_minute_interval_count'):,} "
        f"({timestamps.get('exact_15_minute_interval_percentage'):.6f}%).",
        f"- Duplicate timestamp rows: "
        f"{duplicates.get('duplicate_primary_timestamp_row_count'):,}; duplicate "
        f"complete rows: {duplicates.get('duplicate_complete_row_count'):,}.",
        f"- Gaps above 15 minutes: {gaps.get('gap_count'):,}; estimated absent M15 "
        f"timestamps: {gaps.get('estimated_missing_m15_timestamps'):,}.",
        f"- Invalid OHLC rows: {ohlc.get('combined_invalid_ohlc_count'):,}; flat "
        f"candles: {ohlc.get('flat_candle_count'):,}; zero-body candles: "
        f"{ohlc.get('zero_body_candle_count'):,}.",
        f"- Per-column null, NaN, infinity, and empty-string results: {missing}.",
        f"- Source labels: {source.get('value_details')}.",
        f"- Source-provided count field bounds: "
        f"{count_stats.get('minimum')} to {count_stats.get('maximum')}; median "
        f"{count_stats.get('median')}; mean {count_stats.get('mean')}; standard "
        f"deviation {count_stats.get('standard_deviation')}.",
        f"- Count-field percentiles: {count_stats.get('percentiles')}; sample size "
        f"{count_stats.get('sample_size')}.",
        f"- Apparent maximum source-text decimal places by year: "
        f"{precision.get('apparent_maximum_decimal_places_by_year')}.",
        f"- Apparent source-text precision change years: "
        f"{precision.get('structural_change_years')}.",
        "",
        "## Gap definitions and evidence",
        "",
    ]
    for category, definition in gaps.get("category_definitions", {}).items():
        lines.append(f"- `{category}`: {definition}")
    lines.extend(
        [
            "",
            f"Observed category counts: {gaps.get('category_counts')}. These are "
            "preliminary descriptive categories, not confirmed market-calendar causes.",
            "",
            "## 2023 continuity falsification test",
            "",
            f"- Gaps outside the weekly rule by year: "
            f"{investigation.get('all_gaps_outside_weekly_rule_by_year')}.",
            f"- Non-weekend intraday gaps by year: "
            f"{investigation.get('non_weekend_intraday_gaps_by_year')}.",
            f"- Concentrated 2023 period: "
            f"{investigation.get('concentrated_2023_period')}.",
            f"- Recurring intraday patterns: "
            f"{investigation.get('recurring_intraday_pattern_2023')}.",
            f"- Materiality rule: {investigation.get('materiality_rule')}.",
            f"- 2023 materially different from 2022 and 2024 under that rule: "
            f"{investigation.get('materially_different_from_2022_and_2024')}.",
            "",
            "## Coverage and partial periods",
            "",
            f"- Incomplete first year: {partial.get('incomplete_first_year')} "
            f"({partial.get('first_year')}).",
            f"- Incomplete final year: {partial.get('incomplete_final_year')} "
            f"({partial.get('final_year')}).",
            f"- Boundary months: {partial.get('boundary_months')}.",
            f"- Sparse months: {partial.get('sparse_months')}.",
            "- Continuity-impaired months: "
            f"{partial.get('continuity_impaired_months')}.",
            f"- Month classifications: {partial.get('definitions')}.",
            f"- {partial.get('final_timestamp_observation')}",
            "",
            "## Weekly-boundary coverage diagnostics",
            "",
            f"- Detected boundaries: {weekly.get('boundary_count')}.",
            f"- Common last-bar times (UTC): "
            f"{weekly.get('common_last_bar_times_utc')}.",
            f"- Common first-bar times (UTC): "
            f"{weekly.get('common_first_bar_times_utc')}.",
            f"- {weekly.get('interpretation_limit')}",
            "",
            "## Integrity discontinuity diagnostics",
            "",
            f"- Exact-15-minute close-change diagnostics: "
            f"{movements.get('exact_15_minute')}.",
            f"- Longer-gap close-change diagnostics: "
            f"{movements.get('longer_than_15_minute_gap')}.",
            "- These are bad-print and discontinuity checks, not trading returns or "
            "market-behaviour findings.",
            "",
            "## Count-field relationships",
            "",
            f"- All observations: {relationships.get('all_observations')}.",
            f"- Near configured large gaps: "
            f"{relationships.get('large_gap_observations')}.",
            f"- Weekly-boundary observations: "
            f"{relationships.get('weekly_boundary_observations')}.",
            "- Continuity-impaired UTC dates: "
            f"{relationships.get('continuity_impaired_utc_date_observations')}.",
            "- Computed 2023 affected period: "
            f"{relationships.get('computed_2023_affected_period_observations')}.",
            f"- {relationships.get('interpretation_limit')}",
            "",
            "## Interpretations requiring caution",
            "",
            "- `volume_or_tick_count` is described only as a source-provided count "
            "field. Its empirical distribution can support, but cannot confirm, the "
            "interpretation that it counts constituent M1 observations.",
            "- Long non-weekly gaps are duration/date diagnostics only; their causes "
            "remain unresolved.",
            "- A single consistent source label is not proof of one unchanged "
            "upstream feed.",
            "- Unusually large ranges and close discontinuities are retained and "
            "flagged for later external verification; they are not automatically "
            "errors.",
            "",
            "## Unresolved source assumptions",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in data["unresolved_assumptions"])
    lines.extend(
        [
            "",
            "## Readiness assessment",
            "",
            f"**{readiness.get('state')}**",
            "",
            "Reasons:",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in readiness.get("reasons", []))
    lines.extend(["", "Required actions:", ""])
    actions = readiness.get("required_actions", [])
    lines.extend(f"- {item}" for item in actions)
    if not actions:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Warnings and failures",
            "",
            f"- Warnings: {data['warnings'] or 'None'}",
            f"- Failures: {data['failures'] or 'None'}",
            "",
            "Detailed records are retained in the sibling CSV diagnostic tables. "
            "All findings trace to the registered checksum shown above.",
            "",
        ]
    )
    return "\n".join(lines)
