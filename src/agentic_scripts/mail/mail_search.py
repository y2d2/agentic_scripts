"""The ``mail-search`` CLI — the mail-keeper agent's only reading surface.

Purpose:
    Provide :func:`main`, a read-only command-line interface over
    :class:`~agentic_scripts.mail.reader.NotmuchReader` that implements the verbatim
    contract fixed by the global ``skills/mail-keeper/SKILL.md`` (list mode, detail
    mode, the ``--from``/``--folder``/``--since``/``--until``/``--thread``/``--own`` /
    ``--limit`` filters, and the 0/1/2 exit-code contract). The mail-keeper agent
    invokes this bare (its PATH does not include the project venv), so it must be a
    stable, import-safe console script with no side effects on import.

Rationale:
    The reader is read-only *by construction* and exposes only matched message ids
    per thread row; per-message From/Subject/folder/timestamp therefore come from one
    ``show`` call per listed id (N subprocesses for N messages — acceptable at the
    default ``--limit 25`` on a local index, and the documented cost of NOT extending
    ``reader.py``). This module adds no new notmuch surface: it composes the reader's
    query builders and reads bodies via :meth:`NotmuchReader.body_text` (plain text)
    with a raw-file MIME fallback for HTML-only messages. It never writes anywhere
    except the reader's own temp config, and loads the project ``.env`` first so the
    agent can rely on ``MAIL_INDEX_DB``/``MAIL_MAIL_ROOT``/``MAIL_OWNER_ADDRESS``.

Contract (verbatim from the global skill — byte-for-byte in behavior):
    Usage:
      mail-search <query> [options]           list mode
      mail-search --show <message-id>         detail mode

    Options:
      <query>            full-text query (positional; list mode)
      --from <pattern>   only messages whose From name/address contains <pattern>
                         (case-insensitive)
      --folder <path>    only messages in folder <path> (e.g. INBOX, INBOX/ORBIT,
                         "Sent Items")
      --since <date>     only messages with date >= YYYY-MM-DD
      --until <date>     only messages with date <= YYYY-MM-DD
      --thread           expand matches to the full thread (References/In-Reply-To
                         closure), date order
      --own              only messages sent from the configured user address (style
                         sampling)
      --limit <n>        max messages returned (default 25)
      --index <path>     index DB path (default $MAIL_INDEX_DB; exit 1 if
                         unset/unreadable)

    List-mode stdout (one block per message; blank line between blocks):
      === <message-id> | <folder> | <YYYY-MM-DD HH:MM> | <From: name <addr>> | <Subject>
      <MIME-extracted plain-text body, truncated at 2000 chars>
    Detail-mode stdout: full headers + full plain-text body.
    Exit codes: 0 = ok (even zero matches), 1 = index missing/unreadable,
                2 = usage error.

Usage:
    >>> from agentic_scripts.mail import mail_search
    >>> raise SystemExit(mail_search.main(["--help"]))  # doctest: +SKIP
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from email import message_from_bytes
from pathlib import Path

from dotenv import load_dotenv

from agentic_scripts.mail.reader import (
    NotmuchError,
    NotmuchReader,
    _iter_body_parts,
    q_and,
    q_folder,
    q_thread,
)

# Project root: this file lives at <root>/src/agentic_scripts/mail/mail_search.py, so
# three parents up is the repo root. The CLI loads <root>/.env first (override=False)
# so MAIL_INDEX_DB / MAIL_MAIL_ROOT / MAIL_OWNER_ADDRESS are honoured when present.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Default maildir root and owner address (overridable via env; see the module docstring).
_DEFAULT_MAIL_ROOT = "/workspace/docker/mbsync/backup"
_DEFAULT_OWNER = "yuri.durodie@vub.be"

# Body truncation length for list mode (the skill contract mandates 2000 chars).
_BODY_LIMIT = 2000

# A strict YYYY-MM-DD date (used to validate --since / --until before touching the index).
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Naive HTML tag stripper for the HTML-only MIME fallback (best-effort, documented).
_TAG_RE = re.compile(r"<[^>]+>")


def _usage_error(message: str) -> int:
    """Print a usage error to stderr and return exit code 2.

    Purpose:
        Centralise the "exit 2" path so every usage violation reports to stderr (never
        stdout) with a consistent prefix and the contract's exit code.

    Args:
        message: A human-readable description of the usage error.

    Returns:
        ``2`` (the contract's usage-error exit code).

    Side Effects:
        Writes one line to stderr.
    """
    print(f"mail-search: {message}", file=sys.stderr)
    return 2


def _resolve_index_path(args: argparse.Namespace) -> tuple[Path | None, str]:
    """Resolve the index DB path from ``--index`` else ``$MAIL_INDEX_DB``.

    Purpose:
        Implement the contract's index-resolution rule: an explicit ``--index`` wins;
        otherwise the ``MAIL_INDEX_DB`` environment variable is used; if neither is set
        (or the value is empty) the index is "missing" and the caller exits 1.

    Args:
        args: The parsed argparse namespace.

    Returns:
        A ``(path, reason)`` tuple: ``(resolved_path, "")`` when a path was supplied, or
        ``(None, reason)`` when it is absent (``reason`` is the stderr message).
    """
    if args.index:
        return Path(args.index), ""
    env_value = os.environ.get("MAIL_INDEX_DB", "").strip()
    if not env_value:
        return None, "index DB path unset (pass --index or set MAIL_INDEX_DB)"
    return Path(env_value), ""


def _resolve_account(mail_root: Path) -> tuple[str | None, str]:
    """Determine the single top-level account directory under ``mail_root``.

    Purpose:
        The contract assumes exactly one top-level directory (the maildir account) under
        the mail root; more or zero is a usage error (exit 2). This isolates that check
        so it can be unit-tested without building an index.

    Args:
        mail_root: The maildir root to inspect.

    Returns:
        A ``(account, reason)`` tuple: ``(account_name, "")`` on success, or
        ``(None, reason)`` when the account cannot be determined uniquely.

    Side Effects:
        Reads (does not write) the directory entries of ``mail_root``.
    """
    if not mail_root.is_dir():
        return None, f"mail root is not a directory: {mail_root}"
    top_level = [entry.name for entry in mail_root.iterdir() if entry.is_dir()]
    if len(top_level) != 1:
        return (
            None,
            f"expected exactly one top-level account dir under {mail_root}, "
            f"found {len(top_level)}: {top_level!r}",
        )
    return top_level[0], ""


def _folder_from_filename(filename: str, mail_root: Path, account: str) -> str:
    """Derive a folder path (relative to the account) from a message's filename.

    Purpose:
        Map ``show``'s ``filename[0]`` (an absolute maildir path like
        ``<root>/<account>/INBOX/ORBIT/cur/<file>``) to the folder shown in list-mode
        header lines (e.g. ``INBOX/ORBIT``): strip everything up to and including
        ``<mail_root>/<account>/``, then drop the trailing maildir state segment
        (``cur``/``new``).

    Args:
        filename: The absolute message file path from ``show``'s primary object.
        mail_root: The resolved maildir root.
        account: The account directory name.

    Returns:
        The folder path relative to the account (e.g. ``INBOX``, ``INBOX/ORBIT``,
        ``Sent Items``), or ``""`` when it cannot be derived.
    """
    prefix = f"{mail_root}/{account}/"
    rel = filename[len(prefix) :] if filename.startswith(prefix) else filename
    parts = [p for p in rel.split("/") if p]
    # The maildir layout is <folder>/.../<state>/<file>, so the last two segments are
    # the state dir (cur/new) and the file name. Drop both to leave the folder path.
    if len(parts) >= 2 and parts[-2] in ("cur", "new"):
        parts = parts[:-2]
    return "/".join(parts)


def _body_from_raw(raw_path: Path) -> str:
    """MIME-parse a raw maildir file into plain text (HTML-only fallback).

    Purpose:
        For HTML-only messages the reader's :meth:`NotmuchReader.body_text` returns a
        pointer to the raw file rather than text. This reads the file, parses it with
        the stdlib ``email`` module, and concatenates every ``text/plain`` part (decode
        errors replaced). If only ``text/html`` is present it applies a naive tag-strip
        (documented best-effort — no CSS/JS handling); unreadable input yields ``""``.

    Args:
        raw_path: The absolute path to the raw maildir file.

    Returns:
        The extracted plain text (possibly empty), never raising for I/O or decode
        problems.

    Side Effects:
        Reads the file at ``raw_path`` (read-only).
    """
    try:
        data = raw_path.read_bytes()
    except OSError:
        return ""
    msg = message_from_bytes(data)
    plain_chunks: list[str] = []
    html_chunks: list[str] = []
    for part in msg.walk():
        content_type = str(part.get_content_type()).lower()
        if content_type == "text/plain":
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                plain_chunks.append(payload.decode("utf-8", errors="replace"))
        elif content_type == "text/html":
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                html_chunks.append(payload.decode("utf-8", errors="replace"))
    if plain_chunks:
        return "".join(plain_chunks)
    if html_chunks:
        # Best-effort tag strip for HTML-only messages (documented; not a real renderer).
        text = _TAG_RE.sub("", "".join(html_chunks))
        return re.sub(r"\s+", " ", text).strip()
    return ""


def _format_timestamp(epoch: int) -> str:
    """Format an integer epoch as a local ``YYYY-MM-DD HH:MM`` string.

    Purpose:
        List-mode header lines carry the message date in local calendar time (the
        contract's ``<YYYY-MM-DD HH:MM>``). Converting through the process-local timezone
        keeps it consistent with what an operator sees on this single-user machine.

    Args:
        epoch: The integer Unix timestamp from ``show``'s primary object.

    Returns:
        A ``YYYY-MM-DD HH:MM`` string in local time.
    """
    return datetime.fromtimestamp(epoch, tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M")


def _find_message_by_id(doc: dict, message_id: str) -> dict | None:
    """Return the message object with ``id == message_id`` from a show document.

    Purpose:
        Work around a notmuch 0.38.3 quirk: ``show --format=json 'id:<msgid>'`` returns
        the *thread root* as the primary message, not the requested message — the
        requested message (if it is not the root) appears in the thread context. This
        searches the full parsed document for the message object whose ``id`` matches,
        so callers always get the specific message they asked for.

    Rationale:
        The reader's :meth:`NotmuchReader.show` exposes only the primary (thread root) and
        context; it does not let you pick an arbitrary message by id. Since the CLI needs
        per-message From/Subject/folder/timestamp for *each* listed id, this helper is
        required to recover the correct message object from the nested document.

    Args:
        doc: The full dict returned by :meth:`NotmuchReader.show` (with a ``raw`` key).
        message_id: The Message-Id to find.

    Returns:
        The matching message-object dict, or None if not found in the document.

    Example:
        >>> doc = reader.show("m5@example.com")  # doctest: +SKIP
        >>> _find_message_by_id(doc, "m5@example.com")["id"]  # doctest: +SKIP
        'm5@example.com'
    """
    raw = doc.get("raw")
    if raw is None:
        return None

    def _walk(node: object) -> dict | None:
        if isinstance(node, dict):
            if node.get("id") == message_id:
                return node
            for value in node.values():
                found = _walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for child in node:
                found = _walk(child)
                if found is not None:
                    return found
        return None

    return _walk(raw)


def _body_from_message(msg_obj: dict) -> tuple[str | None, Path | None]:
    """Extract the plain-text body (or raw-file pointer) from a specific message object.

    Purpose:
        Mirror :meth:`NotmuchReader.body_text`'s logic but operate on an arbitrary
        message object (not the thread root). This is required because notmuch's ``show``
        returns the thread root as primary, so :meth:`NotmuchReader.body_text` would
        extract the *wrong* message's body for a non-root message in a thread.

    Args:
        msg_obj: A message-object dict (with ``body`` and ``filename`` keys) from a show
            document — typically the result of :func:`_find_message_by_id`.

    Returns:
        ``(plain_text, None)`` when plain text was found; ``(None, raw_file_path)`` when
        only an HTML part exists (the raw maildir file at ``filename[0]`` for caller-side
        MIME parsing); ``(None, None)`` when neither is present.

    Raises:
        NotmuchError: When the message has an HTML part but no filename to fall back to.
    """
    leaves = _iter_body_parts(msg_obj.get("body"))
    plain_chunks: list[str] = []
    has_html = False
    for part in leaves:
        content_type = str(part.get("content-type", "")).lower()
        if "text/html" in content_type:
            has_html = True
        elif "text/plain" in content_type and isinstance(part.get("content"), str):
            plain_chunks.append(part["content"])

    if plain_chunks:
        return "".join(plain_chunks), None
    if has_html:
        filename = msg_obj.get("filename")
        if not (isinstance(filename, list) and filename):
            raise NotmuchError(
                "body_from_message",
                "no-filename",
                "HTML message has no filename to fall back to",
            )
        return None, Path(filename[0])
    return None, None


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the mail-search CLI.

    Purpose:
        Centralise argument definitions so ``--help`` (exit 0) and all option parsing
        live in one place. The positional query is optional at the argparse level; the
        "list mode requires a query or --folder" rule is enforced in :func:`main` after
        index-free validation (so usage errors exit 2 without touching the index).

    Returns:
        A configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="mail-search",
        description="Read-only notmuch mail search (list + detail modes).",
    )
    parser.add_argument("query", nargs="?", default=None, help="full-text query (list mode)")
    parser.add_argument(
        "--show", metavar="MESSAGE_ID", default=None, help="detail mode: show one message"
    )
    parser.add_argument(
        "--from",
        dest="from_pattern",
        default=None,
        metavar="PATTERN",
        help="From name/address contains PATTERN (case-insensitive)",
    )
    parser.add_argument(
        "--folder",
        default=None,
        metavar="PATH",
        help='folder path (e.g. INBOX, INBOX/ORBIT, "Sent Items")',
    )
    parser.add_argument("--since", default=None, metavar="DATE", help="date >= YYYY-MM-DD")
    parser.add_argument("--until", default=None, metavar="DATE", help="date <= YYYY-MM-DD")
    parser.add_argument(
        "--thread", action="store_true", help="expand matches to the full thread, date order"
    )
    parser.add_argument(
        "--own", action="store_true", help="only messages from the configured user address"
    )
    parser.add_argument(
        "--limit", type=int, default=25, metavar="N", help="max messages returned (default 25)"
    )
    parser.add_argument(
        "--index", default=None, metavar="PATH", help="index DB path (default $MAIL_INDEX_DB)"
    )
    return parser


def _list_mode(
    reader: NotmuchReader,
    mail_root: Path,
    account: str,
    owner: str,
    args: argparse.Namespace,
) -> int:
    """Run list mode and emit the contract's block format to stdout.

    Purpose:
        Implement the list-mode algorithm (query build → search → optional thread
        expansion → per-id show → post-filters → date-ascending order → limit → emit).
        A ``show`` failure on one message is warned to stderr and skipped (exit stays 0);
        zero matches exit 0 with empty stdout.

    Args:
        reader: The configured :class:`NotmuchReader`.
        mail_root: The resolved maildir root (for folder derivation).
        account: The account directory name.
        owner: The configured user address (for ``--own``).
        args: The parsed argparse namespace.

    Returns:
        ``0`` on success (including zero matches); never raises for a single bad message.

    Side Effects:
        Writes list-mode blocks to stdout and warnings to stderr.
    """
    clauses = []
    if args.folder is not None:
        clauses.append(q_folder(account, args.folder))
    if args.query is not None:
        clauses.append(args.query)
    query = q_and(*clauses)

    rows = reader.search(query, limit=10**9)
    # Flatten and dedupe message ids in row order (first-seen wins).
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for msg_id in row["message_ids"]:
            if msg_id not in seen:
                seen.add(msg_id)
                ordered_ids.append(msg_id)

    if args.thread:
        # Expand to the full thread closure by re-searching each distinct thread id.
        expanded: list[str] = []
        expanded_seen: set[str] = set()
        for row in rows:
            tid = row.get("thread")
            if not tid:
                continue
            try:
                t_rows = reader.search(q_thread(tid), limit=10**9)
            except NotmuchError as exc:
                print(f"mail-search: thread search failed for {tid}: {exc}", file=sys.stderr)
                continue
            for t_row in t_rows:
                for msg_id in t_row["message_ids"]:
                    if msg_id not in expanded_seen:
                        expanded_seen.add(msg_id)
                        expanded.append(msg_id)
        ordered_ids = expanded

    owner_lc = owner.lower()
    from_lc = (args.from_pattern or "").lower()
    since_date = datetime.strptime(args.since, "%Y-%m-%d").date() if args.since else None
    until_date = datetime.strptime(args.until, "%Y-%m-%d").date() if args.until else None

    messages: list[dict] = []
    for msg_id in ordered_ids:
        try:
            doc = reader.show(msg_id)
        except NotmuchError as exc:
            print(f"mail-search: skipping {msg_id}: {exc}", file=sys.stderr)
            continue
        # notmuch's show returns the thread root as primary; find the specific message.
        msg_obj = _find_message_by_id(doc, msg_id) or doc["primary"]
        headers = msg_obj.get("headers") or {}
        from_value = str(headers.get("From", ""))

        # Post-filters on the message.
        if args.from_pattern is not None and from_lc not in from_value.lower():
            continue
        if args.own and owner_lc not in from_value.lower():
            continue
        epoch = msg_obj.get("timestamp")
        if isinstance(epoch, int) and (since_date or until_date):
            local_date = datetime.fromtimestamp(epoch, tz=UTC).astimezone().date()
            if since_date and local_date < since_date:
                continue
            if until_date and local_date > until_date:
                continue

        filename = msg_obj.get("filename")
        folder = (
            _folder_from_filename(filename[0], mail_root, account)
            if isinstance(filename, list) and filename
            else ""
        )
        messages.append(
            {
                "id": msg_id,
                "folder": folder,
                "timestamp": epoch if isinstance(epoch, int) else 0,
                "from": from_value,
                "subject": str(headers.get("Subject", "")),
                "obj": msg_obj,
            }
        )

    # Date ascending (stable), then apply the limit.
    messages.sort(key=lambda m: m["timestamp"])
    messages = messages[: args.limit]

    blocks: list[str] = []
    for msg in messages:
        try:
            text, raw_path = _body_from_message(msg["obj"])
        except NotmuchError as exc:
            print(f"mail-search: body extraction failed for {msg['id']}: {exc}", file=sys.stderr)
            text, raw_path = "", None
        if text is not None:
            body = text.strip()[:_BODY_LIMIT]
        elif raw_path is not None:
            body = _body_from_raw(Path(raw_path)).strip()[:_BODY_LIMIT]
        else:
            body = ""
        header_line = (
            f"=== {msg['id']} | {msg['folder']} | {_format_timestamp(msg['timestamp'])} "
            f"| {msg['from']} | {msg['subject']}"
        )
        blocks.append(f"{header_line}\n{body}")

    sys.stdout.write("\n\n".join(blocks))
    if blocks:
        sys.stdout.write("\n")
    return 0


def _detail_mode(reader: NotmuchReader, message_id: str) -> int:
    """Run detail mode: full headers + full plain-text body to stdout.

    Purpose:
        Implement the contract's detail mode — print every header line of the primary
        message followed by its full (untruncated) plain-text body. A missing message or
        a body-extraction failure is reported to stderr with exit 1.

    Args:
        reader: The configured :class:`NotmuchReader`.
        message_id: The Message-Id to display.

    Returns:
        ``0`` on success; ``1`` when the message cannot be shown or its body extracted.

    Side Effects:
        Writes the detail block to stdout and errors to stderr.
    """
    try:
        doc = reader.show(message_id)
    except NotmuchError as exc:
        print(f"mail-search: {exc}", file=sys.stderr)
        return 1
    # notmuch's show returns the thread root as primary; find the specific message.
    msg_obj = _find_message_by_id(doc, message_id) or doc["primary"]
    headers = dict(msg_obj.get("headers") or {})
    # notmuch stores the Message-Id as the message's ``id`` field, not in ``headers``;
    # synthesize it so detail mode prints the full header set (the contract mandates a
    # Message-ID: line).
    if "Message-ID" not in headers and msg_obj.get("id"):
        headers["Message-ID"] = f"<{msg_obj['id']}>"
    for name, value in headers.items():
        sys.stdout.write(f"{name}: {value}\n")
    try:
        text, raw_path = _body_from_message(msg_obj)
    except NotmuchError as exc:
        print(f"mail-search: body extraction failed: {exc}", file=sys.stderr)
        return 1
    if text is not None:
        sys.stdout.write("\n")
        sys.stdout.write(text)
        sys.stdout.write("\n")
    elif raw_path is not None:
        body = _body_from_raw(Path(raw_path))
        sys.stdout.write("\n")
        sys.stdout.write(body)
        if body:
            sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``mail-search`` CLI.

    Purpose:
        Parse arguments, validate usage (exit 2 before any index work), resolve the
        index/mail-root/account/owner, build a read-only :class:`NotmuchReader`, and
        dispatch to list or detail mode. Implements the contract's exit-code semantics:
        0 = ok (even zero matches), 1 = index missing/unreadable, 2 = usage error.

    Rationale:
        Usage validation happens *before* index resolution so ``--help`` exits 0 and
        usage errors exit 2 without touching the filesystem or spawning notmuch. The
        reader's work_dir is a fresh temp dir (left in place; /tmp is ephemeral) and the
        reader itself injects NOTMUCH_CONFIG, so this module never writes config.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``); injected by tests
            for in-process invocation.

    Returns:
        The process exit code: 0 (ok), 1 (index missing/unreadable), or 2 (usage error).

    Side Effects:
        Loads the project ``.env`` (override=False); writes to stdout/stderr; creates a
        temp reader work dir. No other filesystem writes.

    Example:
        >>> import sys
        >>> raise SystemExit(main(["ORBIT", "--index", "/some/index"]))  # doctest: +SKIP
    """
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --- Usage validation (exit 2), before any index work. ---
    if args.show is not None and args.query is not None:
        return _usage_error("--show is exclusive with the positional query")
    if args.show is not None and not args.show.strip():
        return _usage_error("--show requires a non-empty message id")
    if args.since is not None and not _DATE_RE.match(args.since):
        return _usage_error(f"--since must be YYYY-MM-DD (got {args.since!r})")
    if args.until is not None and not _DATE_RE.match(args.until):
        return _usage_error(f"--until must be YYYY-MM-DD (got {args.until!r})")
    if args.show is None and args.query is None and args.folder is None:
        return _usage_error("list mode requires a query or --folder")

    # --- Index resolution (exit 1 when missing/unreadable). ---
    index_path, reason = _resolve_index_path(args)
    if index_path is None:
        print(f"mail-search: {reason}", file=sys.stderr)
        return 1
    if not index_path.is_dir():
        print(
            f"mail-search: index DB path is not an existing directory: {index_path}",
            file=sys.stderr,
        )
        return 1

    mail_root = Path(os.environ.get("MAIL_MAIL_ROOT", "").strip() or _DEFAULT_MAIL_ROOT)
    owner = os.environ.get("MAIL_OWNER_ADDRESS", "").strip() or _DEFAULT_OWNER
    account, reason = _resolve_account(mail_root)
    if account is None:
        return _usage_error(reason)

    work_dir = Path(tempfile.mkdtemp(prefix="mail-search-"))
    reader = NotmuchReader(index_path=index_path, mail_root=mail_root, work_dir=work_dir)

    # Probe the index with a cheap count; a missing-database failure exits 1.
    try:
        reader.count("")
    except NotmuchError as exc:
        print(f"mail-search: index unreadable ({exc})", file=sys.stderr)
        return 1

    if args.show is not None:
        return _detail_mode(reader, args.show.strip())
    return _list_mode(reader, mail_root, account, owner, args)


if __name__ == "__main__":
    raise SystemExit(main())
