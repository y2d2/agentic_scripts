"""Hermetic integration tests for the oc-todo pipeline (Task 4).

A fixture bare repo plays GitHub; a fake agent (:class:`FakeRunner`) and a fake GitHub
(:class:`FakeGitHub`) replace the real collaborators. :meth:`OCTodoWorkflow.run` is driven
directly (NOT via ``scheduler.run``) against a throwaway workspace under ``tmp_path``.

The fake agent edits REAL files in the worktree (line-level removal / a comment edit — not
a whole-file rewrite), which is what makes the "diff removes the marker" assertions
meaningful. NO test touches the network or real ``opencode``: git runs against local bare
repos and every collaborator is a fake. Git identity is set via
``os.environ.setdefault`` at import (mirroring :mod:`tests.test_git`).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

from agentic_scripts.agent import AgentResult
from agentic_scripts.config import Config, load_config
from agentic_scripts.git import Git
from agentic_scripts.state import StateStore
from agentic_scripts.workflows.base import WorkContext
from agentic_scripts.workflows.oc_todo import (
    MARKER_PREFIX,
    OCTodoWorkflow,
    todo_id,
)

# Git identity for every subprocess spawned by these tests (set at import so it is present
# before the first commit; setdefault never clobbers a real environment).
os.environ.setdefault("GIT_AUTHOR_NAME", "Test Author")
os.environ.setdefault("GIT_AUTHOR_EMAIL", "author@example.test")
os.environ.setdefault("GIT_COMMITTER_NAME", "Test Committer")
os.environ.setdefault("GIT_COMMITTER_EMAIL", "committer@example.test")

# --- Fixture constants ------------------------------------------------------- #
REPO = "fixture/owner-repo"  # the owner/name repo id used by every test
OWNER, NAME = REPO.split("/", 1)
MARKER_A = f"# {MARKER_PREFIX} fix bug A in alpha()"  # on main: src/a.py (line 3)
MARKER_B = f"# {MARKER_PREFIX} fix bug B in beta()"  # on dev: src/b.py (line 2)
OC_TODO_REF_RE = re.compile(r"^refs/heads/oc-todo/[0-9a-f]{12}$")


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a raw git command in ``path`` (test setup helper)."""
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    )


def _bare_refs(bare: Path) -> dict[str, str]:
    """Return the bare repo's refs as ``{refname: sha}`` (for before/after comparison)."""
    proc = _git(bare, "for-each-ref", "--format=%(refname) %(objectname)")
    return {line.split()[0]: line.split()[1] for line in proc.stdout.splitlines() if line.strip()}


# --- Fixture repo builder ---------------------------------------------------- #


