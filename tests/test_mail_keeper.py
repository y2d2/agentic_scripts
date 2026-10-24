"""Hermetic tests for the mail-keeper workflow module (Task 5 — newest-first backfill).

These build a throwaway maildir + ``notmuch new`` index entirely inside
``tmp_path_factory`` (following :mod:`tests.test_mail_reader`'s fixture pattern, account
``acct@example.test``) and drive :class:`~agentic_scripts.workflows.mail_keeper.MailKeeper`
with an injected fake agent (monkeypatched ``AgentRunner.run`` — NO real ``opencode``, no
live LLM). They never touch the live notmuch index or maildir backup tree — only the
throwaway fixture world under ``tmp_path``.

The fixture messages (controlled ``Date:`` headers, distinct ids) cover the newest-first
two-boundary detection paths: recent INBOX mail (m1 plain / m2 multipart / m3 HTML-only),
history mail for the multi-run backfill (m9 Sep 15, m6 Aug 15, m10 Jul 15), an OLD message
OUTSIDE the 1-year floor (m8 Mar 2025 — never triaged), a PII-folder message (m4), and
own-mail in Sent Items (m5). The tests below map to the Task 5 spec's acceptance list; the
last test is the load-bearing base-smoke compatibility check (run as part of the full
suite, see :mod:`tests.smoke.test_smoke_base`).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import pytest
import yaml

from agentic_scripts.agent import AgentResult
from agentic_scripts.config import Config, load_config
from agentic_scripts.state import StateStore
from agentic_scripts.workflows import mail_keeper
from agentic_scripts.workflows.base import WorkContext

ACCOUNT = "acct@example.test"
OWNER = "yuri.durodie@vub.be"

# --- Fixture message ids ----------------------------------------------------- #
M3_ID = "m3@fixture.test"  # newest INBOX (Oct 21 11:00), HTML-only
M2_ID = "m2@fixture.test"  # INBOX (Oct 21 10:00), multipart
M1_ID = "m1@fixture.test"  # INBOX (Oct 21 09:00), plain (Coera) — the "action" message
M9_ID = "m9@fixture.test"  # history INBOX (Sep 15), noise
M6_ID = "m6@fixture.test"  # history INBOX (Aug 15), noise
M10_ID = "m10@fixture.test"  # history INBOX (Jul 15), noise — oldest in-window
M8_ID = "m8@fixture.test"  # OLD INBOX (Mar 2025) — OUTSIDE the floor, never triaged
M4_ID = "m4@fixture.test"  # PII folder — must be excluded
M5_ID = "m5@fixture.test"  # Sent Items, own mail — must be excluded
M7_ID = "m7@fixture.test"  # added by the new-mail test (Oct 22)
B1_ID = "b1@fixture.test"  # cross-folder test: NEW mail in INBOX/ORBIT (Oct 22)

# --- Fixture message bodies -------------------------------------------------- #
# m3: newest INBOX (Oct 21 11:00), HTML-only.
M3 = f"""From: Html <html@fixture.test>
To: someone@example.test
Subject: Recent html three
Message-Id: <{M3_ID}>
Date: Mon, 21 Oct 2026 11:00:00 +0000
Content-Type: text/html; charset=utf-8

<html><body>HTML-only marker body.</body></html>
"""

# m2: INBOX (Oct 21 10:00), multipart (html + plain).
M2 = f"""From: Multi <multi@fixture.test>
To: someone@example.test
Subject: Recent multipart two
Message-Id: <{M2_ID}>
Date: Mon, 21 Oct 2026 10:00:00 +0000
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

# m1: INBOX (Oct 21 09:00), plain from Coera — the "action" message.
M1 = f"""From: Coera <coera@fixture.test>
To: someone@example.test
Subject: Recent plain one
Message-Id: <{M1_ID}>
Date: Mon, 21 Oct 2026 09:00:00 +0000
Content-Type: text/plain; charset=utf-8

A recent plain-text message.
"""

# m9: history INBOX (Sep 15), noise.
M9 = f"""From: Sep Sender <sep@fixture.test>
To: someone@example.test
Subject: History nine
Message-Id: <{M9_ID}>
Date: Mon, 15 Sep 2026 09:00:00 +0000
Content-Type: text/plain; charset=utf-8

A September history message.
"""

# m6: history INBOX (Aug 15), noise.
M6 = f"""From: Aug Sender <aug@fixture.test>
To: someone@example.test
Subject: History six
Message-Id: <{M6_ID}>
Date: Mon, 17 Aug 2026 09:00:00 +0000
Content-Type: text/plain; charset=utf-8

An August history message.
"""

# m10: history INBOX (Jul 15), noise — the oldest in-window message.
M10 = f"""From: Jul Sender <jul@fixture.test>
To: someone@example.test
Subject: History ten
Message-Id: <{M10_ID}>
Date: Mon, 13 Jul 2026 09:00:00 +0000
Content-Type: text/plain; charset=utf-8

A July history message (oldest in the window).
"""

# m8: OLD INBOX (Mar 2025) — OUTSIDE the 1-year floor, must never be triaged.
M8 = f"""From: Old Sender <old@fixture.test>
To: someone@example.test
Subject: Pre-floor old mail
Message-Id: <{M8_ID}>
Date: Mon, 17 Mar 2025 09:00:00 +0000
Content-Type: text/plain; charset=utf-8

An old message outside the backfill floor — never triaged.
"""

# m4: PII folder — excluded from detection.
M4 = f"""From: PhD Applicant <phd@fixture.test>
To: someone@example.test
Subject: PhD application (PII)
Message-Id: <{M4_ID}>
Date: Tue, 20 Oct 2026 13:00:00 +0000
Content-Type: text/plain; charset=utf-8

A PII-folder message that must never enter the manifest.
"""

# m5: Sent Items, own mail — excluded (style sampling only).
M5 = f"""From: Yuri Durodie <{OWNER}>
To: coera@fixture.test
Subject: Own sent mail (style)
Message-Id: <{M5_ID}>
Date: Tue, 20 Oct 2026 14:00:00 +0000
Content-Type: text/plain; charset=utf-8

Own corpus message for style sampling only.
"""


def _write_message(folder_rel: str, filename: str, body: str, mail_root: Path) -> None:
    """Write one .eml into ``mail_root/<ACCOUNT>/<folder_rel>/cur/``."""
    cur = mail_root / ACCOUNT / folder_rel / "cur"
    cur.mkdir(parents=True, exist_ok=True)
    (cur / filename).write_text(body, encoding="utf-8")


