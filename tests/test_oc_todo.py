"""Hermetic tests for the oc-todo workflow core (Task 3).

Two groups: (A) pure logic — identity, scan parsing, keep-instruction detection, the
run-planning decision table, and the byte-stable renderers (no git); and (B) real-git
helper tests that exercise :meth:`Git.grep_fixed` / :meth:`Git.show_file` /
:meth:`Git.delete_branch` against throwaway local repos (mirroring ``tests/test_git.py``:
a bare repo is the "remote", identity set via ``os.environ.setdefault`` at import).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from agentic_scripts.config import OCTodo
from agentic_scripts.git import Git, GitError
from agentic_scripts.workflows.oc_todo import (
    MARKER_PREFIX,
    Todo,
    _is_step_exhausted,
    apply_cap,
    clone_dir,
    clone_env_for,
    extract_report_sections,
    fresh_state,
    has_keep_instruction,
    make_entry,
    parse_grep_lines,
    plan_run,
    pr_state_from_api,
    render_brief,
    render_pr_body,
    render_pr_title,
    repo_slug,
    todo_branch_name,
    todo_id,
    validate_state,
    worktree_dir,
)

# Git identity for every subprocess spawned by the real-git tests (set at import so it is
# present before the first commit; setdefault never clobbers a real environment).
os.environ.setdefault("GIT_AUTHOR_NAME", "Test Author")
os.environ.setdefault("GIT_AUTHOR_EMAIL", "author@example.test")
os.environ.setdefault("GIT_COMMITTER_NAME", "Test Committer")
os.environ.setdefault("GIT_COMMITTER_EMAIL", "committer@example.test")


# --------------------------------------------------------------------------- #
# Test helpers (real-git setup, mirroring tests/test_git.py)
# --------------------------------------------------------------------------- #


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a raw git command in ``path`` (test setup helper)."""
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    )


