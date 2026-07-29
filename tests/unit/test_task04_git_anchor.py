from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from eurusd_research.studies.git_anchor import (
    assert_anchor_lineage,
    assert_registered_worktree_matches_anchor,
    commit_tree_id,
    file_sha256,
    is_ancestor,
    registered_path_tree_fingerprint,
    resolve_commit,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Task 04 Tests",
        "-c",
        "user.email=task04@example.invalid",
        "commit",
        "-m",
        message,
    )
    return resolve_commit(root)


@pytest.fixture
def anchored_repository(tmp_path: Path) -> tuple[Path, str, tuple[str, ...]]:
    _git(tmp_path, "init", "-q")
    (tmp_path / "registered.txt").write_text("locked\n", encoding="utf-8")
    (tmp_path / "documentation.md").write_text("v1\n", encoding="utf-8")
    anchor = _commit(tmp_path, "preregistration anchor")
    return tmp_path, anchor, ("registered.txt",)


def _assert_valid(root: Path, anchor: str, paths: tuple[str, ...]) -> None:
    assert_anchor_lineage(
        root,
        anchor_commit=anchor,
        anchor_tree=commit_tree_id(root, anchor),
        paths=paths,
        registered_tree_fingerprint=registered_path_tree_fingerprint(
            root, anchor, paths
        ),
    )


def test_anchor_and_documentation_only_descendant_are_accepted(
    anchored_repository: tuple[Path, str, tuple[str, ...]],
) -> None:
    root, anchor, paths = anchored_repository
    _assert_valid(root, anchor, paths)
    (root / "documentation.md").write_text("v2\n", encoding="utf-8")
    descendant = _commit(root, "documentation-only descendant")
    assert descendant != anchor
    assert is_ancestor(root, anchor, descendant)
    expected = hashlib.sha256((root / "registered.txt").read_bytes()).hexdigest()
    assert file_sha256(root / "registered.txt") == expected
    _assert_valid(root, anchor, paths)


def test_unrelated_history_and_missing_anchor_are_rejected(
    anchored_repository: tuple[Path, str, tuple[str, ...]],
) -> None:
    root, anchor, paths = anchored_repository
    _git(root, "switch", "--orphan", "unrelated")
    (root / "registered.txt").write_text("locked\n", encoding="utf-8")
    _commit(root, "unrelated root")
    assert not is_ancestor(root, anchor)
    with pytest.raises(ValueError, match="does not descend"):
        _assert_valid(root, anchor, paths)
    with pytest.raises(ValueError, match="missing"):
        assert_anchor_lineage(
            root,
            anchor_commit="f" * 40,
            anchor_tree="e" * 40,
            paths=paths,
            registered_tree_fingerprint="d" * 64,
        )


def test_registered_mutation_and_untracked_registered_path_are_rejected(
    anchored_repository: tuple[Path, str, tuple[str, ...]],
) -> None:
    root, anchor, paths = anchored_repository
    (root / "registered.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from anchor"):
        assert_registered_worktree_matches_anchor(root, anchor, paths)
    (root / "registered.txt").write_text("locked\n", encoding="utf-8")
    (root / "untracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="absent"):
        registered_path_tree_fingerprint(root, anchor, (*paths, "untracked.py"))


def test_irrelevant_dirty_path_is_permitted_by_registered_path_policy(
    anchored_repository: tuple[Path, str, tuple[str, ...]],
) -> None:
    root, anchor, paths = anchored_repository
    (root / "notes.tmp").write_text("irrelevant dirt\n", encoding="utf-8")
    _assert_valid(root, anchor, paths)


def test_replacement_design_creates_distinguishable_anchor_lineage(
    anchored_repository: tuple[Path, str, tuple[str, ...]],
) -> None:
    root, original_anchor, paths = anchored_repository
    original_tree = registered_path_tree_fingerprint(root, original_anchor, paths)
    (root / "registered.txt").write_text("replacement design\n", encoding="utf-8")
    replacement_anchor = _commit(root, "replacement design anchor")
    replacement_tree = registered_path_tree_fingerprint(root, replacement_anchor, paths)
    assert replacement_anchor != original_anchor
    assert replacement_tree != original_tree
    with pytest.raises(ValueError, match="differs from anchor"):
        assert_registered_worktree_matches_anchor(root, original_anchor, paths)
    _assert_valid(root, replacement_anchor, paths)