def _build_maildir(mail_root: Path) -> None:
    """Create the nine-message fixture maildir under ``mail_root/<ACCOUNT>/``.

    INBOX holds m1/m2/m3 (recent), m9/m6/m10 (history, in-window) and m8 (pre-floor); the
    PII folder holds m4; Sent Items holds own-mail m5.
    """
    _write_message("INBOX", "m3.eml", M3, mail_root)
    _write_message("INBOX", "m2.eml", M2, mail_root)
    _write_message("INBOX", "m1.eml", M1, mail_root)
    _write_message("INBOX", "m9.eml", M9, mail_root)
    _write_message("INBOX", "m6.eml", M6, mail_root)
    _write_message("INBOX", "m10.eml", M10, mail_root)
    _write_message("INBOX", "m8.eml", M8, mail_root)
    _write_message("INBOX/FU-Admin/PhD_applications", "m4.eml", M4, mail_root)
    _write_message("Sent Items", "m5.eml", M5, mail_root)


def _build_index(index_path: Path, mail_root: Path, work_dir: Path) -> None:
    """Write a reader-style config and run ``notmuch new`` to build the index.

    Test *setup only* — :class:`NotmuchReader` itself never calls ``new`` (read-only).
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

    env = {**os.environ, "NOTMUCH_CONFIG": str(config_path)}
    proc = subprocess.run(["notmuch", "new"], capture_output=True, text=True, env=env, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"notmuch new failed: {proc.stderr}")


def _inbox_max_ts(index_path: Path, mail_root: Path, work_dir: Path) -> int:
    """Return the max message timestamp in INBOX (read-only probe via a fresh reader)."""
    from agentic_scripts.mail.reader import NotmuchReader, q_folder

    reader = NotmuchReader(index_path=index_path, mail_root=mail_root, work_dir=work_dir / "probe")
    rows = reader.search(q_folder(ACCOUNT, "INBOX"), limit=10**9)
    return max(int(r["timestamp"]) for r in rows)


class _FakeRunner:
    """A stand-in for :class:`AgentRunner` whose ``run`` returns a canned result.

    Purpose:
        Inject deterministic agent behaviour without spawning any real ``opencode``. The
        fake records every call (agent, brief, work_dir, title) and returns the canned
        :class:`AgentResult` set on it; tests assert on the recorded calls.
    """

    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.calls: list[dict] = []

    def run(self, *, agent, brief, work_dir, title=None, timeout_seconds=None) -> AgentResult:
        """Record the call and return the canned result (never spawns a subprocess)."""
        self.calls.append({"agent": agent, "brief": brief, "work_dir": work_dir, "title": title})
        return self.result


def _ok_result(final_text: str) -> AgentResult:
    """Build an ``ok`` :class:`AgentResult` with the given final text."""
    return AgentResult(
        status="ok", exit_code=0, final_text=final_text, events=[], error=None, duration_seconds=1.0
    )


def _error_result() -> AgentResult:
    """Build an ``error`` :class:`AgentResult` (no final text)."""
    return AgentResult(
        status="error", exit_code=1, final_text=None, events=[], error="boom", duration_seconds=2.0
    )


def _triage_table(rows: list[tuple[str, str]]) -> str:
    """Render a Triage table from ``[(msg-id, class), ...]`` rows."""
    lines = ["| msg-id | folder | from | class | action taken |", "|---|---|---|---|---|"]
    for msg_id, cls in rows:
        lines.append(f"| {msg_id} | INBOX | sender@fixture.test | {cls} | logged |")
    return "\n".join(lines)


def _read_processed_log(log_path: Path) -> list[dict]:
    """Read the processed log into a list of record dicts (empty when absent)."""
    if not log_path.is_file():
        return []
    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


# --- The hermetic fixture ---------------------------------------------------- #
@pytest.fixture(scope="module")
def hermetic_mail(tmp_path_factory) -> dict:
    """Build a throwaway maildir + index and return the shared paths/metadata.

    Module-scoped so the one-time ``notmuch new`` cost is paid once per session. Tests
    that need to add a message (the steady-state test) write into this tree and re-run
    ``notmuch new`` themselves — they do not mutate the indexed corpus in place, so the
    other tests' counts stay valid.
    """
    base = tmp_path_factory.mktemp("hermetic_mail_keeper")
    mail_root = base / "mail"
    index_path = base / "notmuch-index"
    work_dir = base / "work"

    _build_maildir(mail_root)
    _build_index(index_path, mail_root, work_dir)

    return {
        "base": base,
        "mail_root": mail_root,
        "index_path": index_path,
        "work_dir": work_dir,
        "account": ACCOUNT,
        "inbox_max_ts": _inbox_max_ts(index_path, mail_root, work_dir),
    }


def _make_ctx(
    tmp_path: Path,
    hermetic: dict,
    *,
    admin_repo: Path | None = None,
    fake_runner: _FakeRunner | None = None,
    state_dir: Path | None = None,
) -> WorkContext:
    """Build a :class:`WorkContext` wired to the hermetic mail + an injected fake runner.

    Args:
        tmp_path: The test's temp dir (holds the sandbox).
        hermetic: The shared hermetic-mail metadata (index/mail_root paths).
        admin_repo: The admin repo path (a tmp dir); None exercises the skip path.
        fake_runner: The injected :class:`_FakeRunner` (replaces ``ctx.runner``).
        state_dir: Override for the state dir (defaults to ``tmp_path/state``).

    Returns:
        A fully wired :class:`WorkContext` ready for :meth:`MailKeeper.run`.
    """
    project_root = Path(__file__).resolve().parents[1]
    shipped = yaml.safe_load(
        (project_root / "config" / "workflows.yaml").read_text(encoding="utf-8")
    )
    data = copy.deepcopy(shipped)
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    state_dir = state_dir or (tmp_path / "state")
    data["paths"] = {
        "state_dir": str(state_dir),
        "log_dir": str(tmp_path / "logs"),
        "sandbox_dir": str(sandbox_dir),
    }
    if admin_repo is not None:
        admin_repo.mkdir(parents=True, exist_ok=True)
        data["admin_repo"] = str(admin_repo)
    else:
        data.pop("admin_repo", None)
    cfg_path = tmp_path / "workflows.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    config: Config = load_config(cfg_path)

    logger = logging.getLogger("test.mail_keeper")
    logger.setLevel(logging.CRITICAL)  # quiet: the workflow logs at INFO/DEBUG
    ctx = WorkContext(
        config=config,
        state=StateStore(state_dir),
        logger=logger,
        run_id="test-run-1",
        workflow_name="mail-keeper",
        sandbox_dir=sandbox_dir,
        admin_repo=admin_repo,
    )
    if fake_runner is not None:
        ctx._runner = fake_runner  # inject the fake; ctx.runner returns it lazily
    return ctx


def _set_mail_env(monkeypatch, hermetic: dict, tmp_path: Path) -> Path:
    """Set the four MAIL_* env vars to the hermetic/tmp paths; return the log path."""
    monkeypatch.setenv("MAIL_INDEX_DB", str(hermetic["index_path"]))
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(hermetic["mail_root"]))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    log_path = tmp_path / "processed-log.jsonl"
    monkeypatch.setenv("MAIL_PROCESSED_LOG", str(log_path))
    return log_path


def _manifest_ids_from_brief(brief: str) -> list[str]:
    """Extract the message-ids from a brief's MANIFEST lines (in order).

    Each manifest line is ``<n>. <id> | <folder> | <date> | <from> | <subject>``; the id
    is the first field with its leading ``<n>. `` prefix stripped.
    """
    ids = []
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
        # "<n>. <id> | <folder> | ..." → strip the leading "n. " to leave the id.
        first_field = stripped.split(" | ", 1)[0]
        msg_id = (
            first_field.split(". ", 1)[1].strip() if ". " in first_field else first_field.strip()
        )
        ids.append(msg_id)
    return ids


def _manifest_line_count(brief: str) -> int:
    """Count the numbered MANIFEST lines in a brief."""
    count = 0
    in_manifest = False
    for line in brief.splitlines():
        if line.startswith("MANIFEST ("):
            in_manifest = True
            continue
        if in_manifest and line.strip()[:1].isdigit():
            count += 1
    return count


# msg-id → epoch seconds for the fixture INBOX messages (the deterministic dates above). Used to
# assert global-newest-first ordering without re-deriving timestamps from the index.
ts_of = {
    M3_ID: 1792580400,  # Mon, 21 Oct 2026 11:00:00 +0000
    M2_ID: 1792576800,  # Mon, 21 Oct 2026 10:00:00 +0000
    M1_ID: 1792573200,  # Mon, 21 Oct 2026 09:00:00 +0000
    M9_ID: 1789462800,  # Mon, 15 Sep 2026 09:00:00 +0000
    M6_ID: 1786957200,  # Mon, 17 Aug 2026 09:00:00 +0000
    M10_ID: 1783933200,  # Mon, 13 Jul 2026 09:00:00 +0000
}


def _run_workflow(ctx: WorkContext) -> object:
    """Run the mail-keeper workflow once against ``ctx``."""
    wf = mail_keeper.create(ctx.config)
    assert wf.name == "mail-keeper"
    return wf.run(ctx)


# --------------------------------------------------------------------------- #
# 1. First run = newest-first backfill (fresh state, two-boundary cursors)     #
# --------------------------------------------------------------------------- #
def test_run_one_fresh_state_newest_first(hermetic_mail, tmp_path, monkeypatch):
    """Fresh state → manifest [m3,m2,m1,m9,m6,m10] newest-first; m4/m5/m8 absent; v2 state."""
    log_path = _set_mail_env(monkeypatch, hermetic_mail, tmp_path)

    fake = _FakeRunner(
        _ok_result(
            _triage_table(
                [
                    (M3_ID, "noise"),
                    (M2_ID, "noise"),
                    (M1_ID, "action"),
                    (M9_ID, "noise"),
                    (M6_ID, "noise"),
                    (M10_ID, "noise"),
                ]
            )
        )
    )
    ctx = _make_ctx(tmp_path, hermetic_mail, admin_repo=tmp_path / "admin", fake_runner=fake)

    result = _run_workflow(ctx)

    # Agent called exactly once with the right args.
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["agent"] == "mail-keeper"
    assert Path(call["work_dir"]) == ctx.admin_repo
    brief = call["brief"]

    # Manifest is the 6 newest KEPT messages GLOBALLY (ts desc); PII (m4) + own (m5) + pre-floor
    # (m8) all excluded. Task 5f: the pool is sorted globally newest-first before the cap, so a
    # fresh bootstrap's batch is the global newest set and its order is descending by timestamp.
    ids = _manifest_ids_from_brief(brief)
    assert ids == [M3_ID, M2_ID, M1_ID, M9_ID, M6_ID, M10_ID]
    ts_order = [ts_of[i] for i in ids]
    assert ts_order == sorted(ts_order, reverse=True), (
        "batch must be globally newest-first (ts desc)"
    )
    assert "MANIFEST (6 message(s)):" in brief
    assert M4_ID not in brief
    assert M5_ID not in brief
    assert M8_ID not in brief

    # Result ok with 6 items found.
    assert result.status == "ok"
    assert result.items_found == 6

    # Processed log: exactly 6 lines, 6 keys each, classes match the table.
    records = _read_processed_log(log_path)
    assert len(records) == 6
    expected_classes = {
        M3_ID: "noise",
        M2_ID: "noise",
        M1_ID: "action",
        M9_ID: "noise",
        M6_ID: "noise",
        M10_ID: "noise",
    }
    for rec in records:
        assert set(rec.keys()) == {
            "timestamp",
            "email_file",
            "subject",
            "from",
            "target_section",
            "processed_to",
        }
        assert rec["email_file"] in expected_classes
        assert rec["target_section"] == expected_classes[rec["email_file"]]

    # State v2: floor = now−365d (±2 s); new.last_date = ts(m3) (the batch max). The back
    # frontier stays at the initial floor after run 1 — every batch member is NEW-kind (ts >
    # the previous new=0), so there are no history-kind entries to advance it from. It starts
    # moving only from run 2 onward, when a folder's own history enters the batch.
    state = json.loads((tmp_path / "state" / "mail-keeper.json").read_text(encoding="utf-8"))
    assert "bootstrapped_at" in state
    now = int(time.time())
    assert abs(state["backfill_floor"] - (now - 365 * 86400)) <= 2
    inbox = state["cursors"]["INBOX"]
    assert set(inbox.keys()) == {"new", "back"}
    assert inbox["new"]["last_date"] == hermetic_mail["inbox_max_ts"]  # ts(m3), the newest
    assert inbox["new"]["last_message_id"] == M3_ID
    assert inbox["back"]["last_date"] == state["backfill_floor"]  # initial floor (not dropped)
    assert inbox["back"]["last_date"] >= state["backfill_floor"]  # invariant: never below floor
    assert state["deferred"] == []


# --------------------------------------------------------------------------- #
# 2. Run two = no new mail (history re-walk filtered by the processed log)     #
# --------------------------------------------------------------------------- #
def test_run_two_no_new_mail_hist_filtered_by_log(hermetic_mail, tmp_path, monkeypatch):
    """Run 1 then run 2: no agent call, status ok, log + state content unchanged."""
    log_path = _set_mail_env(monkeypatch, hermetic_mail, tmp_path)

    # Run 1 (fresh state → the newest-first backfill batch).
    fake1 = _FakeRunner(
        _ok_result(
            _triage_table(
                [
                    (M3_ID, "noise"),
                    (M2_ID, "noise"),
                    (M1_ID, "action"),
                    (M9_ID, "noise"),
                    (M6_ID, "noise"),
                    (M10_ID, "noise"),
                ]
            )
        )
    )
    ctx1 = _make_ctx(tmp_path, hermetic_mail, admin_repo=tmp_path / "admin", fake_runner=fake1)
    result1 = _run_workflow(ctx1)
    assert result1.status == "ok"

    state_path = tmp_path / "state" / "mail-keeper.json"
    state_after_run1 = state_path.read_text(encoding="utf-8")
    log_count_after_run1 = len(_read_processed_log(log_path))

    # Run 2: no new mail. The history re-walk of m1/m2 (still in (back, new]) is filtered by
    # the processed log → merged pool empty → NO agent call, state content identical.
    fake2 = _FakeRunner(_ok_result("no-op"))  # must NOT be called
    ctx2 = _make_ctx(tmp_path, hermetic_mail, admin_repo=tmp_path / "admin", fake_runner=fake2)
    result2 = _run_workflow(ctx2)

    assert result2.status == "ok"
    assert result2.items_found == 0
    assert len(fake2.calls) == 0
    assert len(_read_processed_log(log_path)) == log_count_after_run1
    assert state_path.read_text(encoding="utf-8") == state_after_run1
    assert any("no new mail" in a for a in result2.actions)


# --------------------------------------------------------------------------- #
# 3. Run three = new mail (m7) arrives during the backfill                     #
# --------------------------------------------------------------------------- #
def test_run_three_new_mail(tmp_path, monkeypatch):
    """Run 1, then add m7 (Oct 22) + reindex → run 3 manifest exactly [m7]; back unchanged.

    Uses its own isolated corpus (not the shared module fixture) so it never mutates the
    index that the other tests rely on — this keeps the suite order-independent.
    """
    base = tmp_path / "run3"
    mail_root = base / "mail"
    index_path = base / "index"
    work_dir = base / "work"

    # Corpus: the full INBOX set (m1/m2/m3 recent + m9/m6/m10 history) + PII m4 + own m5.
    _build_maildir(mail_root)
    _build_index(index_path, mail_root, work_dir)

    monkeypatch.setenv("MAIL_INDEX_DB", str(index_path))
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(mail_root))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    log_path = tmp_path / "processed-log.jsonl"
    monkeypatch.setenv("MAIL_PROCESSED_LOG", str(log_path))

    # Run 1 (fresh state → the newest-first backfill batch).
    fake1 = _FakeRunner(
        _ok_result(
            _triage_table(
                [
                    (M3_ID, "noise"),
                    (M2_ID, "noise"),
                    (M1_ID, "action"),
                    (M9_ID, "noise"),
                    (M6_ID, "noise"),
                    (M10_ID, "noise"),
                ]
            )
        )
    )
    ctx1 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake1,
    )
    result1 = _run_workflow(ctx1)
    assert result1.status == "ok"

    state_path = tmp_path / "state" / "mail-keeper.json"
    back_after_run1 = json.loads(state_path.read_text(encoding="utf-8"))["cursors"]["INBOX"][
        "back"
    ]["last_date"]

    # Add m7 (newer than everything) to INBOX/cur and re-index.
    m7_body = f"""From: New Sender <new@fixture.test>
