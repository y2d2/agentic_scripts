"""Hermetic tests for runner-owned pruning of checked daily entries (Task 1).

These tests build tiny throwaway vault trees entirely inside ``tmp_path``
(``vault_root/mail/daily/*.md``) and assert on the exact observable state after each
:func:`agentic_scripts.mail.prune.prune_daily` pass — file contents, deletions, and the
``.pruned.jsonl`` line set. They never touch a real vault or any git binary.

Day-file fixture content is built in the exact new format (checkbox line, indented
``Summary:``/``People:``/``Artifacts:``/``Draft:``/``id:`` lines, one blank line between
entries) via :func:`_entry` / :func:`_day_file`. The eight enumerated cases from the task
plan are covered one-for-one (see the numbered section banners).
"""

from __future__ import annotations

import os
from pathlib import Path

from agentic_scripts.mail.prune import PruneSummary, prune_daily


# --------------------------------------------------------------------------- #
# Fixture helpers                                                              #
# --------------------------------------------------------------------------- #
def _entry(
    checked: bool,
    msg_id: str | None,
    summary: str = "A short summary.",
    people: str = "—",
    artifacts: str = "—",
    draft_lines: tuple[str, ...] = (),
) -> str:
    """Build one new-format entry block (checkbox line + indented continuation lines).

    Args:
        checked: True for a ``- [x]`` (checked) entry, False for ``- [ ]``.
        msg_id: The full RFC 5322 Message-ID (without angle brackets); ``None`` models a
            malformed entry with no ``id:`` line.
        summary: Text of the ``Summary:`` line.
        people: Text of the ``People:`` line.
        artifacts: Text of the ``Artifacts:`` line.
        draft_lines: Quoted lines for an inline ``Draft:`` block (empty → omitted).

    Returns:
        The entry as a string with a trailing newline; the ``id:`` line is last.
    """
    box = "x" if checked else " "
    lines = [f"- [{box}] **Sender** — Subject — action", f"  Summary: {summary}"]
    if people != "—":
        lines.append(f"  People: {people}")
    else:
        lines.append("  People: —")
    if artifacts != "—":
        lines.append(f"  Artifacts: {artifacts}")
    else:
        lines.append("  Artifacts: —")
    if draft_lines:
        lines.append("  Draft:")
        for dl in draft_lines:
            lines.append(dl)
    if msg_id is not None:
        lines.append(f"  id: {msg_id}")
    return "\n".join(lines) + "\n"


def _day_file(date: str, entries: list[str], header: str | None = None) -> str:
    """Join a day header with entry blocks separated by exactly one blank line."""
    hdr = header if header is not None else f"# Mail daily — {date}\n"
    body = "\n".join(entries)
    return hdr + "\n" + body


def _write_daily(vault_root: Path, name: str, content: str) -> Path:
    """Create ``vault_root/mail/daily/<name>`` with ``content`` and return its path."""
    daily = vault_root / "mail" / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    path = daily / name
    path.write_text(content, encoding="utf-8")
    return path