def _make_fixture_repo(
    tmp_path: Path, *, keep_dev: bool = False, extra_main_markers: int = 0, with_dev: bool = True
) -> tuple[Path, dict]:
    """Build a working repo on ``main`` (+ an optional ``dev`` branch), then a bare clone.

    Purpose:
        The hermetic "GitHub": ``main`` carries one marker in ``src/a.py`` (line 3); when
        ``with_dev``, ``dev`` (off the marker-free base) adds ``src/b.py`` with a marker
        (line 2). When ``keep_dev`` is set, the line below dev's marker carries an
        ``(oc-original: keep this marker)`` note. ``extra_main_markers`` appends that many
        additional single-marker files on ``main`` (for the cap test). The bare repo ends
        with ``refs/heads/main`` (+ ``refs/heads/dev`` when ``with_dev``).

    Args:
        tmp_path: A unique temp dir (the working repo and bare live under it).
        keep_dev: When True, add a keep-instruction note below dev's marker line.
        extra_main_markers: Number of extra ``src/m<i>.py`` files (one marker each) on main.
        with_dev: When False, skip the ``dev`` branch entirely (single-marker fixture).

    Returns:
        A ``(bare_path, facts)`` tuple; ``facts`` carries the repo id and per-branch
        file/marker/line for assertions.
    """
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    _git(src, "init", "-b", "main")

    # Base commit on main (no markers yet) so dev can branch off it BEFORE any marker is
    # added — that way origin/dev carries ONLY its own marker, not main's.
    (src / "src").mkdir()
    (src / "src" / "a.py").write_text(
        '"""Module alpha."""\n\ndef alpha():\n    return 1\n', encoding="utf-8"
    )
    _git(src, "add", "-A")
    _git(src, "commit", "-m", "base commit (no markers)")

    if with_dev:
        # dev branches off the marker-free base and adds its own marker in src/b.py (line 2).
        _git(src, "checkout", "-b", "dev")
        b_lines = ['"""Module beta."""', MARKER_B]
        if keep_dev:
            b_lines.append("(oc-original: keep this marker)")
        b_lines += ["def beta():", "    return 2", ""]
        (src / "src" / "b.py").write_text("\n".join(b_lines) + "\n", encoding="utf-8")
        _git(src, "add", "-A")
        _git(src, "commit", "-m", "add dev marker")

    # Back on main: add the marker to src/a.py (line 3) + any extra single-marker files.
    _git(src, "checkout", "main")
    a_lines = [
        '"""Module alpha."""',
        "",
        MARKER_A,
        "def alpha():",
        "    return 1",
        "",
    ]
    (src / "src" / "a.py").write_text("\n".join(a_lines) + "\n", encoding="utf-8")
    for i in range(extra_main_markers):
        (src / "src" / f"m{i}.py").write_text(
            f"# {MARKER_PREFIX} extra marker {i}\ndef m{i}():\n    return {i}\n",
            encoding="utf-8",
        )
    _git(src, "add", "-A")
    _git(src, "commit", "-m", "add main marker")

    # Bare remote with both branches (refs/heads/main + refs/heads/dev).
    bare = tmp_path / "remote.git"
    bare.mkdir(parents=True, exist_ok=True)
    _git(bare, "init", "--bare")
    _git(src, "remote", "add", "origin", str(bare))
    _git(src, "push", "-u", "origin", "main")
    if with_dev:
        _git(src, "push", "-u", "origin", "dev")

    facts = {
        "repo": REPO,
        "main": {"file": "src/a.py", "marker": MARKER_A, "line": 3},
    }
    if with_dev:
        facts["dev"] = {"file": "src/b.py", "marker": MARKER_B, "line": 2}
    return bare, facts


# --- Fakes ------------------------------------------------------------------- #


class FakeGitHub:
    """An in-memory stand-in for :class:`GitHubClient` (no network).

    Purpose:
        Record PRs created by the workflow and answer ``find_pr_by_head`` from that list, so
        the pipeline's idempotency check is deterministic. ``set_state`` flips a stored PR's
        state/merged flag to simulate a merge between runs.
    """

    def __init__(self) -> None:
        self.prs: list[dict] = []
        self.create_calls: list[dict] = []

    def find_pr_by_head(self, owner: str, repo: str, head_branch: str) -> dict | None:
        """Return the first stored PR whose head is ``owner:head_branch``, else None.

        Note:
            Mirrors the real GitHub API's list endpoint, which filters by
            ``head={owner}:{branch}`` — a single owner account plus the branch (no repo name).
            This fake matches on that same ``owner:branch`` shape so it stays consistent with
            how :meth:`create_pr` stores the head.
        """
        target = f"{owner}:{head_branch}"
        for pr in self.prs:
            if pr.get("head") == target:
                return pr
        return None

    def create_pr(
        self, owner: str, repo: str, *, title: str, body: str, head: str, base: str
    ) -> tuple[int, str]:
        """Append a new PR and return its ``(number, html_url)``."""
        n = len(self.prs) + 1
        url = f"https://github.com/{owner}/{repo}/pull/{n}"
        self.prs.append(
            {
                "number": n,
                "html_url": url,
                "state": "open",
                "merged": False,
                "head": head,
                "base": base,
                "title": title,
                "body": body,
            }
        )
        self.create_calls.append(
            {"owner": owner, "repo": repo, "title": title, "body": body, "head": head, "base": base}
        )
        return n, url

    def set_state(self, number: int, state: str, merged: bool = False) -> None:
        """Flip the stored PR ``number`` to ``state`` (optionally marking it merged)."""
        for pr in self.prs:
            if pr["number"] == number:
                pr["state"] = state
                pr["merged"] = merged


