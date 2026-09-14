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
from pydantic import ConfigDict, Field, model_validator

from eurusd_research.config import ResearchConfig, StrictModel
from eurusd_research.data.registry import sha256_file
from eurusd_research.research.models import CoverageResult

SOURCE_MANIFEST_SCHEMA_VERSION = "task04-source-dependency-manifest-v1"
TASK03_EVIDENCE_SCHEMA_VERSION = "task03-layered-evidence-v1"
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
    file_type: Literal["python", "toml", "yaml", "json", "makefile"]
    executable: bool
    role: Literal[
        "package_source",
        "task_script",
        "package_contract",
        "runtime_configuration",
        "environment_lock",
        "validation_test",
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


class Task03ScientificMembershipIdentity(StrictModel):
    """Stable scientific population identity required before Task 04 calculation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["task03-scientific-membership-v1"]
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_row_count: int = Field(gt=0)
    observed_date_count: int = Field(gt=0)
    task03_method_id: str = Field(min_length=1)
    task03_method_version: str = Field(min_length=1)
    coverage_schema_version: str = Field(min_length=1)
    stable_lineage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    boundary_classification_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profiles: tuple[Task03ProfileEvidence, ...] = Field(min_length=4, max_length=4)
    strict_subset_default: bool
    strict_disjoint_sensitivity_full: bool
    strict_union_sensitivity_full_equals_default: bool
    sensitivity_2023_subset_sensitivity_full: bool
    scientific_membership_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Task03ScientificMembershipIdentity:
        value = self.model_dump(mode="json")
        fingerprint = cast(str, value.pop("scientific_membership_fingerprint"))
        if canonical_digest(value) != fingerprint:
            raise ValueError("Task 03 scientific-membership fingerprint is invalid")
        return self


class Task03StableArtifactIdentity(StrictModel):
    """Canonical Task 03 artifacts after explicitly registered normalization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["task03-stable-artifact-v1"]
    normalization_policy: Literal[
        "CANONICAL_CONTENT_EXCLUDING_REGISTERED_EXECUTION_CONTEXT"
    ]
    output_inventory: tuple[str, ...] = Field(min_length=1)
    stable_output_sha256: Mapping[str, str]
    stable_artifact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Task03StableArtifactIdentity:
        paths = tuple(self.stable_output_sha256)
        if self.output_inventory != tuple(sorted(self.output_inventory)):
            raise ValueError("Task 03 stable-artifact inventory must be sorted")
        if paths != self.output_inventory:
            raise ValueError("Task 03 stable-artifact hashes must match inventory")
        value = self.model_dump(mode="json")
        fingerprint = cast(str, value.pop("stable_artifact_fingerprint"))
        if canonical_digest(value) != fingerprint:
            raise ValueError("Task 03 stable-artifact fingerprint is invalid")
        return self


class Task03ExecutionContextIdentity(StrictModel):
    """Auditable repository and raw artifact context, not population identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["task03-execution-context-v1"]
    repository_version: str = Field(min_length=1)
    context_variance_policy: Literal[
        "INFORMATIONAL_IF_SCIENTIFIC_AND_STABLE_ARTIFACT_IDENTITIES_MATCH"
    ]
    raw_output_sha256: Mapping[str, str]
    execution_context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Task03ExecutionContextIdentity:
        value = self.model_dump(mode="json")
        fingerprint = cast(str, value.pop("execution_context_fingerprint"))
        if canonical_digest(value) != fingerprint:
            raise ValueError("Task 03 execution-context fingerprint is invalid")
        return self


class Task03RowMembershipEvidence(StrictModel):
    """Layered Task 03 evidence consumed by Task 04 v2.11."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["task03-layered-evidence-v1"]
    architecture: Literal["DESIGN_B_REBUILD_AND_RECONCILE_EXACTLY"]
    scientific_membership: Task03ScientificMembershipIdentity
    stable_artifacts: Task03StableArtifactIdentity
    execution_context: Task03ExecutionContextIdentity
    evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Task03RowMembershipEvidence:
        value = self.model_dump(mode="json")
        fingerprint = cast(str, value.pop("evidence_fingerprint"))
        if canonical_digest(value) != fingerprint:
            raise ValueError("Task 03 layered-evidence fingerprint is invalid")
        return self

    @property
    def profiles(self) -> tuple[Task03ProfileEvidence, ...]:
        return self.scientific_membership.profiles

    @property
    def observed_row_count(self) -> int:
        return self.scientific_membership.observed_row_count

    @property
    def observed_date_count(self) -> int:
        return self.scientific_membership.observed_date_count

    @property
    def task03_method_version(self) -> str:
        return self.scientific_membership.task03_method_version

    @property
    def scientific_membership_fingerprint(self) -> str:
        return self.scientific_membership.scientific_membership_fingerprint

    @property
    def stable_artifact_fingerprint(self) -> str:
        return self.stable_artifacts.stable_artifact_fingerprint

    @property
    def execution_context_fingerprint(self) -> str:
        return self.execution_context.execution_context_fingerprint


def _source_scope(root: Path) -> list[tuple[Path, bool, str]]:
    files: list[tuple[Path, bool, str]] = []
    for path in sorted((root / "src" / "eurusd_research").rglob("*.py")):
        files.append((path, True, "package_source"))
    for path in sorted((root / "scripts").glob("*.py")):
        files.append((path, True, "task_script"))
    for path in sorted((root / "tests").rglob("*.py")):
        files.append((path, True, "validation_test"))
    files.append((root / "Makefile", False, "package_contract"))
    files.append((root / "pyproject.toml", False, "package_contract"))
    for name in ("project.yaml", "data.yaml", "coverage.yaml", "sessions.yaml"):
        files.append((root / "configs" / name, False, "runtime_configuration"))
    files.append(
        (
            root / "studies" / "task04_v2.11_environment_lock.json",
            False,
            "environment_lock",
        )
    )
    return files


def _file_type(path: Path) -> Literal["python", "toml", "yaml", "json", "makefile"]:
    types = {
        ".py": "python",
        ".toml": "toml",
        ".yaml": "yaml",
        ".json": "json",
    }
    try:
        if path.name == "Makefile":
            return "makefile"
        return cast(
            Literal["python", "toml", "yaml", "json", "makefile"],
            types[path.suffix.lower()],
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
            "All Python files under src/eurusd_research, scripts, and tests; the "
            "Makefile; pyproject.toml; project/data/coverage/session runtime "
            "configuration; and the exact "
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
    path = root / "studies" / "task04_v2.11_source_manifest.json"
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


def stable_coverage_artifact_sha256(path: Path) -> str:
    """Hash scientific artifact content after narrowly registered normalization."""
    if path.name == "coverage_summary.json":
        value = json.loads(path.read_text(encoding="utf-8"))
        lineage = value.get("lineage")
        if not isinstance(lineage, dict) or "repository_version" not in lineage:
            raise ValueError("Task 03 summary lacks registered repository context")
        lineage = dict(lineage)
        lineage.pop("repository_version")
        value = {**value, "lineage": lineage}
        return canonical_digest(value)
    if path.name == "coverage_summary.md":
        lines = path.read_text(encoding="utf-8").splitlines()
        normalized = [
            "- Repository version: `<EXECUTION_CONTEXT>`"
            if line.startswith("- Repository version: ")
            else line
            for line in lines
        ]
        return hashlib.sha256(("\n".join(normalized) + "\n").encode()).hexdigest()
    return sha256_file(path)


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
    scientific_payload: dict[str, Any] = {
        "schema_version": "task03-scientific-membership-v1",
        "raw_sha256": coverage.lineage.raw_sha256,
        "observed_row_count": len(row_flags),
        "observed_date_count": len(date_flags),
        "task03_method_id": coverage.lineage.coverage_method_id,
        "task03_method_version": coverage.lineage.coverage_method_version,
        "coverage_schema_version": "research-coverage-artifacts-v1",
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
    }
    scientific = Task03ScientificMembershipIdentity.model_validate(
        {
            **scientific_payload,
            "scientific_membership_fingerprint": canonical_digest(scientific_payload),
        }
    )
    output_inventory = tuple(output_fingerprints)
    stable_output_sha256 = {
        path.relative_to(root).as_posix(): stable_coverage_artifact_sha256(path)
        for path in output_paths
    }
    stable_payload: dict[str, Any] = {
        "schema_version": "task03-stable-artifact-v1",
        "normalization_policy": (
            "CANONICAL_CONTENT_EXCLUDING_REGISTERED_EXECUTION_CONTEXT"
        ),
        "output_inventory": output_inventory,
        "stable_output_sha256": stable_output_sha256,
    }
    stable = Task03StableArtifactIdentity.model_validate(
        {
            **stable_payload,
            "stable_artifact_fingerprint": canonical_digest(stable_payload),
        }
    )
    context_payload: dict[str, Any] = {
        "schema_version": "task03-execution-context-v1",
        "repository_version": coverage.lineage.repository_version,
        "context_variance_policy": (
            "INFORMATIONAL_IF_SCIENTIFIC_AND_STABLE_ARTIFACT_IDENTITIES_MATCH"
        ),
        "raw_output_sha256": output_fingerprints,
    }
    context = Task03ExecutionContextIdentity.model_validate(
        {
            **context_payload,
            "execution_context_fingerprint": canonical_digest(context_payload),
        }
    )
    payload: dict[str, Any] = {
        "schema_version": TASK03_EVIDENCE_SCHEMA_VERSION,
        "architecture": "DESIGN_B_REBUILD_AND_RECONCILE_EXACTLY",
        "scientific_membership": scientific.model_dump(mode="json"),
        "stable_artifacts": stable.model_dump(mode="json"),
        "execution_context": context.model_dump(mode="json"),
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
    expected_scientific_fingerprint: str,
    expected_stable_artifact_fingerprint: str,
) -> Task03RowMembershipEvidence:
    """Fail unless live scientific and stable artifact identities are pinned."""
    path = root / "studies" / "task03_task04_v2.11_evidence.json"
    saved = read_task03_row_membership_evidence(path)
    if saved.scientific_membership_fingerprint != expected_scientific_fingerprint:
        raise ValueError("Task 03 scientific-membership identity is not registered")
    if saved.stable_artifact_fingerprint != expected_stable_artifact_fingerprint:
        raise ValueError("Task 03 stable-artifact identity is not registered")
    current = build_task03_row_membership_evidence(root, coverage, config)
    if current.scientific_membership != saved.scientific_membership:
        raise ValueError("Live Task 03 scientific membership disagrees with evidence")
    if current.stable_artifacts != saved.stable_artifacts:
        raise ValueError("Live Task 03 stable artifacts disagree with evidence")
    return current


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
