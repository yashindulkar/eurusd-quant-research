"""Independent filesystem inventory reconciliation for Task 04."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class InventoryRecord:
    """Independently inspected identity and safety attributes of one file."""

    relative_path: str
    size_bytes: int
    sha256: str
    regular_file: bool
    symbolic_link: bool
    hard_link_count: int
    resolved_contained: bool


@dataclass(frozen=True, slots=True)
class InventoryInspection:
    """Calculated inventory reconciliation; no asserted pass field."""

    expected_paths: tuple[str, ...]
    present_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]
    extra_paths: tuple[str, ...]
    duplicate_normalized_paths: tuple[str, ...]
    unsafe_paths: tuple[str, ...]
    records: tuple[InventoryRecord, ...]
    path_plus_bytes_digest: str

    @property
    def reconciled(self) -> bool:
        return not (
            self.missing_paths
            or self.extra_paths
            or self.duplicate_normalized_paths
            or self.unsafe_paths
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_output_inventory(
    root: Path, expected_paths: tuple[str, ...]
) -> InventoryInspection:
    """Inspect exact paths, types, containment, hashes, and canonical digest."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Independent inventory root must be a real directory")
    canonical_root = root.resolve(strict=True)
    normalized = tuple(Path(item).as_posix() for item in expected_paths)
    duplicate_normalized = tuple(
        sorted({item for item in normalized if normalized.count(item) > 1})
    )
    present = tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if not path.is_dir()
        )
    )
    expected = tuple(sorted(expected_paths))
    missing = tuple(sorted(set(expected).difference(present)))
    extra = tuple(sorted(set(present).difference(expected)))
    records: list[InventoryRecord] = []
    unsafe: list[str] = []
    aggregate = hashlib.sha256()
    for relative in present:
        path = root / relative
        lexical_safe = (
            not Path(relative).is_absolute()
            and ".." not in Path(relative).parts
            and "\\" not in relative
        )
        link = path.is_symlink() or any(
            parent.is_symlink() for parent in path.parents if parent != root.parent
        )
        try:
            resolved = path.resolve(strict=True)
            contained = resolved.is_relative_to(canonical_root)
            metadata = os.lstat(path)
            regular = stat.S_ISREG(metadata.st_mode)
            links = int(metadata.st_nlink)
        except (FileNotFoundError, OSError):
            contained, regular, links = False, False, 0
        if not lexical_safe or link or not contained or not regular or links != 1:
            unsafe.append(relative)
        if not regular or link:
            continue
        size = path.stat().st_size
        file_hash = _sha256(path)
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(str(size).encode("ascii"))
        aggregate.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                aggregate.update(chunk)
        aggregate.update(b"\0")
        records.append(
            InventoryRecord(relative, size, file_hash, regular, link, links, contained)
        )
    return InventoryInspection(
        expected_paths=expected,
        present_paths=present,
        missing_paths=missing,
        extra_paths=extra,
        duplicate_normalized_paths=duplicate_normalized,
        unsafe_paths=tuple(sorted(unsafe)),
        records=tuple(records),
        path_plus_bytes_digest=aggregate.hexdigest(),
    )
