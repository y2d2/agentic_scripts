"""Hermetic tests for the ``mail-search`` CLI (Task 1).

These tests build a throwaway maildir + notmuch index entirely inside
``tmp_path_factory`` (following :mod:`tests.test_mail_reader`'s fixture pattern) and
invoke the CLI in-process via :func:`agentic_scripts.mail.mail_search.main` with
``capsys``-style capture + ``monkeypatch`` env. They never touch the live index at
``/workspace/docker/mbsync/notmuch/`` or the maildir at
``/workspace/docker/mbsync/backup``.

Fixture messages (account ``acct@example.test``):
    m1  INBOX, plain text, From: Coera <coera@orbit.example.test>, Subject: EUG schedule
    m2  INBOX, multipart plain+html, From: Alice <alice@example.test>
    m3  INBOX, HTML-only with a body > 2000 chars, From: Bob <bob@example.test>
    m4  INBOX, replies to m1 (References/In-Reply-To), From: Coera <coera@orbit.example.test>
    m5  Sent Items, plain text, From: Yuri Durodie <yuri.durodie@vub.be>

Dates are chosen so that --since/--until boundary tests are unambiguous and --thread
on a query matching m1 returns both m1 and m4 in date order.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from agentic_scripts.mail import mail_search
from agentic_scripts.mail.reader import NotmuchReader

ACCOUNT = "acct@example.test"
OWNER = "yuri.durodie@vub.be"

M1_ID = "m1@orbit.example.test"
M2_ID = "m2@example.test"
M3_ID = "m3@example.test"
M4_ID = "m4@orbit.example.test"
M5_ID = "m5@vub.be"

# m1: plain text, recent date (the --since/--until anchor). Body contains "EUG".
M1 = """From: Coera <coera@orbit.example.test>
To: someone@example.test
Subject: EUG schedule
Message-Id: <m1@orbit.example.test>
Date: Tue, 20 Oct 2026 10:00:00 +0000
Content-Type: text/plain; charset=utf-8

EUG meeting on the 25th. Please confirm attendance.
"""

# m2: multipart plain+html (exercises the reader's plain-text path over a container).
M2 = """From: Alice <alice@example.test>
To: someone@example.test
Subject: Multipart hello
Message-Id: <m2@example.test>
Date: Tue, 21 Oct 2026 09:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="BOUNDARY"

--BOUNDARY
Content-Type: text/plain; charset=utf-8

Plain part of the multipart message.
--BOUNDARY
Content-Type: text/html; charset=utf-8

<p>Html part of the multipart message.</p>
--BOUNDARY--
"""

# m3: HTML-only with a body > 2000 chars (exercises the raw-file MIME fallback).
_HTML_BODY = "<html><body>" + ("<p>Long html paragraph. " * 60) + "</body></html>"
M3 = f"""From: Bob <bob@example.test>
To: someone@example.test
Subject: Html only long body
Message-Id: <m3@example.test>
Date: Tue, 22 Oct 2026 08:00:00 +0000
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

{_HTML_BODY}
"""

# m4: replies to m1 (References/In-Reply-To), later date than m1.
M4 = """From: Coera <coera@orbit.example.test>
To: someone@example.test
Subject: Re: EUG schedule
Message-Id: <m4@orbit.example.test>
Date: Wed, 21 Oct 2026 15:00:00 +0000
References: <m1@orbit.example.test>
In-Reply-To: <m1@orbit.example.test>
Content-Type: text/plain; charset=utf-8

Confirming for the EUG meeting. See you there.
"""

# m5: sent by the owner, in Sent Items.
M5 = """From: Yuri Durodie <yuri.durodie@vub.be>
To: coera@orbit.example.test
Subject: Re: EUG schedule (sent)
Message-Id: <m5@vub.be>
Date: Thu, 22 Oct 2026 16:00:00 +0000
References: <m4@orbit.example.test>
In-Reply-To: <m4@orbit.example.test>
Content-Type: text/plain; charset=utf-8

