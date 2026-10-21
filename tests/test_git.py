"""Hermetic tests for the Git helper — throwaway local repos, no network.

A bare repo serves as the "remote" (local-protocol clone, no auth); every git
subprocess inherits a git identity set at module import via ``os.environ.setdefault``
so commits work in any container environment.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from agentic_scripts.git import Git, GitError

# Git identity for every subprocess spawned by these tests (set at import so it is
# present before the first commit; setdefault never clobbers a real environment).
os.environ.setdefault("GIT_AUTHOR_NAME", "Test Author")
os.environ.setdefault("GIT_AUTHOR_EMAIL", "author@example.test")
os.environ.setdefault("GIT_COMMITTER_NAME", "Test Committer")
os.environ.setdefault("GIT_COMMITTER_EMAIL", "committer@example.test")


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a raw git command in ``path`` (test setup helper)."""
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    )


def init_repo(path: Path, branch: str = "main") -> Path:
    """Initialize a repo with one commit on ``branch``; return the commit SHA.

    Args:
        path: Directory to initialize (created if missing).
        branch: Initial branch name.

    Returns:
        The full SHA of the first commit.
    """
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", branch)
    (path / "file.txt").write_text("initial\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "initial commit")
    return _git(path, "rev-parse", "HEAD").stdout.strip()


def init_bare(path: Path, head_branch: str = "main") -> None:
    """Initialize a bare repo to act as the local "remote".

    Args:
        path: Directory for the bare repository (created if missing).
        head_branch: Branch the bare repo's HEAD symref points at; must match the
            branch pushed into it, otherwise ``git clone`` cannot check out a branch.
    """
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--bare")
    _git(path, "symbolic-ref", "HEAD", f"refs/heads/{head_branch}")


@pytest.fixture
def git() -> Git:
    """A fresh stateless Git helper."""
    return Git()


@pytest.fixture
def remote_and_clone(tmp_path: Path) -> tuple[Path, Path, str]:
    """Build a bare remote with one commit on main and a full clone of it.

    Returns:
        Tuple of (bare_remote_path, clone_path, source_sha).
    """
    src = init_repo(tmp_path / "src", branch="main")
    bare = tmp_path / "remote.git"
    init_bare(bare)
    _git(tmp_path / "src", "remote", "add", "origin", str(bare))
    _git(tmp_path / "src", "push", "-u", "origin", "main")

    clone = tmp_path / "clone"
    Git().clone(str(bare), clone)
    return bare, clone, src


def _drop_origin_head(path: Path) -> None:
    """Delete the origin/HEAD symref a local clone creates (spurious in branches()).

    Cloning a local bare repo writes ``.git/refs/remotes/origin/HEAD``; for-each-ref
    then lists it as a spurious branch named ``origin``. Real origins don't expose this,
    so the test drops it to keep the remote view clean.

    Args:
        path: A path inside the clone.
    """
    subprocess.run(
        ["git", "-C", str(path), "remote", "set-head", "-d", "origin"],
        capture_output=True,
        text=True,
    )


def test_is_repo_true_false(
    git: Git, remote_and_clone: tuple[Path, Path, str], tmp_path: Path
) -> None:
    """is_repo is True inside a repo and False in a plain directory."""
    _, clone, _ = remote_and_clone
    assert git.is_repo(clone) is True
    assert git.is_repo(tmp_path / "not_a_repo") is False


def test_clone_branch_revparse_depth(
    git: Git, remote_and_clone: tuple[Path, Path, str], tmp_path: Path
) -> None:
    """Clone checks out main at the source SHA; depth=1 clone also works."""
    bare, clone, src_sha = remote_and_clone
    assert git.current_branch(clone) == "main"
    assert git.rev_parse(clone, "HEAD") == src_sha

    shallow = tmp_path / "shallow"
    git.clone(str(bare), shallow, depth=1)
    assert git.current_branch(shallow) == "main"
    assert git.rev_parse(shallow, "HEAD") == src_sha


def test_push_new_branch_and_commit_idempotent(
    git: Git, remote_and_clone: tuple[Path, Path, str], tmp_path: Path
) -> None:
    """Push a new branch; branches() sees it after fetch; empty commit returns False."""
    bare, clone, _ = remote_and_clone

    (clone / "new.txt").write_text("branch work\n", encoding="utf-8")
    git.add(clone, ["new.txt"])
    assert git.commit(clone, "add new.txt") is True
    _git(clone, "checkout", "-b", "feature/x")  # local branch to push (spec: push <branch>)
    git.push(clone, "feature/x", upstream=True)

    fresh = tmp_path / "fresh"
    git.clone(str(bare), fresh)
    _drop_origin_head(fresh)  # local clones create an origin/HEAD symref; drop it
    git.fetch(fresh)
    assert git.branches(fresh) == ["feature/x", "main"]

    # Idempotency: a second commit with no changes returns False, not an error.
    assert git.commit(clone, "should be a no-op") is False


def test_worktree_add_remove(
    git: Git, remote_and_clone: tuple[Path, Path, str], tmp_path: Path
) -> None:
    """worktree_add creates feature/x at the current ref; remove cleans up."""
    _, clone, _ = remote_and_clone

    wt = tmp_path / "wt"
    git.worktree_add(clone, wt, "feature/x", "HEAD")
    assert wt.is_dir()
    assert git.current_branch(wt) == "feature/x"

    git.worktree_remove(clone, wt)
    assert not wt.exists()

    with pytest.raises(GitError):
        git.worktree_remove(clone, wt)  # second removal fails


def test_rev_parse_bad_ref_raises(git: Git, remote_and_clone: tuple[Path, Path, str]) -> None:
    """A bad ref raises GitError whose message contains 'failed (exit'."""
    _, clone, _ = remote_and_clone
    with pytest.raises(GitError) as excinfo:
        git.rev_parse(clone, "definitely-not-a-ref")
    assert "failed (exit" in str(excinfo.value)


def test_commit_changes_sha(git: Git, remote_and_clone: tuple[Path, Path, str]) -> None:
    """A commit with staged changes returns True and moves HEAD."""
    _, clone, _ = remote_and_clone
    old_sha = git.rev_parse(clone, "HEAD")

    (clone / "change.txt").write_text("changed\n", encoding="utf-8")
    git.add(clone, ["change.txt"])
    assert git.commit(clone, "change") is True

    new_sha = git.rev_parse(clone, "HEAD")
    assert new_sha != old_sha
