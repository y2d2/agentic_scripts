"""The ``mail-keeper`` workflow: index-freshness canary, newest-first backfill-aware
new-mail detection (two-boundary cursors + a fixed 1-year floor), a ≤10-message manifest,
one batched agent invocation, the runner-owned processed log, and mail-backup
byte-identity verification.

Purpose:
    Provide :func:`create` (the scheduler's entry point) returning a
    :class:`MailKeeper` that, on each gate-open (or ``--force``) run, verifies the
    notmuch index against the maildir (canary; report-and-defer on staleness), detects
    candidates per triage folder using a **two-boundary cursor** — ``new`` = newest-seen
    forward boundary, ``back`` = oldest-processed backward frontier — plus a fixed
    **1-year backfill floor** captured at first run (mail older than the floor is never
    triaged). Each run's manifest fills **newest-first**: new mail first, then deferred
    overflow, then history newest-first, capped at :data:`MAX_BATCH`. The workflow builds
    the ≤:data:`MAX_BATCH` manifest (PII folder + own mail excluded *before* the agent),
    invokes the ``mail-keeper`` agent exactly once with that manifest, and — only on an
    ``ok`` agent result — advances the cursors (manifest min/max), appends the v1-schema
    processed log, and verifies the mail backup tree is byte-identical before and after.

Rationale:
    The runner owns everything around the agent: freshness, state (two-boundary cursors +
    floor + deferred), manifest building, the single agent call, the processed log, and
    the guardrail check. The agent owns only triage + vault writes + its own commit/push
    (see the global ``skills/mail-keeper`` skill). This split is what makes re-runs
    idempotent: an agent failure advances nothing, so the same batch is re-presented next
    run and the agent's dedup rule (grep msg-id before every write) makes re-delivery
    safe. The workflow NEVER writes vault files, NEVER sends mail, and NEVER runs
    ``notmuch new``.

    Backfill model (user decision 2026-10-23): history is processed **newest-first**
    (notmuch's natural row order — no reversal) in capped batches until every folder's
    ``back`` frontier reaches the floor; a folder whose backfill is complete skips the
    history walk entirely (steady state = new-mail-only runs). Newly arriving mail is
    never starved because each run fills its batch with new mail first.

Environment (read at run time; env wins over the defaults below):
    MAIL_INDEX_DB       notmuch index dir   (default /workspace/docker/mbsync/notmuch)
    MAIL_MAIL_ROOT      maildir root        (default /workspace/docker/mbsync/backup)
    MAIL_OWNER_ADDRESS  owner address       (default yuri.durodie@vub.be)
    MAIL_PROCESSED_LOG  processed-log path  (default /workspace/Obsidian/config/
                        email-processing-log.jsonl)

Cost note:
    One ``notmuch show`` ≈ 0.5–0.6 s on the live 13k index, so the detection walk is
    budgeted to ≤ ~20 shows per run (~12 s worst case); a full-folder ``search`` ≈ 1 s.
    The canary disk walk over the ~4.5 GB tree takes ~1–3 s. All filesystem traversal
    uses Python ``os.walk`` — GNU ``find`` does not descend into this maildir and must
    never be used here.

Usage:
    >>> from agentic_scripts.workflows.mail_keeper import create  # doctest: +SKIP
    >>> wf = create(config)  # config is a loaded Config  # doctest: +SKIP
    >>> wf.name
    'mail-keeper'
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_scripts.config import Config
from agentic_scripts.mail import canary

# Private import (documented): Task 1 shipped the thread-root-quirk workaround in
# mail_search.py. ``_find_message_by_id`` recovers the *requested* message object from a
# show document — notmuch 0.38.3's ``show --format=json 'id:<msgid>'`` returns the
# THREAD ROOT as ``primary``, not the requested message, so per-message fields must be
# read from the recovered object, never from ``doc["primary"]``. We import it rather than
# duplicate the ~15-line helper (single source of truth for the quirk workaround).
from agentic_scripts.mail.mail_search import _find_message_by_id
from agentic_scripts.mail.reader import NotmuchError, NotmuchReader, q_folder
from agentic_scripts.workflows.base import WorkflowResult

# --- Constants (module-level; see module docstring for the env surface) -------- #

#: Per-run manifest cap — the user-confirmed history-backfill throughput knob. Cap-
#: truncated messages live in ``state.deferred`` and are re-injected next run (no loss).
MAX_BATCH = 10

#: The fixed backfill floor window: a folder's history is triaged only down to
#: ``first-run-now − BACKFILL_WINDOW_SECONDS``; mail older than the floor is never triaged.
BACKFILL_WINDOW_SECONDS = 365 * 86400

#: The PII folder, excluded from detection/manifest/drafts/commits by default. Any
#: folder under this prefix is also excluded (defense in depth on top of the loop).
PII_FOLDER = "INBOX/FU-Admin/PhD_applications"

#: Folders never triaged: the PII folder and the owner's own corpus (style sampling only).
EXCLUDED_FOLDERS = {"Sent Items", PII_FOLDER}

#: The triage-eligible label set. A folder is eligible iff it is not in EXCLUDED_FOLDERS
#: and not under the PII prefix; :data:`TRIAGE_FOLDERS` is that set materialised.
TRIAGE_FOLDERS: list[str] = [
    "INBOX",
    "INBOX/Admin",
    "INBOX/Admin/Data_storage",
    "INBOX/FU-Admin",
    "INBOX/FU-Admin/Nerdland",
    "INBOX/FU-Admin/VICON_ICT",
    "INBOX/ORBIT",
    "INBOX/Spin-off",
    "INBOX/Students",
]

#: Defaults for the env-overridable paths (env wins; see module docstring).
_DEFAULT_INDEX_DB = "/workspace/docker/mbsync/notmuch"
_DEFAULT_MAIL_ROOT = "/workspace/docker/mbsync/backup"
_DEFAULT_OWNER = "yuri.durodie@vub.be"
_DEFAULT_PROCESSED_LOG = "/workspace/Obsidian/config/email-processing-log.jsonl"

#: The state-document key under ``state/mail-keeper.json``.
_STATE_KEY = "mail-keeper"

#: A manifest entry's shape (see :func:`_detect`): message_id, folder, timestamp, from,
#: from_addresses, subject. ``deferred`` reuses this shape so it round-trips through JSON.
_MANIFEST_FIELDS = ("message_id", "folder", "timestamp", "from", "from_addresses", "subject")

#: Best-effort parse of a Triage-table row: ``| <id> | <folder> | <from> | <class> | ...``.
#: The class is the 4th column, so exactly two cells (folder + from) sit between the id and
#: the class. Each cell is anchored with ``\s*...\s*`` because a bare ``[^|]*`` is greedy
#: and would otherwise back-track to swallow the class token into a preceding cell.
_TRIAGE_ROW_RE = re.compile(
    r"^\|\s*(?P<id>\S+?)\s*\|\s*[^|]*?\s*\|\s*[^|]*?\s*\|\s*(?P<class>noise|info|action|urgent)\s*\|"
)


def create(config: Config) -> "MailKeeper":  # noqa: UP037 - forward ref; class defined below
    """Create and return a :class:`MailKeeper` instance (the scheduler's entry point).

    Args:
        config: The fully validated :class:`~agentic_scripts.config.Config`. Accepted for
            contract uniformity; the workflow reads its own paths from the environment at
            run time, so ``config`` is not used to build state.

    Returns:
        A new :class:`MailKeeper`, ready to be run by the scheduler.

    Example:
        >>> wf = create(config)  # doctest: +SKIP
        >>> wf.name
        'mail-keeper'
    """
    return MailKeeper()


def _env_str(name: str, default: str) -> str:
    """Return the env var ``name`` (stripped) or ``default`` when unset/blank.

    Purpose:
        Centralise the "env wins over default" resolution for the workflow's four paths.

    Args:
        name: The environment variable name.
        default: The value used when the variable is absent or blank.

    Returns:
        The resolved, stripped string value.
    """
    return os.environ.get(name, "").strip() or default


def _folder_under_pii(folder: str) -> bool:
    """Return True if ``folder`` is the PII folder or lives under it.

    Purpose:
        Defense-in-depth exclusion: a message whose derived folder is under the PII
        prefix is dropped even though the per-folder detection loop already skips it.

    Args:
        folder: A folder path relative to the account (e.g. ``INBOX/ORBIT``).

    Returns:
        True when ``folder`` equals or is nested under :data:`PII_FOLDER`.
    """
    return folder == PII_FOLDER or folder.startswith(PII_FOLDER + "/")


def _parse_from_addresses(from_header: str) -> list[str]:
    """Parse the address(es) out of an RFC 5322 ``From`` header, dropping display names.

    Purpose:
        The processed log stores addresses only (v1 stored ``.get('email')`` values). A
        header like ``Name <addr>`` or a bare ``addr`` yields ``[addr]``; a comma-joined
        list of such terms yields one address per term.

    Args:
        from_header: The raw ``From`` header string (possibly empty).

    Returns:
        A list of address strings (display names stripped), in header order. Empty input
        yields an empty list.
    """
    if not from_header:
        return []
    addresses: list[str] = []
    for term in from_header.split(","):
        term = term.strip()
        if not term:
            continue
        if "<" in term and ">" in term:
            inner = term[term.index("<") + 1 : term.rindex(">")]
            addr = inner.strip()
        else:
            # Bare address (or a display name with no angle brackets — best effort).
            addr = term.split()[-1] if term.split() else ""
        if addr:
            addresses.append(addr)
    return addresses


def _local_date(epoch: int) -> str:
    """Format an integer epoch as a local calendar ``YYYY-MM-DD`` date.

    Purpose:
        Manifest/brief lines carry the message's local calendar date (the spec mandates
        LOCAL dates of the int-epoch timestamp), so this converts through the process-local
        timezone for consistency with what an operator sees on this single-user machine.

    Args:
        epoch: The integer Unix timestamp from a message object.

    Returns:
        A ``YYYY-MM-DD`` string in local time.
    """
    return datetime.fromtimestamp(epoch, tz=UTC).astimezone().strftime("%Y-%m-%d")


def _folder_from_filename(filename: str, mail_root: Path, account: str) -> str:
    """Derive a folder path (relative to the account) from a message's filename.

    Purpose:
        Map ``show``'s ``filename[0]`` (an absolute maildir path like
        ``<root>/<account>/INBOX/ORBIT/cur/<file>``) to a folder path relative to the
        account (e.g. ``INBOX/ORBIT``): strip everything up to and including
        ``<mail_root>/<account>/``, then drop the trailing maildir state segment
        (``cur``/``new``).

    Args:
        filename: The absolute message file path from a message object.
        mail_root: The resolved maildir root.
        account: The account directory name.

    Returns:
        The folder path relative to the account, or ``""`` when it cannot be derived.
    """
    prefix = f"{mail_root}/{account}/"
    rel = filename[len(prefix) :] if filename.startswith(prefix) else filename
    parts = [p for p in rel.split("/") if p]
    # The maildir layout is <folder>/.../<state>/<file>; the last two segments are the
    # state dir (cur/new) and the file name. Drop both to leave the folder path.
    if len(parts) >= 2 and parts[-2] in ("cur", "new"):
        parts = parts[:-2]
    return "/".join(parts)


def _backup_snapshot(mail_root: Path) -> dict[str, tuple[int, int]]:
    """Snapshot every regular file under ``mail_root`` as ``{relpath: (size, mtime_ns)}``.

    Purpose:
        The guardrail's before/after comparison: a byte-identical snapshot taken right
        before and after the agent call proves the mail backup tree was untouched. A trip
        means the agent (permission-denied from the backup) somehow mutated it — a config
        or denial gap that must surface as an error.

    Rationale:
        Python ``os.walk`` is mandatory — GNU ``find`` does not descend into this maildir
        (reproduced failure), so it must never be used here. The walk is pure read-only;
        on the ~4.5 GB production tree it takes ~1–3 s, which is acceptable for a per-run
        guardrail check.

    Args:
        mail_root: The maildir root to snapshot (the parent of the account directory).

    Returns:
        A dict mapping each regular file's path relative to ``mail_root`` to its
        ``(size, mtime_ns)`` pair (~13k entries on the live tree).
    """
    snapshot: dict[str, tuple[int, int]] = {}
    root = Path(mail_root)
    if not root.is_dir():
        return snapshot
    for dirpath, _dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for name in filenames:
            full = base / name
            try:
                if not full.is_file():
                    continue
                stat = full.stat()
            except OSError:
                continue  # a file that vanished mid-walk is not a guardrail concern
            rel = str(full.relative_to(root))
            snapshot[rel] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def _render_brief(run_id: str, manifest: list[dict], owner: str) -> str:
    """Render the agent brief in the exact stable format the skill parses by eye.

    Purpose:
        Produce the single batched invocation's message: a header naming the run and the
        batch size, the skill pointer + final-report mandate, and the ``MANIFEST`` block
        with one numbered line per entry in merge order (new mail first, then deferred,
        then history newest-first). The format is load-bearing — the agent reads it by
        eye — so it must stay byte-stable.

    Args:
        run_id: The unique run identifier for this invocation.
        manifest: The list of manifest entries in merge order (new mail first).
        owner: The owner address (carried in the brief header for context).

    Returns:
        The brief string, exactly in the documented format.
    """
    n = len(manifest)
    lines = [
        f"mail-keeper run {run_id} — triage the new-mail manifest below "
        f"(batch of {n}, newest-first).",
        "Follow skill: mail-keeper (run, triage, vault fills, drafts, commit policy). "
        "Your final message must be the result report with the Triage table "
        "(| msg-id | folder | from | class | action taken |).",
        "",
        f"MANIFEST ({n} message(s)):",
    ]
    for i, entry in enumerate(manifest, start=1):
        lines.append(
            f"{i}. {entry['message_id']} | {entry['folder']} | {_local_date(entry['timestamp'])}"
            f" | {entry['from']} | {entry['subject']}"
        )
    return "\n".join(lines)


def _parse_triage_classes(final_text: str | None) -> dict[str, str] | None:
    """Best-effort parse of a Triage table from the agent's final text.

    Purpose:
        Map each manifest message-id to its triage class (``noise``/``info``/``action``/
        ``urgent``) as reported by the agent, so the processed log can record the class.
        This is best-effort: a row that does not match the table shape is skipped, and an
        absent table yields None (the caller then treats every entry as ``mail-keeper``).

    Args:
        final_text: The agent's final message (its result report), or None.

    Returns:
        A ``{msg-id: class}`` dict when at least one row matched, else None.
    """
    if not final_text:
        return None
    classes: dict[str, str] = {}
    for line in final_text.splitlines():
        m = _TRIAGE_ROW_RE.match(line.strip())
        if m:
            classes[m.group("id")] = m.group("class")
    return classes or None


def _is_step_exhausted(final_text: str | None) -> bool:
    """Return True when the agent's final message is opencode's step-cap boilerplate.

    Purpose:
        Detect that the agent hit its frontmatter ``steps`` cap mid-triage. When this happens,
        opencode still **exits 0** and uses the step-exhaustion boilerplate as the "final
        message" — so the CLI cannot distinguish a step-exhausted run from a real success by
        exit code alone. Without this sentinel the workflow would record the run ``ok`` (append
        to the processed log + advance cursors) for triage that never completed (the Run-A
        incident, 2026-10-25). The caller treats a step-exhausted "ok" as a failure: no log
        append, no cursor advance, and the batch is re-presented next run.

    Args:
        final_text: The agent's final message (its result report), or None.

    Returns:
        True when ``final_text`` contains (case-insensitive) one of the two stable fragments of
        opencode's step-cap boilerplate — ``maximum steps reached`` or ``maximum number of steps
        allowed``; False for None/empty or a normal report.
    """
    if not final_text:
        return False
    lowered = final_text.lower()
    return "maximum steps reached" in lowered or "maximum number of steps allowed" in lowered


def _load_processed_log_ids(log_path: Path) -> set[str]:
    """Read the processed log once and return the set of already-processed message-ids.

    Purpose:
        Detection de-duplicates candidates against messages already recorded in the
        processed log, so a re-run never re-presents mail that was already triaged. The
        file is read at run start (tolerant of its absence — first runs have none).

    Args:
        log_path: The processed-log path (``MAIL_PROCESSED_LOG``).

    Returns:
        A set of message-id strings (the ``email_file`` field of each record). Empty when
        the file is missing or a line is malformed.
    """
    ids: set[str] = set()
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                email_file = record.get("email_file")
                if isinstance(email_file, str):
                    ids.add(email_file)
    except OSError:
        return set()  # missing/unreadable log → nothing processed yet
    return ids


def _append_processed_log(
    log_path: Path, entries: list[dict], classes: dict[str, str] | None
) -> int:
    """Append one v1-schema record per manifest entry to the processed log.

    Purpose:
        The runner-owned audit trail: after an ``ok`` agent run, every manifest message is
        recorded with its triage class (or ``mail-keeper`` when unparseable). One compact
        JSON line per entry, appended in ``a`` mode; the parent dir is created on demand.

    Args:
        log_path: The processed-log path (created if absent, along with its parent dir).
        entries: The manifest entries to record (each carrying message_id/subject/from_addresses).
        classes: A ``{msg-id: class}`` map from :func:`_parse_triage_classes`, or None.

    Returns:
        The number of records appended (``len(entries)``).

    Side Effects:
        Creates the log's parent directory and appends ``len(entries)`` JSON lines to the
        file (UTF-8, compact separators, one per line).
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    with log_path.open("a", encoding="utf-8") as fh:
        for entry in entries:
            msg_id = entry["message_id"]
            target_section = (classes or {}).get(msg_id, "mail-keeper")
            record = {
                "timestamp": now,
                "email_file": msg_id,
                "subject": entry.get("subject", ""),
                "from": entry.get("from_addresses", []),
                "target_section": target_section,
                "processed_to": "",
            }
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    return len(entries)