Sent from the owner's account for style sampling.
"""


def _build_maildir(mail_root: Path) -> None:
    """Create the five-message maildir under ``mail_root/<ACCOUNT>/``."""
    inbox_cur = mail_root / ACCOUNT / "INBOX" / "cur"
    sent_cur = mail_root / ACCOUNT / "Sent Items" / "cur"
    inbox_cur.mkdir(parents=True, exist_ok=True)
    sent_cur.mkdir(parents=True, exist_ok=True)
    (inbox_cur / "m1.eml").write_text(M1, encoding="utf-8")
    (inbox_cur / "m2.eml").write_text(M2, encoding="utf-8")
    (inbox_cur / "m3.eml").write_text(M3, encoding="utf-8")
    (inbox_cur / "m4.eml").write_text(M4, encoding="utf-8")
    (sent_cur / "m5.eml").write_text(M5, encoding="utf-8")


def _build_index(index_path: Path, mail_root: Path, work_dir: Path) -> None:
    """Write a reader-style config and run ``notmuch new`` to build the index.

    Test setup only — :class:`NotmuchReader` itself never calls ``new`` (read-only
    contract). The config uses ``synchronize_flags=false`` (reader side), matching what
    the class would generate, so the fixture exercises the same read-only surface.
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


# The module-scoped fixture stashes its paths here so per-test fixtures (which cannot
# depend on a module-scoped fixture without triggering the scope mismatch) can read the
# mail root and index path to point the CLI at the throwaway tree.
_SESSION: dict[str, object] = {}


@pytest.fixture(scope="module")
def hermetic_mail(tmp_path_factory) -> tuple[NotmuchReader, Path, dict]:
    """Build a throwaway maildir + index and return (reader, base_dir, metadata).

    Module-scoped so the one-time ``notmuch new`` cost is paid once per test session.
    Every path lives under a fresh ``tmp_path_factory`` directory; nothing outside it is
    touched. The reader's work_dir is separate from the setup work_dir (the CLI builds
    its own temp work dir at runtime). Paths are also stashed in :data:`_SESSION` so the
    per-test env fixture can point the CLI at this tree.
    """
    base = tmp_path_factory.mktemp("hermetic_mail_search")
    mail_root = base / "mail"
    index_path = base / "notmuch-index"
    work_dir = base / "work"

    _build_maildir(mail_root)
    _build_index(index_path, mail_root, work_dir)

    reader = NotmuchReader(
        index_path=index_path, mail_root=mail_root, work_dir=base / "reader-work"
    )
    metadata = {
        "m1": M1_ID,
        "m2": M2_ID,
        "m3": M3_ID,
        "m4": M4_ID,
        "m5": M5_ID,
        "account": ACCOUNT,
        "mail_root": mail_root,
        "index_path": index_path,
    }
    _SESSION["mail_root"] = mail_root
    _SESSION["index_path"] = index_path
    return reader, base, metadata


@pytest.fixture
def env_setup(monkeypatch) -> None:
    """Point the CLI at the throwaway mail root + owner; clear MAIL_INDEX_DB.

    The CLI resolves ``mail_root`` from ``MAIL_MAIL_ROOT`` (else the live default) and
    the index from ``--index`` (passed per test). We set ``MAIL_MAIL_ROOT`` to the
    fixture's throwaway tree so the reader's generated config points at it, and clear
    ``MAIL_INDEX_DB`` so an unset env var cannot leak a live path into the CLI.
    """
    monkeypatch.setenv("MAIL_MAIL_ROOT", str(_SESSION["mail_root"]))
    monkeypatch.setenv("MAIL_OWNER_ADDRESS", OWNER)
    monkeypatch.delenv("MAIL_INDEX_DB", raising=False)


def _run_cli(hermetic_mail, env_setup, *args: str) -> tuple[int, str, str]:
    """Invoke the CLI in-process and return (exit_code, stdout, stderr)."""
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mail_search.main(list(args))
    return code, out.getvalue(), err.getvalue()


def _index_flag(meta: dict) -> list[str]:
    """Return the ``--index <path>`` argv fragment for the fixture index."""
    return ["--index", str(meta["index_path"])]


# --------------------------------------------------------------------------- #
# 1. Usage errors (exit 2) and --help (exit 0)                                #
# --------------------------------------------------------------------------- #
def test_usage_no_query_no_folder(hermetic_mail, env_setup):
    """No query and no --folder → exit 2."""
    code, _out, err = _run_cli(hermetic_mail, env_setup, *_index_flag(hermetic_mail[2]))
    assert code == 2
    assert "query or --folder" in err


def test_usage_show_plus_positional(hermetic_mail, env_setup):
    """--show + positional query → exit 2 (mutually exclusive)."""
    code, _out, err = _run_cli(
        hermetic_mail, env_setup, M1_ID, "--show", M1_ID, *_index_flag(hermetic_mail[2])
    )
    assert code == 2
    assert "exclusive" in err