class FakeRunner:
    """A stand-in for :class:`AgentRunner` that simulates the agent's REAL work.

    Purpose:
        For mode ``"ok"`` it finds the marker line in the worktree (searching all text files
        under ``work_dir`` for :data:`MARKER_PREFIX`) and edits it exactly as the real agent
        would — removing the marker line (unless the brief says keep) and appending a fix
        comment — then returns an ``ok`` result with a skill-shaped report. Other modes make
        no file change and return their canned result. Every call is recorded in
        :attr:`calls`.

    Attributes:
        mode: One of ``"ok"``, ``"timeout"``, ``"step-exhausted"``, ``"blockers"``, ``"no-op"``.
        calls: A list of ``(agent, brief, work_dir, title)`` tuples, one per invocation.
    """

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.calls: list[tuple[str, str, Path, str | None]] = []

    def _find_marker(self, work_dir: Path) -> tuple[Path, int] | None:
        """Return ``(file_path, 0-based line index)`` of the first marker line, or None."""
        for path in sorted(work_dir.rglob("*")):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if MARKER_PREFIX in line:
                    return path, i
        return None

    def _do_ok_work(self, work_dir: Path, brief: str) -> None:
        """Simulate the agent's fix: remove the marker line (unless keep) + a comment edit."""
        keep = "Keep-instruction: yes" in brief
        found = self._find_marker(work_dir)
        if found is None:
            return  # nothing to do (defensive — the worktree always has the marker here)
        path, idx = found
        lines = path.read_text(encoding="utf-8").splitlines()
        if not keep:
            del lines[idx]
        lines.insert(idx, "# fixed by oc-todo-resolver")  # a realistic line-level edit
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _report(self, work_dir: Path) -> str:
        """Build a skill-shaped result report (Blockers = None)."""
        return (
            "# oc-todo-resolver Output\n"
            "\n"
            "## Summary\n"
            "Removed marker and fixed bug A in alpha(); appended the fix comment.\n"
            "\n"
            "## Files\n"
            "| File | Action |\n"
            "|---|---|\n"
            f"| `{work_dir.name}/src/a.py` | modify |\n"
            "\n"
            "## Build / Tests\n"
            "- `pytest`: not configured\n"
            "\n"
            "## Blockers\n"
            "None\n"
        )

    def run(
        self,
        *,
        agent: str,
        brief: str,
        work_dir: Path,
        title: str | None = None,
        timeout_seconds: int | None = None,
    ) -> AgentResult:
        """Record the call and return the canned :class:`AgentResult` for this mode."""
        self.calls.append((agent, brief, work_dir, title))
        if self.mode == "ok":
            self._do_ok_work(work_dir, brief)
            return AgentResult(
                status="ok",
                exit_code=0,
                final_text=self._report(work_dir),
                events=[],
                error=None,
                duration_seconds=0.1,
            )
        if self.mode == "timeout":
            return AgentResult(
                status="timeout",
                exit_code=None,
                final_text=None,
                events=[],
                error="agent run exceeded 300s",
                duration_seconds=300.0,
            )
        if self.mode == "step-exhausted":
            return AgentResult(
                status="ok",
                exit_code=0,
                final_text="maximum steps reached — partial work, see summary",
                events=[],
                error=None,
                duration_seconds=10.0,
            )
        if self.mode == "blockers":
            report = (
                "# oc-todo-resolver Output\n\n## Summary\nAttempted the fix.\n\n"
                "## Files\n| File | Action |\n|---|---|\n\n"
                "## Build / Tests\n- `pytest`: FAIL\n\n## Blockers\n- tests fail: 2 errors\n"
            )
            return AgentResult(
                status="ok",
                exit_code=0,
                final_text=report,
                events=[],
                error=None,
                duration_seconds=5.0,
            )
        # "no-op": a normal report but no file change (the agent did nothing).
        return AgentResult(
            status="ok",
            exit_code=0,
            final_text=self._report(work_dir),
            events=[],
            error=None,
            duration_seconds=0.1,
        )