def _read_state(ctx: Any) -> dict:
    """Load the workflow's state document (empty when absent).

    Purpose:
        Centralise the load so a corrupt state file surfaces as a business error rather
        than an uncaught exception (the run wrapper maps it to ``status="error"``).

    Args:
        ctx: The shared :class:`~agentic_scripts.workflows.base.WorkContext`.

    Returns:
        The parsed state dict (``{}`` when no state file exists yet).
    """
    return ctx.state.load(_STATE_KEY)


def _save_state(ctx: Any, data: dict) -> None:
    """Atomically persist the workflow's state document (single write per run).

    Purpose:
        Prefer one :meth:`StateStore.save` per run over per-key ``update`` calls so the
        whole document is written atomically in a single pass.

    Args:
        ctx: The shared :class:`~agentic_scripts.workflows.base.WorkContext`.
        data: The full state document to persist (cursors, deferred, bootstrapped_at).
    """
    ctx.state.save(_STATE_KEY, data)


def _fresh_state(now: int, floor: int) -> dict:
    """Build the fresh-state document for a first run (state v2 schema).

    Purpose:
        On the very first run there is no recorded progress. The two-boundary model starts
        every triage folder at ``new = {last_date: 0, ...}`` (so run 1's ``new_set`` is
        everything) and ``back = {last_date: floor, ...}`` (so the backward frontier begins
        exactly at the floor and only moves down to processed-min). The fixed
        ``backfill_floor`` is captured once here and never recomputed.

    Args:
        now: The current integer epoch (used for ``bootstrapped_at``).
        floor: The backfill floor in epoch seconds (``now − BACKFILL_WINDOW_SECONDS``).

    Returns:
        A fresh state dict with keys ``bootstrapped_at``, ``backfill_floor``, ``cursors``
        (one two-boundary entry per triage folder), and an empty ``deferred`` list.
    """
    cursors: dict[str, dict] = {}
    for folder in TRIAGE_FOLDERS:
        if _folder_under_pii(folder) or folder in EXCLUDED_FOLDERS:
            continue  # PII + own corpus are never searched (defense in depth)
        cursors[folder] = {
            "new": {"last_date": 0, "last_message_id": ""},
            "back": {"last_date": floor, "last_message_id": ""},
        }
    return {
        "bootstrapped_at": datetime.fromtimestamp(now, tz=UTC).isoformat(),
        "backfill_floor": floor,
        "cursors": cursors,
        "deferred": [],
    }