def test_usage_show_alone(hermetic_mail, env_setup):
    """--show with an empty id → exit 2 (requires a non-empty message id)."""
    code, _out, err = _run_cli(
        hermetic_mail, env_setup, "--show", "", *_index_flag(hermetic_mail[2])
    )
    assert code == 2
    assert "non-empty" in err


def test_usage_bad_since(hermetic_mail, env_setup):
    """Invalid --since (not YYYY-MM-DD) → exit 2."""
    code, _out, err = _run_cli(
        hermetic_mail, env_setup, "EUG", "--since", "not-a-date", *_index_flag(hermetic_mail[2])
    )
    assert code == 2
    assert "YYYY-MM-DD" in err


def test_help_exits_zero(hermetic_mail, env_setup):
    """--help → exit 0 (before index resolution)."""
    # argparse raises SystemExit(0) for --help; main propagates it.
    with pytest.raises(SystemExit) as exc_info:
        _run_cli(hermetic_mail, env_setup, "--help")
    assert exc_info.value.code == 0


# --------------------------------------------------------------------------- #
# 2. Index missing/unreadable (exit 1)                                        #
# --------------------------------------------------------------------------- #
def test_index_unset_env_no_flag(hermetic_mail, env_setup):
    """MAIL_INDEX_DB unset + no --index → exit 1 with a stderr reason."""
    code, _out, err = _run_cli(hermetic_mail, env_setup, "EUG")
    assert code == 1
    assert "index" in err.lower()


def test_index_nonexistent_path(hermetic_mail, env_setup):
    """--index /nonexistent → exit 1."""
    code, _out, err = _run_cli(
        hermetic_mail, env_setup, "EUG", "--index", "/nonexistent-index-path"
    )
    assert code == 1
    assert "not an existing directory" in err


# --------------------------------------------------------------------------- #
# 3. List mode: block format, body, blank-line separation, zero-match         #
# --------------------------------------------------------------------------- #
def test_list_mode_block_format(hermetic_mail, env_setup):
    """A query matching m1 (and its reply m4) emits the contract block format."""
    code, out, _err = _run_cli(hermetic_mail, env_setup, "EUG", *_index_flag(hermetic_mail[2]))
    assert code == 0

    lines = out.split("\n")
    header_lines = [ln for ln in lines if ln.startswith("=== ")]
    # m1 and m4 both contain "EUG" (m4 subject "Re: EUG schedule").
    assert len(header_lines) >= 2

    # The m1 header line matches the contract shape exactly.
    m1_line = next(ln for ln in header_lines if M1_ID in ln)
    assert m1_line.startswith(f"=== {M1_ID} | INBOX | ")
    assert "| Coera <coera@orbit.example.test> | EUG schedule" in m1_line

    # Body present (the plain-text body of m1).
    assert "EUG meeting on the 25th" in out

    # No trailing blank line: the output must not end with two newlines.
    assert not out.endswith("\n\n")


def test_list_mode_blank_line_between_blocks(hermetic_mail, env_setup):
    """Multiple matches are separated by exactly one blank line."""
    code, out, _err = _run_cli(hermetic_mail, env_setup, "EUG", *_index_flag(hermetic_mail[2]))
    assert code == 0
    blocks = out.split("\n\n")
    assert len(blocks) >= 2
    # Each block's first line is a header.
    for block in blocks:
        assert block.startswith("=== ")


def test_list_mode_zero_match(hermetic_mail, env_setup):
    """A query matching nothing → exit 0, empty stdout."""
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "zzz-no-such-term-xyz", *_index_flag(hermetic_mail[2])
    )
    assert code == 0
    assert out == ""


# --------------------------------------------------------------------------- #
# 4. Filters                                                                  #
# --------------------------------------------------------------------------- #
def test_filter_from_case_insensitive(hermetic_mail, env_setup):
    """--from COERA (case-insensitive, partial) matches m1 and m4 (both Coera)."""
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "EUG", "--from", "COERA", *_index_flag(hermetic_mail[2])
    )
    assert code == 0
    assert M1_ID in out
    assert M4_ID in out
    # m5 (owner) and m2/m3 are not Coera.
    assert M5_ID not in out


def test_filter_folder_inbox_vs_sent(hermetic_mail, env_setup):
    """--folder INBOX vs --folder 'Sent Items' (space) select different messages."""
    # INBOX: m1..m4 present, m5 absent.
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "--folder", "INBOX", *_index_flag(hermetic_mail[2])
    )
    assert code == 0
    assert M1_ID in out and M4_ID in out
    assert M5_ID not in out

    # Sent Items (with a space): m5 present, INBOX messages absent.
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "--folder", "Sent Items", *_index_flag(hermetic_mail[2])
    )
    assert code == 0
    assert M5_ID in out
    assert M1_ID not in out


