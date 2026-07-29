"""Git-object anchoring for the Task 04 registered replication."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from eurusd_research.studies.integrity import canonical_digest


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"Git anchor command failed: {' '.join(arguments)}: {detail}")
    return result.stdout.strip()


def resolve_commit(root: Path, reference: str = "HEAD") -> str:
    """Resolve a full commit ID or fail closed."""
    value = _git(root, "rev-parse", "--verify", f"{reference}^{{commit}}")
    if len(value) != 40:
        raise ValueError(f"Git anchor is not a full SHA-1 commit ID: {value}")
    return value


def commit_exists(root: Path, commit: str) -> bool:
    """Return whether the exact commit object remains locally reachable by ID."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def is_ancestor(root: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    """Return whether ancestor is in descendant's Git history."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise ValueError("Git ancestry could not be evaluated")
    return result.returncode == 0


def commit_tree_id(root: Path, commit: str) -> str:
    """Return the immutable tree object for a commit."""
    return _git(root, "rev-parse", "--verify", f"{commit}^{{tree}}")


def _tree_entry(root: Path, commit: str, relative_path: str) -> dict[str, str]:
    output = _git(root, "ls-tree", commit, "--", relative_path)
    if not output:
        raise ValueError(f"Registered anchor path is absent: {relative_path}")
    lines = output.splitlines()
    if len(lines) != 1:
        raise ValueError(f"Registered anchor path is ambiguous: {relative_path}")
    metadata, observed_path = lines[0].split("\t", 1)
    mode, object_type, object_id = metadata.split()
    if observed_path != relative_path or object_type != "blob":
        raise ValueError(f"Registered anchor path is not a file: {relative_path}")
    if mode not in {"100644", "100755"}:
        raise ValueError(
            f"Registered anchor path has unsafe mode {mode}: {relative_path}"
        )
    return {
        "path": relative_path,
        "mode": mode,
        "object_type": object_type,
        "git_blob_id": object_id,
    }


def registered_path_tree_fingerprint(
    root: Path, commit: str, paths: tuple[str, ...]
) -> str:
    """Fingerprint exact registered Git blobs in path order."""
    if len(paths) != len(set(paths)):
        raise ValueError("Registered anchor path inventory contains duplicates")
    entries = [_tree_entry(root, commit, path) for path in sorted(paths)]
    return canonical_digest(entries)


def assert_registered_worktree_matches_anchor(
    root: Path, commit: str, paths: tuple[str, ...]
) -> None:
    """Reject tracked, dirty, missing, linked, or untracked execution changes."""
    for relative_path in sorted(paths):
        expected = _tree_entry(root, commit, relative_path)
        path = root / relative_path
        if not path.is_file() or path.is_symlink():
            raise ValueError(
                f"Registered worktree path is missing or unsafe: {relative_path}"
            )
        observed_blob = _git(root, "hash-object", "--", relative_path)
        if observed_blob != expected["git_blob_id"]:
            raise ValueError(
                f"Registered worktree path differs from anchor: {relative_path}"
            )


def assert_anchor_lineage(
    root: Path,
    *,
    anchor_commit: str,
    anchor_tree: str,
    paths: tuple[str, ...],
    registered_tree_fingerprint: str,
) -> None:
    """Validate object existence, ancestry, tree identity, and worktree state."""
    if not commit_exists(root, anchor_commit):
        raise ValueError("Task 04 preregistration anchor commit is missing")
    if not is_ancestor(root, anchor_commit):
        raise ValueError("Task 04 completion does not descend from its anchor")
    if commit_tree_id(root, anchor_commit) != anchor_tree:
        raise ValueError("Task 04 preregistration anchor tree identity changed")
    if (
        registered_path_tree_fingerprint(root, anchor_commit, paths)
        != registered_tree_fingerprint
    ):
        raise ValueError("Task 04 registered-path tree fingerprint is invalid")
    assert_registered_worktree_matches_anchor(root, anchor_commit, paths)


def file_sha256(path: Path) -> str:
    """Small local helper used by anchor-control tests."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
