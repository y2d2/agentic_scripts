"""Hermetic end-to-end smoke test for the mail-keeper workflow (Task 4).

Drives a real forced ``run()`` of the SHIPPED-style config (paths/env pointed at fixtures)
through the full pipeline — canary, backfill start (first run = oldest batch of the fixture
history), detection, one agent invocation (a deterministic fake ``opencode`` shim performing
the agent's contract: provenance-tagged vault edit + todo line + draft + ``OC:`` commit +
push), processed-log append, cursor advance, backup byte-identity, no-new-mail re-run,
new-mail-after-backfill, and the agent-failure → retry path.

Everything is hermetic: throwaway maildir / notmuch index / vault git repo / bare remote /
shims under ``tmp_path``; NO real ``opencode``, NO live LLM, and NO writes to the production
Obsidian vault, the mbsync backup/index tree, or the real processed log. The test module never
references any of those live paths (acceptance #6 — verified by grep). All filesystem traversal
of the fixture maildir uses Python ``os.walk`` (GNU ``find`` is forbidden for this maildir).

The fake agent is a standalone executable Python 3 script written by the test (no third-party
imports). It parses argv (``--dir``, ``--title``, the final positional brief), performs the
deterministic vault edits + git commit/push, and emits an NDJSON event stream whose final
``text`` event carries the result report with the EXACT Triage table that Task 3's
``_parse_triage_classes`` parses. The brief format is the contract: the shim's manifest-line
parser matches the ACTUAL output of ``mail_keeper._render_brief`` (one line per entry,
date-ascending, ids WITHOUT angle brackets).

The fixture world mirrors the real vault's IA so the shim's writes are realistic:
``todos/active.md``, ``projects/ORBIT/00_Project_management/01_Meetings.md`` (with
``## EUG Meetings``), empty ``people/`` + ``mail/drafts/`` dirs, a ``.gitignore`` containing
``mail``, a baseline commit on branch ``feature/test``, and a bare remote named ``origin``.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from agentic_scripts.scheduler import run

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_CONFIG = REPO_ROOT / "config" / "workflows.yaml"

# --- Fixture identity (git + mail) ------------------------------------------- #
ACCOUNT = "acct@example.test"
OWNER = "yuri.durodie@vub.be"
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Fixture Author",
    "GIT_AUTHOR_EMAIL": "fixture@author.test",
    "GIT_COMMITTER_NAME": "Fixture Committer",
    "GIT_COMMITTER_EMAIL": "fixture@committer.test",
}

# --- Fixture message ids ----------------------------------------------------- #
M6_ID = "m6@fixture.test"  # OLD (~2 months back), INBOX — the backfill anchor (oldest)
M1_ID = "m1@fixture.test"  # recent, INBOX, plain (Coera) — the "action" message
M2_ID = "m2@fixture.test"  # recent, INBOX, multipart (Nikos)
M3_ID = "m3@fixture.test"  # recent, INBOX, HTML-only (Nikos)
M4_ID = "m4@fixture.test"  # recent, PII folder — must be excluded from the brief
M5_ID = "m5@fixture.test"  # recent, Sent Items, own mail — must be excluded from the brief
M7_ID = "m7@fixture.test"  # added by test 3 (newest)

# --- Fixture message bodies -------------------------------------------------- #
# m6: OLD (~2 months back), INBOX. Oldest → sorts first in the backfill batch.
M6 = f"""From: Old Sender <old@fixture.test>
To: someone@example.test
Subject: Backfill anchor old
Message-Id: <{M6_ID}>
Date: Mon, 17 Aug 2026 09:00:00 +0000
Content-Type: text/plain; charset=utf-8

An old message that the backfill must pick up first.
"""

# m1: recent (Oct 20), INBOX, plain from Coera — the "action" message.
M1 = f"""From: Coera <coera@orbit.example.test>
To: someone@example.test
Subject: EUG schedule
Message-Id: <{M1_ID}>
Date: Tue, 20 Oct 2026 10:00:00 +0000
Content-Type: text/plain; charset=utf-8

EUG session confirmed; deck due Friday.
"""

# m2: recent (Oct 20), INBOX, multipart (plain+html) from Nikos — noise.
M2 = f"""From: Nikos <nikos@orbit.example.test>
To: someone@example.test
Subject: Multipart two
Message-Id: <{M2_ID}>
Date: Tue, 20 Oct 2026 11:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="BOUNDARY"

--BOUNDARY
Content-Type: text/html; charset=utf-8

<p>Multipart html marker.</p>
--BOUNDARY
Content-Type: text/plain; charset=utf-8