To: someone@example.test
Subject: New mail during backfill
Message-Id: <{M7_ID}>
Date: Tue, 22 Oct 2026 12:00:00 +0000
Content-Type: text/plain; charset=utf-8

A brand-new message arriving while the backfill is in flight.
"""
    _write_message("INBOX", "m7.eml", m7_body, mail_root)
    _build_index(index_path, mail_root, tmp_path / "reindex")

    # Run 3: manifest exactly [m7] (new mail only); back frontier unchanged.
    fake3 = _FakeRunner(_ok_result(_triage_table([(M7_ID, "info")])))
    ctx3 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake3,
    )
    result3 = _run_workflow(ctx3)
    assert result3.status == "ok"

    brief3 = fake3.calls[0]["brief"]
    ids3 = _manifest_ids_from_brief(brief3)
    assert ids3 == [M7_ID]
    assert _manifest_line_count(brief3) == 1

    # Processed log +1 line with the table's class.
    records = _read_processed_log(log_path)
    assert len(records) == 7
    assert records[-1]["email_file"] == M7_ID
    assert records[-1]["target_section"] == "info"

    # new.last_date advanced to ts(m7); back.last_date unchanged (still ts(m10)).
    state3 = json.loads(state_path.read_text(encoding="utf-8"))
    inbox3 = state3["cursors"]["INBOX"]
    assert inbox3["new"]["last_message_id"] == M7_ID
    assert inbox3["new"]["last_date"] > back_after_run1
    assert inbox3["back"]["last_date"] == back_after_run1


# --------------------------------------------------------------------------- #
# 4. New mail is never starved during the backfill (MAX_BATCH monkeypatched)   #
# --------------------------------------------------------------------------- #
def test_new_mail_not_starved_during_backfill(tmp_path, monkeypatch):
    """FRESH world, MAX_BATCH=3: run 1 [m3,m2,m1] (deferred m9,m6,m10); run 2 [n1,m9,m6].

    The load-bearing no-starvation test: with 3 deferred history messages waiting, a new
    message n1 (Oct 22) must still land FIRST in run 2's batch. Uses its own isolated corpus
    (not the shared module fixture) so it never mutates the index the other tests rely on.
    """
    base = tmp_path / "nostarve"
    mail_root = base / "mail"
    index_path = base / "index"
    work_dir = base / "work"

    _build_maildir(mail_root)
    _build_index(index_path, mail_root, work_dir)

    monkeypatch.setenv("MAIL_INDEX_DB", str(index_path))
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(mail_root))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    log_path = tmp_path / "processed-log.jsonl"
    monkeypatch.setenv("MAIL_PROCESSED_LOG", str(log_path))
    monkeypatch.setattr(mail_keeper, "MAX_BATCH", 3)

    # Run 1 (fresh state): manifest [m3,m2,m1]; deferred = kept overflow [m9,m6,m10].
    fake1 = _FakeRunner(
        _ok_result(_triage_table([(M3_ID, "noise"), (M2_ID, "noise"), (M1_ID, "action")]))
    )
    ctx1 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake1,
    )
    result1 = _run_workflow(ctx1)
    assert result1.status == "ok"

    brief1 = fake1.calls[0]["brief"]
    ids1 = _manifest_ids_from_brief(brief1)
    assert ids1 == [M3_ID, M2_ID, M1_ID]
    state_path = tmp_path / "state" / "mail-keeper.json"
    state1 = json.loads(state_path.read_text(encoding="utf-8"))
    deferred_ids1 = [d["message_id"] for d in state1["deferred"]]
    assert deferred_ids1 == [M9_ID, M6_ID, M10_ID]  # kept overflow, newest-first

    # Add n1 (Oct 22 09:00 — newer than m3) to INBOX/cur and re-index.
    N1_ID = "n1@fixture.test"
    n1_body = f"""From: New Sender <new@fixture.test>