def _pruned_lines(vault_root: Path) -> list[str]:
    """Return the non-empty lines of ``.pruned.jsonl`` (empty when absent)."""
    path = vault_root / "mail" / "daily" / ".pruned.jsonl"
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# 1. Mixed file: 2 checked + 2 unchecked, one checked carries a Draft block   #
# --------------------------------------------------------------------------- #
def test_mixed_file_prunes_checked_keeps_unchecked(tmp_path):
    """Checked blocks are removed; unchecked blocks stay byte-identical and in order."""
    draft = (
        "  > To: Coera <coera@orbit.example.org>",
        "  > Subject: Re: EUG schedule",
        "  > Hi Coera,",
        "  >",
        "  > Confirmed on our side for the 24th.",
        "  > Best,",
        "  > Me",
    )
    entries = [
        _entry(
            True,
            "chk1@orbit.example.org",
            summary="Checked one with a draft block.",
            artifacts="projects/ORBIT/01_Meetings.md → ## EUG Meetings",
            draft_lines=draft,
        ),
        _entry(False, "unk1@example.test", summary="Unchecked one."),
        _entry(True, "chk2@orbit.example.org", summary="Checked two."),
        _entry(False, "unk2@example.test", summary="Unchecked two."),
    ]
    content = _day_file("2026-11-01", entries)
    path = _write_daily(tmp_path, "d.md", content)

    result = prune_daily(tmp_path)

    assert result == PruneSummary(
        entries_pruned=2,
        files_touched=("d.md",),
        files_deleted=(),
        ids_recorded=("chk1@orbit.example.org", "chk2@orbit.example.org"),
    )

    after = path.read_text(encoding="utf-8")
    # Both checked blocks (and their drafts) are gone.
    assert "chk1@orbit.example.org" not in after
    assert "chk2@orbit.example.org" not in after
    assert "Confirmed on our side for the 24th." not in after
    # Both unchecked blocks survive, byte-identical and in original order.
    assert _entry(False, "unk1@example.test", summary="Unchecked one.") in after
    assert _entry(False, "unk2@example.test", summary="Unchecked two.") in after
    assert after.index("unk1@example.test") < after.index("unk2@example.test")
    # Day header intact.
    assert after.startswith("# Mail daily — 2026-11-01\n")
    # Exactly one blank line between the two surviving entries.
    unk1 = _entry(False, "unk1@example.test", summary="Unchecked one.")
    unk2 = _entry(False, "unk2@example.test", summary="Unchecked two.")
    assert f"{unk1}\n{unk2}" in after
    # File NOT deleted.
    assert path.exists()
    # .pruned.jsonl has exactly the 2 checked msg-ids, one per line.
    assert _pruned_lines(tmp_path) == ["chk1@orbit.example.org", "chk2@orbit.example.org"]


# --------------------------------------------------------------------------- #
# 2. All-checked file: file deleted, ids recorded                             #
# --------------------------------------------------------------------------- #
def test_all_checked_file_deleted(tmp_path):
    """A day-file whose only entries are all checked is deleted; ids are recorded."""
    entries = [
        _entry(True, "a1@orbit.example.org", summary="First."),
        _entry(True, "a2@orbit.example.org", summary="Second."),
    ]
    path = _write_daily(tmp_path, "gone.md", _day_file("2026-11-02", entries))

    result = prune_daily(tmp_path)

    assert not path.exists()
    assert result.files_deleted == ("gone.md",)
    assert result.files_touched == ()
    assert result.entries_pruned == 2
    assert result.ids_recorded == ("a1@orbit.example.org", "a2@orbit.example.org")
    assert _pruned_lines(tmp_path) == ["a1@orbit.example.org", "a2@orbit.example.org"]


# --------------------------------------------------------------------------- #
# 3. Old-format file (no checkboxes): byte-identical, 0 pruned                #
# --------------------------------------------------------------------------- #
def test_old_format_file_untouched(tmp_path):
    """A pre-rework file with no checkbox lines is left byte-identical."""
    old = (
        "# Mail daily — 2026-10-18\n"
        "\n"
        "## Run\n"
        "- batch size: 3\n"
        "\n"
        "### a1b2c3d4e5f6@orbit.example.org\n"
        "Subject: EUG schedule\n"
        "Class: action\n"
    )
    path = _write_daily(tmp_path, "old.md", old)

    result = prune_daily(tmp_path)

    assert path.read_text(encoding="utf-8") == old
    assert result == PruneSummary(0, (), (), ())
    # No .pruned.jsonl created (nothing pruned).
    assert not (tmp_path / "mail" / "daily" / ".pruned.jsonl").exists()


# --------------------------------------------------------------------------- #
# 4. Idempotent second pass                                                   #
# --------------------------------------------------------------------------- #
def test_second_pass_is_idempotent(tmp_path):
    """A second prune over the case-1 state removes nothing and adds no ids."""
    entries = [
        _entry(True, "chk1@orbit.example.org", summary="Checked one."),
        _entry(False, "unk1@example.test", summary="Unchecked one."),
        _entry(True, "chk2@orbit.example.org", summary="Checked two."),
        _entry(False, "unk2@example.test", summary="Unchecked two."),
    ]
    path = _write_daily(tmp_path, "d.md", _day_file("2026-11-01", entries))

    first = prune_daily(tmp_path)
    after_first = path.read_text(encoding="utf-8")
    lines_after_first = _pruned_lines(tmp_path)

    second = prune_daily(tmp_path)

    assert second == PruneSummary(0, (), (), ())
    # No file changes on the second pass.
    assert path.read_text(encoding="utf-8") == after_first
    # .pruned.jsonl line count unchanged (no duplicate lines).
    assert _pruned_lines(tmp_path) == lines_after_first
    # Sanity: the first pass did prune, so this is a meaningful idempotency check.
    assert first.entries_pruned == 2


