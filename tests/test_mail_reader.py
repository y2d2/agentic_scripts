"""Hermetic tests for the notmuch mail reader (Task 4).

These tests build a throwaway maildir + notmuch index entirely inside ``tmp_path``
and never touch the live index at ``/workspace/docker/mbsync/notmuch/``. Indexing via
``notmuch new`` happens only in fixture *setup* — the :class:`NotmuchReader` class
API itself never calls ``new`` (read-only contract). The maildir layout, the reader
config, and the notmuch binary are all isolated per test session.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from agentic_scripts.mail.reader import (
    NotmuchError,
    NotmuchReader,
    q_and,
    q_date_prefix,
    q_folder,
    q_from,
    q_id,
    q_text,
    q_thread,
)

ACCOUNT = "acct"

M1_ID = "m1@example.com"
M2_ID = "m2@example.com"
M3_ID = "m3@example.com"

# The three fixture messages. m1/m3 are plain text from Alice; m2 is HTML-only from
# Bob (its body part carries only content-length, so the reader must fall back to the
# raw maildir file). Dates are in 2026 for the date-prefix test.
M1 = """From: Alice <alice@example.com>
To: someone@example.com
Subject: Hello plain
Message-Id: <m1@example.com>
Date: Tue, 20 Oct 2026 10:00:00 +0000
Content-Type: text/plain; charset=utf-8

This is a plain hello body.
"""

M2 = """From: Bob <bob@example.com>
To: someone@example.com
Subject: Html only
Message-Id: <m2@example.com>
Date: Tue, 20 Oct 2026 11:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="BOUNDARY"

--BOUNDARY
Content-Type: text/html; charset=utf-8

<p>This is an HTML body marker.</p>
--BOUNDARY--
"""

M3 = """From: Alice <alice@example.com>
To: someone@example.com
Subject: Second from alice
Message-Id: <m3@example.com>
Date: Tue, 20 Oct 2026 12:00:00 +0000
Content-Type: text/plain; charset=utf-8

Second plain body.
"""

HTML_MARKER = "This is an HTML body marker."


def _build_maildir(mail_root: Path) -> None:
    """Create the three-message maildir under ``mail_root/<ACCOUNT>/cur/``."""
    cur = mail_root / ACCOUNT / "cur"
    cur.mkdir(parents=True, exist_ok=True)
    (cur / "m1.eml").write_text(M1, encoding="utf-8")
    (cur / "m2.eml").write_text(M2, encoding="utf-8")
    (cur / "m3.eml").write_text(M3, encoding="utf-8")


def _build_index(index_path: Path, mail_root: Path, work_dir: Path) -> None:
    """Write a reader-style config and run ``notmuch new`` to build the index.

    This is test *setup only* — :class:`NotmuchReader` itself never calls ``new``.
    The config uses ``synchronize_flags=false`` (reader side), matching what the
    class would generate, so the fixture exercises the same read-only surface.
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


@pytest.fixture(scope="module")
def hermetic_mail(tmp_path_factory) -> tuple[NotmuchReader, Path, dict]:
    """Build a throwaway maildir + index and return (reader, base_dir, metadata).

    Module-scoped so the one-time ``notmuch new`` cost is paid once per test session,
    keeping total wall time comfortably under 30s. Every path lives under a fresh
    ``tmp_path_factory`` directory; nothing outside it is touched.
    """
    base = tmp_path_factory.mktemp("hermetic_mail")
    mail_root = base / "mail"
    index_path = base / "notmuch-index"
    work_dir = base / "work"

    _build_maildir(mail_root)
    _build_index(index_path, mail_root, work_dir)

    reader = NotmuchReader(index_path=index_path, mail_root=mail_root, work_dir=work_dir)
    metadata = {
        "m1": M1_ID,
        "m2": M2_ID,
        "m3": M3_ID,
        "account": ACCOUNT,
        "alice_ids": [M1_ID, M3_ID],
    }
    return reader, base, metadata


# --------------------------------------------------------------------------- #
# 1. count() behaviour                                                        #
# --------------------------------------------------------------------------- #
def test_count_total_and_filtered(hermetic_mail):
    """count() == 3 total; from:Alice == 2; folder:cur consistent with its own query."""
    reader, _base, meta = hermetic_mail

    assert reader.count() == 3
    assert reader.count(q_from("Alice")) == 2

    # Folder consistency: the account's top-level dir is what notmuch reports as the
    # folder for these messages. Assert against count()'s own value (consistency),
    # not a hardcoded name — but also pin the expected shape (account root).
    assert reader.count(q_folder(meta["account"], "")) == 3


# --------------------------------------------------------------------------- #
# 2. search() thread rows                                                     #
# --------------------------------------------------------------------------- #
def test_search_from_alice(hermetic_mail):
    """search(from:Alice) yields 1-2 threads whose message_ids union is the Alice ids."""
    reader, _base, meta = hermetic_mail

    rows = reader.search(q_from("Alice"))
    assert 1 <= len(rows) <= 2

    union: set[str] = set()
    for row in rows:
        union.update(row["message_ids"])
        assert row["subject"]
        assert row["authors"]
        assert row["timestamp"] is not None and row["timestamp"] != ""

    assert union == set(meta["alice_ids"])