def test_filter_folder_missing(hermetic_mail, env_setup):
    """--folder INBOX/ORBIT (missing) → zero matches, exit 0."""
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "--folder", "INBOX/ORBIT", *_index_flag(hermetic_mail[2])
    )
    assert code == 0
    assert out == ""


def test_filter_since_until_boundary(hermetic_mail, env_setup):
    """--since/--until boundary behaviour on the EUG thread."""
    meta = hermetic_mail[2]
    # m1 is 2026-10-20, m4 is 2026-10-21 (UTC). Since 2026-10-20 → both.
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "EUG", "--since", "2026-10-20", *_index_flag(meta)
    )
    assert code == 0
    assert M1_ID in out and M4_ID in out

    # Since 2026-10-21 → only m4 (m1 is the day before).
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "EUG", "--since", "2026-10-21", *_index_flag(meta)
    )
    assert code == 0
    assert M4_ID in out
    assert M1_ID not in out

    # Until 2026-10-20 → only m1.
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "EUG", "--until", "2026-10-20", *_index_flag(meta)
    )
    assert code == 0
    assert M1_ID in out
    assert M4_ID not in out


def test_filter_own(hermetic_mail, env_setup):
    """--own returns only m5 (the owner's sent message)."""
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "EUG", "--own", *_index_flag(hermetic_mail[2])
    )
    assert code == 0
    assert M5_ID in out
    assert M1_ID not in out and M4_ID not in out


def test_filter_limit(hermetic_mail, env_setup):
    """--limit 2 returns at most 2 messages."""
    code, out, _err = _run_cli(
        hermetic_mail,
        env_setup,
        "--folder",
        "INBOX",
        "--limit",
        "2",
        *_index_flag(hermetic_mail[2]),
    )
    assert code == 0
    header_lines = [ln for ln in out.split("\n") if ln.startswith("=== ")]
    assert len(header_lines) == 2


# --------------------------------------------------------------------------- #
# 5. --thread expansion                                                       #
# --------------------------------------------------------------------------- #
def test_thread_expansion(hermetic_mail, env_setup):
    """--thread on a query matching m1 returns both m1 and m4 in date order."""
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "EUG", "--thread", *_index_flag(hermetic_mail[2])
    )
    assert code == 0
    # Both m1 and m4 are in the same thread (m4 references m1).
    assert M1_ID in out
    assert M4_ID in out
    # Date order: m1 (Oct 20) before m4 (Oct 21).
    assert out.index(M1_ID) < out.index(M4_ID)


# --------------------------------------------------------------------------- #
# 6. HTML-only MIME fallback                                                  #
# --------------------------------------------------------------------------- #
def test_html_only_fallback(hermetic_mail, env_setup):
    """m3 (HTML-only) body is non-empty via the raw-file MIME fallback."""
    reader, _base, meta = hermetic_mail

    # Direct unit call: body_text returns (None, raw_path) for HTML-only m3.
    text, path = reader.body_text(M3_ID)
    assert text is None
    assert isinstance(path, Path)
    assert path.exists()

    # The CLI's fallback extractor produces non-empty tag-stripped text.
    body = mail_search._body_from_raw(path)
    assert "Long html paragraph" in body
    assert "<p>" not in body  # tags stripped

    # And the CLI list mode emits a non-empty body block for m3.
    code, out, _err = _run_cli(hermetic_mail, env_setup, "Html only long body", *_index_flag(meta))
    assert code == 0
    assert M3_ID in out
    # The tag-stripped body appears (truncated to 2000 chars but non-empty).
    assert "Long html paragraph" in out


# --------------------------------------------------------------------------- #
# 7. Detail mode                                                              #
# --------------------------------------------------------------------------- #
def test_detail_mode(hermetic_mail, env_setup):
    """--show <m1-id> prints full headers + the full (untruncated) body."""
    code, out, _err = _run_cli(
        hermetic_mail, env_setup, "--show", M1_ID, *_index_flag(hermetic_mail[2])
    )
    assert code == 0
    # Header lines present.
    assert "From:" in out
    assert "Subject:" in out
    assert "Date:" in out
    assert "Message-ID:" in out
    # Full (untruncated) body present.
    assert "EUG meeting on the 25th. Please confirm attendance." in out