# --------------------------------------------------------------------------- #
# 5. Dedup against pre-existing ids                                           #
# --------------------------------------------------------------------------- #
def test_dedup_against_preexisting_ids(tmp_path):
    """A checked entry whose id is already in .pruned.jsonl gains no duplicate line."""
    daily = tmp_path / "mail" / "daily"
    daily.mkdir(parents=True)
    (daily / ".pruned.jsonl").write_text("already@orbit.example.org\n", encoding="utf-8")

    entries = [
        _entry(True, "already@orbit.example.org", summary="Already recorded."),
        _entry(False, "keep@example.test", summary="Still unchecked."),
    ]
    path = _write_daily(tmp_path, "d.md", _day_file("2026-11-03", entries))

    result = prune_daily(tmp_path)

    # Entry still removed; file kept (one unchecked entry survives).
    after = path.read_text(encoding="utf-8")
    assert "already@orbit.example.org" not in after
    assert "keep@example.test" in after
    # .pruned.jsonl gains 0 lines — no duplicate of the pre-existing id.
    assert _pruned_lines(tmp_path) == ["already@orbit.example.org"]
    # ids_recorded is empty for that (deduped) id.
    assert result.ids_recorded == ()
    assert result.entries_pruned == 1
    assert result.files_touched == ("d.md",)


# --------------------------------------------------------------------------- #
# 6. Missing dir: empty summary, nothing created                              #
# --------------------------------------------------------------------------- #
def test_missing_daily_dir_returns_empty(tmp_path):
    """prune_daily on a vault with no mail/daily dir returns an empty summary."""
    result = prune_daily(tmp_path)

    assert result == PruneSummary(0, (), (), ())
    # No directories or files created.
    assert not (tmp_path / "mail").exists()


# --------------------------------------------------------------------------- #
# 7. Unchecked-only file: byte-identical, empty summary                       #
# --------------------------------------------------------------------------- #
def test_unchecked_only_file_untouched(tmp_path):
    """A file with only unchecked entries is left byte-identical and not rewritten."""
    entries = [
        _entry(False, "u1@example.test", summary="Unchecked one."),
        _entry(False, "u2@example.test", summary="Unchecked two."),
    ]
    content = _day_file("2026-11-04", entries)
    path = _write_daily(tmp_path, "u.md", content)

    result = prune_daily(tmp_path)

    assert path.read_text(encoding="utf-8") == content
    assert result == PruneSummary(0, (), (), ())
    # Not even rewritten: no temp file lingers and mtime is unchanged.
    before_mtime = os.stat(path).st_mtime_ns
    prune_daily(tmp_path)
    assert os.stat(path).st_mtime_ns == before_mtime


# --------------------------------------------------------------------------- #
# 8. Malformed entry (checked, no id line): removed, no id appended           #
# --------------------------------------------------------------------------- #
def test_malformed_checked_entry_no_id(tmp_path):
    """A checked entry with no id: line is still removed; no id is recorded."""
    entries = [
        _entry(True, None, summary="Checked but has no id line."),
        _entry(False, "keep@example.test", summary="Unchecked survivor."),
    ]
    path = _write_daily(tmp_path, "d.md", _day_file("2026-11-05", entries))

    result = prune_daily(tmp_path)

    after = path.read_text(encoding="utf-8")
    assert "Checked but has no id line." not in after
    assert "keep@example.test" in after
    # No id appended for the malformed entry.
    assert _pruned_lines(tmp_path) == []
    assert result.ids_recorded == ()
    # The block was still removed (counted as pruned).
    assert result.entries_pruned == 1
    assert result.files_touched == ("d.md",)
