"""Thin, deterministic git plumbing for workflows; no branching policy, no PR logic
(those live in the workflow layer); secrets (PATs) come from the environment, never
from arguments.

Purpose:
    Wrap the exact set of git operations the OC-todo and mail-keeper workflows need —
    repo detection, branch/ref resolution, clone/fetch, remote branch listing, worktree
    add/remove, staged adds, idempotent commits, and push — as small, explicit
    subprocess calls with bounded timeouts.

Rationale:
    Workflows must report git failures with context (the stderr tail) instead of bare
    exceptions, so every method raises :class:`GitError` on non-zero exit carrying the
    last lines of stderr. ``commit`` is the idempotency primitive: a second run with no
    changes returns False rather than creating an empty commit or raising. No
    ``shell=True``, no ``check=True`` — argv lists and explicit exit-code handling keep
    behaviour deterministic and testable against throwaway local repos.

Usage:
    >>> from agentic_scripts.git import Git, GitError
    >>> git = Git()
    >>> if git.is_repo(repo_path):
    ...     git.fetch(repo_path)
    ...     branch = git.current_branch(repo_path)
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a git operation fails (non-zero exit or timeout).

    Attributes:
        message: Formatted as ``<op> failed (exit <code>): <stderr tail>`` — the stderr
            tail is the last ~40 lines of the child's stderr, so callers can log or
            surface it directly without re-running the command.
    """


