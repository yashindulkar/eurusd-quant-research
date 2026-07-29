"""Pre-result dependency and Task 03 membership controls for Task 04."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd
from pydantic import ConfigDict, Field

from eurusd_research.config import ResearchConfig, StrictModel
from eurusd_research.data.registry import sha256_file
from eurusd_research.research.models import CoverageResult

SOURCE_MANIFEST_SCHEMA_VERSION = "task04-source-dependency-manifest-v1"
TASK03_EVIDENCE_SCHEMA_VERSION = "task03-row-membership-evidence-v1"
ENVIRONMENT_LOCK_SCHEMA_VERSION = "task04-environment-lock-v1"

PROFILE_NAMES = (
    "DEFAULT_RESEARCH",
    "STRICT_CONTINUITY",
    "SENSITIVITY_FULL",
    "SENSITIVITY_2023",
)

_STABLE_LINEAGE_FIELDS = (
    "dataset_logical_name",
    "dataset_version",
    "raw_sha256",
    "audit_method_version",
    "audit_result_content_sha256",
    "audit_gap_table_sha256",
    "audit_monthly_table_sha256",
    "coverage_method_id",
    "coverage_method_version",
    "coverage_config_sha256",
)


def canonical_json(value: object) -> bytes:
    """Return standards-compliant canonical JSON bytes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def canonical_digest(value: object) -> str:
    """Return the SHA-256 of canonical JSON."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


class SourceDependencyEntry(StrictModel):
    """One executable or runtime-contract file in the registered closure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    file_type: Literal["python", "toml", "yaml", "json"]
    executable: bool
    role: Literal[
        "package_source",
        "task_script",
        "package_contract",
        "runtime_configuration",
        "environment_lock",
    ]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SourceDependencyManifest(StrictModel):
    """Deterministic manifest for the complete declared execution closure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["task04-source-dependency-manifest-v1"]
    scope_policy: str = Field(min_length=1)
    entries: tuple[SourceDependencyEntry, ...] = Field(min_length=1)
    source_tree_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class Task03ProfileEvidence(StrictModel):
    """Pinned row and date membership identity for one Task 03 profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: Literal[
        "DEFAULT_RESEARCH",
        "STRICT_CONTINUITY",
        "SENSITIVITY_FULL",
        "SENSITIVITY_2023",
    ]
    row_total: int = Field(gt=0)
    row_included: int = Field(ge=0)
    date_total: int = Field(gt=0)
    date_included: int = Field(ge=0)
    row_membership_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    date_membership_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Task03RowMembershipEvidence(StrictModel):
    """Authoritative Task 03 row-addressable evidence consumed by Task 04."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["task03-row-membership-evidence-v1"]
    architecture: Literal["DESIGN_B_REBUILD_AND_RECONCILE_EXACTLY"]
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_row_count: int = Field(gt=0)
    observed_date_count: int = Field(gt=0)
    task03_method_id: str = Field(min_length=1)
    task03_method_version: str = Field(min_length=1)
    stable_lineage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    boundary_classification_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profiles: tuple[Task03ProfileEvidence, ...] = Field(min_length=4, max_length=4)
    strict_subset_default: bool
    strict_disjoint_sensitivity_full: bool
    strict_union_sensitivity_full_equals_default: bool
    sensitivity_2023_subset_sensitivity_full: bool
    coverage_output_sha256: Mapping[str, str]
    coverage_output_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def _source_scope(root: Path) -> list[tuple[Path, bool, str]]:
    files: list[tuple[Path, bool, str]] = []
    for path in sorted((root / "src" / "eurusd_research").rglob("*.py")):
        files.append((path, True, "package_source"))
    for path in sorted((root / "scripts").glob("*.py")):
        files.append((path, True, "task_script"))
    files.append((root / "pyproject.toml", False, "package_contract"))
    for name in ("project.yaml", "data.yaml", "coverage.yaml", "sessions.yaml"):
        files.append((root / "configs" / name, False, "runtime_configuration"))
    files.append(
        (
            root / "studies" / "task04_v2.3_environment_lock.json",
            False,
            "environment_lock",
        )
    )
    return files


def _file_type(path: Path) -> Literal["python", "toml", "yaml", "json"]:
    types = {
        ".py": "python",
        ".toml": "toml",
        ".yaml": "yaml",
        ".json": "json",
    }
    try:
        return cast(
            Literal["python", "toml", "yaml", "json"], types[path.suffix.lower()]
        )
    except KeyError as error:
        raise ValueError(
            f"Unsupported dependency-manifest file type: {path}"
        ) from error


def build_source_dependency_manifest(root: Path) -> SourceDependencyManifest:
    """Build the declared source closure without calculating Task 04 results."""
    entries: list[dict[str, object]] = []
    for path, executable, role in _source_scope(root):
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"Task 04 dependency is missing or unsafe: {path}")
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "file_type": _file_type(path),
                "executable": executable,
                "role": role,
                "sha256": sha256_file(path),
            }
        )
    entries.sort(key=lambda item: str(item["path"]))
    source_tree = canonical_digest(entries)
    payload = {
        "schema_version": SOURCE_MANIFEST_SCHEMA_VERSION,
        "scope_policy": (
            "All Python files under src/eurusd_research and scripts, pyproject.toml, "
            "project/data/coverage/session runtime configuration, and the exact "
            "Task 04 environment lock. Task 04 executable configuration and "
            "registration are bound separately by the receipt and Git anchor."
        ),
        "entries": entries,
        "source_tree_fingerprint": source_tree,
    }
    return SourceDependencyManifest.model_validate(
        {
            **payload,
            "dependency_manifest_fingerprint": canonical_digest(payload),
        }
    )


def write_json_once(path: Path, value: Mapping[str, object]) -> None:
    """Write deterministic JSON without replacing existing evidence."""
    if path.exists():
        raise FileExistsError(f"Integrity evidence already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_source_dependency_manifest(path: Path) -> SourceDependencyManifest:
    """Read and self-validate the source dependency manifest."""
    value = json.loads(path.read_text(encoding="utf-8"))
    manifest = SourceDependencyManifest.model_validate(value)
    payload = manifest.model_dump(mode="json")
    fingerprint = cast(str, payload.pop("dependency_manifest_fingerprint"))
    if canonical_digest(payload) != fingerprint:
        raise ValueError("Task 04 dependency manifest fingerprint is invalid")
    return manifest


def validate_source_dependency_manifest(
    root: Path, expected_fingerprint: str
) -> SourceDependencyManifest:
    """Require the current complete source scope to match pinned evidence."""
    path = root / "studies" / "task04_v2.3_source_manifest.json"
    saved = read_source_dependency_manifest(path)
    if saved.dependency_manifest_fingerprint != expected_fingerprint:
        raise ValueError("Task 04 dependency manifest identity is not registered")
    current = build_source_dependency_manifest(root)
    if current != saved:
        raise ValueError("Task 04 registered execution dependency closure changed")
    return saved


def _membership_digest(keys: Iterable[object], mask: Iterable[object]) -> str:
    digest = hashlib.sha256()
    for key, included in zip(keys, mask, strict=True):
        digest.update(str(key).encode("utf-8"))
        digest.update(b"|1\n" if bool(included) else b"|0\n")
    return digest.hexdigest()


def _frame_digest(frame: pd.DataFrame, columns: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for values in frame.loc[:, list(columns)].itertuples(index=False, name=None):
        digest.update(("|".join(str(value) for value in values) + "\n").encode("utf-8"))
    return digest.hexdigest()


def _stable_lineage(coverage: CoverageResult) -> dict[str, str]:
    value = coverage.lineage.to_dict()
    return {field: str(value[field]) for field in _STABLE_LINEAGE_FIELDS}


def build_task03_row_membership_evidence(
    root: Path,
    coverage: CoverageResult,
    config: ResearchConfig,
) -> Task03RowMembershipEvidence:
    """Build row-level Task 03 evidence without calculating Task 04 outcomes."""
    row_flags = coverage.flags_by_level["row"]
    date_flags = coverage.flags_by_level["date"]
    row_masks = coverage.profile_masks_by_level["row"]
    date_masks = coverage.profile_masks_by_level["date"]
    profile_records: list[dict[str, object]] = []
    for profile in PROFILE_NAMES:
        profile_records.append(
            {
                "profile": profile,
                "row_total": len(row_masks),
                "row_included": int(row_masks[profile].sum()),
                "date_total": len(date_masks),
                "date_included": int(date_masks[profile].sum()),
                "row_membership_sha256": _membership_digest(
                    row_flags["raw_row_number"], row_masks[profile]
                ),
                "date_membership_sha256": _membership_digest(
                    date_flags["utc_date"], date_masks[profile]
                ),
            }
        )
    default = row_masks["DEFAULT_RESEARCH"]
    strict = row_masks["STRICT_CONTINUITY"]
    sensitivity = row_masks["SENSITIVITY_FULL"]
    sensitivity_2023 = row_masks["SENSITIVITY_2023"]
    coverage_directory = root / "reports" / "coverage"
    output_paths = sorted(
        path
        for path in coverage_directory.iterdir()
        if path.is_file() and not path.is_symlink()
    )
    output_fingerprints = {
        path.relative_to(root).as_posix(): sha256_file(path) for path in output_paths
    }
    boundary_columns = (
        "raw_row_number",
        "weekly_gap_boundary",
        "long_nonweekly_gap_boundary",
        "nonweekend_gap_boundary",
        "unclassified_gap_boundary",
        "continuity_impaired_period",
        "affected_period_2023",
        "partial_boundary_year",
        "partial_boundary_month",
    )
    payload: dict[str, Any] = {
        "schema_version": TASK03_EVIDENCE_SCHEMA_VERSION,
        "architecture": "DESIGN_B_REBUILD_AND_RECONCILE_EXACTLY",
        "raw_sha256": coverage.lineage.raw_sha256,
        "observed_row_count": len(row_flags),
        "observed_date_count": len(date_flags),
        "task03_method_id": coverage.lineage.coverage_method_id,
        "task03_method_version": coverage.lineage.coverage_method_version,
        "stable_lineage_sha256": canonical_digest(_stable_lineage(coverage)),
        "boundary_classification_sha256": _frame_digest(row_flags, boundary_columns),
        "profiles": profile_records,
        "strict_subset_default": bool((strict & ~default).sum() == 0),
        "strict_disjoint_sensitivity_full": bool((strict & sensitivity).sum() == 0),
        "strict_union_sensitivity_full_equals_default": bool(
            (strict | sensitivity).equals(default)
        ),
        "sensitivity_2023_subset_sensitivity_full": bool(
            (sensitivity_2023 & ~sensitivity).sum() == 0
        ),
        "coverage_output_sha256": output_fingerprints,
        "coverage_output_inventory_sha256": canonical_digest(output_fingerprints),
    }
    return Task03RowMembershipEvidence.model_validate(
        {**payload, "evidence_fingerprint": canonical_digest(payload)}
    )


def read_task03_row_membership_evidence(
    path: Path,
) -> Task03RowMembershipEvidence:
    """Read and self-validate pinned Task 03 membership evidence."""
    value = json.loads(path.read_text(encoding="utf-8"))
    evidence = Task03RowMembershipEvidence.model_validate(value)
    payload = evidence.model_dump(mode="json")
    fingerprint = cast(str, payload.pop("evidence_fingerprint"))
    if canonical_digest(payload) != fingerprint:
        raise ValueError("Task 03 row-membership evidence fingerprint is invalid")
    return evidence


def validate_task03_row_membership(
    root: Path,
    coverage: CoverageResult,
    config: ResearchConfig,
    *,
    expected_fingerprint: str,
) -> Task03RowMembershipEvidence:
    """Fail before Task 04 calculation unless live masks match pinned evidence."""
    path = root / "studies" / "task03_task04_v2.3_mask_evidence.json"
    saved = read_task03_row_membership_evidence(path)
    if saved.evidence_fingerprint != expected_fingerprint:
        raise ValueError("Task 03 row-membership evidence identity is not registered")
    current = build_task03_row_membership_evidence(root, coverage, config)
    if current != saved:
        raise ValueError("Live Task 03 row-level masks disagree with pinned evidence")
    return saved


def assert_regular_contained_file(path: Path, root: Path) -> None:
    """Require a non-linked regular file lexically and physically below root."""
    if path.is_symlink():
        raise RuntimeError(f"Symbolic links are forbidden in Task 04 outputs: {path}")
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"Task 04 output escapes its root: {path}") from error
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"Task 04 output path is unsafe: {path}")
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise RuntimeError(
            f"Task 04 output resolves outside its root: {path}"
        ) from error
    current = path
    while current != root:
        if current.is_symlink():
            raise RuntimeError(f"Task 04 output has a symbolic-link parent: {path}")
        current = current.parent
    mode = path.stat(follow_symlinks=False).st_mode
    if not stat.S_ISREG(mode):
        raise RuntimeError(f"Task 04 output is not a regular file: {path}")
    if path.stat(follow_symlinks=False).st_nlink != 1:
        raise RuntimeError(f"Task 04 output has multiple hard links: {path}")