class RaisingRunner:
    """A runner that raises if ever called (for the orphan-resume test)."""

    def __init__(self) -> None:
        self.calls: list = []

    def run(self, **kwargs) -> AgentResult:  # noqa: ANN001 - mirror AgentRunner.run signature
        """Raise AssertionError — the orphan path must never invoke the agent."""
        self.calls.append(kwargs)
        raise AssertionError("agent must not be called on an orphan-branch resume")


# --- Context / workflow builders --------------------------------------------- #


def _write_config(
    tmp_path: Path,
    *,
    repos: list[str],
    repo_urls: dict[str, str],
    test_commands: dict[str, str] | None = None,
    max_todos_per_repo: int = 3,
) -> Config:
    """Write a minimal valid config YAML under ``tmp_path`` and load it.

    Args:
        tmp_path: The temp dir to write the config file into.
        repos: The ``oc_todo.repos`` list.
        repo_urls: The ``oc_todo.repo_urls`` mapping (repo -> local bare path).
        test_commands: Optional per-repo test command map.
        max_todos_per_repo: The per-run per-repo cap.

    Returns:
        A fully validated :class:`Config` (paths pointed at the tmp workspace).
    """
    data = {
        "machine": {
            "quiet_window": {"start": "22:00", "end": "08:00"},
            "load_threshold": 32.0,
            "poll_interval_minutes": 30,
            "gate_polls_required": 1,
            "gate_poll_tolerance_minutes": 10,
        },
        "agent": {
            "binary": "opencode",
            "model": None,
            "max_steps": 80,
            "timeout_minutes": 5,
            "auto_approve": True,
        },
        "paths": {
            "state_dir": str(tmp_path / "state"),
            "log_dir": str(tmp_path / "logs"),
            "sandbox_dir": str(tmp_path / "sandbox"),
        },
        "workflows": {},
        "oc_todo": {
            "repos": repos,
            "max_todos_per_repo": max_todos_per_repo,
            "test_commands": test_commands or {},
            "repo_urls": repo_urls,
        },
    }
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_config(cfg_path)


def make_ctx(tmp_path: Path, cfg: Config) -> WorkContext:
    """Build a :class:`WorkContext` over the tmp workspace (real StateStore, quiet logger).

    Args:
        tmp_path: The temp dir holding state/log/sandbox.
        cfg: A loaded :class:`Config` whose paths point at ``tmp_path``.

    Returns:
        A fully wired :class:`WorkContext` (``run_id="test-run"``, ``admin_repo=None``).
    """
    import logging

    logger = logging.getLogger("test.oc-todo")
    logger.setLevel(logging.CRITICAL)  # quiet: the workflow logs at INFO/DEBUG
    return WorkContext(
        config=cfg,
        state=StateStore(tmp_path / "state"),
        logger=logger,
        run_id="test-run",
        workflow_name="oc-todo",
        sandbox_dir=tmp_path / "sandbox",
        admin_repo=None,
    )


def make_wf(cfg: Config, fake_gh: FakeGitHub, fake_runner) -> OCTodoWorkflow:
    """Build an :class:`OCTodoWorkflow` with a real Git + the injected fakes.

    Args:
        cfg: A loaded :class:`Config`.
        fake_gh: The injected :class:`FakeGitHub`.
        fake_runner: The injected :class:`FakeRunner` (or a raising runner).

    Returns:
        An :class:`OCTodoWorkflow` wired to the fakes.
    """
    return OCTodoWorkflow(cfg.oc_todo, github=fake_gh, runner=fake_runner)


