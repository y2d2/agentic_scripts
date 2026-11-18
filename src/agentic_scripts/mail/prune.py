"""Runner-owned pruning of checked daily entries for the mail-keeper workflow.

Purpose:
    Provide a pure, deterministic, stdlib-only :func:`prune_daily` that removes
    checked (``- [x]``) entry blocks from the mail-keeper day-files under
    ``<vault_root>/mail/daily/``, records each pruned msg-id in
    ``<vault_root>/mail/daily/.pruned.jsonl`` (deduped, append-only), and deletes any
    day-file left with no surviving entries. It is the runner-side replacement for the
    agent-side "Checkbox Lifecycle" step: the runner calls it once per run, before
    manifest processing, so a checked-off mail never competes with the current batch.

Rationale:
    Day-files are git-ignored and local-only (the vault's ``.gitignore`` carries a bare
    ``mail`` line), so pruning them produces no git activity — the durable audit stays
    in the ``OC:`` commit messages + the processed log. Pruning is therefore safe to
    run on every invocation and must be *idempotent*: re-running over an already-pruned
    tree removes nothing, appends no duplicate ids, and leaves byte-identical files
    untouched (an unchecked-only file is never even rewritten). The function touches
    nothing outside ``<vault_root>/mail/daily/`` — never vault notes, never ``todos/``,
    never the notmuch index, never any git binary.

Atomicity:
    Each modified day-file is rewritten via a temp file in the same directory plus
    ``os.replace`` (an interrupted run must never corrupt a day-file). The append-only
    ``.pruned.jsonl`` is made crash-safe the same way: read existing content, append the
    new ids, and atomically replace — so a torn write can never lose previously-recorded
    ids.

Usage:
    >>> from pathlib import Path  # doctest: +SKIP
    >>> from agentic_scripts.mail.prune import prune_daily  # doctest: +SKIP
    >>> summary = prune_daily(Path("/workspace/Obsidian"))  # doctest: +SKIP
    >>> summary.entries_pruned  # doctest: +SKIP
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# A checkbox line: an optional indent, a dash, a space, and "[ ]" or "[x]". This is the
# *only* line shape that starts an entry block; old-format day-files (pre-rework) carry
# no such line and are therefore never touched.
_CHECKBOX_RE = re.compile(r"^\s*- \[( |x)\] ")


@dataclass(frozen=True)
class PruneSummary:
    """Outcome of one :func:`prune_daily` pass over a vault's day-files.

    All collection fields are tuples (not lists) so the summary is hashable and stays
    JSON-serialisable if ever logged. Basenames — not full paths — are recorded because
    the caller already knows the root; this keeps the summary portable.

    Attributes:
        entries_pruned: Number of checked entry blocks removed across all day-files.
        files_touched: Day-file basenames that were rewritten (checked entries removed,
            file kept because at least one entry survived).
        files_deleted: Day-file basenames deleted because they were left with zero
            surviving entries (day header / whitespace only).
        ids_recorded: msg-ids actually appended to ``.pruned.jsonl`` *this* pass, in the
            order their day-files were processed; ids already present in the file at pass
            start are excluded (dedup keeps re-runs idempotent — a second pass or a
            pre-existing id yields an empty / partial tuple).
    """

    entries_pruned: int
    files_touched: tuple[str, ...]
    files_deleted: tuple[str, ...]
    ids_recorded: tuple[str, ...]


def prune_daily(vault_root: Path) -> PruneSummary:
    """Prune checked (``- [x]``) entries from the vault's mail day-files.

    Purpose:
        The single entry point the mail-keeper runner calls before manifest processing.
        It scans ``<vault_root>/mail/daily/*.md`` in sorted order, removes every checked
        entry block, records each pruned msg-id in ``.pruned.jsonl`` (deduped), and
        deletes any day-file left empty. Unchecked entries are always preserved verbatim;
        old-format files (no checkbox lines) are never touched.

    Rationale:
        See the module docstring for why this is runner-owned, idempotent, and fenced to
        ``<vault_root>/mail/daily/``. Per-file errors (e.g. an unreadable file) are *not*
        caught here — they propagate to the caller, which decides best-effort handling
        (the runner, in Task 2). Only a missing / non-directory day-files folder is a
        benign no-op.

    Args:
        vault_root: The Obsidian vault root (the workflow's ``admin_repo``). Day-files
            live at ``<vault_root>/mail/daily/``.

    Returns:
        A :class:`PruneSummary` describing what was removed, rewritten, deleted, and
        recorded in this pass. An empty summary is returned when the day-files directory
        is missing or not a directory (nothing is created).

    Side Effects:
        Rewrites modified day-files atomically (same-dir temp + ``os.replace``), deletes
        emptied day-files, and appends new msg-ids to ``<vault_root>/mail/daily/
        .pruned.jsonl`` (created if absent, written atomically). Touches nothing outside
        that directory.

    Example:
        >>> summary = prune_daily(Path("/workspace/Obsidian"))  # doctest: +SKIP
        >>> isinstance(summary, PruneSummary)  # doctest: +SKIP
        True
    """
    daily_dir = Path(vault_root) / "mail" / "daily"
    if not daily_dir.is_dir():
        return PruneSummary(0, (), (), ())

    day_files = sorted(daily_dir.glob("*.md"), key=lambda p: p.name)

    # Read the existing pruned-ids once up front so dedup is decided against a single,
    # stable set for the whole pass (and so `ids_recorded` can report only the ids that
    # were actually appended this pass).
    pruned_path = daily_dir / ".pruned.jsonl"
    existing_ids: list[str] = []
    if pruned_path.exists():
        for raw in pruned_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line:
                existing_ids.append(line)
    present_ids = set(existing_ids)

    entries_pruned = 0
    files_touched: list[str] = []
    files_deleted: list[str] = []
    new_ids: list[str] = []

    for path in day_files:
        text = path.read_text(encoding="utf-8")
        # Old-format file (no checkbox line anywhere): leave byte-identical.
        if not _has_checkbox(text):
            continue

        pruned, kept_lines, removed_ids = _prune_entries(text)
        # `pruned` counts checked blocks removed (whether or not each had a usable id);
        # `removed_ids` is only the ids that were actually recorded.
        entries_pruned += pruned
        new_ids.extend(removed_ids)

        if pruned == 0:
            # No checked entries in this file → nothing to remove. Leave it byte-identical
            # (do not even rewrite it), so unchecked-only files are never touched and a
            # re-run over an already-pruned tree is a no-op.
            continue

        if not _any_entry_kept(kept_lines):
            # Day-file left with zero surviving entries → delete it.
            path.unlink()
            files_deleted.append(path.name)
        else:
            _atomic_write_text(path, "".join(kept_lines))
            files_touched.append(path.name)

    # Dedup against the ids present at pass start: only ids not already recorded are
    # appended, and `ids_recorded` reports exactly those (so a re-run or a pre-existing
    # id yields an empty / partial `ids_recorded`, keeping re-runs idempotent).
    additions = [mid for mid in new_ids if mid not in present_ids]
    if additions:
        _append_pruned_ids(pruned_path, existing_ids, additions)

    return PruneSummary(
        entries_pruned=entries_pruned,
        files_touched=tuple(files_touched),
        files_deleted=tuple(files_deleted),
        ids_recorded=tuple(additions),
    )


def _has_checkbox(text: str) -> bool:
    """Return True if ``text`` contains at least one checkbox line.

    Purpose:
        Distinguish new-format day-files (which carry ``- [ ]`` / ``- [x]`` entry lines)
        from old-format files (pre-rework ``## Run`` blocks / ``### <msg-id>`` headings,
        no checkboxes). Old-format files must be left byte-identical.

    Args:
        text: The full day-file content.

    Returns:
        True when at least one line matches :data:`_CHECKBOX_RE`.
    """
    return any(_CHECKBOX_RE.match(line) for line in text.splitlines())


def _prune_entries(text: str) -> tuple[int, list[str], list[str]]:
    """Split a day-file into entry blocks and drop the checked ones.

    Purpose:
        Line-based parse (not a whole-file regex): iterate lines tracking "inside an
        entry" state. A checkbox line starts a block; the next checkbox line or EOF ends
        the previous one. Each block is its checkbox line plus its indented continuation
        lines up to (not including) the next checkbox — blank separator lines belong to
        the *preceding* block for removal purposes but are re-normalised to exactly one
        blank line between surviving entries. The day header and any content before the
        first checkbox line is preserved untouched.

    Args:
        text: Full day-file content (guaranteed to contain at least one checkbox line by
            the caller).

    Returns:
        A 3-tuple ``(removed_count, kept_lines, removed_ids)`` where ``kept_lines`` are
        the surviving lines (header + unchecked entries, blank-line-normalised, each with
        its trailing newline), and ``removed_ids`` is the msg-id of each pruned checked
        entry in file order (empty string omitted for entries with no usable ``id:``).

    Side Effects:
        None — pure text transformation.
    """
    lines = text.splitlines(keepends=True)

    # Preamble: everything before the first checkbox line, preserved verbatim.
    preamble_end = 0
    while preamble_end < len(lines) and not _CHECKBOX_RE.match(lines[preamble_end]):
        preamble_end += 1

    # Group lines into (checkbox_line, block_lines) where block_lines includes the
    # checkbox line itself plus its continuation up to the next checkbox.
    blocks: list[list[str]] = []
    i = preamble_end
    while i < len(lines):
        # Every line from the first checkbox onward either starts a new block (checkbox)
        # or extends the current one (continuation), so the inner loop always consumes at
        # least the checkbox line itself and `i` strictly advances.
        block = [lines[i]]
        i += 1
        while i < len(lines) and not _CHECKBOX_RE.match(lines[i]):
            block.append(lines[i])
            i += 1
        blocks.append(block)

    kept_blocks: list[list[str]] = []
    removed_ids: list[str] = []
    removed_count = 0
    for block in blocks:
        checkbox = block[0]
        checked = bool(re.match(r"^\s*- \[x\] ", checkbox))
        if checked:
            removed_count += 1
            msg_id = _extract_msg_id(block)
            if msg_id:
                removed_ids.append(msg_id)
        else:
            kept_blocks.append(block)

    # Re-normalise: preamble, then each surviving block with exactly one blank line
    # between consecutive blocks (and between the preamble and the first block when both
    # are non-empty). Preserve each block's internal lines verbatim.
    out: list[str] = list(lines[:preamble_end])

    def _ensure_single_blank() -> None:
        """Collapse any run of blank lines at the end of ``out`` to exactly one."""
        while len(out) >= 2 and not out[-1].strip() and not out[-2].strip():
            out.pop()
        # If the last line is a single blank, keep it as the separator; otherwise ensure
        # there is exactly one blank between the previous block and the next.
        if out and not out[-1].strip():
            return  # already ends in a blank → separator present
        if out:
            out.append("\n")

    for block in kept_blocks:
        _ensure_single_blank()
        out.extend(block)

    return removed_count, out, removed_ids


def _any_entry_kept(kept_lines: list[str]) -> bool:
    """Return True if any surviving line is a (unchecked) checkbox entry.

    Purpose:
        Implement the delete rule: a day-file left with zero entries after removal — only
        the day header / whitespace — must be deleted. An unchecked ``- [ ]`` line means
        an entry survived, so the file is kept.

    Args:
        kept_lines: The surviving lines produced by :func:`_prune_entries`.

    Returns:
        True when at least one line matches the checkbox pattern (i.e. an entry remains).
    """
    return any(_CHECKBOX_RE.match(line) for line in kept_lines)


def _extract_msg_id(block: list[str]) -> str:
    """Best-effort extraction of a checked entry's msg-id from its ``id:`` line.

    Purpose:
        Per the day-file format, ``id:`` is the last line of an entry and carries the full
        RFC 5322 Message-ID without angle brackets. This is defensive: a missing or
        malformed ``id:`` yields an empty string (no id recorded) rather than raising —
        matching the "never crash on user data" property of the sibling canary/reader
        modules. Surrounding ``<>`` are stripped if present.

    Args:
        block: The entry's lines, including its checkbox line and continuation lines.

    Returns:
        The msg-id string (angle brackets stripped), or "" when no usable ``id:`` line is
        found.
    """
    for line in reversed(block):
        stripped = line.strip()
        if stripped.startswith("id:"):
            value = stripped[len("id:") :].strip().strip("<>").strip()
            return value
    return ""


def _append_pruned_ids(path: Path, existing: list[str], additions: list[str]) -> None:
    """Atomically rewrite ``.pruned.jsonl`` with the existing ids plus new additions.

    Purpose:
        Record pruned msg-ids (one per line, no angle brackets) so the runner's later
        dedup step can skip already-pruned mail. Dedup is decided by the caller against a
        single stable set read at pass start; this function simply merges the existing
        lines with the new additions and writes them atomically (same-dir temp +
        ``os.replace``), so a torn write can never lose previously-recorded ids.

    Args:
        path: The ``<vault_root>/mail/daily/.pruned.jsonl`` file.
        existing: Lines already in the file at pass start (in original order).
        additions: New msg-ids to append (already deduped by the caller).

    Side Effects:
        Creates or rewrites ``path`` atomically. No other writes.
    """
    merged = list(existing) + list(additions)
    payload = "".join(f"{line}\n" for line in merged)
    _atomic_write_text(path, payload)


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomically write ``content`` to ``path`` via a same-directory temp file.

    Purpose:
        Guarantee an interrupted run never leaves a torn day-file or pruned-ids record:
        the temp file is written fully, then ``os.replace`` swaps it into place (atomic on
        POSIX), so the target is always either the old complete content or the new
        complete content.

    Args:
        path: The destination file.
        content: The full text to write.

    Side Effects:
        Creates a sibling temp file, then replaces ``path`` with it.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        # Best-effort cleanup of a partial temp file; the original target is intact.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
