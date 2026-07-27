from __future__ import annotations

from pathlib import Path

import pytest

from eurusd_research.paths import find_repository_root, project_path


def test_repository_root_from_nested_path(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "configs").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_repository_root(nested) == tmp_path


def test_repository_root_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Could not find"):
        find_repository_root(tmp_path)


def test_project_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        project_path("../outside", tmp_path)