def _state_doc(ctx: WorkContext) -> dict:
    """Return the workflow's persisted state document ({} when absent)."""
    return ctx.state.load("oc-todo")


# --- Tests ------------------------------------------------------------------- #


def test_two_branches_two_prs(tmp_path: Path) -> None:
    """[AC1] Two markers on main+dev → 2 PRs on the right bases; state pr_open; cleanup."""
    bare, facts = _make_fixture_repo(tmp_path)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    fake_gh = FakeGitHub()
    wf = make_wf(cfg, fake_gh, FakeRunner("ok"))

    result = wf.run(ctx)

    assert result.status == "ok"
    assert len(fake_gh.prs) == 2
    by_base = {pr["base"]: pr for pr in fake_gh.prs}
    assert set(by_base) == {"main", "dev"}
    for pr in fake_gh.prs:
        assert re.match(r"^fixture:oc-todo/[0-9a-f]{12}$", pr["head"])
    # Each PR body quotes the exact marker verbatim + file path + line number.
    main_pr = by_base["main"]
    assert MARKER_A in main_pr["body"]
    assert "src/a.py" in main_pr["body"] and "line `3`" in main_pr["body"]
    dev_pr = by_base["dev"]
    assert MARKER_B in dev_pr["body"]
    assert "src/b.py" in dev_pr["body"] and "line `2`" in dev_pr["body"]

    # State: both entries pr_open with pr_number/pr_url/commit_sha.
    st = _state_doc(ctx)
    tid_a = todo_id(REPO, "main", facts["main"]["file"], MARKER_A)
    tid_b = todo_id(REPO, "dev", facts["dev"]["file"], MARKER_B)
    assert st["todos"][tid_a]["status"] == "pr_open"
    assert st["todos"][tid_b]["status"] == "pr_open"
    for tid in (tid_a, tid_b):
        entry = st["todos"][tid]
        assert entry["pr_number"] and entry["pr_url"] and entry["commit_sha"]

    # The bare remote now has exactly 2 new oc-todo/* refs.
    refs = _bare_refs(bare)
    oc_refs = [r for r in refs if OC_TODO_REF_RE.match(r)]
    assert len(oc_refs) == 2

    # No worktree dirs remain under sandbox/oc-todo/wt (cleanup).
    wt_root = tmp_path / "sandbox" / "wt"
    leftovers = list(wt_root.rglob("*")) if wt_root.exists() else []
    assert not [p for p in leftovers if p.is_dir()], f"worktree dirs remain: {leftovers}"


def test_pr_diff_removes_marker(tmp_path: Path) -> None:
    """[AC2 diff] The pushed branch has the marker removed; exactly 1 commit, OC: message."""
    bare, facts = _make_fixture_repo(tmp_path)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    wf = make_wf(cfg, FakeGitHub(), FakeRunner("ok"))
    wf.run(ctx)

    tid_a = todo_id(REPO, "main", facts["main"]["file"], MARKER_A)
    branch = f"oc-todo/{tid_a}"

    # Throwaway clone of the bare repo; inspect the pushed branch's committed content.
    scratch = tmp_path / "scratch"
    git = Git()
    git.clone(str(bare), scratch)
    git.fetch(scratch)  # ensure the oc-todo/* ref is present locally
    # Marker is gone from the branch's tree (the FakeRunner removed it).
    assert git.grep_fixed(scratch, f"origin/{branch}", MARKER_PREFIX) == []
    # Exactly one commit on the branch beyond main, with an "OC:" message.
    log = _git(scratch, "log", "--oneline", f"origin/{branch}", "--not", "origin/main")
    commits = [line for line in log.stdout.splitlines() if line.strip()]
    assert len(commits) == 1
    assert commits[0].split(" ", 1)[1].startswith("OC: ")


