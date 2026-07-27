"""Task 02-backed orchestration for canonical research coverage metadata."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pandas as pd

from eurusd_research.config import CoverageConfig, ResearchConfig, load_config
from eurusd_research.data.audit import MONTHLY_COVERAGE_COLUMNS
from eurusd_research.data.gaps import GAP_COLUMNS
from eurusd_research.data.registry import DatasetManifest, read_manifest, sha256_file
from eurusd_research.data.reporting import normalize_audit_result
from eurusd_research.paths import find_repository_root, project_path
from eurusd_research.research.eligibility import (
    aggregate_flags,
    build_profile_masks,
    build_row_flags,
    validate_canonical_profile_algebra,
)
from eurusd_research.research.models import CoverageLineage, CoverageResult
from eurusd_research.research.registry import (
    FLAG_COLUMNS,
    RULES,
    SENSITIVITY_FLAGS,
    serialized_rule_registry,
)

LEVELS = ("row", "date", "month", "year", "dataset")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Coverage audit result is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise ValueError("Coverage audit result must be a JSON object")
    return cast(dict[str, Any], value)


def _stable_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _repository_version(
    root: Path, ignored_generated_paths: tuple[Path, ...] = ()
) -> str:
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if head.returncode != 0 or not head.stdout.strip():
        raise ValueError("Repository version cannot be resolved from Git")
    status_arguments = [
        "git",
        "-C",
        str(root),
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        ".",
    ]
    for path in ignored_generated_paths:
        relative = path.as_posix().rstrip("/")
        status_arguments.extend((f":(exclude){relative}", f":(exclude){relative}/**"))
    status = subprocess.run(
        status_arguments,
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        raise ValueError("Repository worktree state cannot be resolved from Git")
    suffix = "+dirty" if status.stdout.strip() else "+clean"
    return f"git:{head.stdout.strip()}{suffix}"


def _validate_audit_contract(
    audit: dict[str, Any],
    manifest: DatasetManifest,
    gaps: pd.DataFrame,
    monthly: pd.DataFrame,
    config: ResearchConfig,
) -> None:
    if tuple(gaps.columns) != GAP_COLUMNS:
        raise ValueError("Task 02 gap artifact has an incompatible schema")
    if tuple(monthly.columns) != MONTHLY_COVERAGE_COLUMNS:
        raise ValueError("Task 02 monthly artifact has an incompatible schema")
    metadata = audit.get("audit_metadata", {})
    if (
        metadata.get("audit_method_version")
        != config.coverage.required_audit_method_version
    ):
        raise ValueError("Task 02 audit method version is incompatible")
    thresholds = metadata.get("effective_thresholds", {})
    expected_thresholds = {
        "cadence_minutes": config.data.audit.cadence_minutes,
        "continuity_impaired_min_nonweekend_gap_count": (
            config.data.audit.continuity_impaired_min_nonweekend_gap_count
        ),
        "large_gap_minimum_minutes": config.data.audit.large_gap_minimum_minutes,
        "recurring_gap_minimum_count": (config.data.audit.recurring_gap_minimum_count),
        "weekly_gap_minimum_minutes": (config.data.audit.weekly_gap_minimum_minutes),
    }
    if thresholds != expected_thresholds:
        raise ValueError("Task 02 audit thresholds are stale or incompatible")
    identity = audit.get("dataset_identity", {})
    if identity.get("sha256_after") != manifest.sha256:
        raise ValueError("Task 02 audit SHA-256 does not match the manifest")
    if identity.get("dataset_version") != manifest.dataset_version:
        raise ValueError("Task 02 audit dataset version does not match the manifest")
    identity_requirements = (
        "checksum_matches_manifest",
        "file_size_matches_manifest",
        "manifest_config_file_reconciliation_satisfied",
        "raw_unchanged_during_audit",
    )
    if not all(identity.get(field) is True for field in identity_requirements):
        raise ValueError("Task 02 audit identity reconciliation is incomplete")
    schema = audit.get("schema_results", {})
    if (
        schema.get("row_count") != manifest.row_count
        or schema.get("row_count_matches_manifest") is not True
    ):
        raise ValueError("Task 02 audit row identity is stale")
    timestamps = audit.get("timestamp_results", {})
    if (
        timestamps.get("first_timestamp") != manifest.first_timestamp
        or timestamps.get("last_timestamp") != manifest.last_timestamp
        or timestamps.get("first_timestamp_matches_manifest") is not True
        or timestamps.get("last_timestamp_matches_manifest") is not True
    ):
        raise ValueError("Task 02 audit timestamp bounds are stale")
    audit_time = pd.Timestamp(metadata.get("audit_timestamp_utc"))
    registration_time = pd.Timestamp(manifest.registration_timestamp_utc)
    if audit_time < registration_time:
        raise ValueError("Task 02 audit predates the registered dataset manifest")
    if audit.get("failures"):
        raise ValueError("Task 02 audit has fatal findings; coverage is not generated")
    state = audit.get("final_readiness_assessment", {}).get("state")
    if state not in {"READY", "CONDITIONALLY_READY"}:
        raise ValueError(f"Task 02 audit readiness is not usable: {state}")
    if len(gaps) != audit.get("gap_summary", {}).get("gap_count"):
        raise ValueError("Task 02 gap artifact count disagrees with its audit result")
    expected_category_counts = audit.get("gap_summary", {}).get("category_counts", {})
    observed_category_counts = {
        str(key): int(value)
        for key, value in gaps["preliminary_category"]
        .value_counts()
        .sort_index()
        .items()
    }
    if observed_category_counts != dict(sorted(expected_category_counts.items())):
        raise ValueError("Task 02 gap categories are stale or incompatible")
    expected_missing = audit.get("gap_summary", {}).get(
        "estimated_missing_m15_timestamps"
    )
    if int(gaps["estimated_missing_m15_timestamps"].sum()) != expected_missing:
        raise ValueError("Task 02 gap missing-timestamp total is stale")
    partial = audit.get("partial_period_results", {})
    impaired_json = list(partial.get("continuity_impaired_months", []))
    impaired_csv = (
        monthly.loc[monthly["continuity_impaired_month"], "month"].astype(str).tolist()
    )
    if impaired_json != impaired_csv:
        raise ValueError("Task 02 continuity-impaired months disagree across artifacts")
    boundary_json = list(partial.get("boundary_months", []))
    boundary_csv = monthly.loc[monthly["boundary_month"], "month"].astype(str).tolist()
    if boundary_json != boundary_csv:
        raise ValueError("Task 02 boundary months disagree across artifacts")
    audit_monthly = audit.get("monthly_coverage", [])
    if len(audit_monthly) != len(monthly):
        raise ValueError("Task 02 monthly artifact row count is stale")
    comparison_fields = (
        "month",
        "bar_count",
        "boundary_month",
        "sparse_month",
        "continuity_impaired_month",
        "partial_observed_month",
        "classification_reasons",
    )
    for expected, (_, observed) in zip(audit_monthly, monthly.iterrows(), strict=True):
        for field in comparison_fields:
            observed_value = observed[field]
            if pd.isna(observed_value):
                observed_value = ""
            if observed_value != expected[field]:
                raise ValueError(
                    f"Task 02 monthly artifact is stale at {expected['month']}:{field}"
                )
    affected = audit.get("continuity_investigation_2023", {}).get(
        "concentrated_2023_period"
    )
    if affected is None:
        raise ValueError("Task 02 audit has no computed 2023 affected-period bounds")
    before_values = set(gaps["timestamp_before"].astype(str))
    after_values = set(gaps["timestamp_after"].astype(str))
    if (
        affected["first_timestamp_before"] not in before_values
        or affected["last_timestamp_after"] not in after_values
    ):
        raise ValueError("Task 02 affected-period bounds are stale")


def _coverage_config_digest(config: CoverageConfig) -> str:
    return _stable_digest(config.model_dump(mode="json"))


def _load_evidence(
    root: Path, config: ResearchConfig
) -> tuple[
    DatasetManifest,
    dict[str, Any],
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
    str,
    str,
    str,
]:
    raw_path = project_path(config.data.raw_dataset_path, root)
    manifest = read_manifest(project_path(config.data.registered_manifest_path, root))
    raw_stat_before = raw_path.stat()
    checksum_before = sha256_file(raw_path)
    if checksum_before != manifest.sha256:
        raise ValueError("Raw SHA-256 does not match the authoritative manifest")
    audit_path = project_path(config.coverage.audit_result_path, root)
    gap_path = project_path(config.coverage.audit_gap_table_path, root)
    monthly_path = project_path(config.coverage.audit_monthly_table_path, root)
    audit = _read_json(audit_path)
    gaps = pd.read_csv(gap_path)
    monthly = pd.read_csv(monthly_path)
    normalized_audit = normalize_audit_result(cast(dict[str, object], audit))
    audit_content_checksum = _stable_digest(normalized_audit)
    gap_checksum = sha256_file(gap_path)
    monthly_checksum = sha256_file(monthly_path)
    if audit_content_checksum != config.coverage.required_audit_result_content_sha256:
        raise ValueError("Task 02 audit content fingerprint is stale")
    if gap_checksum != config.coverage.required_audit_gap_table_sha256:
        raise ValueError("Task 02 gap artifact fingerprint is stale")
    if monthly_checksum != config.coverage.required_audit_monthly_table_sha256:
        raise ValueError("Task 02 monthly artifact fingerprint is stale")
    _validate_audit_contract(audit, manifest, gaps, monthly, config)
    raw_timestamps = pd.read_csv(
        raw_path,
        usecols=[config.data.timestamp_column],
        dtype={config.data.timestamp_column: "string"},
    )[config.data.timestamp_column]
    if len(raw_timestamps) != manifest.row_count:
        raise ValueError("Raw row count changed after the Task 02 audit")
    checksum_after = sha256_file(raw_path)
    if checksum_after != checksum_before:
        raise RuntimeError("Raw dataset changed during coverage generation")
    raw_stat_after = raw_path.stat()
    if (
        raw_stat_before.st_size,
        raw_stat_before.st_mtime_ns,
    ) != (
        raw_stat_after.st_size,
        raw_stat_after.st_mtime_ns,
    ):
        raise RuntimeError("Raw dataset metadata changed during coverage generation")
    return (
        manifest,
        audit,
        gaps,
        monthly,
        raw_timestamps,
        checksum_before,
        gap_checksum,
        monthly_checksum,
    )


def _flag_counts(frame: pd.DataFrame) -> list[dict[str, object]]:
    total = len(frame)
    records: list[dict[str, object]] = []
    for flag in FLAG_COLUMNS:
        true_count = int(frame[flag].sum())
        records.append(
            {
                "flag": flag,
                "rule_id": RULES[flag].rule_id,
                "true_count": true_count,
                "false_count": total - true_count,
                "true_percentage": (true_count / total * 100.0 if total else 0.0),
            }
        )
    return records


def _profile_records(
    flags_by_level: dict[str, pd.DataFrame],
    profile_masks: dict[str, pd.DataFrame],
    config: CoverageConfig,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for profile_name, profile in config.profiles.items():
        for level in LEVELS:
            mask = profile_masks[level][profile_name]
            total = len(mask)
            included = int(mask.sum())
            records.append(
                {
                    "profile": profile_name,
                    "description": profile.description,
                    "level": level,
                    "total_units": total,
                    "included_units": included,
                    "excluded_units": total - included,
                    "included_percentage": (included / total * 100.0 if total else 0.0),
                    "require_all": "|".join(profile.require_all),
                    "require_any": "|".join(profile.require_any),
                    "exclude_any": "|".join(profile.exclude_any),
                }
            )
    return records


def _sensitivity_breakdown(row_flags: pd.DataFrame) -> dict[str, object]:
    reason_count = row_flags[list(SENSITIVITY_FLAGS)].sum(axis=1)
    rule_counts = []
    for flag in SENSITIVITY_FLAGS:
        affected = row_flags[flag]
        rule_counts.append(
            {
                "flag": flag,
                "rule_id": RULES[flag].rule_id,
                "row_count": int(affected.sum()),
                "unique_only_row_count": int((affected & reason_count.eq(1)).sum()),
            }
        )
    combinations = (
        row_flags.loc[
            row_flags["requires_sensitivity_analysis"], list(SENSITIVITY_FLAGS)
        ]
        .value_counts(sort=False)
        .reset_index(name="row_count")
    )
    combination_records = []
    for _, record in combinations.iterrows():
        flags = [flag for flag in SENSITIVITY_FLAGS if bool(record[flag])]
        combination_records.append(
            {
                "flags": "|".join(flags),
                "row_count": int(record["row_count"]),
            }
        )
    combination_records.sort(key=lambda item: str(item["flags"]))
    union_count = int(row_flags["requires_sensitivity_analysis"].sum())
    if sum(cast(int, item["row_count"]) for item in combination_records) != union_count:
        raise RuntimeError("Sensitivity combination counts do not reconcile")
    return {
        "union_row_count": union_count,
        "contributing_rules": rule_counts,
        "mutually_exclusive_combinations": combination_records,
    }


def _build_summary(
    lineage: CoverageLineage,
    flags_by_level: dict[str, pd.DataFrame],
    profile_masks: dict[str, pd.DataFrame],
    config: CoverageConfig,
    audit: dict[str, Any],
) -> dict[str, Any]:
    row_flags = flags_by_level["row"]
    return {
        "method": {
            "method_id": config.method_id,
            "method_version": config.method_version,
            "purpose": "reversible research coverage and eligibility metadata",
            "does_not_clean_or_repair_raw_data": True,
        },
        "lineage": lineage.to_dict(),
        "task_02_relationship": {
            "consumes_registered_audit_artifacts": True,
            "duplicates_audit_logic": False,
            "audit_readiness": audit["final_readiness_assessment"]["state"],
        },
        "level_semantics": {
            "row": "one observed raw CSV row; physical row number is retained",
            "date": (
                "one UTC date with observations; all-rules require every row and "
                "any-rules require at least one row"
            ),
            "month": (
                "one UTC month with observations; propagated from its observed rows"
            ),
            "year": "one UTC year with observations; propagated from its observed rows",
            "dataset": (
                "the registered dataset; all-rules require every row and any-rules "
                "require at least one row"
            ),
        },
        "rule_registry": serialized_rule_registry(),
        "continuity_impaired_months": audit["partial_period_results"][
            "continuity_impaired_months"
        ],
        "affected_period_2023": audit["continuity_investigation_2023"][
            "concentrated_2023_period"
        ],
        "eligibility_status_counts": {
            str(key): int(value)
            for key, value in row_flags["eligibility_status"]
            .value_counts(sort=False)
            .sort_index()
            .items()
        },
        "sensitivity_analysis": _sensitivity_breakdown(row_flags),
        "flag_counts_by_level": {
            level: _flag_counts(frame) for level, frame in flags_by_level.items()
        },
        "coverage_profiles": _profile_records(flags_by_level, profile_masks, config),
    }


def build_coverage(
    *,
    root: Path,
    config: ResearchConfig,
    repository_version: str | None = None,
) -> CoverageResult:
    """Build all coverage flags and masks without writing outputs."""
    (
        manifest,
        audit,
        gaps,
        monthly,
        raw_timestamps,
        checksum,
        gap_checksum,
        monthly_checksum,
    ) = _load_evidence(root, config)
    normalized_audit = normalize_audit_result(cast(dict[str, object], audit))
    lineage = CoverageLineage(
        dataset_logical_name=manifest.logical_dataset_name,
        dataset_version=manifest.dataset_version,
        raw_sha256=checksum,
        audit_method_version=str(audit["audit_metadata"]["audit_method_version"]),
        audit_result_content_sha256=_stable_digest(normalized_audit),
        audit_result_path=config.coverage.audit_result_path.as_posix(),
        audit_gap_table_sha256=gap_checksum,
        audit_gap_table_path=config.coverage.audit_gap_table_path.as_posix(),
        audit_monthly_table_sha256=monthly_checksum,
        audit_monthly_table_path=config.coverage.audit_monthly_table_path.as_posix(),
        coverage_method_id=config.coverage.method_id,
        coverage_method_version=config.coverage.method_version,
        coverage_config_sha256=_coverage_config_digest(config.coverage),
        repository_version=repository_version
        or _repository_version(
            root, ignored_generated_paths=(config.coverage.output_directory,)
        ),
    )
    row_flags = build_row_flags(raw_timestamps, audit, gaps, monthly, lineage)
    flags_by_level = {
        level: aggregate_flags(row_flags, level, lineage) for level in LEVELS
    }
    validate_canonical_profile_algebra(config.coverage.profiles)
    profile_masks = build_profile_masks(flags_by_level, config.coverage.profiles)
    summary = _build_summary(
        lineage, flags_by_level, profile_masks, config.coverage, audit
    )
    return CoverageResult(lineage, flags_by_level, profile_masks, summary)


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _atomic_csv(path: Path, records: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    pd.DataFrame.from_records(records).to_csv(
        temporary, index=False, lineterminator="\n", float_format="%.12g"
    )
    temporary.replace(path)


def render_coverage_markdown(summary: dict[str, Any]) -> str:
    """Render the concise coverage report solely from computed metadata."""
    lineage = summary["lineage"]
    statuses = summary["eligibility_status_counts"]
    affected = summary["affected_period_2023"]
    profile_rows = [
        row for row in summary["coverage_profiles"] if row["level"] == "row"
    ]
    lines = [
        "# Research Coverage and Eligibility Framework",
        "",
        "## Scope",
        "",
        "This framework assigns reversible descriptive eligibility metadata. It "
        "does not clean, repair, delete, or reorder raw observations and does not "
        "perform market-behaviour analysis.",
        "",
        "## Lineage",
        "",
        f"- Dataset version: `{lineage['dataset_version']}`",
        f"- Raw SHA-256: `{lineage['raw_sha256']}`",
        f"- Task 02 audit method: `{lineage['audit_method_version']}`",
        "- Normalized Task 02 result fingerprint: "
        f"`{lineage['audit_result_content_sha256']}`",
        f"- Task 02 gap-table fingerprint: `{lineage['audit_gap_table_sha256']}`",
        "- Task 02 monthly-table fingerprint: "
        f"`{lineage['audit_monthly_table_sha256']}`",
        f"- Coverage method: `{lineage['coverage_method_id']}` "
        f"(`{lineage['coverage_method_version']}`)",
        f"- Repository version: `{lineage['repository_version']}`",
        "",
        "## Eligibility summary",
        "",
    ]
    lines.extend(f"- `{name}`: {count:,} rows" for name, count in statuses.items())
    lines.extend(
        [
            "",
            "Coverage warnings do not make an otherwise valid row ineligible under "
            "`DEFAULT_RESEARCH`; they mark it for sensitivity analysis.",
            "",
            "## Task 02 continuity evidence",
            "",
            "- Continuity-impaired UTC months: "
            + ", ".join(summary["continuity_impaired_months"]),
            "- Audited concentrated-2023 inclusive bounds: "
            f"{affected['first_timestamp_before']} through "
            f"{affected['last_timestamp_after']}.",
            "",
            "## Sensitivity population",
            "",
            "The sensitivity population is the union of the following rules; "
            "counts overlap and therefore do not add arithmetically:",
            "",
        ]
    )
    lines.extend(
        f"- `{item['flag']}` ({item['rule_id']}): {item['row_count']:,} rows; "
        f"{item['unique_only_row_count']:,} rows have only this condition"
        for item in summary["sensitivity_analysis"]["contributing_rules"]
    )
    lines.extend(
        [
            "",
            "Mutually exclusive rule combinations and the union total are retained "
            "in `coverage_summary.json` for exact reconciliation.",
            "",
            "## Coverage profiles",
            "",
            "| Profile | Included rows | Excluded rows | Included % |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in profile_rows:
        lines.append(
            f"| {row['profile']} | {row['included_units']:,} | "
            f"{row['excluded_units']:,} | {row['included_percentage']:.6f} |"
        )
    lines.extend(
        [
            "",
            "Profile exclusions are masks, not deletions. The same registered rows "
            "remain available through `FULL_DATASET` and sensitivity profiles.",
            "",
            "## Level semantics",
            "",
        ]
    )
    lines.extend(
        f"- **{level}:** {description}"
        for level, description in summary["level_semantics"].items()
    )
    lines.extend(
        [
            "",
            "The CSV outputs contain aggregate flag and profile counts only; the "
            "package API builds the row/date/month/year/dataset masks on demand.",
            "",
        ]
    )
    return "\n".join(lines)


def write_coverage_outputs(result: CoverageResult, output_directory: Path) -> None:
    """Write deterministic, bounded coverage summaries and count tables."""
    output_directory.mkdir(parents=True, exist_ok=True)
    _atomic_text(
        output_directory / "coverage_summary.json",
        json.dumps(result.summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    _atomic_text(
        output_directory / "coverage_summary.md",
        render_coverage_markdown(result.summary),
    )
    for level in ("row", "date", "month"):
        _atomic_csv(
            output_directory / f"{level}_flag_counts.csv",
            _flag_counts(result.flags_by_level[level]),
        )
    _atomic_csv(
        output_directory / "coverage_profiles.csv",
        cast(list[dict[str, object]], result.summary["coverage_profiles"]),
    )


def generate_coverage(
    root: Path | None = None, output_directory: Path | None = None
) -> CoverageResult:
    """Build and write configured coverage outputs."""
    repository_root = (root or find_repository_root()).resolve()
    config = load_config(repository_root)
    result = build_coverage(root=repository_root, config=config)
    destination = output_directory or project_path(
        config.coverage.output_directory, repository_root
    )
    write_coverage_outputs(result, destination)
    return result