class Git:
    """Thin wrapper around git subprocess calls for workflow plumbing.

    Every method shells out with ``subprocess.run([...], capture_output=True,
    text=True, timeout=...)`` and raises :class:`GitError` on non-zero exit. Timeouts:
    300s for clone/fetch/push (network-bound), 60s for local operations.

    Note:
        This class holds no state; it is safe to share across workflows. It performs
        no branching policy and no PR logic — those belong to the workflow layer.
    """

    _TIMEOUT_LOCAL = 60
    _TIMEOUT_REMOTE = 300

    def _run(self, op: str, argv: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        """Run one git command and raise GitError on non-zero exit or timeout.

        Args:
            op: The operation name (e.g. ``"clone"``), used in error messages.
            argv: The full argv list, starting with ``"git"``.
            timeout: Per-operation timeout in seconds.

        Returns:
            The completed process (stdout/stderr captured as text).

        Raises:
            GitError: If the command exits non-zero or exceeds ``timeout``; the message
                includes the exit code and a stderr tail.
        """
        try:
            return subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise GitError(
                f"{op} failed (exit {exc.returncode}): timed out after {timeout}s"
            ) from exc

    def _check(self, op: str, proc: subprocess.CompletedProcess[str]) -> None:
        """Raise GitError with a stderr tail when ``proc`` exited non-zero.

        Args:
            op: The operation name for the error message.
            proc: The completed process to inspect.
        """
        if proc.returncode != 0:
            tail = "\n".join(proc.stderr.strip().splitlines()[-40:])
            raise GitError(f"{op} failed (exit {proc.returncode}): {tail}")

    def is_repo(self, path: Path) -> bool:
        """Return whether ``path`` is inside a git work tree.

        Args:
            path: Any path to test (the containing repo counts).

        Returns:
            True if ``git rev-parse --is-inside-work-tree`` succeeds in ``path``, else
            False. A non-repo path returns False rather than raising — callers use this
            as a probe, not as an assertion.
        """
        proc = self._run(
            "rev-parse",
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            timeout=self._TIMEOUT_LOCAL,
        )
        return proc.returncode == 0

    def current_branch(self, path: Path) -> str:
        """Return the short name of the branch checked out at ``path``.

        Args:
            path: A path inside the repository.

        Returns:
            The branch name from ``rev-parse --abbrev-ref HEAD`` (stripped).

        Raises:
            GitError: If the repo is missing or HEAD cannot be resolved (e.g. detached
                in an unborn state).
        """
        proc = self._run(
            "current_branch",
            ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
            timeout=self._TIMEOUT_LOCAL,
        )
        self._check("current_branch", proc)
        return proc.stdout.strip()

    def rev_parse(self, path: Path, ref: str) -> str:
        """Resolve ``ref`` to a full commit SHA in the repo at ``path``.

        Args:
            path: A path inside the repository.
            ref: Any git revision (branch name, tag, SHA prefix, ``HEAD``, ...).

        Returns:
            The 40-character commit SHA for ``ref``.

        Raises:
            GitError: For bad refs — workflows rely on this to validate references
                before acting on them.
        """
        proc = self._run(
            "rev_parse",
            ["git", "-C", str(path), "rev-parse", ref],
            timeout=self._TIMEOUT_LOCAL,
        )
        self._check("rev_parse", proc)
        return proc.stdout.strip()

    def clone(self, url: str, path: Path, *, depth: int | None = None) -> None:
        """Clone ``url`` into ``path`` (local-path URLs supported; no auth handling).

        Args:
            url: The remote URL — for these workflows a local bare-repo path (no
                network, no credentials in the argument; PATs come from the environment).
            path: Destination directory; its parent must already exist.
            depth: Optional shallow-clone depth (``--depth N``); None for full clones.

        Raises:
            GitError: On any failure (e.g. auth failure, missing destination) — the
                message carries git's stderr tail.
        """
        argv = ["git", "clone"]
        if depth is not None:
            argv += ["--depth", str(depth)]
        argv += [url, str(path)]
        proc = self._run("clone", argv, timeout=self._TIMEOUT_REMOTE)
        self._check("clone", proc)

    def fetch(self, path: Path, remote: str = "origin") -> None:
        """Fetch all refs from ``remote`` into the repo at ``path``.

        Args:
            path: A path inside the repository.
            remote: Remote name to fetch from (default ``"origin"``).
        """
        proc = self._run(
            "fetch", ["git", "-C", str(path), "fetch", remote], timeout=self._TIMEOUT_REMOTE
        )
        self._check("fetch", proc)

    def branches(self, path: Path) -> list[str]:
        """List remote-tracking branch names for ``origin`` (short, sorted).

        Args:
            path: A path inside the repository.

        Returns:
            Branch names with the ``origin/`` prefix stripped and ``HEAD`` dropped,
            sorted alphabetically. Run :meth:`fetch` first for a current view.
        """
        proc = self._run(
            "branches",
            [
                "git",
                "-C",
                str(path),
                "for-each-ref",
                "--format=%(refname:short)",
                "refs/remotes/origin/",
            ],
            timeout=self._TIMEOUT_LOCAL,
        )
        self._check("branches", proc)
        names = [
            line.removeprefix("origin/")
            for line in proc.stdout.splitlines()
            if line.strip() and not line.endswith("/HEAD")
        ]
        return sorted(names)

    def worktree_add(self, repo: Path, worktree_path: Path, new_branch: str, ref: str) -> None:
        """Create a new worktree at ``worktree_path`` on a new branch from ``ref``.

        Args:
            repo: A path inside the main repository (the worktree is registered there).
            worktree_path: Where to check out the new worktree; must not exist yet.
            new_branch: Name of the branch to create (``-b``) in the new worktree.
            ref: The starting point for ``new_branch`` (branch/SHA/tag).

        Raises:
            GitError: If the worktree or branch already exists, or ``ref`` is bad.
        """
        proc = self._run(
            "worktree_add",
            ["git", "-C", str(repo), "worktree", "add", "-b", new_branch, str(worktree_path), ref],
            timeout=self._TIMEOUT_LOCAL,
        )
        self._check("worktree_add", proc)

    def worktree_remove(self, repo: Path, worktree_path: Path, *, force: bool = False) -> None:
        """Remove the worktree at ``worktree_path`` from the repo at ``repo``.

        Args:
            repo: A path inside the main repository.
            worktree_path: The worktree directory to remove.
            force: Pass ``--force`` (removes even with uncommitted changes).

        Raises:
            GitError: If the worktree does not exist (e.g. a second removal) or is dirty
                without ``force``.
        """
        argv = ["git", "-C", str(repo), "worktree", "remove"]
        if force:
            argv.append("--force")
        argv.append(str(worktree_path))
        proc = self._run("worktree_remove", argv, timeout=self._TIMEOUT_LOCAL)
        self._check("worktree_remove", proc)

    def add(self, path: Path, paths: list[str] | None = None) -> None:
        """Stage changes in the repo at ``path``.

        Args:
            path: A path inside the repository (used as ``-C`` target).
            paths: Specific paths to stage; when None, stages everything (``add -A``).
        """
        argv = ["git", "-C", str(path), "add"]
        if paths is None:
            argv.append("-A")
        else:
            argv.extend(paths)
        proc = self._run("add", argv, timeout=self._TIMEOUT_LOCAL)
        self._check("add", proc)

    def commit(self, path: Path, message: str) -> bool:
        """Commit staged changes with ``message``; the idempotency primitive.

        Args:
            path: A path inside the repository.
            message: The commit message (``-m``).

        Returns:
            True when a commit was created; **False** (no raise) when there is nothing
            to commit — a second run with no changes must not create an empty commit,
            which is what workflow idempotency relies on.

        Raises:
            GitError: On genuine failures (e.g. missing identity, merge conflicts).
        """
        proc = self._run(
            "commit", ["git", "-C", str(path), "commit", "-m", message], timeout=self._TIMEOUT_LOCAL
        )
        if proc.returncode == 0:
            return True
        combined = f"{proc.stdout}\n{proc.stderr}"
        if "nothing to commit" in combined:
            return False
        self._check("commit", proc)
        raise AssertionError("unreachable: _check must have raised GitError")

    def push(
        self, path: Path, branch: str, *, remote: str = "origin", upstream: bool = False
    ) -> None:
        """Push ``branch`` to ``remote``, optionally setting the upstream.

        Args:
            path: A path inside the repository.
            branch: The local branch name to push.
            remote: Remote to push to (default ``"origin"``).
            upstream: Pass ``--set-upstream <remote>`` (first push of a new branch).
        """
        argv = ["git", "-C", str(path), "push"]
        if upstream:
            argv.append("--set-upstream")
        argv += [remote, branch]
        proc = self._run("push", argv, timeout=self._TIMEOUT_REMOTE)
        self._check("push", proc)
