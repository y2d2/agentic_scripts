"""Index-freshness canary for the mail-keeper workflow.

Purpose:
    Provide a pure, deterministic comparison between the on-disk maildir message counts
    and the notmuch index counts, so the mail-keeper workflow can detect (and report) a
    stale index before it triages new mail. The three public functions are:
    :func:`disk_message_counts` (walk the maildir with Python ``os.walk``),
    :func:`index_folder_counts` (count via the reader), and :func:`run_canaries`
    (combine them into a staleness verdict + a live spot-check).

Rationale:
    The index is refreshed by an external mbsync writer; this module only *verifies*
    freshness, never re-indexes. Staleness is defined as the disk count exceeding the
    index count beyond :data:`STALE_TOLERANCE` (new mail not yet indexed), the index
    ever being ahead of disk for any folder (a broken state), or the ``Sent Items``
    folder delta being non-zero (acceptance: Sent Items must equal disk exactly). The
    spot-check proves the index is *readable* end-to-end by resolving one real message
    via ``show`` + ``body_text``. All filesystem traversal uses Python ``os.walk`` —
    GNU ``find`` does not descend into this maildir (reproduced failure), so it must
    never be used here.

Cost note:
    The disk walk over the ~4.5 GB production tree takes ~1–3 s; that is acceptable for
    a per-run freshness check and is documented here so callers do not mistake it for a
    bug. Hermetic tests run against tiny throwaway trees where the walk is instant.

Usage:
    >>> from agentic_scripts.mail import canary  # doctest: +SKIP
    >>> result = canary.run_canaries(reader, mail_root, "yuri.durodie@vub.be")  # doctest: +SKIP
    >>> result["stale"]  # doctest: +SKIP
"""

from __future__ import annotations

import os
from pathlib import Path

from agentic_scripts.mail.reader import NotmuchReader, q_folder

# Tolerance (in messages) for disk-ahead-of-index staleness. Observed live delta on
# 2026-10-19 was 36; 100 gives headroom while still catching a genuinely stale index.
STALE_TOLERANCE = 100


def disk_message_counts(mail_root: Path, account: str) -> dict[str, int]:
    """Count on-disk maildir messages per folder using Python ``os.walk``.

    Purpose:
        Walk ``mail_root/<account>`` and count regular message files directly inside the
        ``new/`` and ``cur/`` state directories of every message folder (a directory that
        contains a ``new/`` or ``cur/`` child). The ``tmp/`` state dir and anything deeper
        are skipped. This is the disk-side half of the freshness comparison.

    Rationale:
        Maildir layout means messages live in ``<folder>/new/`` and ``<folder>/cur/``;
        counting regular files there (and nowhere else) matches what ``notmuch new``
        indexes. Python ``os.walk`` is mandatory — GNU ``find`` does not descend into
        this maildir (reproduced failure), so it must never be used here.

    Args:
        mail_root: The maildir root (the parent of the account directory).
        account: The single top-level account directory name.

    Returns:
        A dict ``{"total": N, "<folder>": n, ...}`` where folder keys are relative to the
        account (e.g. ``"INBOX"``, ``"INBOX/ORBIT"``, ``"Sent Items"``) and ``total`` is
        the sum across all folders.

    Side Effects:
        Read-only filesystem traversal of ``mail_root/<account>``.

    Example:
        >>> counts = disk_message_counts(Path("mail"), "acct")  # doctest: +SKIP
        >>> counts["total"] >= sum(v for k, v in counts.items() if k != "total")  # doctest: +SKIP
    """
    account_root = Path(mail_root) / account
    per_folder: dict[str, int] = {}
    if not account_root.is_dir():
        return {"total": 0}

    for dirpath, _dirnames, filenames in os.walk(account_root):
        current = Path(dirpath)
        # A message folder is one whose parent (relative to the account) has a new/ or
        # cur/ child; here we count files inside any directory named 'new' or 'cur'.
        if current.name not in ("new", "cur"):
            continue
        # The folder is the parent of this state dir, relative to the account root.
        folder_rel = current.parent.relative_to(account_root)
        folder_key = str(folder_rel) if str(folder_rel) != "." else ""
        count = 0
        for name in filenames:
            if (current / name).is_file():
                count += 1
        per_folder[folder_key] = per_folder.get(folder_key, 0) + count

    total = sum(per_folder.values())
    result = {"total": total}
    result.update(per_folder)
    return result


def index_folder_counts(reader: NotmuchReader, account: str, folders: list[str]) -> dict[str, int]:
    """Count indexed messages per folder via the reader.

    Purpose:
        The index-side half of the freshness comparison: run ``reader.count`` for each
        requested folder (via :func:`q_folder`) plus a bare total count. Mirrors the key
        shape of :func:`disk_message_counts` so the two can be diffed folder-by-folder.

    Args:
        reader: A configured :class:`NotmuchReader`.
        account: The account directory name (used to build ``folder:`` queries).
        folders: Folder paths (relative to the account) to count, e.g.
            ``["INBOX", "Sent Items"]``.

    Returns:
        A dict ``{"total": N, "<folder>": n, ...}`` with one key per folder plus ``total``
        (the reader's bare all-messages count).

    Side Effects:
        Spawns a notmuch subprocess per folder (read-only counts).

    Example:
        >>> counts = index_folder_counts(reader, "acct", ["INBOX"])  # doctest: +SKIP
    """
    result: dict[str, int] = {}
    for folder in folders:
        result[folder] = reader.count(q_folder(account, folder))
    result["total"] = reader.count("")
    return result