def test_keep_instruction_preserves_marker(tmp_path: Path) -> None:
    """[AC2 keep] A keep-instruction leaves the marker verbatim; PR body says keep=yes."""
    bare, facts = _make_fixture_repo(tmp_path, keep_dev=True)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    fake_gh = FakeGitHub()
    wf = make_wf(cfg, fake_gh, FakeRunner("ok"))
    result = wf.run(ctx)

    assert result.status == "ok"
    dev_pr = next(pr for pr in fake_gh.prs if pr["base"] == "dev")
    assert "**Keep-instruction:** yes" in dev_pr["body"]

    tid_b = todo_id(REPO, "dev", facts["dev"]["file"], MARKER_B)
    branch = f"oc-todo/{tid_b}"
    scratch = tmp_path / "scratch"
    git = Git()
    git.clone(str(bare), scratch)
    git.fetch(scratch)  # ensure the oc-todo/* ref is present locally
    # The marker line is STILL present verbatim on the pushed branch.
    lines = git.grep_fixed(scratch, f"origin/{branch}", MARKER_PREFIX)
    assert len(lines) == 1
    assert MARKER_B in lines[0]


def test_rerun_opens_no_new_prs(tmp_path: Path) -> None:
    """[AC3 first half] A second run opens no new PRs; both todos stay pr_open."""
    bare, _ = _make_fixture_repo(tmp_path)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    fake_gh = FakeGitHub()

    wf1 = make_wf(cfg, fake_gh, FakeRunner("ok"))
    r1 = wf1.run(ctx)
    assert r1.status == "ok" and len(fake_gh.prs) == 2
    st_after_run1 = _state_doc(ctx)

    # Second run with a fresh runner: both todos are pr_open with open PRs → skipped.
    wf2 = make_wf(cfg, fake_gh, FakeRunner("ok"))
    r2 = wf2.run(ctx)
    assert r2.status == "ok"
    assert r2.items_found == 2
    assert len(fake_gh.prs) == 2  # create_pr called exactly twice total
    assert any("skip" in a.lower() for a in r2.actions), f"no skip note: {r2.actions}"

    st_after_run2 = _state_doc(ctx)
    assert st_after_run1 == st_after_run2  # state unchanged
    for tid, entry in st_after_run2["todos"].items():
        assert entry["status"] == "pr_open"


def test_merge_resolves_todo(tmp_path: Path) -> None:
    """[AC3 second half] A merged PR + marker removed on main → todo resolved; no new PRs."""
    bare, facts = _make_fixture_repo(tmp_path)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    fake_gh = FakeGitHub()

    wf1 = make_wf(cfg, fake_gh, FakeRunner("ok"))
    wf1.run(ctx)
    main_pr = next(pr for pr in fake_gh.prs if pr["base"] == "main")

    # Simulate the merge: PR closed+merged AND the marker removed on main (pushed).
    fake_gh.set_state(main_pr["number"], "closed", merged=True)
    scratch = tmp_path / "scratch"
    git = Git()
    git.clone(str(bare), scratch)
    a_text = (scratch / "src" / "a.py").read_text(encoding="utf-8")
    (scratch / "src" / "a.py").write_text(a_text.replace(MARKER_A + "\n", ""), encoding="utf-8")
    git.add(scratch)
    assert git.commit(scratch, "remove marker A on main") is True
    git.push(scratch, "main")

    # Re-run: todo A resolves (merged), todo B stays pr_open; zero new PRs.
    wf2 = make_wf(cfg, fake_gh, FakeRunner("ok"))
    r2 = wf2.run(ctx)
    assert r2.status == "ok"
    assert len(fake_gh.prs) == 2  # no new PRs

    st = _state_doc(ctx)
    tid_a = todo_id(REPO, "main", facts["main"]["file"], MARKER_A)
    tid_b = todo_id(REPO, "dev", facts["dev"]["file"], MARKER_B)
    assert st["todos"][tid_a]["status"] == "resolved"
    assert st["todos"][tid_b]["status"] == "pr_open"