To: someone@example.test
Subject: New mail while backfill in flight
Message-Id: <{N1_ID}>
Date: Tue, 22 Oct 2026 09:00:00 +0000
Content-Type: text/plain; charset=utf-8

A new message that must not be starved by the pending backfill.
"""
    _write_message("INBOX", "n1.eml", n1_body, mail_root)
    _build_index(index_path, mail_root, tmp_path / "reindex")

    # Run 2: batch EXACTLY [n1, m9, m6] (3 entries — the cap re-applied). n1 FIRST even with 3
    # deferred history messages waiting (no starvation): the pool is new[n1] + deferred
    # [m9,m6,m10] = 4 entries; the ≤ MAX_BATCH=3 cap takes the first 3 as the batch and defers
    # the 4th (m10) again. (Task 5b: this replaces the old 4-entry assertion that encoded the
    # batch-cap bug.)
    fake2 = _FakeRunner(
        _ok_result(_triage_table([(N1_ID, "info"), (M9_ID, "noise"), (M6_ID, "noise")]))
    )
    ctx2 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake2,
    )
    result2 = _run_workflow(ctx2)
    assert result2.status == "ok"

    brief2 = fake2.calls[0]["brief"]
    ids2 = _manifest_ids_from_brief(brief2)
    assert ids2 == [N1_ID, M9_ID, M6_ID], f"batch must be exactly [n1,m9,m6]: {ids2}"
    assert _manifest_line_count(brief2) == 3, "the batch cap (3) must hold on run 2"

    state2 = json.loads(state_path.read_text(encoding="utf-8"))
    inbox2 = state2["cursors"]["INBOX"]
    assert inbox2["new"]["last_message_id"] == N1_ID  # new.last_date = ts(n1)
    deferred_ids2 = [d["message_id"] for d in state2["deferred"]]
    assert deferred_ids2 == [M10_ID]  # m10 is the only remaining overflow (re-injected next run)


# --------------------------------------------------------------------------- #
# 4b. Cross-folder new mail is never starved (Task 5b regression pin)          #
# --------------------------------------------------------------------------- #
def test_cross_folder_new_mail_not_starved(tmp_path, monkeypatch):
    """MAX_BATCH=3: a second folder's GENUINELY-NEW mail (b1) lands in the batch even though a
    large folder's history is pending — pass 1 collects new-mail folders' ``new_set`` UNBOUNDED,
    so INBOX's bounded history cannot starve it.

    Task 5f adjustment (recorded): under Change 1 a FRESH-frontier folder's mail routes to the
    BOUNDED history pass, so b1 must arrive AFTER run 1 — when INBOX's new frontier has advanced
    past m3 — for b1 to be genuinely NEW (ts > ORBIT's new.last_date) and thus protected by the
    unbounded pass. This is exactly the "new mail never starved" invariant; a fresh-frontier
    folder's backfill is bounded by design (that is what kills the Run-1 deferred explosion).
    Under the Task 5 per-folder single-pass code this still FAILS: INBOX's history would consume
    the shared kept budget before ORBIT's b1 was collected → b1 starved. This test pins the fix.
    """
    base = tmp_path / "crossfolder"
    mail_root = base / "mail"
    index_path = base / "index"
    work_dir = base / "work"

    # Corpus: the INBOX fixture set + a second triage folder (INBOX/ORBIT) with 4 in-window
    # history messages (o1..o4, 2026 dates below the INBOX history). b1 is added AFTER run 1.
    _build_maildir(mail_root)

    def _orbit_msg(mid: str, date_line: str, subject: str) -> str:
        return f"""From: Orbit Sender <{mid.split("@")[0]}@orbit.example.test>
To: someone@example.test
Subject: {subject}
Message-Id: <{mid}>
Date: {date_line}
Content-Type: text/plain; charset=utf-8

An ORBIT message.
"""

    for mid, date_line in [
        ("o1@fixture.test", "Mon, 01 Jun 2026 09:00:00 +0000"),
        ("o2@fixture.test", "Mon, 08 Jun 2026 09:00:00 +0000"),
        ("o3@fixture.test", "Mon, 15 Jun 2026 09:00:00 +0000"),
        ("o4@fixture.test", "Mon, 22 Jun 2026 09:00:00 +0000"),
    ]:
        _write_message(
            "INBOX/ORBIT",
            f"{mid.split('@')[0]}.eml",
            _orbit_msg(mid, date_line, f"Orbit {mid}"),
            mail_root,
        )

    _build_index(index_path, mail_root, work_dir)

    monkeypatch.setenv("MAIL_INDEX_DB", str(index_path))
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(mail_root))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    log_path = tmp_path / "processed-log.jsonl"
    monkeypatch.setenv("MAIL_PROCESSED_LOG", str(log_path))
    monkeypatch.setattr(mail_keeper, "MAX_BATCH", 3)

    # Run 1 (fresh state, MAX_BATCH=3): INBOX batch [m3,m2,m1]; ORBIT's o1..o4 are bounded
    # history (fresh frontier → deferred). INBOX's new frontier advances to ts(m3).
    fake1 = _FakeRunner(_ok_result("cross-folder run 1 (no table)"))
    ctx1 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake1,
    )
    result1 = _run_workflow(ctx1)
    assert result1.status == "ok"

    # Add b1 (Oct 22 — NEWER than INBOX's new frontier ts(m3)=Oct 21) to ORBIT and re-index.
    # Now b1 is genuinely NEW in ORBIT (ts > ORBIT's new.last_date=0).
    _write_message(
        "INBOX/ORBIT",
        "b1.eml",
        _orbit_msg(B1_ID, "Tue, 22 Oct 2026 09:00:00 +0000", "Orbit new b1"),
        mail_root,
    )
    _build_index(index_path, mail_root, tmp_path / "reindex")

    # Run 2: b1 (ORBIT NEW mail) MUST be in the batch — it is collected in pass 1 (new-mail
    # folders' new_set, UNBOUNDED), so INBOX's bounded history cannot starve it. Under the Task 5
    # per-folder single-pass code, INBOX's history would consume the shared kept budget before
    # ORBIT's b1 was ever collected → b1 would be absent (deferred). This is the regression pin.
    fake2 = _FakeRunner(_ok_result("cross-folder run 2 (no table)"))
    ctx2 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake2,
    )
    result2 = _run_workflow(ctx2)
    assert result2.status == "ok"

    brief2 = fake2.calls[0]["brief"]
    ids2 = _manifest_ids_from_brief(brief2)
    assert B1_ID in ids2, f"b1 must not be starved by INBOX's history: {ids2}"
    # The batch respects the cap.
    assert len(ids2) == 3, f"batch must respect MAX_BATCH=3: {ids2}"


# --------------------------------------------------------------------------- #
# 4c. Per-folder frontier advances (Task 5b)                                   #
# --------------------------------------------------------------------------- #
def test_per_folder_frontier_advances(tmp_path, monkeypatch):
    """Run 1 (new-kind → back stays floor), then run 2 (history batch → INBOX back = ts(m10));
    a folder absent from the batch keeps both boundaries.

    Uses MAX_BATCH=3 so run 1 delivers only [m3,m2,m1] (all new-kind) and defers m9/m6/m10 —
    leaving them UNPROCESSED so run 2's history re-walk (not log-filtered) delivers them as the
    batch. This is the scenario the spec describes; with the default MAX_BATCH=10, run 1 would
    deliver all 6 and run 2 would be a no-new-mail run (the m9/m6/m10 re-walk is processed-log
    filtered — see test_run_two_no_new_mail_hist_filtered_by_log).
    """
    base = tmp_path / "frontier"
    mail_root = base / "mail"
    index_path = base / "index"
    work_dir = base / "work"

    _build_maildir(mail_root)
    # No second folder with in-window mail: the spec's run-2 batch is exactly the INBOX history
    # [m9,m6,m10], so every other triage folder stays empty (absent from both batches). The
    # absent-folder invariant is verified on INBOX/ORBIT (stays at the floor, empty id).
    _build_index(index_path, mail_root, work_dir)

    monkeypatch.setenv("MAIL_INDEX_DB", str(index_path))
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(mail_root))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    log_path = tmp_path / "processed-log.jsonl"
    monkeypatch.setenv("MAIL_PROCESSED_LOG", str(log_path))
    monkeypatch.setattr(mail_keeper, "MAX_BATCH", 3)

    # Run 1 (fresh state, MAX_BATCH=3): batch = [m3,m2,m1] (all new-kind); deferred [m9,m6,m10].
    fake1 = _FakeRunner(_ok_result("frontier run 1 (no table)"))
    ctx1 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake1,
    )
    result1 = _run_workflow(ctx1)
    assert result1.status == "ok"

    state_path = tmp_path / "state" / "mail-keeper.json"
    st1 = json.loads(state_path.read_text(encoding="utf-8"))
    floor = st1["backfill_floor"]
    inbox1 = st1["cursors"]["INBOX"]
    # Run 1: all new-kind → back stays at the floor; new = ts(m3).
    assert inbox1["back"]["last_date"] == floor, "run 1 batch is all new-kind → back stays floor"
    assert inbox1["new"]["last_message_id"] == M3_ID

    # Run 2: no new mail → batch = the INBOX history below ts(m3), newest-first [m9, m6, m10].
    fake2 = _FakeRunner(_ok_result("frontier run 2 (no table)"))
    ctx2 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake2,
    )
    result2 = _run_workflow(ctx2)
    assert result2.status == "ok"

    brief2 = fake2.calls[0]["brief"]
    ids2 = _manifest_ids_from_brief(brief2)
    assert ids2 == [M9_ID, M6_ID, M10_ID], f"run 2 batch must be the INBOX history: {ids2}"

    st2 = json.loads(state_path.read_text(encoding="utf-8"))
    inbox2 = st2["cursors"]["INBOX"]
    # INBOX back advanced to ts(m10) (the history batch's min); new unchanged (ts(m3)).
    assert inbox2["back"]["last_message_id"] == M10_ID, "INBOX back must advance to ts(m10)"
    assert inbox2["back"]["last_date"] < inbox1["new"]["last_date"]
    assert inbox2["new"]["last_message_id"] == M3_ID, "INBOX new unchanged"

    # A folder NOT in the batch (ORBIT) keeps both boundaries (unchanged across runs 1→2).
    orbit1_cur = st1["cursors"]["INBOX/ORBIT"]
    orbit2 = st2["cursors"]["INBOX/ORBIT"]
    assert orbit2 == orbit1_cur, "a folder absent from the batch must keep both boundaries"


# --------------------------------------------------------------------------- #
# 4d. Fresh bootstrap: deferred is capped (Task 5f — kills the Run-1 explosion) #
# --------------------------------------------------------------------------- #
def test_fresh_bootstrap_deferred_capped(tmp_path, monkeypatch):
    """FRESH world, MAX_BATCH=3: run 1 batch = 3 newest globally; deferred ≤ MAX_BATCH.

    Before Task 5f a fresh bootstrap routed the whole in-window backlog through the UNBOUNDED
    new pass → ~2,680 entries into deferred_new (the Run-1 state explosion). After the fix, a
    fresh-frontier folder's mail is backfill → the BOUNDED history pass, so deferred_new stays
    ≤ MAX_BATCH. A second _detect (next run) re-picks up exactly deferred_new's head minus
    processed — no loss, no dupe. Uses its own isolated corpus (not the shared module fixture).
    """
    base = tmp_path / "freshcap"
    mail_root = base / "mail"
    index_path = base / "index"
    work_dir = base / "work"

    _build_maildir(mail_root)
    _build_index(index_path, mail_root, work_dir)

    monkeypatch.setenv("MAIL_INDEX_DB", str(index_path))
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(mail_root))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    log_path = tmp_path / "processed-log.jsonl"
    monkeypatch.setenv("MAIL_PROCESSED_LOG", str(log_path))
    monkeypatch.setattr(mail_keeper, "MAX_BATCH", 3)

    # Run 1 (fresh state, MAX_BATCH=3): batch = the 3 newest KEPT globally; deferred ≤ 3.
    fake1 = _FakeRunner(_ok_result("freshcap run 1 (no table)"))
    ctx1 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake1,
    )
    result1 = _run_workflow(ctx1)
    assert result1.status == "ok"

    brief1 = fake1.calls[0]["brief"]
    ids1 = _manifest_ids_from_brief(brief1)
    # The 3 newest KEPT messages globally (m3, m2, m1 — all INBOX; no other folder has mail).
    assert ids1 == [M3_ID, M2_ID, M1_ID], f"run 1 batch must be the 3 newest globally: {ids1}"

    state_path = tmp_path / "state" / "mail-keeper.json"
    st1 = json.loads(state_path.read_text(encoding="utf-8"))
    deferred_ids1 = [d["message_id"] for d in st1["deferred"]]
    # The load-bearing assertion: the fresh-bootstrap backlog is CAPPED (not ~2,680 entries).
    assert len(deferred_ids1) <= 3, (
        f"fresh-bootstrap deferred must be ≤ MAX_BATCH=3: {deferred_ids1}"
    )
    # The kept overflow is exactly [m9, m6, m10] (the next-newest history after the batch), in
    # global-newest-first order. Pre-Task-5f this was the ENTIRE unbounded backlog (~2,680 live);
    # pinning it to the capped kept set proves the explosion is gone.
    assert deferred_ids1 == [M9_ID, M6_ID, M10_ID], (
        f"deferred should be the capped kept overflow [m9,m6,m10]: {deferred_ids1}"
    )

    # Run 2: no new mail → batch = deferred re-injected + history re-walk, deduped, capped. The
    # head of run-1's deferred (m9) is re-presented first; no loss (m10 still reachable), no dupe.
    fake2 = _FakeRunner(_ok_result("freshcap run 2 (no table)"))
    ctx2 = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake2,
    )
    result2 = _run_workflow(ctx2)
    assert result2.status == "ok"

    brief2 = fake2.calls[0]["brief"]
    ids2 = _manifest_ids_from_brief(brief2)
    # No loss: the deferred head (m9) is re-presented; no dupe: each id appears once.
    assert M9_ID in ids2, f"run 1's deferred head m9 must be re-presented on run 2: {ids2}"
    assert len(ids2) == len(set(ids2)), f"no duplicates in the batch: {ids2}"
    assert len(ids2) <= 3, f"run 2 batch must respect MAX_BATCH=3: {ids2}"


# --------------------------------------------------------------------------- #
# 4e. Pool is globally newest-first across folders (Task 5f — Change 2)        #
# --------------------------------------------------------------------------- #
def test_pool_global_newest_first_order(tmp_path, monkeypatch):
    """Two folders with interleaved dates → batch order is GLOBAL (90,80,70,60), not per-folder.

    Before Task 5f the pool was per-folder-block ordered (folder A's rows then folder B's), so a
    folder's older mail could sit ahead of another folder's newer mail. After Change 2 the pool is
    sorted globally newest-first (ts desc, id tie-break) before the cap. Uses its own isolated
    corpus with two triage folders (INBOX + INBOX/ORBIT) and interleaved in-window dates.
    """
    base = tmp_path / "globalorder"
    mail_root = base / "mail"
    index_path = base / "index"
    work_dir = base / "work"

    def _msg(mid: str, date_line: str, subject: str) -> str:
        return f"""From: Sender <{mid.split("@")[0]}@fixture.test>
To: someone@example.test
Subject: {subject}
Message-Id: <{mid}>
Date: {date_line}
Content-Type: text/plain; charset=utf-8

A message.
"""

    # INBOX (folder A): ts 90 (a1, Oct 20) and ts 70 (a2, Sep 15).
    _write_message(
        "INBOX",
        "a1.eml",
        _msg("a1@fixture.test", "Sun, 20 Oct 2026 09:00:00 +0000", "A one"),
        mail_root,
    )
    _write_message(
        "INBOX",
        "a2.eml",
        _msg("a2@fixture.test", "Mon, 15 Sep 2026 09:00:00 +0000", "A two"),
        mail_root,
    )
    # INBOX/ORBIT (folder B): ts 80 (b2, Oct 10) and ts 60 (b4, Aug 15). Interleaved with A.
    _write_message(
        "INBOX/ORBIT",
        "b2.eml",
        _msg("b2@fixture.test", "Thu, 08 Oct 2026 09:00:00 +0000", "B two"),
        mail_root,
    )
    _write_message(
        "INBOX/ORBIT",
        "b4.eml",
        _msg("b4@fixture.test", "Mon, 17 Aug 2026 09:00:00 +0000", "B four"),
        mail_root,
    )
    # A Sent Items message is required for the canary spot-check (own-mail → excluded from
    # detection, so it does not affect the batch-ordering assertion).
    _write_message("Sent Items", "m5.eml", M5, mail_root)

    _build_index(index_path, mail_root, work_dir)

    monkeypatch.setenv("MAIL_INDEX_DB", str(index_path))
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(mail_root))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    log_path = tmp_path / "processed-log.jsonl"
    monkeypatch.setenv("MAIL_PROCESSED_LOG", str(log_path))
    # MAX_BATCH=4 so all four in-window messages fit the batch (the ordering is the assertion).
    monkeypatch.setattr(mail_keeper, "MAX_BATCH", 4)

    fake = _FakeRunner(_ok_result("globalorder run 1 (no table)"))
    ctx = _make_ctx(
        tmp_path,
        {"mail_root": mail_root, "index_path": index_path},
        admin_repo=tmp_path / "admin",
        fake_runner=fake,
    )
    result = _run_workflow(ctx)
    assert result.status == "ok"

    ids = _manifest_ids_from_brief(fake.calls[0]["brief"])
    # GLOBAL newest-first: a1 (Oct 20) > b2 (Oct 8) > a2 (Sep 15) > b4 (Aug 17). NOT A-block
    # then B-block (which would be a1, a2, b2, b4).
    assert ids == ["a1@fixture.test", "b2@fixture.test", "a2@fixture.test", "b4@fixture.test"], (
        f"batch must be globally newest-first across folders: {ids}"
    )


# --------------------------------------------------------------------------- #
# 5. The floor excludes old mail (m8 never presented)                          #
# --------------------------------------------------------------------------- #
def test_floor_excludes_old_mail(hermetic_mail, tmp_path, monkeypatch):
    """The pre-floor message m8 (Mar 2025) is absent from every brief across runs 1–4."""
    _set_mail_env(monkeypatch, hermetic_mail, tmp_path)

    # Run 1: fresh state → the newest-first backfill batch (m8 must be absent).
    fake1 = _FakeRunner(_ok_result("run 1 (no table)"))
    ctx1 = _make_ctx(tmp_path, hermetic_mail, admin_repo=tmp_path / "admin", fake_runner=fake1)
    result1 = _run_workflow(ctx1)
    assert result1.status == "ok"
    brief1 = fake1.calls[0]["brief"]
    assert M8_ID not in brief1, "pre-floor m8 must never be presented"

    # Runs 2–4: no new mail (m8 stays excluded by the floor on every re-walk).
    for i in range(2, 5):
        fake = _FakeRunner(_ok_result("no-op"))  # must NOT be called
        ctx = _make_ctx(tmp_path, hermetic_mail, admin_repo=tmp_path / "admin", fake_runner=fake)
        result = _run_workflow(ctx)
        assert result.status == "ok"
        assert len(fake.calls) == 0
    # m8 is never in the processed log either.
    records = _read_processed_log(tmp_path / "processed-log.jsonl")
    assert M8_ID not in {r["email_file"] for r in records}


# --------------------------------------------------------------------------- #
# 6. Agent failure → retry (no progress on failure; same ids re-presented)    #
# --------------------------------------------------------------------------- #
def test_agent_failure_retry(hermetic_mail, tmp_path, monkeypatch):
    """Fresh state + agent error → status error, NO state file, log absent; retry re-presents."""
    _set_mail_env(monkeypatch, hermetic_mail, tmp_path)

    fake = _FakeRunner(_error_result())
    ctx = _make_ctx(tmp_path, hermetic_mail, admin_repo=tmp_path / "admin", fake_runner=fake)

    result = _run_workflow(ctx)

    assert result.status == "error"
    assert any("agent run error" in e for e in result.errors)
    # NO state file (the workflow writes no state on agent failure → fresh re-detection).
    assert not (tmp_path / "state" / "mail-keeper.json").exists()
    # Processed log NOT created.
    assert not (tmp_path / "processed-log.jsonl").exists()

    # Retry with a good shim re-presents the SAME ids (the newest-first backfill batch).
    fake2 = _FakeRunner(
        _ok_result(
            _triage_table(
                [
                    (M3_ID, "noise"),
                    (M2_ID, "noise"),
                    (M1_ID, "action"),
                    (M9_ID, "noise"),
                    (M6_ID, "noise"),
                    (M10_ID, "noise"),
                ]
            )
        )
    )
    ctx2 = _make_ctx(tmp_path, hermetic_mail, admin_repo=tmp_path / "admin", fake_runner=fake2)
    result2 = _run_workflow(ctx2)
    assert len(fake2.calls) == 1
    ids = _manifest_ids_from_brief(fake2.calls[0]["brief"])
    assert ids == [M3_ID, M2_ID, M1_ID, M9_ID, M6_ID, M10_ID]
    assert result2.status == "ok"


# --------------------------------------------------------------------------- #
# 7. v1 schema guard (no auto-migration)                                      #
# --------------------------------------------------------------------------- #
def test_v1_schema_guard(hermetic_mail, tmp_path, monkeypatch):
    """A v1-shaped state (folder cursor without new/back) → status error, no migration."""
    _set_mail_env(monkeypatch, hermetic_mail, tmp_path)

    # Pre-write a v1-shaped state: a flat {last_date, last_message_id} cursor entry.
    state_dir = tmp_path / "state"
    StateStore(state_dir).save(
        "mail-keeper",
        {
            "bootstrapped_at": "2026-10-21T22:30:00+00:00",
            "cursors": {"INBOX": {"last_date": 1, "last_message_id": M1_ID}},
            "deferred": [],
        },
    )

    fake = _FakeRunner(_ok_result("must-not-run"))  # must NOT be called
    ctx = _make_ctx(
        tmp_path,
        hermetic_mail,
        admin_repo=tmp_path / "admin",
        fake_runner=fake,
        state_dir=state_dir,
    )

    result = _run_workflow(ctx)

    assert result.status == "error"
    assert any("state schema mismatch" in e for e in result.errors)
    assert any("delete state/mail-keeper.json" in e for e in result.errors)
    # No auto-migration: the agent was never invoked.
    assert len(fake.calls) == 0


# --------------------------------------------------------------------------- #
# 8. Backup integrity trip                                                    #
# --------------------------------------------------------------------------- #
def test_backup_integrity_trip(hermetic_mail, tmp_path, monkeypatch):
    """Mutated post-snapshot → status error with a guardrail message (agent was ok)."""
    _set_mail_env(monkeypatch, hermetic_mail, tmp_path)

    real_snapshot = mail_keeper._backup_snapshot
    # Mutate the REAL file's mtime on disk between the two snapshot calls: touching the
    # actual file is the unambiguous way to make before/after differ (the agent is a fake
    # that does not write, so the only "change" is this deliberate touch).
    target_file = hermetic_mail["mail_root"] / ACCOUNT / "INBOX" / "cur" / "m1.eml"
    mut_state = {"calls": 0}

    def mutating_snapshot(mail_root: Path) -> dict:
        mut_state["calls"] += 1
        if mut_state["calls"] == 2:
            # Second call (post-agent): bump the file's mtime so the snapshot differs.
            time.sleep(0.01)
            target_file.touch()
        return real_snapshot(mail_root)

    monkeypatch.setattr(mail_keeper, "_backup_snapshot", mutating_snapshot)

    fake = _FakeRunner(
        _ok_result(
            _triage_table(
                [
                    (M3_ID, "noise"),
                    (M2_ID, "noise"),
                    (M1_ID, "action"),
                    (M9_ID, "noise"),
                    (M6_ID, "noise"),
                    (M10_ID, "noise"),
                ]
            )
        )
    )
    ctx = _make_ctx(tmp_path, hermetic_mail, admin_repo=tmp_path / "admin", fake_runner=fake)

    result = _run_workflow(ctx)

    assert result.status == "error"
    assert any("guardrail trip" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# 9. Index missing                                                            #
# --------------------------------------------------------------------------- #
def test_index_missing(hermetic_mail, tmp_path, monkeypatch):
    """MAIL_INDEX_DB → nonexistent path → skipped; no state; agent + canary not run."""
    monkeypatch.setenv("MAIL_INDEX_DB", str(tmp_path / "no-such-index"))
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(hermetic_mail["mail_root"]))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    monkeypatch.setenv("MAIL_PROCESSED_LOG", str(tmp_path / "no-log.jsonl"))

    canary_calls = {"n": 0}
    real_run_canaries = mail_keeper.canary.run_canaries

    def spy_run_canaries(*args, **kwargs):
        canary_calls["n"] += 1
        return real_run_canaries(*args, **kwargs)

    monkeypatch.setattr(mail_keeper.canary, "run_canaries", spy_run_canaries)

    fake = _FakeRunner(_ok_result("must-not-run"))
    ctx = _make_ctx(tmp_path, hermetic_mail, admin_repo=tmp_path / "admin", fake_runner=fake)

    result = _run_workflow(ctx)

    assert result.status == "skipped"
    # No state file created.
    assert not (tmp_path / "state" / "mail-keeper.json").exists()
    # Agent not called; canary not run.
    assert len(fake.calls) == 0
    assert canary_calls["n"] == 0


# --------------------------------------------------------------------------- #
# 10. Base-smoke compatibility (load-bearing)                                 #
# --------------------------------------------------------------------------- #
def test_base_smoke_compatibility():
    """The ACTUAL base smoke suite passes with mail-keeper enabled + env isolation in place.

    This is the load-bearing check: it runs :mod:`tests.smoke.test_smoke_base` (which, via
    Task 3b's additive edit, points MAIL_INDEX_DB at a nonexistent tmp path) and asserts all
    5 tests pass. The run-log assertions (``WORKFLOW mail-keeper status=skipped`` present,
    ``agent mail-keeper started`` absent) are verified by the full-suite run recorded in the
    result report; here we drive the suite in-process to keep this test hermetic and fast.
    """
    import subprocess as _subprocess

    proc = _subprocess.run(
        ["uv", "run", "pytest", "tests/smoke/test_smoke_base.py", "-q"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=120,
    )
    assert proc.returncode == 0, f"base smoke failed:\n{proc.stdout}\n{proc.stderr}"
    assert "5 passed" in proc.stdout
