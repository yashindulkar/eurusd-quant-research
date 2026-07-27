"""Repository path discovery independent of the process working directory."""

from __future__ import annotations

from pathlib import Path

_ROOT_MARKERS = ("pyproject.toml", "configs")


def find_repository_root(start: Path | None = None) -> Path:
    """Find the nearest ancestor containing the repository markers.

    Args:
        start: File or directory from which to begin. Defaults to this module.

    Raises:
        FileNotFoundError: If no repository root can be found.
    """
    candidate = (start or Path(__file__)).resolve()
    if candidate.is_file():
        candidate = candidate.parent

    for directory in (candidate, *candidate.parents):
        if all((directory / marker).exists() for marker in _ROOT_MARKERS):
            return directory

    raise FileNotFoundError(
        f"Could not find repository root from {candidate}; "
        f"expected markers: {', '.join(_ROOT_MARKERS)}"
    )


def project_path(relative_path: str | Path, root: Path | None = None) -> Path:
    """Resolve a repository-relative path and prevent traversal outside root."""
    repository_root = (root or find_repository_root()).resolve()
    resolved = (repository_root / relative_path).resolve()
    if not resolved.is_relative_to(repository_root):
        raise ValueError(f"Path escapes repository root: {relative_path}")
    return resolved