def test_agent_timeout_fails_and_retries(tmp_path: Path) -> None:
    """[AC4 timeout] A timeout → failed state + business error; a retry with ok opens a PR."""
    bare, facts = _make_fixture_repo(tmp_path)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    fake_gh = FakeGitHub()

    # Run 1: timeout → error status, failed state, no oc-todo ref pushed for that todo.
    wf1 = make_wf(cfg, fake_gh, FakeRunner("timeout"))
    r1 = wf1.run(ctx)
    assert r1.status == "error"
    assert r1.errors, "expected a business error for the per-todo failure"
    st1 = _state_doc(ctx)
    failed_tids = [tid for tid, e in st1["todos"].items() if e["status"] == "failed"]
    assert len(failed_tids) == 2  # both todos timed out (one agent call each)
    for tid in failed_tids:
        assert "timeout" in st1["todos"][tid]["last_error"]
    # No oc-todo/* ref was pushed.
    refs = _bare_refs(bare)
    assert not [r for r in refs if OC_TODO_REF_RE.match(r)]
    # Worktree cleaned up.
    wt_root = tmp_path / "sandbox" / "wt"
    assert not [p for p in wt_root.rglob("*") if p.is_dir()] if wt_root.exists() else True

    # Run 2: ok → PRs created; state pr_open; attempts == 2.
    wf2 = make_wf(cfg, fake_gh, FakeRunner("ok"))
    r2 = wf2.run(ctx)
    assert r2.status == "ok"
    assert len(fake_gh.prs) == 2
    st2 = _state_doc(ctx)
    for tid in failed_tids:
        entry = st2["todos"][tid]
        assert entry["status"] == "pr_open"
        assert entry["attempts"] == 2


def test_step_exhausted_treated_as_failure(tmp_path: Path) -> None:
    """[AC4 steps] A step-exhausted agent → failed; a retry with ok opens a PR."""
    bare, _ = _make_fixture_repo(tmp_path)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    fake_gh = FakeGitHub()

    wf1 = make_wf(cfg, fake_gh, FakeRunner("step-exhausted"))
    r1 = wf1.run(ctx)
    assert r1.status == "error"
    st1 = _state_doc(ctx)
    for tid, entry in st1["todos"].items():
        assert entry["status"] == "failed"
        assert "step cap" in entry["last_error"] or "steps" in entry["last_error"]
    # No push, no PR.
    refs = _bare_refs(bare)
    assert not [r for r in refs if OC_TODO_REF_RE.match(r)]
    assert len(fake_gh.prs) == 0

    wf2 = make_wf(cfg, fake_gh, FakeRunner("ok"))
    r2 = wf2.run(ctx)
    assert r2.status == "ok"
    assert len(fake_gh.prs) == 2


def test_blockers_report_fails_no_pr(tmp_path: Path) -> None:
    """[blocker gate] A blockers report → failed (reason carries the text); no PR/branch."""
    bare, _ = _make_fixture_repo(tmp_path)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    fake_gh = FakeGitHub()

    wf = make_wf(cfg, fake_gh, FakeRunner("blockers"))
    result = wf.run(ctx)
    assert result.status == "error"
    st = _state_doc(ctx)
    for tid, entry in st["todos"].items():
        assert entry["status"] == "failed"
        assert "tests fail: 2 errors" in entry["last_error"]
    # No oc-todo/* branch on the bare remote; no PR.
    refs = _bare_refs(bare)
    assert not [r for r in refs if OC_TODO_REF_RE.match(r)]
    assert len(fake_gh.prs) == 0


def test_cap_limits_and_drains(tmp_path: Path) -> None:
    """[caps] 4 markers on main, cap 2 → run1: 2 PRs + note; run2: 2 more; run3: zero."""
    # Single-branch fixture (no dev) with 3 extra main markers = 4 total on main.
    bare, _ = _make_fixture_repo(tmp_path, with_dev=False, extra_main_markers=3)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)}, max_todos_per_repo=2)
    ctx = make_ctx(tmp_path, cfg)
    fake_gh = FakeGitHub()

    r1 = make_wf(cfg, fake_gh, FakeRunner("ok")).run(ctx)
    assert len(fake_gh.prs) == 2
    assert any("not processed this run" in a for a in r1.actions), f"no cap note: {r1.actions}"

    r2 = make_wf(cfg, fake_gh, FakeRunner("ok")).run(ctx)
    assert len(fake_gh.prs) == 4
    assert r2.status == "ok"

    r3 = make_wf(cfg, fake_gh, FakeRunner("ok")).run(ctx)
    assert len(fake_gh.prs) == 4  # zero new PRs
    assert r3.status == "ok"