Multipart plain marker.
--BOUNDARY--
"""

# m3: recent (Oct 20), INBOX, HTML-only from Nikos — noise.
M3 = f"""From: Nikos <nikos@orbit.example.test>
To: someone@example.test
Subject: Html three
Message-Id: <{M3_ID}>
Date: Tue, 20 Oct 2026 12:00:00 +0000
Content-Type: text/html; charset=utf-8

<html><body>HTML-only marker body.</body></html>
"""

# m4: recent (Oct 20), PII folder — excluded from detection/manifest.
M4 = f"""From: PhD Applicant <phd@fixture.test>
To: someone@example.test
Subject: PhD application (PII)
Message-Id: <{M4_ID}>
Date: Tue, 20 Oct 2026 13:00:00 +0000
Content-Type: text/plain; charset=utf-8

A PII-folder message that must never enter the manifest.
"""

# m5: recent (Oct 20), Sent Items, own mail — excluded (style sampling only).
M5 = f"""From: Yuri Durodie <{OWNER}>
To: coera@orbit.example.test
Subject: Own sent mail (style)
Message-Id: <{M5_ID}>
Date: Tue, 20 Oct 2026 14:00:00 +0000
Content-Type: text/plain; charset=utf-8

Own corpus message for style sampling only.
"""

# m7: newest (Oct 21), INBOX — added by test 3 to exercise new-mail-after-backfill.
M7 = f"""From: New Sender <new@fixture.test>
To: someone@example.test
Subject: Brand new mail
Message-Id: <{M7_ID}>
Date: Wed, 21 Oct 2026 09:30:00 +0000
Content-Type: text/plain; charset=utf-8

A brand-new message arriving after the backfill.
"""


# --- The fake ``opencode`` shim (the deterministic fake agent) --------------- #
# A standalone executable Python 3 script, written by the test into ``tmp_path`` and chmod
# 0755. No third-party imports. It mirrors the REAL agent contract (skills/mail-keeper):
# parse the brief's MANIFEST lines, perform provenance-tagged vault edits for the "action"
# message (m1), commit only the touched paths with an ``OC:`` message, push to origin, and
# emit an NDJSON stream whose final text event carries the result report with the EXACT
# Triage table that Task 3's _parse_triage_classes parses. The manifest-line parser matches
# the ACTUAL output of mail_keeper._render_brief (ids without angle brackets).
SHIM_SOURCE = r'''#!/usr/bin/env python3
"""Deterministic fake ``opencode`` shim for the mail-keeper smoke test.

Parses argv (--dir, --title, final positional brief), performs the agent's contract
(provenance-tagged vault edits + todo line + draft + OC: commit + push), and emits an NDJSON
event stream whose final text event is the result report with the Triage table. No
third-party imports; stdlib only. Writes its captured brief as its first act so failure-mode
briefs are capturable.
"""

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _git(vault: str, *args: str) -> None:
    """Run a git command in the vault (fixture identity via env); ignore failures."""
    try:
        subprocess.run(
            ["git", "-C", vault, *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception:
        pass


def _append_under(section_header: str, line: str, path: Path) -> None:
    """Append ``line`` immediately after the first occurrence of ``section_header``.

    Falls back to appending at end-of-file when the header is not found (robustness).
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    inserted = False
    for ln in lines:
        out.append(ln)
        if not inserted and ln.strip() == section_header:
            out.append(line + "\n")
            inserted = True
    if not inserted:
        out.append(line + "\n")
    path.write_text("".join(out), encoding="utf-8")