# --------------------------------------------------------------------------- #
# 3. message_ids() dedup                                                      #
# --------------------------------------------------------------------------- #
def test_message_ids_free_text(hermetic_mail):
    """message_ids over a free-text query returns the two Alice ids, deduped."""
    reader, _base, meta = hermetic_mail

    ids = reader.message_ids("alice")
    assert set(ids) == set(meta["alice_ids"])
    # Deduplicated: no repeats even though both messages match.
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# 4. show() primary + context                                                 #
# --------------------------------------------------------------------------- #
def test_show_primary(hermetic_mail):
    """show(m1) returns the correct primary id, a Subject header, and a list context."""
    reader, _base, meta = hermetic_mail

    doc = reader.show(meta["m1"])
    assert doc["primary"]["id"] == meta["m1"]
    headers = doc["primary"]["headers"]
    assert "Hello plain" in headers.get("Subject", "")
    assert isinstance(doc["context"], list)
    # raw is the full parsed document (a nested recursive list).
    assert isinstance(doc["raw"], list)


# --------------------------------------------------------------------------- #
# 5. body_text() plain-text path                                              #
# --------------------------------------------------------------------------- #
def test_body_text_plain(hermetic_mail):
    """body_text(m1) returns the plain text and a None path."""
    reader, _base, meta = hermetic_mail

    text, path = reader.body_text(meta["m1"])
    assert path is None
    assert text is not None
    assert "plain hello" in text


# --------------------------------------------------------------------------- #
# 6. body_text() HTML-only fallback                                           #
# --------------------------------------------------------------------------- #
def test_body_text_html_fallback(hermetic_mail):
    """body_text(m2) returns (None, raw_path) pointing at the existing maildir file."""
    reader, _base, meta = hermetic_mail

    text, path = reader.body_text(meta["m2"])
    assert text is None
    assert isinstance(path, Path)
    assert path.exists()
    assert HTML_MARKER in path.read_bytes().decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# 7. count on a nonexistent id query                                          #
# --------------------------------------------------------------------------- #
def test_count_nonexistent_id(hermetic_mail):
    """count(id:<missing>) returns 0, not an error."""
    reader, _base, _meta = hermetic_mail

    assert reader.count(q_id("does-not-exist@example.com")) == 0


# --------------------------------------------------------------------------- #
# 8. query-builder unit tests (no notmuch involved)                           #
# --------------------------------------------------------------------------- #
def test_builder_outputs():
    """Each builder emits exactly the verified working form."""
    assert q_from("Yuri Durodie") == 'from:"Yuri Durodie"'
    assert q_folder("a@b", "Sent Items") == 'folder:"a@b/Sent Items"'
    assert q_date_prefix(2026) == "date:2026*"
    assert q_id("m1@example.com") == "id:m1@example.com"
    assert q_thread("0000000000000001") == "thread:0000000000000001"
    assert q_text("hello world") == "hello world"


def test_builder_q_and_join():
    """q_and joins clauses with ' and '."""
    assert q_and(q_from("x"), q_date_prefix(2026)) == 'from:"x" and date:2026*'


def test_builder_q_and_empty_raises():
    """q_and() with no clauses raises NotmuchError (a caller bug)."""
    with pytest.raises(NotmuchError):
        q_and()


def test_builder_q_and_rejects_broken_prefix():
    """q_and rejects a clause whose first token uses an unsupported prefix."""
    with pytest.raises(NotmuchError):
        q_and("after:2026-01-01")
    with pytest.raises(NotmuchError):
        q_and(q_from("x"), "before:2027-01-01")


# --------------------------------------------------------------------------- #
# 9. broken query surfaces                                                    #
# --------------------------------------------------------------------------- #
def test_broken_query_surfaces(hermetic_mail):
    """Document how this build treats the broken ``all:`` form at runtime.

    Note (deviation from task spec test #9): in notmuch 0.38.3 as installed here,
    ``all:`` is a *silent no-op* — ``notmuch count 'all:'`` exits 0 and prints ``0``
    rather than erroring. The builder's refusal contract (test 8) is what keeps these
    forms out of real queries; this test records the actual runtime behaviour so the
    build's quirk is documented by an executable assertion instead of a false
    expectation of a non-zero exit.
    """
    reader, _base, _meta = hermetic_mail

    # The broken form silently no-ops: it does NOT error and matches nothing.
    assert reader.count("all:") == 0


# --------------------------------------------------------------------------- #
# 10. read-only contract (mtime snapshot)                                     #
# --------------------------------------------------------------------------- #
def test_read_only_contract(hermetic_mail):
    """A search + show cycle leaves every maildir file's mtime unchanged."""
    reader, base, meta = hermetic_mail

    mail_root = base / "mail"
    files = sorted(p for p in mail_root.rglob("*") if p.is_file())
    assert files, "expected at least one mail file to snapshot"
    before = {p: p.stat().st_mtime_ns for p in files}

    reader.search(q_from("Alice"))
    reader.show(meta["m1"])

    after = {p: p.stat().st_mtime_ns for p in files}
    assert before == after, "reader mutated maildir mtimes (read-only contract violated)"


# --------------------------------------------------------------------------- #
# Acceptance item 4: generated config matches the canonical reader config     #
# --------------------------------------------------------------------------- #
def test_generated_config_matches_canonical(hermetic_mail):
    """The reader's generated config equals the canonical template modulo paths."""
    reader, _base, _meta = hermetic_mail

    config_path = reader.work_dir / "notmuch-reader-config"
    assert config_path.is_file()
    # 0600 permissions.
    mode = config_path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    text = config_path.read_text(encoding="utf-8")
    expected = (
        "[database]\n"
        f"path={reader.index_path}\n"
        f"mail_root={reader.mail_root}\n"
        "[maildir]\n"
        "synchronize_flags=false\n"
    )
    assert text == expected