def _validate_state(st: dict) -> str | None:
    """Validate a loaded state document against the v2 schema.

    Purpose:
        The repo has no v1 state to migrate (verified 2026-10-23), so a mismatched shape is
        an operator error, not something to auto-migrate. A v1-shaped entry (a folder cursor
        that is a flat ``{last_date, ...}`` dict rather than the two-boundary
        ``{new, back}`` mapping) or a missing ``backfill_floor`` must surface as a clear,
        actionable error telling the operator to delete the state file.

    Args:
        st: The parsed state document (possibly empty on a first run).

    Returns:
        An error message string when the shape is invalid, else None. The message contains
        ``"state schema mismatch"`` and the instruction ``"delete state/mail-keeper.json"``.
    """
    if not st:
        return None  # no state yet → first run (the caller initialises it)
    if "backfill_floor" not in st:
        return (
            "state schema mismatch: 'backfill_floor' is missing — delete "
            "state/mail-keeper.json and let the workflow re-bootstrap."
        )
    cursors = st.get("cursors", {}) or {}
    for folder, entry in cursors.items():
        if not (isinstance(entry, dict) and "new" in entry and "back" in entry):
            return (
                f"state schema mismatch: folder {folder!r} has a v1-shaped cursor "
                "(missing the two-boundary 'new'/'back' keys) — delete "
                "state/mail-keeper.json and let the workflow re-bootstrap."
            )
    return None