def init_repo(path: Path, branch: str = "main") -> Path:
    """Initialize a repo with one commit on ``branch``; return the path.

    Args:
        path: Directory to initialize (created if missing).
        branch: Initial branch name.

    Returns:
        The initialized repository path.
    """
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", branch)
    (path / "file.txt").write_text("initial\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "initial commit")
    return path


def init_bare(path: Path, head_branch: str = "main") -> None:
    """Initialize a bare repo to act as the local "remote".

    Args:
        path: Directory for the bare repository (created if missing).
        head_branch: Branch the bare repo's HEAD symref points at.
    """
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--bare")
    _git(path, "symbolic-ref", "HEAD", f"refs/heads/{head_branch}")


@pytest.fixture
def git() -> Git:
    """A fresh stateless Git helper."""
    return Git()


# --------------------------------------------------------------------------- #
# A. Pure logic (no git)
# --------------------------------------------------------------------------- #


def test_repo_slug_and_layout_paths(tmp_path: Path) -> None:
    """repo_slug maps owner/name -> owner__name; clone/worktree dirs nest under it."""
    assert repo_slug("owner/name") == "owner__name"

    sandbox = tmp_path / "oc-todo"
    assert clone_dir(sandbox, "owner/name") == sandbox / "clones" / "owner__name"
    assert worktree_dir(sandbox, "owner/name", "abc123def456") == (
        sandbox / "wt" / "owner__name" / "abc123def456"
    )


def test_todo_id_stable_distinct_and_hex() -> None:
    """todo_id is stable, 12 hex chars, and distinct for different identities."""
    a = todo_id("o/r", "dev", "src/x.py", "OC-todo: fix x")
    assert a == todo_id("o/r", "dev", "src/x.py", "OC-todo: fix x")  # stable
    assert len(a) == 12
    int(a, 16)  # raises ValueError if not hex

    b = todo_id("o/r", "dev", "src/x.py", "OC-todo: fix y")  # different marker
    c = todo_id("o/r", "main", "src/x.py", "OC-todo: fix x")  # different branch
    d = todo_id("o/other", "dev", "src/x.py", "OC-todo: fix x")  # different repo
    e = todo_id("o/r", "dev", "src/y.py", "OC-todo: fix x")  # different file
    assert len({a, b, c, d, e}) == 5


def test_todo_branch_name() -> None:
    """todo_branch_name prefixes the id with oc-todo/ (fresh-branch invariant)."""
    assert todo_branch_name("abc123def456") == "oc-todo/abc123def456"


def test_parse_grep_lines_exact_shape() -> None:
    """An exact-shape line parses into a Todo with the right fields; keep is False."""
    ref = "origin/dev"
    todos = parse_grep_lines("o/r", "dev", ref, [f"{ref}:src/a.py:7:{MARKER_PREFIX} do x"])
    assert len(todos) == 1
    t = todos[0]
    assert (t.repo, t.branch, t.file, t.line, t.marker, t.keep) == (
        "o/r",
        "dev",
        "src/a.py",
        7,
        f"{MARKER_PREFIX} do x",
        False,
    )


def test_parse_grep_lines_colon_in_file_path() -> None:
    """A ":" inside the file path is handled by the greedy file group."""
    ref = "origin/dev"
    todos = parse_grep_lines("o/r", "dev", ref, [f"{ref}:src/a:b.py:7:{MARKER_PREFIX} x"])
    assert len(todos) == 1
    assert todos[0].file == "src/a:b.py"
    assert todos[0].line == 7


def test_parse_grep_lines_drops_non_marker_and_bad_lines() -> None:
    """Content without the marker prefix is dropped; non-integer line numbers skipped."""
    ref = "origin/dev"
    lines = [
        f"{ref}:src/a.py:3:some other line",  # no marker prefix -> dropped
        f"{ref}:src/b.py:notanumber:{MARKER_PREFIX} x",  # bad line number -> skipped
        f"{ref}:src/c.py:9:{MARKER_PREFIX} kept",  # valid -> kept
    ]
    todos = parse_grep_lines("o/r", "dev", ref, lines)
    assert len(todos) == 1
    assert todos[0].file == "src/c.py"
    assert todos[0].marker == f"{MARKER_PREFIX} kept"


def test_has_keep_instruction() -> None:
    """oc-original (any case) in the window -> True; clean lines -> False."""
    marker = f"# {MARKER_PREFIX} do it"
    assert has_keep_instruction([f"{marker} (oc-original: keep this marker)"]) is True
    assert has_keep_instruction([f"{marker} (OC-ORIGINAL: keep)"]) is True  # case-insensitive
    assert has_keep_instruction([marker, "line1", "line2", "line3"]) is False
    # oc-original on the 3rd context line (marker + next 3 lines) -> True
    assert has_keep_instruction([marker, "l1", "l2", "# note: oc-original here"]) is True


def _entry(status: str | None, tid: str = "x" * 12) -> dict:
    """Build a minimal state entry (or return {} for the absent case)."""
    if status is None:
        return {}
    return {"status": status}


@pytest.mark.parametrize(
    ("entry", "pr_state", "expected_action", "expected_reason"),
    [
        # --- 8 current-todo matrix cells (entry status x pr_state) ---
        ({}, None, "process", None),  # absent
        ({"status": "failed"}, None, "process", None),  # failed
        (
            {"status": "resolved"},
            None,
            "process",
            "marker reappeared after resolution — re-attempt",
        ),
        ({"status": "pr_open"}, "open", "skip", "PR already open"),
        ({"status": "pr_open"}, "merged", "resolve", None),
        ({"status": "pr_open"}, "closed", "process", "PR closed unmerged — retry"),
        ({"status": "pr_open"}, "missing", "process", "recorded PR no longer exists — re-verify"),
        (
            {"status": "pr_open"},
            None,
            "skip",
            "PR state unknown (API error) — guardrail: no re-creation",
        ),
    ],
)
def test_plan_run_current_matrix(
    entry: dict, pr_state: str | None, expected_action: str, expected_reason: str | None
) -> None:
    """plan_run classifies each current-todo cell per the decision table."""
    todo = Todo(repo="o/r", branch="dev", file="f.py", line=1, marker=f"{MARKER_PREFIX} m")
    tid = todo.id  # derived identity — state is keyed by it
    st = {"version": 1, "todos": {tid: entry}} if entry else {"version": 1, "todos": {}}
    pr_states = {tid: pr_state} if pr_state is not None or entry.get("status") == "pr_open" else {}

    actions = plan_run([todo], st, pr_states)
    assert len(actions) == 1
    action = actions[0]
    assert action["action"] == expected_action
    assert action["todo"] is todo
    if expected_reason is None:
        assert "reason" not in action
    else:
        assert action.get("reason") == expected_reason


@pytest.mark.parametrize("status", ["pr_open", "failed"])
def test_plan_run_vanished_entries(status: str) -> None:
    """A recorded entry whose marker vanished resolves, regardless of its status."""
    tid = "b" * 12
    st = {"version": 1, "todos": {tid: {"status": status}}}
    actions = plan_run([], st, {})
    assert len(actions) == 1
    action = actions[0]
    assert action["action"] == "resolve"
    assert action["entry_id"] == tid
    assert action["entry"]["status"] == status
    assert action["reason"] == "marker no longer present"


def test_plan_run_mixed_current_and_vanished() -> None:
    """Current todos and vanished entries are both emitted in one pass."""
    todo = Todo(repo="o/r", branch="dev", file="f.py", line=1, marker=f"{MARKER_PREFIX} m")
    tid_gone = "d" * 12  # a recorded id that is NOT the current todo's derived id
    assert todo.id != tid_gone
    st = {"version": 1, "todos": {tid_gone: {"status": "pr_open"}}}
    actions = plan_run([todo], st, {})
    assert len(actions) == 2
    by_action = {a["action"] for a in actions}
    assert by_action == {"process", "resolve"}


def test_render_brief_exact_format() -> None:
    """render_brief emits the exact header, verbatim marker, and both keep wordings."""
    todo = Todo(repo="o/r", branch="dev", file="src/a.py", line=7, marker=f"{MARKER_PREFIX} do x")

    brief_no_keep = render_brief("run-123", todo, None)
    lines = brief_no_keep.splitlines()
    assert lines[0] == (
        "oc-todo-resolver run run-123 — resolve exactly ONE OC-todo marker in this "
        "sandboxed worktree."
    )
    assert f"Marker: {MARKER_PREFIX} do x" in lines  # verbatim marker
    assert "Test command: none" in lines  # no test command
    assert "Keep-instruction: no — implement the todo and remove the marker line exactly" in lines

    keep_todo = Todo(
        repo="o/r", branch="dev", file="src/a.py", line=7, marker=f"{MARKER_PREFIX} do x", keep=True
    )
    brief_keep = render_brief("run-123", keep_todo, "uv run pytest")
    assert "Test command: uv run pytest" in brief_keep.splitlines()
    assert (
        "Keep-instruction: yes — implement the todo but leave the marker line verbatim"
        in brief_keep.splitlines()
    )


def test_render_pr_title_strip_collapse_truncate() -> None:
    """render_pr_title strips the decoration + prefix, collapses whitespace, cuts at 72."""
    # Prefix stripped + leading/trailing whitespace collapsed.
    assert render_pr_title(f"{MARKER_PREFIX}   fix   the thing  ") == "OC: fix the thing"

    # A comment-decorated marker (the typical shape) strips the decoration first.
    assert render_pr_title(f"# {MARKER_PREFIX} fix bug A") == "OC: fix bug A"
    # Other comment decorations are stripped too (% with no space, //).
    assert render_pr_title(f"%{MARKER_PREFIX} do x") == "OC: do x"
    assert render_pr_title(f"// {MARKER_PREFIX} do y") == "OC: do y"
    # A bare (undecorated) marker still works.
    assert render_pr_title(f"{MARKER_PREFIX} fix") == "OC: fix"

    # A 200-char marker body is truncated to exactly 72 chars after the "OC: " prefix.
    long_body = "x" * 200
    title = render_pr_title(f"{MARKER_PREFIX} {long_body}")
    assert title.startswith("OC: ")
    assert len(title) == len("OC: ") + 72
    assert title == "OC: " + ("x" * 72)

    # A decorated 200-char marker still truncates at 72 (decoration stripped first).
    decorated = render_pr_title(f"# {MARKER_PREFIX} {long_body}")
    assert len(decorated) == len("OC: ") + 72


def test_extract_report_sections_full_and_missing() -> None:
    """extract_report_sections pulls all four sections; missing/None handled."""
    report = (
        "# oc-todo-resolver Output\n"
        "\n"
        "## Summary\n"
        "Fixed the parser.\n"
        "\n"
        "## Files\n"
        "| File | Action |\n"
        "|---|---|\n"
        "| `a.py` | modify |\n"
        "\n"
        "## Build / Tests\n"
        "- `uv run pytest`: PASS\n"
        "\n"
        "## Acceptance Verification\n"
        "- Marker removed? YES\n"
        "\n"
        "## Blockers\n"
        "None\n"
    )
    sections = extract_report_sections(report)
    assert sections["has_report"] is True
    assert sections["summary"] == "Fixed the parser."
    assert "a.py" in sections["files"]
    assert "PASS" in sections["tests"]
    assert sections["blockers"].lower() == "none"

    # A report missing ## Blockers -> blockers "" (other sections still extracted).
    no_blockers = "## Summary\nS\n\n## Files\nF\n\n## Build / Tests\nT\n"
    got = extract_report_sections(no_blockers)
    assert got["blockers"] == ""
    assert got["summary"] == "S"

    # None input -> all empty + has_report False.
    empty = extract_report_sections(None)
    assert empty == {"summary": "", "files": "", "tests": "", "blockers": "", "has_report": False}


def test_render_pr_body_format_and_fallbacks() -> None:
    """render_pr_body quotes the marker in a fence, names location/branch/run id, and falls back."""
    todo = Todo(repo="o/r", branch="dev", file="src/a.py", line=7, marker=f"{MARKER_PREFIX} do x")

    empty_sections = {"summary": "", "files": "", "tests": "", "blockers": ""}
    body = render_pr_body(todo, "o/r", empty_sections, "run-9")
    lines = body.splitlines()
    assert "```" in lines  # the marker fence
    # The marker appears verbatim inside the fence.
    fence_idx = lines.index("```")
    assert lines[fence_idx + 1] == f"{MARKER_PREFIX} do x"
    assert "- **Location:** `src/a.py` line `7`" in lines
    assert "- **Base branch:** `dev`" in lines
    assert "run-9" in body  # run id in the footer
    # Empty sections -> fallbacks.
    assert "(agent report unavailable)" in body
    assert "\n\n-\n" in body  # the files/tests "-" fallback

    # Non-empty sections are embedded verbatim.
    body2 = render_pr_body(
        todo, "o/r", {"summary": "S", "files": "F", "tests": "T", "blockers": ""}, "run-9"
    )
    assert "\n## Agent summary\n\nS\n" in body2


def test_is_step_exhausted() -> None:
    """_is_step_exhausted fires on both boilerplate phrases (any case), else False."""
    assert _is_step_exhausted("Maximum Steps Reached") is True
    assert _is_step_exhausted("the run hit the Maximum Number of Steps Allowed cap") is True
    assert _is_step_exhausted("## Summary\nAll done, tests pass.") is False
    assert _is_step_exhausted(None) is False


def test_apply_cap() -> None:
    """apply_cap splits first-cap vs rest; a large cap processes everything."""
    todos = [
        Todo(repo="o/r", branch="dev", file=f"f{i}.py", line=1, marker=f"{MARKER_PREFIX} m{i}")
        for i in range(4)
    ]
    to_process, not_processed = apply_cap(todos, 2)
    assert len(to_process) == 2 and len(not_processed) == 2
    assert to_process == todos[:2] and not_processed == todos[2:]

    all_done, none_left = apply_cap(todos[:2], 5)
    assert all_done == todos[:2] and none_left == []


def test_clone_env_for() -> None:
    """clone_env_for returns the exact 3-key auth triple for a PAT; None/empty -> None."""
    env = clone_env_for("ghp_secret123")
    assert env == {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": "Authorization: Bearer ghp_secret123",
    }
    assert clone_env_for(None) is None
    assert clone_env_for("") is None


def test_validate_state() -> None:
    """validate_state accepts first-run and v1; rejects wrong version / non-dict todos."""
    assert validate_state({}) is None  # first run
    assert validate_state({"version": 1, "todos": {}}) is None

    bad_version = validate_state({"version": 2, "todos": {}})
    assert bad_version is not None
    assert "state schema mismatch" in bad_version
    assert "delete state/oc-todo.json" in bad_version

    bad_todos = validate_state({"version": 1, "todos": [1]})
    assert bad_todos is not None
    assert "state schema mismatch" in bad_todos


def test_fresh_state_and_make_entry() -> None:
    """fresh_state is v1-empty; make_entry stamps status/attempts/updated_at."""
    assert fresh_state() == {"version": 1, "todos": {}}

    todo = Todo(repo="o/r", branch="dev", file="f.py", line=3, marker=f"{MARKER_PREFIX} m")
    entry = make_entry(todo, "pr_open", pr_number=42)
    assert entry["status"] == "pr_open"
    assert entry["attempts"] == 0
    assert entry["pr_number"] == 42
    assert entry["repo"] == "o/r" and entry["marker"] == f"{MARKER_PREFIX} m"
    assert "updated_at" in entry


def test_pr_state_from_api() -> None:
    """pr_state_from_api maps merged / open / closed, defaulting odd states to closed."""
    assert pr_state_from_api({"merged": True, "state": "open"}) == "merged"
    assert pr_state_from_api({"merged": False, "state": "open"}) == "open"
    assert pr_state_from_api({"merged": False, "state": "closed"}) == "closed"
    assert pr_state_from_api({"merged": False, "state": "weird"}) == "closed"


def test_octodo_workflow_shell() -> None:
    """OCTodoWorkflow exposes name and stores injected collaborators (defaults when None)."""
    from agentic_scripts.workflows.oc_todo import OCTodoWorkflow

    settings = OCTodo(repos=["o/r"], max_todos_per_repo=3, test_commands={}, repo_urls={})
    wf = OCTodoWorkflow(settings)
    assert wf.name == "oc-todo"
    assert isinstance(wf._git, Git)
    assert wf._runner_override is None

    class FakeGit:  # noqa: D101 - minimal test double
        pass

    fake_git = FakeGit()
    wf2 = OCTodoWorkflow(settings, git=fake_git)
    assert wf2._git is fake_git


# --------------------------------------------------------------------------- #
# B. Real-git helper tests (throwaway local repos)
# --------------------------------------------------------------------------- #


def _build_remote_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """Build a bare remote with main + side branches and a full clone of it.

    Returns:
        A ``(bare, clone)`` tuple; the clone has ``origin/main`` (marker "alpha") and
        ``origin/side`` (a different marker). The clone is left checked out on main.
    """
    src = init_repo(tmp_path / "src", branch="main")
    # main: one marker line.
    (src / "todo.txt").write_text(f"{MARKER_PREFIX} alpha\n", encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "commit", "-m", "add main marker")

    # side: a different marker on its own branch.
    _git(src, "checkout", "-b", "side")
    (src / "todo.txt").write_text(f"{MARKER_PREFIX} beta\n", encoding="utf-8")
    _git(src, "commit", "-am", "change side marker")

    bare = tmp_path / "remote.git"
    init_bare(bare)
    _git(src, "remote", "add", "origin", str(bare))
    _git(src, "push", "-u", "origin", "main")
    _git(src, "push", "-u", "origin", "side")

    clone = tmp_path / "clone"
    Git().clone(str(bare), clone)
    return bare, clone


def test_grep_fixed_main_side_and_no_match(git: Git, tmp_path: Path) -> None:
    """grep_fixed returns the ref-prefixed marker line; a branch with no marker -> []."""
    _bare, clone = _build_remote_and_clone(tmp_path)

    main_lines = git.grep_fixed(clone, "origin/main", MARKER_PREFIX)
    assert len(main_lines) == 1
    assert main_lines[0].startswith("origin/main:")
    assert "alpha" in main_lines[0]

    side_lines = git.grep_fixed(clone, "origin/side", MARKER_PREFIX)
    assert len(side_lines) == 1
    assert side_lines[0].startswith("origin/side:")
    assert "beta" in side_lines[0]

    # A branch with no marker -> exit-1 path -> []. Build it on a separate worktree so the
    # clone's checkout stays clean, then grep the committed ref (a local branch name).
    wt = tmp_path / "wt-clean"
    git.worktree_add(clone, wt, "clean", "origin/main")
    (wt / "todo.txt").write_text("no marker here\n", encoding="utf-8")
    _git(wt, "commit", "-am", "remove marker on clean")
    assert git.grep_fixed(clone, "clean", MARKER_PREFIX) == []


def test_grep_fixed_excludes_binary(git: Git, tmp_path: Path) -> None:
    """grep_fixed skips binary files (-I); a committed ref has no untracked files to ignore.

    Note:
        The spec's ``--exclude-standard`` (.gitignore) sub-case is not exercisable here —
        git errors (exit 128) when ``--exclude-standard`` is combined with a committed ref,
        and a committed ref contains no untracked files for it to filter. The binary-exclusion
        half of the spec's "standard exclusions" is what ``-I`` provides and is tested below.
    """
    _bare, clone = _build_remote_and_clone(tmp_path)

    # Binary file containing the marker bytes (a NUL byte makes git treat it as binary).
    (clone / "blob.bin").write_bytes(b"\x00\x01" + MARKER_PREFIX.encode() + b"\xff")
    _git(clone, "add", "-A")
    sha = _git(clone, "commit", "-m", "add binary marker file").stdout.strip()

    lines = git.grep_fixed(clone, sha, MARKER_PREFIX)
    joined = "\n".join(lines)
    assert "blob.bin" not in joined  # -I skips the binary file


def test_show_file_at_ref_and_missing(git: Git, tmp_path: Path) -> None:
    """show_file returns the file content at origin/main; a missing path raises GitError."""
    _bare, clone = _build_remote_and_clone(tmp_path)

    content = git.show_file(clone, "origin/main", "todo.txt")
    assert content == f"{MARKER_PREFIX} alpha"  # trailing newline stripped

    with pytest.raises(GitError):
        git.show_file(clone, "origin/main", "does-not-exist.txt")


def test_delete_branch(git: Git, tmp_path: Path) -> None:
    """delete_branch removes a local branch; rev_parse then raises GitError."""
    _bare, clone = _build_remote_and_clone(tmp_path)

    # Create the branch without checking it out (a checked-out branch cannot be deleted).
    _git(clone, "branch", "temp-branch")
    git.delete_branch(clone, "temp-branch")  # force=True -> -D
    with pytest.raises(GitError):
        git.rev_parse(clone, "temp-branch")