def run_canaries(
    reader: NotmuchReader,
    mail_root: Path,
    account: str,
    *,
    tolerance: int = STALE_TOLERANCE,
    folders: list[str] | None = None,
) -> dict:
    """Run the disk-vs-index freshness canaries and return a verdict.

    Purpose:
        Compare on-disk message counts against index counts, compute per-folder deltas,
        decide whether the index is stale, and perform a live spot-check that one real
        ``Sent Items`` message resolves via ``show`` + ``body_text``. This is the single
        entry point the mail-keeper workflow calls before triaging new mail.

    Rationale:
        Staleness means "the index may be missing recent mail" (disk ahead of index
        beyond tolerance), "the index is broken" (index ahead of disk for any folder), or
        "Sent Items drifted" (its delta must be exactly zero per the acceptance rule).
        Reasons are human-readable strings so a stale verdict can be reported verbatim.
        The spot-check guards against an index that *counts* correctly but cannot resolve
        a message end-to-end.

    Args:
        reader: A configured :class:`NotmuchReader` over the target index.
        mail_root: The maildir root (parent of the account directory).
        account: The single top-level account directory name.
        tolerance: Max allowed disk-ahead-of-index total delta before "stale" (default
            :data:`STALE_TOLERANCE`).
        folders: Folder paths to compare; defaults to the folder keys discovered by
            :func:`disk_message_counts` (minus ``total``).

    Returns:
        A dict with keys ``total_disk``, ``total_index``, ``per_folder`` (mapping each
        folder to ``{"disk", "index", "delta"}``), ``stale`` (bool), ``reasons`` (list of
        human-readable strings, empty when fresh), and ``spot_check`` (``{"ok": bool,
        "message_id": str | None, "note": str}``).

    Side Effects:
        Read-only filesystem walk + read-only notmuch counts/show. No writes.

    Example:
        >>> result = run_canaries(reader, Path("mail"), "acct")  # doctest: +SKIP
        >>> isinstance(result["stale"], bool)  # doctest: +SKIP
        True
    """
    disk = disk_message_counts(mail_root, account)
    if folders is None:
        folders = [key for key in disk if key != "total"]

    index = index_folder_counts(reader, account, folders)

    per_folder: dict[str, dict] = {}
    reasons: list[str] = []
    for folder in folders:
        disk_count = disk.get(folder, 0)
        index_count = index.get(folder, 0)
        delta = disk_count - index_count
        per_folder[folder] = {"disk": disk_count, "index": index_count, "delta": delta}

    total_disk = disk.get("total", 0)
    total_index = index.get("total", 0)

    # Staleness rule 1: disk ahead of the index beyond tolerance (new mail not indexed).
    if total_disk - total_index > tolerance:
        reasons.append(
            f"index is stale: disk has {total_disk} messages, index has {total_index} "
            f"(delta {total_disk - total_index} > tolerance {tolerance})"
        )

    # Staleness rule 2: any folder where the index is ahead of disk (broken state).
    for folder, entry in per_folder.items():
        if entry["delta"] < 0:
            reasons.append(
                f"folder '{folder}' has index ({entry['index']}) ahead of "
                f"disk ({entry['disk']}) — broken index"
            )

    # Staleness rule 3: Sent Items must equal disk exactly (acceptance rule).
    if "Sent Items" in per_folder and per_folder["Sent Items"]["delta"] != 0:
        reasons.append(
            f"'Sent Items' delta is {per_folder['Sent Items']['delta']} "
            f"(must be 0: index {per_folder['Sent Items']['index']} vs "
            f"disk {per_folder['Sent Items']['disk']})"
        )

    spot_check = _spot_check_sent_items(reader, account)

    return {
        "total_disk": total_disk,
        "total_index": total_index,
        "per_folder": per_folder,
        "stale": bool(reasons),
        "reasons": reasons,
        "spot_check": spot_check,
    }


def _spot_check_sent_items(reader: NotmuchReader, account: str) -> dict:
    """Resolve one real Sent Items message end-to-end as a liveness spot-check.

    Purpose:
        Prove the index is not merely count-correct but actually resolvable: search the
        newest ``Sent Items`` message, then confirm ``show`` + ``body_text`` succeed and
        return a body or a raw-file pointer. This catches an index that counts right but
        cannot resolve a message.

    Args:
        reader: A configured :class:`NotmuchReader`.
        account: The account directory name.

    Returns:
        A dict ``{"ok": bool, "message_id": str | None, "note": str}`` where ``ok`` is
        True when a message was found and resolved without exception.

    Side Effects:
        Read-only notmuch search/show/body_text. No writes.
    """
    try:
        rows = reader.search(q_folder(account, "Sent Items"), limit=1)
    except Exception as exc:  # noqa: BLE001 - report any failure as a failed spot-check
        return {"ok": False, "message_id": None, "note": f"search failed: {exc}"}
    if not rows or not rows[0].get("message_ids"):
        return {
            "ok": False,
            "message_id": None,
            "note": "no Sent Items message found to spot-check",
        }

    msg_id = rows[0]["message_ids"][0]
    try:
        reader.show(msg_id)
        text, raw_path = reader.body_text(msg_id)
    except Exception as exc:  # noqa: BLE001 - report any failure as a failed spot-check
        return {"ok": False, "message_id": msg_id, "note": f"show/body_text failed: {exc}"}

    if text is not None or raw_path is not None:
        return {
            "ok": True,
            "message_id": msg_id,
            "note": "resolved Sent Items message with body/raw path",
        }
    return {"ok": False, "message_id": msg_id, "note": "no body or raw path returned"}