def main() -> int:
    argv = sys.argv[1:]

    def _flag(name: str) -> str | None:
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv):
                return argv[i + 1]
        return None

    vault = _flag("--dir") or os.getcwd()
    # The brief is the LAST positional argument (after any --title value).
    brief = argv[-1]

    # First act: capture the brief (so failure-mode briefs are capturable too).
    try:
        with open(os.path.join(vault, "..", "brief.txt"), "w", encoding="utf-8") as fh:
            fh.write(brief)
    except Exception:
        pass

    # Parse MANIFEST lines (the ACTUAL _render_brief format: ids WITHOUT angle brackets).
    entries: list[dict] = []
    in_manifest = False
    for line in brief.splitlines():
        if line.startswith("MANIFEST ("):
            in_manifest = True
            continue
        if not in_manifest:
            continue
        m = re.match(
            r"^\d+\.\s+(?P<id>\S+)\s*\|\s*(?P<folder>[^|]+?)\s*\|\s*"
            r"(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*(?P<from>[^|]+?)\s*\|\s*(?P<subject>.*)$",
            line,
        )
        if m:
            entries.append(m.groupdict())

    # The workflow already excludes PII + own mail; the shim just asserts their ABSENCE.
    for e in entries:
        assert "m4@fixture.test" not in e["id"], "PII message must not be in the manifest"
        assert "m5@fixture.test" not in e["id"], "own mail must not be in the manifest"

    today = datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
    touched: list[str] = []

    # m1 is the "action" message: meetings line + todo line + draft.
    for e in entries:
        if "m1@fixture.test" not in e["id"]:
            continue  # m6/m2/m3 (and any other) are noise → no writes
        date = e["date"]
        src = f'*(from: Coera, "EUG schedule", {date}, m1@fixture.test)*'

        meetings = Path(vault) / "projects" / "ORBIT" / "00_Project_management" / "01_Meetings.md"
        _append_under(
            "## EUG Meetings",
            f"- {date} EUG session confirmed; deck due Friday {src}",
            meetings,
        )
        touched.append("projects/ORBIT/00_Project_management/01_Meetings.md")

        todos = Path(vault) / "todos" / "active.md"
        _append_under(
            "## 📂 Projects",
            f"- [ ] Confirm EUG deck (from Coera — {date}) {src}",
            todos,
        )
        touched.append("todos/active.md")

        drafts_dir = Path(vault) / "mail" / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        draft = drafts_dir / f"{date}_eug-schedule.md"
        draft.write_text(
            f"To: Coera <coera@orbit.example.test>\n"
            f"Subject: Re: EUG schedule\n"
            "\n"
            "Hi Coera,\n"
            "Confirmed — I will have the deck ready by Friday.\n"
            "Thanks for the heads-up.\n"
            "---\n"
            f'*(from: Me, "draft reply to EUG schedule", {date}, m1@fixture.test)*\n',
            encoding="utf-8",
        )
        touched.append(f"mail/drafts/{date}_eug-schedule.md")

    # Git: add only the touched paths (drafts are gitignored → not staged), commit, push.
    if touched:
        _git(vault, "add", *touched)
        _git(
            vault,
            "commit",
            "-m",
            f"OC: mail triage ({len(entries)} mail(s) triaged, 2 vault edit(s), 1 draft(s))",
        )
    _git(vault, "push", "origin", "HEAD")

    # Triage table: one row per manifest id received (the backfill batch is m6,m1,m2,m3).
    header = "| msg-id | folder | from | class | action taken |"
    sep = "|---|---|---|---|---|"
    rows = ["## Triage", header, sep]
    for e in entries:
        if "m1@fixture.test" in e["id"]:
            cls, action = "action", "meetings+todo+draft"
        else:
            cls, action = "noise", "logged only"
        folder = e["folder"].strip()
        sender = e["from"].strip()
        rows.append(f"| {e['id']} | {folder} | {sender} | {cls} | {action} |")
    report = "\n".join(rows)

    # NDJSON event stream (matches the opencode run --format json schema).
    ts = datetime.now(UTC).isoformat()
    for event in (
        {"type": "step_start", "timestamp": ts},
        {"type": "tool_use", "timestamp": ts, "tool": "bash"},
        {"type": "text", "timestamp": ts, "part": {"text": report}},
    ):
        print(json.dumps(event), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

# The failure shim: writes the brief (first act), emits an NDJSON error event, exits 1.
SHIM_FAIL_SOURCE = r'''#!/usr/bin/env python3
"""Failure-mode fake ``opencode`` shim for the mail-keeper smoke test.

Writes its captured brief as its first act, then emits a single NDJSON error event and
exits 1 (so AgentRunner maps it to status="error"). No vault edits, no git.
"""

import json
import os
import sys
from datetime import UTC, datetime


def main() -> int:
    argv = sys.argv[1:]
    if "--dir" in argv:
        i = argv.index("--dir")
        vault = argv[i + 1] if i + 1 < len(argv) else os.getcwd()
    else:
        vault = os.getcwd()
    brief = argv[-1]

    try:
        with open(os.path.join(vault, "..", "brief.txt"), "w", encoding="utf-8") as fh:
            fh.write(brief)
    except Exception:
        pass

    ts = datetime.now(UTC).isoformat()
    err_event = {"type": "error", "timestamp": ts, "error": "simulated agent failure"}
    print(json.dumps(err_event), flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


# --- Fixture builders -------------------------------------------------------- #
def _write_message(folder_rel: str, filename: str, body: str, mail_root: Path) -> None:
    """Write one .eml into ``mail_root/<ACCOUNT>/<folder_rel>/cur/``."""
    cur = mail_root / ACCOUNT / folder_rel / "cur"
    cur.mkdir(parents=True, exist_ok=True)
    (cur / filename).write_text(body, encoding="utf-8")


def _build_maildir(mail_root: Path) -> None:
    """Create the six-message fixture maildir under ``mail_root/<ACCOUNT>/``."""
    _write_message("INBOX", "m6.eml", M6, mail_root)
    _write_message("INBOX", "m1.eml", M1, mail_root)
    _write_message("INBOX", "m2.eml", M2, mail_root)
    _write_message("INBOX", "m3.eml", M3, mail_root)
    _write_message("INBOX/FU-Admin/PhD_applications", "m4.eml", M4, mail_root)
    _write_message("Sent Items", "m5.eml", M5, mail_root)


def _notmuch_new(index_path: Path, mail_root: Path, work_dir: Path) -> None:
    """Write a reader-style notmuch config and run ``notmuch new`` to (re)index.

    Test *setup only* — the workflow's :class:`NotmuchReader` never calls ``new`` itself.
    Re-running over an existing index adds any new maildir files (used by test 3).
    """
    index_path.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    config_text = (
        "[database]\n"
        f"path={index_path.resolve()}\n"
        f"mail_root={mail_root.resolve()}\n"
        "[maildir]\n"
        "synchronize_flags=false\n"
    )
    config_path = work_dir / "setup-config"
    config_path.write_text(config_text, encoding="utf-8")
    config_path.chmod(0o600)

    env = {**os.environ, **GIT_IDENTITY, "NOTMUCH_CONFIG": str(config_path)}
    proc = subprocess.run(["notmuch", "new"], capture_output=True, text=True, env=env, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"notmuch new failed: {proc.stderr}")


def _git(vault: Path, *args: str) -> None:
    """Run a git command in the fixture vault with the fixture identity (raises on error)."""
    env = {**os.environ, **GIT_IDENTITY}
    proc = subprocess.run(
        ["git", "-C", str(vault), *args], capture_output=True, text=True, timeout=60, env=env
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")


def _build_vault(vault: Path, bare_remote: Path) -> None:
    """Create the fixture vault git repo (mirroring the real vault's IA) + bare remote.

    Sets up: ``todos/active.md``, ``projects/ORBIT/00_Project_management/01_Meetings.md``
    (with ``## EUG Meetings``), empty ``people/`` + ``mail/drafts/`` dirs, a ``.gitignore``
    containing ``mail``, a baseline commit on branch ``feature/test``, and a bare remote
    named ``origin`` with an initial push (so the shim's ``git push origin HEAD`` works).
    """
    vault.mkdir(parents=True, exist_ok=True)

    # todos/active.md with the required section headers.
    todos = vault / "todos"
    todos.mkdir(exist_ok=True)
    (todos / "active.md").write_text(
        "# Active Tasks\n\n## 📂 Projects\n\n## 💰 Funding & Grants\n\n## ⏳ Waiting On\n",
        encoding="utf-8",
    )

    # projects/ORBIT/00_Project_management/01_Meetings.md with ## EUG Meetings.
    meetings_dir = vault / "projects" / "ORBIT" / "00_Project_management"
    meetings_dir.mkdir(parents=True, exist_ok=True)
    (meetings_dir / "01_Meetings.md").write_text(
        "# ORBIT Meetings\n\n## EUG Meetings\n", encoding="utf-8"
    )

    # people/ (empty + .gitkeep) and mail/drafts/ (empty + .gitkeep).
    (vault / "people").mkdir(exist_ok=True)
    (vault / "people" / ".gitkeep").write_text("", encoding="utf-8")
    (vault / "mail" / "drafts").mkdir(parents=True, exist_ok=True)
    (vault / "mail" / "drafts" / ".gitkeep").write_text("", encoding="utf-8")

    # .gitignore containing "mail" (so drafts are gitignored).
    (vault / ".gitignore").write_text("mail\n", encoding="utf-8")

    # Git: init, baseline commit on feature/test, bare remote + initial push.
    _git(vault, "init", "-q", "-b", "feature/test")
    _git(vault, "add", "-A")
    _git(vault, "commit", "-q", "-m", "OC: baseline fixture vault")

    bare_remote.mkdir(parents=True, exist_ok=True)
    _git(bare_remote, "init", "-q", "--bare")
    _git(vault, "remote", "add", "origin", str(bare_remote))
    _git(vault, "push", "-q", "origin", "HEAD")


def _write_shim(path: Path, source: str) -> None:
    """Write a shim script to ``path`` and chmod it 0755."""
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _backup_snapshot(mail_root: Path) -> dict[str, tuple[int, int]]:
    """Snapshot every regular file under ``mail_root`` as ``{relpath: (size, mtime_ns)}``.

    Independent of the workflow's internal check — the test computes its own before/after
    to prove backup byte-identity. Uses Python ``os.walk`` (GNU ``find`` is forbidden).
    """
    snapshot: dict[str, tuple[int, int]] = {}
    for dirpath, _dirnames, filenames in os.walk(mail_root):
        base = Path(dirpath)
        for name in filenames:
            full = base / name
            try:
                if not full.is_file():
                    continue
                stat = full.stat()
            except OSError:
                continue
            snapshot[str(full.relative_to(mail_root))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def _write_config(
    tmp_path: Path,
    state_dir: Path,
    log_dir: Path,
    sandbox_dir: Path,
    *,
    admin_repo: Path,
    agent_binary: Path,
) -> Path:
    """Write a tmp copy of the SHIPPED config pointed at fixtures; return its path.

    ``paths`` → tmp dirs, ``admin_repo`` → fixture vault, ``agent.binary`` → shim path,
    ``agent.model: null``, ``agent.timeout_minutes: 5``. The ``noop`` entry runs first
    (harmless); ``mail-keeper`` second.
    """
    data = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    data["paths"] = {
        "state_dir": str(state_dir),
        "log_dir": str(log_dir),
        "sandbox_dir": str(sandbox_dir),
    }
    data["admin_repo"] = str(admin_repo)
    data["agent"]["binary"] = str(agent_binary)
    data["agent"]["model"] = None
    data["agent"]["timeout_minutes"] = 5
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return cfg_path


def _build_world(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    agent_binary: str = "shim",
) -> dict:
    """Build the full hermetic fixture world and wire the env; return a paths dict.

    Creates under ``tmp_path``: maildir + notmuch index (6 messages), fixture vault git repo
    + bare remote, the good/failure shims, state/log/sandbox dirs, a tmp config copy pointed
    at the fixtures, and sets the four ``MAIL_*`` env vars via ``monkeypatch.setenv``.

    Args:
        tmp_path: The test's temp dir (all fixtures live under it).
        monkeypatch: pytest MonkeyPatch (sets/restores the MAIL_* env vars).
        agent_binary: Which shim to point ``agent.binary`` at — ``"shim"`` or ``"shim_fail"``.

    Returns:
        A dict of paths: maildir, index, vault, bare_remote, shim, shim_fail, config_path,
        processed_log, state, logs, sandbox, plus the fixture metadata (account, owner).
    """
    mail_root = tmp_path / "mail"
    index_path = tmp_path / "notmuch-index"
    work_dir = tmp_path / "work"
    vault = tmp_path / "vault"
    bare_remote = tmp_path / "bare-remote"
    shim = tmp_path / "shim.py"
    shim_fail = tmp_path / "shim_fail.py"
    state_dir = tmp_path / "state"
    log_dir = tmp_path / "logs"
    sandbox_dir = tmp_path / "sandbox"

    for d in (state_dir, log_dir, sandbox_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Maildir + index.
    _build_maildir(mail_root)
    _notmuch_new(index_path, mail_root, work_dir)

    # Vault git repo + bare remote.
    _build_vault(vault, bare_remote)

    # Shims.
    _write_shim(shim, SHIM_SOURCE)
    _write_shim(shim_fail, SHIM_FAIL_SOURCE)

    # Config copy pointed at the fixtures.
    binary = shim if agent_binary == "shim" else shim_fail
    cfg_path = _write_config(
        tmp_path, state_dir, log_dir, sandbox_dir, admin_repo=vault, agent_binary=binary
    )

    # Env (the workflow reads these at run time; in-process run() loads .env with
    # override=False, so the test env wins).
    processed_log = tmp_path / "processing.jsonl"
    monkeypatch.setenv("MAIL_INDEX_DB", str(index_path))
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(mail_root))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    monkeypatch.setenv("MAIL_PROCESSED_LOG", str(processed_log))

    return {
        "tmp": tmp_path,
        "maildir": mail_root,
        "index": index_path,
        "work_dir": work_dir,
        "vault": vault,
        "bare_remote": bare_remote,
        "shim": shim,
        "shim_fail": shim_fail,
        "config_path": cfg_path,
        "processed_log": processed_log,
        "state": state_dir,
        "logs": log_dir,
        "sandbox": sandbox_dir,
        "account": ACCOUNT,
        "owner": OWNER,
    }


# --- Run helpers ------------------------------------------------------------- #
def _run_logs(log_dir: Path) -> list[Path]:
    """Return all ``run-*.log`` files in a log dir, sorted by name."""
    return sorted(log_dir.glob("run-*.log"))


def _last_run(log_dir: Path) -> str:
    """Return the contents of ``logs/last-run.txt`` (empty string if absent)."""
    path = log_dir / "last-run.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _read_processed_log(log_path: Path) -> list[dict]:
    """Read the processed log into a list of record dicts (empty when absent)."""
    if not log_path.is_file():
        return []
    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _manifest_ids_from_brief(brief: str) -> list[str]:
    """Extract the message-ids from a brief's MANIFEST lines, in order (oldest-first)."""
    ids: list[str] = []
    in_manifest = False
    for line in brief.splitlines():
        if line.startswith("MANIFEST ("):
            in_manifest = True
            continue
        if not in_manifest:
            continue
        stripped = line.strip()
        if not stripped or not stripped[0].isdigit():
            continue
        # Strip the leading "<n>. " prefix; the id is the first whitespace-delimited field.
        body = stripped.split(".", 1)[1].strip()
        ids.append(body.split()[0])
    return ids


def _vault_head(vault: Path) -> str:
    """Return the vault's current HEAD commit sha (empty when no commits)."""
    proc = subprocess.run(
        ["git", "-C", str(vault), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


# --- The four smoke tests ---------------------------------------------------- #
def test_mail_keeper_backfill_batch_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 1: fresh world + forced run → backfill batch of 4 (m6,m1,m2,m3 oldest-first)."""
    w = _build_world(tmp_path, monkeypatch)

    # Pre-run backup snapshot (independent of the workflow's internal check).
    snap_before = _backup_snapshot(w["maildir"])

    code = run(
        ["run", "--force", "--config", str(w["config_path"])],
        now=datetime(2026, 10, 21, 22, 30),  # inside the quiet window; forced anyway
        load=(0.1, 0.1, 0.1),
        run_id="mk-smoke-1",
    )

    assert code == 0
    log_text = _run_logs(w["logs"])[0].read_text(encoding="utf-8")
    assert "WORKFLOW mail-keeper status=ok" in log_text
    # The agent ran: the shim's NDJSON events are logged at INFO (the "agent ... started"
    # line is DEBUG and not in the file). event step_start/tool_use/text prove the shim ran.
    assert "event step_start #1" in log_text
    assert "event tool_use #2" in log_text
    assert "event text #3" in log_text

    # The shim's captured brief: the backfill batch of 4, oldest-first, PII/own excluded.
    brief = (w["tmp"] / "brief.txt").read_text(encoding="utf-8")
    ids = _manifest_ids_from_brief(brief)
    assert ids == [M6_ID, M1_ID, M2_ID, M3_ID], f"unexpected manifest order: {ids}"
    assert M4_ID not in brief, "PII message must not appear in the brief"
    assert M5_ID not in brief, "own mail must not appear in the brief"

    # Processed log: exactly 4 lines with the v1 6-field schema and expected classes.
    records = _read_processed_log(w["processed_log"])
    assert len(records) == 4, f"expected 4 processed-log lines, got {len(records)}"
    by_id = {r["email_file"]: r for r in records}
    assert set(by_id) == {M6_ID, M1_ID, M2_ID, M3_ID}
    expected_keys = {"timestamp", "email_file", "subject", "from", "target_section", "processed_to"}
    for rec in records:
        assert set(rec.keys()) == expected_keys, f"bad schema: {set(rec.keys())}"
    assert by_id[M6_ID]["target_section"] == "noise"
    assert by_id[M1_ID]["target_section"] == "action"
    assert by_id[M2_ID]["target_section"] == "noise"
    assert by_id[M3_ID]["target_section"] == "noise"

    # Vault: provenance edits + todo line + draft.
    meetings_path = w["vault"] / "projects" / "ORBIT" / "00_Project_management" / "01_Meetings.md"
    meetings = meetings_path.read_text(encoding="utf-8")
    assert M1_ID in meetings, "meetings line must carry the m1 provenance id"
    todos = (w["vault"] / "todos" / "active.md").read_text(encoding="utf-8")
    assert M1_ID in todos, "todo line must carry the m1 provenance id"
    drafts = list((w["vault"] / "mail" / "drafts").glob("2026-*_eug-schedule.md"))
    assert len(drafts) == 1, f"expected exactly one draft, got {len(drafts)}"
    draft_text = drafts[0].read_text(encoding="utf-8")
    assert "To: Coera <coera@orbit.example.test>" in draft_text
    assert "Subject: Re: EUG schedule" in draft_text
    assert M1_ID in draft_text, "draft must carry the m1 provenance footer"

    # Vault git: OC: commit pushed to the bare remote; clean status (drafts gitignored).
    subject = subprocess.run(
        ["git", "-C", str(w["vault"]), "log", "-1", "--format=%s"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    assert subject.startswith("OC:"), f"expected OC: commit, got {subject!r}"
    # The shim's push lands on refs/heads/feature/test in the bare repo (no remote-tracking
    # ref is created in the vault by a plain push). Query the bare repo directly.
    bare_log = subprocess.run(
        ["git", "-C", str(w["bare_remote"]), "log", "--oneline", "feature/test"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    assert subject in bare_log, "the OC: commit must be pushed to the bare remote"
    status = subprocess.run(
        ["git", "-C", str(w["vault"]), "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    assert status == "", f"vault should be clean (drafts gitignored), got: {status!r}"

    # Backup integrity: the maildir's file set + sizes + mtimes are unchanged.
    snap_after = _backup_snapshot(w["maildir"])
    assert snap_before == snap_after, "the mail backup tree changed during the run"


def test_mail_keeper_no_new_mail_after_backfill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 2: continue the world → run 2 has no agent call, no new log lines, HEAD unchanged."""
    w = _build_world(tmp_path, monkeypatch)

    # Run 1 (the backfill batch).
    code1 = run(
        ["run", "--force", "--config", str(w["config_path"])],
        now=datetime(2026, 10, 21, 22, 30),
        load=(0.1, 0.1, 0.1),
        run_id="mk-smoke-2a",
    )
    assert code1 == 0
    head_after_run1 = _vault_head(w["vault"])
    log_count_after_run1 = len(_read_processed_log(w["processed_log"]))
    assert log_count_after_run1 == 4

    # Run 2: no new mail → no agent call, no new processed-log lines, HEAD unchanged.
    t0 = time.monotonic()
    code2 = run(
        ["run", "--force", "--config", str(w["config_path"])],
        now=datetime(2026, 10, 21, 22, 35),
        load=(0.1, 0.1, 0.1),
        run_id="mk-smoke-2b",
    )
    elapsed = time.monotonic() - t0

    assert code2 == 0
    log2 = _run_logs(w["logs"])[1].read_text(encoding="utf-8")
    assert "WORKFLOW mail-keeper status=ok" in log2
    # No agent call on a no-new-mail run: none of the shim's NDJSON events are logged.
    assert "event step_start" not in log2, "no agent call on a no-new-mail run"
    assert len(_read_processed_log(w["processed_log"])) == log_count_after_run1
    assert _vault_head(w["vault"]) == head_after_run1, "HEAD must be unchanged on no-new-mail"
    assert elapsed < 10.0, f"no-new-mail run should be fast, took {elapsed:.1f}s"


def test_mail_keeper_new_mail_after_backfill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 3: continue the world → add m7 + reindex → run 3 processes exactly [m7]."""
    w = _build_world(tmp_path, monkeypatch)

    # Run 1 (the backfill batch).
    code1 = run(
        ["run", "--force", "--config", str(w["config_path"])],
        now=datetime(2026, 10, 21, 22, 30),
        load=(0.1, 0.1, 0.1),
        run_id="mk-smoke-3a",
    )
    assert code1 == 0

    # Add m7 (newer Date) + reindex the fixture index.
    _write_message("INBOX", "m7.eml", M7, w["maildir"])
    _notmuch_new(w["index"], w["maildir"], w["work_dir"])

    # Run 3: manifest exactly [m7]; processed log +1 line; zero duplicates vs runs 1–2.
    code3 = run(
        ["run", "--force", "--config", str(w["config_path"])],
        now=datetime(2026, 10, 21, 22, 40),
        load=(0.1, 0.1, 0.1),
        run_id="mk-smoke-3b",
    )
    assert code3 == 0

    brief = (w["tmp"] / "brief.txt").read_text(encoding="utf-8")
    ids = _manifest_ids_from_brief(brief)
    assert ids == [M7_ID], f"expected manifest exactly [m7], got {ids}"

    records = _read_processed_log(w["processed_log"])
    # Run 1 added 4 (m6,m1,m2,m3); run 3 adds 1 (m7) → 5 total.
    assert len(records) == 5, f"expected 5 processed-log lines, got {len(records)}"
    ids_in_log = [r["email_file"] for r in records]
    assert M7_ID in ids_in_log, "m7 must be recorded in the processed log"
    # Zero duplicate lines vs runs 1–2: every id appears exactly once.
    assert len(ids_in_log) == len(set(ids_in_log)), f"duplicate ids in processed log: {ids_in_log}"


def test_mail_keeper_agent_failure_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 4: fresh world with the failure shim → error run (no progress), then retry OK.

    Run 1 uses ``shim_fail`` (empty state → backfill start presents 4 candidates): the agent
    fails, so the workflow reports status=error, writes NO processed log and advances NO
    cursors/state. Re-running with a config copy pointing ``agent.binary`` back at the good
    shim re-presents the SAME 4 ids and succeeds (4 log lines, OC: commit present).

    Note: per scheduler.py's documented contract ("Per-workflow errors never change the exit
    code"), run 1 exits 0 even though the workflow reports status=error; last-run.txt records
    ``overall: error``. The test asserts against this ACTUAL behavior (see result report).
    """
    w = _build_world(tmp_path, monkeypatch, agent_binary="shim_fail")

    # Run 1: failure shim → workflow error, no log/state progress.
    code1 = run(
        ["run", "--force", "--config", str(w["config_path"])],
        now=datetime(2026, 10, 21, 22, 30),
        load=(0.1, 0.1, 0.1),
        run_id="mk-smoke-4a",
    )
    # ACTUAL behavior: per-workflow errors never change the exit code (scheduler.py).
    assert code1 == 0
    log1 = _run_logs(w["logs"])[0].read_text(encoding="utf-8")
    assert "WORKFLOW mail-keeper status=error" in log1
    assert "overall: error" in _last_run(w["logs"])

    # The failure shim captured the brief (first act) with all 4 backfill ids.
    brief = (w["tmp"] / "brief.txt").read_text(encoding="utf-8")
    ids = _manifest_ids_from_brief(brief)
    assert ids == [M6_ID, M1_ID, M2_ID, M3_ID], f"failure run must present all 4 ids: {ids}"

    # No processed log (the agent failed → no append).
    assert not w["processed_log"].is_file(), "no processed log on a failed agent run"

    # Vault HEAD unchanged (baseline commit only — the failure shim does no git work).
    head_after_fail = _vault_head(w["vault"])
    baseline = subprocess.run(
        ["git", "-C", str(w["vault"]), "rev-list", "--max-parents=0", "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    assert head_after_fail == baseline, "vault HEAD must be the baseline after a failed run"

    # No state file with advanced cursors (the workflow writes NO state on agent failure).
    state_file = w["state"] / "mail-keeper.json"
    if state_file.is_file():
        st = json.loads(state_file.read_text(encoding="utf-8"))
        for folder, cur in (st.get("cursors") or {}).items():
            assert cur.get("last_date", 0) == 0, f"cursor advanced on failure: {folder}"

    # Re-run with a config copy pointing agent.binary back at the good shim.
    retry_dir = tmp_path / "retry"
    retry_dir.mkdir(parents=True, exist_ok=True)
    retry_cfg = _write_config(
        retry_dir,
        w["state"],
        w["logs"],
        w["sandbox"],
        admin_repo=w["vault"],
        agent_binary=w["shim"],
    )
    code2 = run(
        ["run", "--force", "--config", str(retry_cfg)],
        now=datetime(2026, 10, 21, 22, 35),
        load=(0.1, 0.1, 0.1),
        run_id="mk-smoke-4b",
    )
    assert code2 == 0

    # The SAME 4 ids are re-presented and the run succeeds.
    brief2 = (w["tmp"] / "brief.txt").read_text(encoding="utf-8")
    ids2 = _manifest_ids_from_brief(brief2)
    assert ids2 == [M6_ID, M1_ID, M2_ID, M3_ID], f"retry must re-present the same 4 ids: {ids2}"

    records = _read_processed_log(w["processed_log"])
    assert len(records) == 4, f"expected 4 processed-log lines after retry, got {len(records)}"
    log2 = _run_logs(w["logs"])[1].read_text(encoding="utf-8")
    assert "WORKFLOW mail-keeper status=ok" in log2

    # An OC: commit is now present (the good shim committed + pushed).
    subject = subprocess.run(
        ["git", "-C", str(w["vault"]), "log", "-1", "--format=%s"],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    assert subject.startswith("OC:"), f"expected an OC: commit after retry, got {subject!r}"