def _cursor_for(cursors: dict, folder: str, floor: int) -> tuple[dict, dict]:
    """Return a folder's two-boundary cursors, defaulting to the fresh-state shape.

    Purpose:
        A triage folder absent from ``cursors`` (e.g. added after bootstrap) is treated as
        freshly initialised: ``new = {last_date: 0}`` and ``back = {last_date: floor}``.
        Existing entries are returned as-is (the v2 shape was validated by the caller).

    Args:
        cursors: The state's ``cursors`` mapping.
        folder: A triage folder path.
        floor: The backfill floor in epoch seconds (for fresh defaults).

    Returns:
        A ``(new_cursor, back_cursor)`` tuple of ``{last_date, last_message_id}`` dicts.
    """
    entry = cursors.get(folder)
    if isinstance(entry, dict) and "new" in entry and "back" in entry:
        return entry["new"], entry["back"]
    return (
        {"last_date": 0, "last_message_id": ""},
        {"last_date": floor, "last_message_id": ""},
    )


def _detect(
    reader: NotmuchReader,
    mail_root: Path,
    account: str,
    owner: str,
    cursors: dict,
    floor: int,
    processed_ids: set[str],
    deferred: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Detect candidates across all triage folders and build the batch + deferred.

    Purpose:
        The core of detection (Task 5b three-pass global collection). For each triage folder,
        ONE ``search`` (no year prefix — notmuch's natural row order is **newest-first**, used
        directly, no reversal) splits rows into ``new_set`` (``ts > new.last_date``) and
        ``hist_set`` (``back.last_date < ts <= new.last_date``), EXCEPT when the folder's
        backfill is complete (``back.last_date < floor``), in which case ``hist_set = []``
        (defensive guard — it never fires, because the strict filter keeps ``back > floor``;
        kept as documentation). The candidate pool is then built in three passes over ALL
        folders so new mail in a small folder is never starved by a large folder's history:

        - **Pass 1** — every folder's ``new_set`` (UNBOUNDED only for folders with an advanced
          frontier, ``new_last > 0``; a fresh-frontier folder's mail is backfill → bounded
          history pass);
        - **Pass 1.5** — the previous run's ``deferred`` re-injected (already-kept entries: no
          re-``show``, de-duplicated by id) so cap-overflow mail is never lost;
        - **Pass 2** — every folder's ``hist_set`` (folder order, each newest-first).

        The pool is sorted globally newest-first (ts desc, id tie-break) before the cap is
        applied, so the batch is the true global newest-first across new/deferred/history.

        The global KEPT-entry budget (``2 * MAX_BATCH`` margin for exclusions) bounds the walk.
        It is applied to history only: pass 1 collects ALL new mail unbounded (newest-first), so
        a small folder's NEW mail can never be starved by a large folder's backfill — this is the
        user-confirmed "new mail is never starved" invariant, and it is what the spec's own
        ``test_cross_folder_new_mail_not_starved`` pins. (Deviation from the spec's literal
        "ONE shared budget across all passes", which would let an early folder's history consume
        the budget before a later folder's new mail is collected — see the result report.) Each
        candidate id gets ONE ``show`` to recover the requested message object (the notmuch 0.38.3
        thread-root quirk); a message is kept iff its timestamp is strictly greater than
        ``max(back.last_date, floor)`` AND it is not from the owner AND its folder is not under
        the PII prefix AND its id is not already in the processed log (the permanent floor is
        enforced here — mail below it is never triaged).
        The batch is the globally-newest-first ``pool[:MAX_BATCH]`` (the pool is sorted ts-desc,
        id tie-break, before the cap); ``deferred_new = pool[MAX_BATCH:]`` (re-injected next run).

    Args:
        reader: The configured :class:`NotmuchReader` over the target index.
        mail_root: The resolved maildir root (for folder derivation from filenames).
        account: The single top-level account directory name.
        owner: The owner address (case-insensitive) — own-mail exclusion.
        cursors: The state's ``cursors`` mapping (two-boundary ``{new, back}`` per folder).
        floor: The fixed backfill floor in epoch seconds (from the state document).
        processed_ids: The set of already-processed message-ids (de-dup source).
        deferred: The previous run's deferred entries (re-injected in pass 1.5, no re-show).

    Returns:
        A ``(batch, deferred_new)`` tuple: the batch in merge order (≤ MAX_BATCH) and the list
        of kept-but-over-cap entries (the next run's deferred).

    Side Effects:
        Read-only notmuch ``search``/``show`` calls (one per candidate id, bounded by the
        global ``2 * MAX_BATCH`` KEPT-entry budget). No writes. A ``NotmuchError`` on a single
        ``show`` is logged and that id skipped.
    """
    owner_lc = owner.lower()
    # Candidate pool in merge order: all new (pass 1) → deferred (pass 1.5) → all history
    # (pass 2). De-duplicated by message id; capped at the END so the ≤ MAX_BATCH batch cap is
    # re-applied to the final batch (deferred never rides on top of the manifest). The KEPT-entry
    # budget bounds worst-case cost across all three passes.
    pool: list[dict] = []
    seen_ids: set[str] = set()

    def _collect(row_set: list[dict], folder: str, back_last_date: int, *, bounded: bool) -> None:
        """Walk ``row_set`` (newest-first) and append kept candidate entries to the pool.

        Per id: ONE ``show`` to recover the requested message object (the thread-root quirk),
        then keep iff ``ts > max(back.last_date, floor)`` AND not own-mail AND not under PII
        AND not in the processed log. The effective lower bound is ``max(back, floor)``: a
        message is re-walkable (not yet processed) only if it sits above BOTH the folder's
        back frontier and the permanent floor (mail below the floor is never triaged). A
        single bad ``show`` is logged and skipped (never aborts). When ``bounded``, the global
        KEPT-entry budget stops the walk once enough candidates are gathered; new mail is
        collected unbounded (``bounded=False``) so it can never be starved by history.
        """
        lower_bound = max(back_last_date, floor)
        for row in row_set:
            if bounded and len(pool) >= 2 * MAX_BATCH:
                return
            for msg_id in row.get("message_ids", []):
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
                try:
                    doc = reader.show(msg_id)
                except NotmuchError as exc:
                    print(f"mail-keeper: skipping {msg_id}: {exc}")  # noqa: T201 - diagnostic
                    continue
                msg = _find_message_by_id(doc, msg_id) or doc["primary"]
                epoch = msg.get("timestamp")
                if not isinstance(epoch, int) or epoch <= lower_bound:
                    continue  # strict > max(back, floor): the permanent floor is enforced here
                headers = msg.get("headers") or {}
                from_header = str(headers.get("From", ""))
                if owner_lc in from_header.lower():
                    continue  # own mail is excluded (style sampling only, never triaged)
                filename = msg.get("filename")
                folder_of_msg = (
                    _folder_from_filename(filename[0], mail_root, account)
                    if isinstance(filename, list) and filename
                    else ""
                )
                if _folder_under_pii(folder_of_msg):
                    continue  # defense in depth: the loop already excluded this folder
                if msg_id in processed_ids:
                    continue  # already triaged in a previous run (primary history dedup)
                pool.append(
                    {
                        "message_id": msg_id,
                        "folder": folder_of_msg or folder,
                        "timestamp": epoch,
                        "from": from_header,
                        "from_addresses": _parse_from_addresses(from_header),
                        "subject": str(headers.get("Subject", "")),
                    }
                )

    # One search per folder; split each into new_set / hist_set on the two boundaries. The
    # defensive completion-skip (``back < floor``) never fires under the strict filter but is
    # kept as a documented guard.
    new_sets: list[tuple[str, list[dict], int]] = []
    hist_sets: list[tuple[str, list[dict], int]] = []
    for folder in TRIAGE_FOLDERS:
        if _folder_under_pii(folder) or folder in EXCLUDED_FOLDERS:
            continue  # PII + own corpus are never searched (defense in depth)
        new_cur, back_cur = _cursor_for(cursors, folder, floor)
        new_last_date = int(new_cur.get("last_date", 0))
        back_last_date = int(back_cur.get("last_date", 0))
        try:
            rows = reader.search(q_folder(account, folder), limit=10**9)
        except NotmuchError:
            raise  # a per-folder search failure is a business error for the run wrapper
        if new_last_date == 0:
            # Folder's new frontier has never advanced: it has no "new" mail — its entire
            # in-window mail is backfill. Route it to the bounded history pass so a fresh
            # bootstrap cannot flood the pool/deferred with the whole backlog. The floor
            # lower bound is enforced inside _collect (lower_bound = max(back, floor)).
            new_set: list[dict] = []
            hist_set = list(rows)
        else:
            new_set = [row for row in rows if int(row.get("timestamp", 0)) > new_last_date]
            if back_last_date < floor:
                hist_set = []  # truly complete → skip the history walk (defensive)
            else:
                hist_set = [
                    row
                    for row in rows
                    if back_last_date < int(row.get("timestamp", 0)) <= new_last_date
                ]
        new_sets.append((folder, new_set, back_last_date))
        hist_sets.append((folder, hist_set, back_last_date))

    # Pass 1: every folder's new mail, collected UNBOUNDED and ordered GLOBALLY newest-first
    # across folders (not per-folder) — a small folder's NEW mail can never be displaced by a
    # large folder's older "new" mail, so new mail is never starved (the user-confirmed
    # invariant). Only folders with an advanced frontier (new_last > 0) contribute here; a
    # fresh-frontier folder's mail is routed to the bounded history pass instead. The final
    # pool is re-sorted globally newest-first before the cap (see below), so this pass order
    # only affects which candidates are gathered, not their batch position.
    all_new_rows: list[tuple[dict, str, int]] = []
    for folder, new_set, back_last_date in new_sets:
        for row in new_set:
            all_new_rows.append((row, folder, back_last_date))
    all_new_rows.sort(key=lambda item: -int(item[0].get("timestamp", 0)))
    for row, folder, back_last_date in all_new_rows:
        _collect([row], folder, back_last_date, bounded=False)

    # Pass 1.5: re-inject the previous run's deferred (already-kept entries — no re-show),
    # de-duplicated by id, so cap-overflow mail is never lost.
    for entry in deferred:
        msg_id = entry.get("message_id")
        if msg_id and msg_id not in seen_ids:
            seen_ids.add(msg_id)
            pool.append(dict(entry))

    # Pass 2: every folder's history (newest-first), after all new mail; BOUNDED by the global
    # KEPT-entry budget so a huge backfill does not blow up per-run cost.
    for folder, hist_set, back_last_date in hist_sets:
        _collect(hist_set, folder, back_last_date, bounded=True)

    # Sort the pool GLOBALLY newest-first (ts desc, id tie-break) BEFORE the cap is applied:
    # this makes the batch the true global newest-first across new/deferred/history and drains
    # the deferred queue in recency order. A genuinely-new arrival always beats older history;
    # a new arrival OLDER than current history is ordered by recency (not lost — it stays in
    # the pool/deferred and is processed in order).
    pool.sort(key=lambda e: (-int(e["timestamp"]), e["message_id"]))
    batch = pool[:MAX_BATCH]
    deferred_new = [dict(c) for c in pool[MAX_BATCH:]]
    return batch, deferred_new


class MailKeeper:
    """The mail-keeper workflow: canary → backfill-aware detection → agent → state.

    A stateless object whose single :meth:`run` performs one run against the shared
    context and reports its outcome as a :class:`WorkflowResult`. It never raises for
    business failures (the run body is wrapped and unexpected exceptions are mapped to
    ``status="error"``), never writes vault files, never sends mail, and never runs
    ``notmuch new``.

    Attributes:
        name: The stable workflow name, matching its config key (``"mail-keeper"``).
    """

    name = "mail-keeper"

    def run(self, ctx) -> WorkflowResult:
        """Perform one mail-keeper run and report its outcome.

        Purpose:
            Execute the full pipeline: precheck (admin_repo + index readable), canary
            (stale → report-and-defer, never lose), state load (v2 two-boundary cursors +
            fixed 1-year floor; a v1-shaped state is a hard error), detection (three-pass
            global collection — all folders' new mail, then deferred, then all folders'
            history — with PII/own/processed exclusions), batch build (≤ MAX_BATCH, the cap
            re-applied to the final batch so deferred never rides on top of it), pre-backup
            snapshot, one agent invocation, and — only on ``ok`` — triage-class parse,
            processed-log append, TRUE per-folder cursor advance (each folder's own new/max +
            history-kind back/min; absent folders unchanged), deferred clear, and post-backup
            byte-identity check.

        Args:
            ctx: The shared :class:`~agentic_scripts.workflows.base.WorkContext`.

        Returns:
            A :class:`WorkflowResult`: ``skipped`` (admin_repo unset or index missing),
            ``ok`` (no new mail, or a successful agent run with an unchanged backup tree),
            or ``error`` (agent failure, agent step-cap exhaustion (sentinel on the final
            message), guardrail trip, or an unexpected exception).

        Side Effects:
            Read-only notmuch + filesystem; on the no-new-mail and agent-``ok`` paths it
            persists state and (on ``ok``) appends to the processed log. An agent failure
            writes NO state at all (fresh re-detection next run is identical). Never
            touches vault files, never sends mail, never runs ``notmuch new``.
        """
        try:
            return self._run(ctx)
        except Exception as exc:  # noqa: BLE001 - map unexpected exceptions to a business error
            ctx.logger.error("mail-keeper run failed unexpectedly: %s", exc)
            return WorkflowResult(
                status="error",
                errors=[f"unexpected error during mail-keeper run: {exc}"],
            )

    def _run(self, ctx) -> WorkflowResult:
        """The unwrapped run body (called by :meth:`run`, which maps exceptions)."""
        actions: list[str] = []
        errors: list[str] = []

        # --- 1. Precheck: admin_repo + index readable. No state writes on skip. --- #
        admin_repo = ctx.admin_repo
        if admin_repo is None:
            return WorkflowResult(status="skipped", actions=["admin_repo not configured"])

        index_db = Path(_env_str("MAIL_INDEX_DB", _DEFAULT_INDEX_DB))
        mail_root = Path(_env_str("MAIL_MAIL_ROOT", _DEFAULT_MAIL_ROOT))
        owner = _env_str("MAIL_OWNER_ADDRESS", _DEFAULT_OWNER)
        processed_log = Path(_env_str("MAIL_PROCESSED_LOG", _DEFAULT_PROCESSED_LOG))

        if not index_db.is_dir():
            return WorkflowResult(
                status="skipped",
                actions=[f"notmuch index missing/unreadable: {index_db}"],
            )

        reader = NotmuchReader(
            index_path=index_db, mail_root=mail_root, work_dir=ctx.sandbox_dir / "mail-keeper"
        )
        try:
            reader.count("")  # first count probes readability (missing DB → NotmuchError)
        except NotmuchError as exc:
            return WorkflowResult(
                status="skipped", actions=[f"notmuch index missing/unreadable: {exc}"]
            )

        # Resolve the single top-level account dir under mail_root (the spec assumption).
        account = self._resolve_account(mail_root)
        if account is None:
            return WorkflowResult(
                status="skipped", actions=[f"no account dir found under {mail_root}"]
            )

        # --- 2. Canary: report-and-defer on staleness; continue either way. --- #
        canary_res = canary.run_canaries(reader, mail_root, account)
        if canary_res["stale"]:
            actions.append(
                "index stale (deferring, never losing): disk="
                f"{canary_res['total_disk']} index={canary_res['total_index']} "
                f"reasons={'; '.join(canary_res['reasons'])}"
            )
        if not canary_res["spot_check"]["ok"]:
            errors.append(f"canary spot-check failed: {canary_res['spot_check']['note']}")

        # --- 3. State: v2 two-boundary cursors + fixed floor + deferred. --- #
        st = _read_state(ctx)
        schema_err = _validate_state(st)
        if schema_err is not None:
            return WorkflowResult(status="error", errors=[schema_err])

        first_run = "bootstrapped_at" not in st
        if first_run:
            now = int(time.time())
            floor = now - BACKFILL_WINDOW_SECONDS
            st = _fresh_state(now, floor)
            actions.append(
                f"first run: backfilling newest-first down to the 1-year floor "
                f"({BACKFILL_WINDOW_SECONDS // 86400} days)"
            )

        cursors = st.get("cursors", {}) or {}
        floor = int(st.get("backfill_floor", 0))
        deferred: list[dict] = st.get("deferred", []) or []

        # --- 4. Detection (three-pass global collection: all new → deferred → all hist). --- #
        processed_ids = _load_processed_log_ids(processed_log)
        batch, deferred_new = _detect(
            reader, mail_root, account, owner, cursors, floor, processed_ids, deferred
        )

        # The batch is the final ≤ MAX_BATCH set (deferred was re-injected into the candidate
        # pool inside _detect and the cap re-applied) — it goes to the brief, the processed log,
        # and the cursor update. NO deferred append on top of the manifest (the old bug).
        merged = batch

        # --- 5. Batch empty → no agent call; persist state; return ok. --- #
        if not merged:
            st["deferred"] = deferred_new
            _save_state(ctx, st)
            actions.append(
                f"no new mail ({len(processed_ids)} candidates excluded: PII/own/processed)"
            )
            return WorkflowResult(status="ok", items_found=0, actions=actions, errors=errors)

        # --- 6. Pre-walk: snapshot the backup tree right before the agent call. --- #
        snapshot_before = _backup_snapshot(mail_root)

        # --- 7. Agent call (exactly once per run). --- #
        brief = _render_brief(ctx.run_id, merged, owner)
        agent = ctx.runner.run(
            agent="mail-keeper", brief=brief, work_dir=admin_repo, title=f"mail-keeper {ctx.run_id}"
        )

        # --- 9. Agent error/timeout → no cursor advance, no log append; re-present next run. --- #
        if agent.status in {"error", "timeout"}:
            errors.append(
                f"agent run {agent.status}: {agent.error} (duration {agent.duration_seconds:.0f}s)"
            )
            return WorkflowResult(
                status="error", items_found=len(merged), actions=actions, errors=errors
            )

        # Step-exhaustion sentinel: opencode exits 0 when the agent hits its frontmatter step cap,
        # with the boilerplate as final message. Without this check the run would be recorded ok —
        # processed log + cursors advanced — for triage that never completed (Run-A incident,
        # 2026-10-25). Treat as failure: no log append, no cursor advance, batch re-presented.
        if agent.status == "ok" and _is_step_exhausted(agent.final_text):
            errors.append(
                "agent hit its step cap (opencode exited 0 with step-exhaustion boilerplate) — "
                "treating as failure; batch re-presented next run"
            )
            return WorkflowResult(
                status="error", items_found=len(merged), actions=actions, errors=errors
            )

        # --- 8. Agent ok: parse classes, append log, advance cursors, guardrail check. --- #
        classes = _parse_triage_classes(agent.final_text)

        # (a) Append processed-log records for EVERY batch entry.
        appended = _append_processed_log(processed_log, merged, classes)

        # (c) Advance cursors (only on ok + non-empty batch): TRUE PER-FOLDER frontier. For each
        # folder PRESENT in the batch: new_f = max ts of that folder's own batch entries;
        # back_f = min ts of that folder's HISTORY-kind entries (ts < the folder's PREVIOUS
        # new.last_date — no kind field needed). Folders absent from the batch keep both
        # boundaries. Invariant: back.last_date never drops below the floor (every kept ts is
        # strictly > the previous frontier ≥ floor).
        # Known quirk (documented, NOT fixed): a folder's FIRST batched entries (old new_last = 0)
        # advance `new`, not `back` — so its back stays at the floor until the SECOND touch. From
        # the second touch onward back tracks correctly. Harmless: the processed log + re-collection
        # keep correctness, and the backfill-complete guard is defensive-only (it never fires under
        # the strict filter). See Task 5f in the result report.
        new_cursors = {folder: dict(entry) for folder, entry in cursors.items()}
        for folder in TRIAGE_FOLDERS:
            if _folder_under_pii(folder) or folder in EXCLUDED_FOLDERS:
                continue
            entries_f = [e for e in merged if e["folder"] == folder]
            if not entries_f:
                continue  # folder absent from the batch → keep both boundaries unchanged
            old_new, old_back = _cursor_for(cursors, folder, floor)
            old_new_last = int(old_new.get("last_date", 0))
            old_back_last = int(old_back.get("last_date", floor))
            new_cur = dict(old_new)
            back_cur = dict(old_back)
            # new_f: max ts of this folder's own batch entries.
            newest_f = max(entries_f, key=lambda e: int(e.get("timestamp", 0)))
            if int(newest_f["timestamp"]) > old_new_last:
                new_cur = {
                    "last_date": int(newest_f["timestamp"]),
                    "last_message_id": newest_f["message_id"],
                }
            # back_f: min ts of this folder's history-kind entries (ts < the PREVIOUS new).
            # A fresh-state back sits AT the floor, so a deferred history batch (delivered in a
            # later run) has its min ABOVE the current back — advance back UP to that min (the
            # "oldest processed" frontier), not just down. Invariant: never below the floor.
            hist_f = [e for e in entries_f if int(e.get("timestamp", 0)) < old_new_last]
            if hist_f:
                oldest_hist = min(hist_f, key=lambda e: int(e.get("timestamp", 0)))
                ts_oldest = int(oldest_hist["timestamp"])
                if ts_oldest > old_back_last and ts_oldest >= floor:
                    back_cur = {
                        "last_date": ts_oldest,
                        "last_message_id": oldest_hist["message_id"],
                    }
            new_cursors[folder] = {"new": new_cur, "back": back_cur}
        st["cursors"] = new_cursors
        st["deferred"] = deferred_new

        # (d) Backfill-complete log: a folder whose frontier crossed the floor this run. This
        # transition never fires under the strict filter (back stays > floor); kept as a
        # documented guard.
        for folder, entry in new_cursors.items():
            old_back = int(_cursor_for(cursors, folder, floor)[1].get("last_date", floor))
            if old_back > floor >= int(entry["back"]["last_date"]):
                actions.append(f"backfill complete for {folder}")

        # (e) Persist state (single atomic write).
        _save_state(ctx, st)

        # (f) Post-walk: byte-identity guardrail check.
        snapshot_after = _backup_snapshot(mail_root)
        if snapshot_before != snapshot_after:
            errors.append("mail backup tree changed during the run (guardrail trip)")

        # (g) Log the agent's result report in full; summarise actions.
        ctx.logger.info("mail-keeper agent final report:\n%s", agent.final_text or "")
        class_summary = ", ".join(sorted(set((classes or {}).values()))) or "unparsed"
        actions.append(f"agent ok ({len(merged)} messages, classes: {class_summary})")
        actions.append(f"processed log: +{appended} record(s)")
        if snapshot_before == snapshot_after:
            actions.append("backup tree unchanged")
        if canary_res["stale"]:
            actions.append("staleness: deferred (index stale, see above)")

        status = "error" if errors else "ok"
        return WorkflowResult(
            status=status, items_found=len(merged), actions=actions, errors=errors
        )

    @staticmethod
    def _resolve_account(mail_root: Path) -> str | None:
        """Return the single top-level account dir under ``mail_root`` (or None).

        Purpose:
            The spec assumes exactly one top-level directory (the maildir account) under
            the mail root; zero or more is a skip condition, not an error.

        Args:
            mail_root: The maildir root to inspect.

        Returns:
            The account directory name, or None when it cannot be determined uniquely.
        """
        if not mail_root.is_dir():
            return None
        top_level = [entry.name for entry in mail_root.iterdir() if entry.is_dir()]
        return top_level[0] if len(top_level) == 1 else None
