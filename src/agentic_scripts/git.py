"""Thin, deterministic git plumbing for workflows; no branching policy, no PR logic
(those live in the workflow layer); secrets (PATs) come from the environment, never
from arguments.

Purpose:
    Wrap the exact set of git operations the registered workflows need — repo detection,
    branch/ref resolution, clone/fetch, remote branch
    listing, tree listing, single-file reads (text and binary), worktree add/remove,
    staged adds, tracked renames, branch re-point checkouts, idempotent commits, and
    push — as small, explicit subprocess calls with bounded timeouts.

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

import os
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
    text=True, timeout=...)`` (or ``text=False`` for the binary-safe
    :meth:`show_file_bytes` read) and raises :class:`GitError` on non-zero exit.
    Timeouts: 300s for clone/fetch/push (network-bound), 60s for local operations.

    Note:
        This class holds no state; it is safe to share across workflows. It performs
        no branching policy and no PR logic — those belong to the workflow layer.
    """

    _TIMEOUT_LOCAL = 60
    _TIMEOUT_REMOTE = 300

    def _run(
        self,
        op: str,
        argv: list[str],
        *,
        timeout: int,
        env: dict[str, str] | None = None,
        binary: bool = False,
    ) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
        """Run one git command and raise GitError on non-zero exit or timeout.

        Args:
            op: The operation name (e.g. ``"clone"``), used in error messages.
            argv: The full argv list, starting with ``"git"``.
            timeout: Per-operation timeout in seconds.
            env: Optional environment for the child process; None inherits the current
                environment (the default). Callers pass a merged dict to inject auth
                config without putting secrets in argv.
            binary: When True, capture stdout/stderr as raw bytes (``text=False``) —
                the binary-safe path for :meth:`show_file_bytes`, where decoding the
                blob as text would raise ``UnicodeDecodeError`` on non-UTF-8 content.
                The default (False) decodes as text.

        Returns:
            The completed process (stdout/stderr captured as text, or raw bytes when
            ``binary``).

        Raises:
            GitError: If the command exits non-zero or exceeds ``timeout``; the message
                includes the exit code and a stderr tail.
        """
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=not binary,
                timeout=timeout,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitError(
                f"{op} failed (exit {exc.returncode}): timed out after {timeout}s"
            ) from exc

    def _check(
        self, op: str, proc: subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]
    ) -> None:
        """Raise GitError with a stderr tail when ``proc`` exited non-zero.

        Args:
            op: The operation name for the error message.
            proc: The completed process to inspect (text or binary capture).
        """
        if proc.returncode != 0:
            stderr = (
                proc.stderr
                if isinstance(proc.stderr, str)
                else proc.stderr.decode("utf-8", "replace")
            )
            tail = "\n".join(stderr.strip().splitlines()[-40:])
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

    def clone(
        self,
        url: str,
        path: Path,
        *,
        depth: int | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Clone ``url`` into ``path`` (local-path URLs supported; no auth handling).

        Args:
            url: The remote URL — for these workflows a local bare-repo path (no
                network, no credentials in the argument; PATs come from the environment).
            path: Destination directory; its parent must already exist.
            depth: Optional shallow-clone depth (``--depth N``); None for full clones.
            env: Optional extra environment variables for the child process. When given,
                the subprocess runs with ``{**os.environ, **env}`` — used to inject git
                auth config env (``GIT_CONFIG_*``) so PATs never appear in argv. None
                keeps the existing behaviour (the inherited environment).

        Raises:
            GitError: On any failure (e.g. auth failure, missing destination) — the
                message carries git's stderr tail.
        """
        argv = ["git", "clone"]
        if depth is not None:
            argv += ["--depth", str(depth)]
        argv += [url, str(path)]
        proc = self._run(
            "clone",
            argv,
            timeout=self._TIMEOUT_REMOTE,
            env={**os.environ, **env} if env is not None else None,
        )
        self._check("clone", proc)

    def fetch(
        self,
        path: Path,
        remote: str = "origin",
        *,
        prune: bool = True,
        env: dict[str, str] | None = None,
    ) -> None:
        """Fetch all refs from ``remote`` into the repo at ``path``.

        Args:
            path: A path inside the repository.
            remote: Remote name to fetch from (default ``"origin"``).
            prune: When True (the default), pass ``--prune`` so stale remote-tracking
                refs disappear when their branch is deleted upstream. Set False to keep
                them (e.g. a local bare remote where pruning is harmless but unneeded).
            env: Optional extra environment variables for the child process (see
                :meth:`clone`). None keeps the existing behaviour.
        """
        argv = ["git", "-C", str(path), "fetch"]
        if prune:
            argv.append("--prune")
        argv.append(remote)
        proc = self._run(
            "fetch",
            argv,
            timeout=self._TIMEOUT_REMOTE,
            env={**os.environ, **env} if env is not None else None,
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

    def ls_tree(self, repo: Path, ref: str) -> list[str]:
        """Return the file paths in ``ref``'s tree (recursive, sorted, no directories).

        Purpose:
            A scanner's primitive: enumerate every file committed on a
            branch ref (e.g. ``"origin/dev"``) without checking it out, so candidate plan
            folders (``planning/**/work_plan.md``) can be identified from their paths
            alone. Runs ``git -C <repo> ls-tree -r --name-only <ref>`` — ``-r`` recurses
            through directories and ``--name-only`` drops the mode/type/SHA columns,
            leaving one path per file.

        Rationale:
            A local, bounded operation (no network), so it uses :attr:`_TIMEOUT_LOCAL`.
            Unlike :meth:`grep_fixed`, there is no "no match" exit code here: an empty
            tree (e.g. an empty commit) yields ``[]``, and a bad ref exits non-zero and
            raises :class:`GitError`.

        Args:
            repo: A path inside the repository to run in.
            ref: The revision to list (e.g. ``"origin/dev"``).

        Returns:
            The repo-root-relative file paths, sorted; empty for an empty tree.

        Raises:
            GitError: For a bad ref or a missing repo — the message carries git's stderr
                tail.
        """
        proc = self._run(
            "ls_tree",
            ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref],
            timeout=self._TIMEOUT_LOCAL,
        )
        self._check("ls_tree", proc)
        return sorted(line for line in proc.stdout.splitlines() if line.strip())

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

    def mv(self, path: Path, src: str, dst: str) -> None:
        """Move a tracked path ``src`` to ``dst`` (staged) in the repo at ``path``.

        Purpose:
            An archive step's primitive: ``git -C <path> mv <src>
            <dst>`` moves a plan folder to ``planning/archived/<topic>/`` as a staged
            rename, so the archive commit records the move (not a delete + add) and the
            history stays reviewable.

        Rationale:
            A local, bounded operation (no network), so it uses :attr:`_TIMEOUT_LOCAL`.
            The rename is staged immediately (git mv stages by default) — the caller
            commits with :meth:`commit`.

        Args:
            path: A path inside the repository (used as the ``-C`` target).
            src: The source path (repo-root-relative, tracked).
            dst: The destination path (repo-root-relative; its parent must exist).

        Raises:
            GitError: If ``src`` is not tracked or ``dst`` cannot be created (e.g. the
                destination parent is missing) — the message carries git's stderr tail.
        """
        proc = self._run(
            "mv",
            ["git", "-C", str(path), "mv", src, dst],
            timeout=self._TIMEOUT_LOCAL,
        )
        self._check("mv", proc)

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

    def checkout(self, path: Path, branch: str, ref: str | None = None) -> None:
        """Check out ``branch``, re-pointing it to ``ref`` when given (``-B``).

        Purpose:
            Ensure a workflow-owned clone is on a specific branch: a listing clone
            checks out the remote's default branch, and the listing may
            live on a different one — ``checkout -B <branch> <ref>`` (e.g. ``-B main
            origin/main``) creates or resets the local branch to ``ref`` and switches to
            it. With ``ref=None`` a plain ``checkout -B <branch>`` simply re-selects the
            branch (no re-point).

        Rationale:
            ``-B`` is deliberate: the prompts clone is workflow-owned (its local branches
            are never user state), so resetting the local branch to the remote tip is the
            standard re-point after a concurrent remote update. A plain ``checkout -b``
            would fail when the branch already exists, and a plain ``checkout`` would
            leave a stale local branch behind the remote.

        Args:
            path: A path inside the repository (used as the ``-C`` target).
            branch: The branch to check out (created or reset when given a ``ref``).
            ref: The start point to re-point ``branch`` to (e.g. ``"origin/main"``);
                None for no re-point.

        Raises:
            GitError: If ``ref`` is bad or the checkout is impossible (e.g. local
                uncommitted changes would be overwritten) — the message carries git's
                stderr tail.
        """
        argv = ["git", "-C", str(path), "checkout", "-B", branch]
        if ref is not None:
            argv.append(ref)
        proc = self._run("checkout", argv, timeout=self._TIMEOUT_LOCAL)
        self._check("checkout", proc)

    def grep_fixed(
        self, repo: Path, ref: str, pattern: str, *, exclude_standard: bool = False
    ) -> list[str]:
        """Fixed-string grep of ``ref``'s tree for lines containing ``pattern``.

        Purpose:
            The OC-todo scanner's primitive: find every occurrence of the marker on a
            specific branch ref without checking it out. Runs ``git -C <repo> grep -n
            -F -I -e <pattern> <ref>`` and returns the raw output lines, each of the shape
            ``<ref>:<file>:<line>:<content>``.

        Rationale:
            ``-F`` treats ``pattern`` as a fixed string (no regex metacharacters) and
            ``-I`` skips binary files — together they are the "standard binary/build
            exclusions" for a *committed* ref (build artifacts are not committed, so there
            is nothing to ignore). Exit code 1 is git grep's "no match" code (not an error)
            and yields ``[]``; any other non-zero exit raises :class:`GitError` via
            :meth:`_check`.

        Note:
            ``--exclude-standard`` is deliberately NOT passed for a ref: it only applies to
            *untracked* files, and git errors out (exit 128) when it is combined with a
            committed ref — the scanner always greps a ref, so the flag would break every
            call. The ``exclude_standard`` parameter is retained for API stability but is
            intentionally inert here (documented; see the Task 3 result report).

        Args:
            repo: A path inside the repository to run in.
            ref: The revision to grep (e.g. ``"origin/dev"``).
            pattern: The fixed string to search for (e.g. ``"OC-todo:"``).
            exclude_standard: Retained for API stability; ignored when grepping a ref
                (see the Note — ``--exclude-standard`` is incompatible with tracked
                contents and would make every call fail).

        Returns:
            The raw output lines (one per match), empty when there is no match.

        Raises:
            GitError: On any genuine failure (bad ref, missing repo) — exit 1 is the
                documented "no match" code and does not raise.
        """
        argv = ["git", "-C", str(repo), "grep", "-n", "-F", "-I", "-e", pattern]
        # NOTE: --exclude-standard is intentionally omitted — it is incompatible with a
        # committed ref (git exits 128); the scanner always greps a ref. See the Note above.
        argv.append(ref)
        proc = self._run("grep_fixed", argv, timeout=self._TIMEOUT_LOCAL)
        if proc.returncode == 1:
            return []  # git grep's "no match" code — not an error
        self._check("grep_fixed", proc)
        return proc.stdout.splitlines()

    def show_file(self, repo: Path, ref: str, path: str) -> str:
        """Return the content of ``path`` as it exists at ``ref``.

        Purpose:
            Read a single file from an arbitrary revision without checking it out — the
            OC-todo workflow uses this to pull the keep-instruction context window around
            a marker line (the marker line plus the next :data:`KEEP_CONTEXT_LINES` lines).

        Args:
            repo: A path inside the repository to run in.
            ref: The revision to read from (e.g. ``"origin/dev"``).
            path: The file path relative to the repository root.

        Returns:
            The file content with its trailing newline removed.

        Raises:
            GitError: If the path does not exist at ``ref`` (or ``ref`` is bad) — git's
                stderr tail names the missing path.
        """
        proc = self._run(
            "show_file",
            ["git", "-C", str(repo), "show", f"{ref}:{path}"],
            timeout=self._TIMEOUT_LOCAL,
        )
        self._check("show_file", proc)
        return proc.stdout.rstrip("\n")

    def show_file_bytes(self, repo: Path, ref: str, path: str) -> bytes:
        """Return the raw bytes of ``path`` as it exists at ``ref`` (binary-safe).

        Purpose:
            Binary-safe single-file read from an arbitrary revision without checking it
            out — a plan-folder hasher uses this to read arbitrary files, which may
            contain binary assets (images, committed build artifacts) that would crash
            a text-mode read: with ``text=True``, ``git show`` of a non-UTF-8 blob
            raises ``UnicodeDecodeError`` on stdout decoding, which is NOT a
            :class:`GitError` and escapes the scanner's defensive handlers.

        Rationale:
            The identical ``git -C <repo> show <ref>:<path>`` argv as :meth:`show_file`
            with ``text=False``, so the returned bytes are exactly the blob bytes —
            ``git show`` emits the blob verbatim (no trailing-newline rstrip; a blob's
            trailing newlines are content). Same local timeout and :class:`GitError`
            handling as every other method here.

        Note:
            :meth:`show_file` remains the text form for text-only consumers (the
            plan listing file, the OC-todo marker context window), whose trailing
            newlines are stripped; use :meth:`show_file_bytes` whenever the content may
            not be valid UTF-8.

        Args:
            repo: A path inside the repository to run in.
            ref: The revision to read from (e.g. ``"origin/dev"``).
            path: The file path relative to the repository root.

        Returns:
            The exact blob bytes (no decoding, no stripping).

        Raises:
            GitError: If the path does not exist at ``ref`` (or ``ref`` is bad) — git's
                stderr tail names the missing path.
        """
        proc = self._run(
            "show_file_bytes",
            ["git", "-C", str(repo), "show", f"{ref}:{path}"],
            timeout=self._TIMEOUT_LOCAL,
            binary=True,
        )
        self._check("show_file_bytes", proc)
        return proc.stdout

    def delete_branch(self, path: Path, branch: str, *, force: bool = True) -> None:
        """Delete the local branch ``branch`` in the repo at ``path``.

        Purpose:
            Clean up a per-todo worktree branch after its PR is merged or the todo is
            resolved. The caller pre-checks existence via :meth:`rev_parse`; this method
            does not — a missing branch raises :class:`GitError`.

        Args:
            path: A path inside the repository.
            branch: The local branch name to delete.
            force: When True (default) use ``-D`` (delete even if unmerged); when False
                use ``-d`` (delete only if merged).

        Raises:
            GitError: If the branch does not exist or is not safe to delete without
                ``force`` — the message carries git's stderr tail.
        """
        flag = "-D" if force else "-d"
        proc = self._run(
            "delete_branch",
            ["git", "-C", str(path), "branch", flag, branch],
            timeout=self._TIMEOUT_LOCAL,
        )
        self._check("delete_branch", proc)

    def prune_worktrees(self, repo: Path) -> None:
        """Deregister worktree entries whose directories no longer exist.

        Purpose:
            Run ``git -C <repo> worktree prune`` to drop the bookkeeping for any worktree
            whose directory was removed out from under git (e.g. a crash between
            :meth:`worktree_add` and :meth:`worktree_remove`, or an operator deleting the
            sandbox). This is the crash-recovery step: a stale entry would otherwise make
            a later ``worktree add`` of the same path fail with "already exists".

        Rationale:
            A local, bounded operation (no network), so it uses :attr:`_TIMEOUT_LOCAL`. It
            is idempotent — pruning when there is nothing to prune succeeds silently — so
            callers may invoke it best-effort after a failed :meth:`worktree_remove`.

        Args:
            repo: A path inside the main repository (the worktrees are registered here).

        Raises:
            GitError: On any failure (e.g. ``repo`` is not a repository) — the message
                carries git's stderr tail.
        """
        proc = self._run(
            "prune_worktrees",
            ["git", "-C", str(repo), "worktree", "prune"],
            timeout=self._TIMEOUT_LOCAL,
        )
        self._check("prune_worktrees", proc)