def test_only_fresh_branches_pushed(tmp_path: Path) -> None:
    """[AC5] Every new ref is oc-todo/<12hex>; main and dev SHAs are byte-identical."""
    bare, _ = _make_fixture_repo(tmp_path)
    before = _bare_refs(bare)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    wf = make_wf(cfg, FakeGitHub(), FakeRunner("ok"))
    wf.run(ctx)

    after = _bare_refs(bare)
    new_refs = [r for r in after if r not in before]
    assert len(new_refs) == 2
    for ref in new_refs:
        assert OC_TODO_REF_RE.match(ref), f"unexpected new ref: {ref}"
    # main and dev are byte-identical before/after.
    assert after["refs/heads/main"] == before["refs/heads/main"]
    assert after["refs/heads/dev"] == before["refs/heads/dev"]


def test_agent_no_op_fails(tmp_path: Path) -> None:
    """[commit-False] A no-op agent (no changes) → failed 'no changes'; no PR."""
    bare, _ = _make_fixture_repo(tmp_path)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)
    fake_gh = FakeGitHub()

    wf = make_wf(cfg, fake_gh, FakeRunner("no-op"))
    result = wf.run(ctx)
    assert result.status == "error"
    st = _state_doc(ctx)
    for tid, entry in st["todos"].items():
        assert entry["status"] == "failed"
        assert "no changes" in entry["last_error"]
    assert len(fake_gh.prs) == 0
    refs = _bare_refs(bare)
    assert not [r for r in refs if OC_TODO_REF_RE.match(r)]


def test_orphan_branch_resumes_without_agent(tmp_path: Path) -> None:
    """[orphan resume] A pre-pushed oc-todo/<id> branch (no PR) → PR without an agent run."""
    # Single-marker fixture (main only) so the ONLY todo is the orphan — the raising runner
    # proves the agent is never invoked on the resume path.
    bare, facts = _make_fixture_repo(tmp_path, with_dev=False)
    cfg = _write_config(tmp_path, repos=[REPO], repo_urls={REPO: str(bare)})
    ctx = make_ctx(tmp_path, cfg)

    # Pre-push a branch oc-todo/<tid_a> with the fixed file (marker removed), 1 commit.
    tid_a = todo_id(REPO, "main", facts["main"]["file"], MARKER_A)
    branch = f"oc-todo/{tid_a}"
    scratch = tmp_path / "scratch"
    git = Git()
    git.clone(str(bare), scratch)
    _git(scratch, "checkout", "-b", branch, "origin/main")
    a_text = (scratch / "src" / "a.py").read_text(encoding="utf-8")
    (scratch / "src" / "a.py").write_text(
        a_text.replace(MARKER_A + "\n", "# fixed by oc-todo-resolver\n"), encoding="utf-8"
    )
    git.add(scratch)
    assert git.commit(scratch, "OC: fix bug A in alpha()") is True
    git.push(scratch, branch, upstream=True)

    # A runner that raises if called (the orphan path must never invoke the agent).
    raiser = RaisingRunner()
    fake_gh = FakeGitHub()
    wf = make_wf(cfg, fake_gh, raiser)
    result = wf.run(ctx)

    assert result.status == "ok"
    assert raiser.calls == []  # the agent was never invoked
    # A PR was created from the orphan branch (head = that branch, base = main).
    a_prs = [pr for pr in fake_gh.prs if pr["base"] == "main"]
    assert len(a_prs) == 1
    assert a_prs[0]["head"] == f"fixture:{branch}"
    assert "Branch reused from a previous run" in a_prs[0]["body"]
