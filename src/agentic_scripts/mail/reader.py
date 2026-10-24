"""Read-only notmuch mail reader for agentic_scripts workflows.

Purpose:
    Provide :class:`NotmuchReader`, a thin, *read-only* wrapper over the ``notmuch``
    0.38.3 command-line interface, plus pure query-builder helpers (:func:`q_text`,
    :func:`q_from`, :func:`q_folder`, :func:`q_id`, :func:`q_thread`,
    :func:`q_date_prefix`, :func:`q_and`). The wrapper generates its own reader
    config (with ``synchronize_flags=false``), injects it via ``NOTMUCH_CONFIG``, and
    exposes ``count`` / ``search`` / ``message_ids`` / ``show`` / ``body_text`` over
    the verified 0.38.3 JSON shapes, so workflow code never shells out to notmuch
    directly.

Rationale:
    The reader must be read-only *by construction*: it never flips maildir flags and
    never invokes ``notmuch new`` (indexing is a test/setup concern, not the class
    API). A dedicated generated config keeps the reader isolated from any ambient
    ``~/.config/notmuch`` and guarantees ``synchronize_flags=false``. The query
    builders emit only the forms verified to work in this build and deliberately
    refuse the unsupported ones (see :data:`SUPPORTED_PREFIXES`), so a caller cannot
    accidentally construct a query that notmuch silently reinterprets as free text.

Read-only contract:
    ``NotmuchReader`` opens its index and maildir read-only. It creates only its own
    config file inside ``work_dir`` and never mutates the contents of
    ``index_path`` or ``mail_root``. In particular it does not run ``notmuch new``
    and does not set ``synchronize_flags=true`` (that belongs to the mbsync *writer*
    side only). Callers may freely share a reader across read operations.

Verified notmuch 0.38.3 shapes (empirical, read-only probes against the live index):
    - ``notmuch count [query]`` prints a single integer line; bare ``count`` is the
      total message count.
    - ``notmuch search --format=json <query>`` emits a JSON *array of thread
      objects*: ``{thread, timestamp, date_relative, matched, total, authors,
      subject, query, tags}``. ``query`` is a 2-element list
      ``[matched_subquery, unmatched_subquery]`` where each element is a
      space-joined string of ``id:<msgid>`` clauses (or ``null`` when empty).
      Message-ids never contain spaces, so a whitespace split safely recovers the
      per-thread message ids. ``timestamp`` is an integer epoch.
    - ``--format=messages`` does NOT exist in this build; per-message data comes from
      ``show``.
    - ``notmuch show --format=json 'id:<msgid>'`` emits a *nested recursive JSON
      list*. The primary message is the first message object in document order (a
      dict carrying an ``id`` key); thread-context messages are nested deeper and
      carry ``match=false``. Each message object has keys
      ``{id, match, excluded, filename[], timestamp, date_relative, tags, duplicate,
      body[], crypto, headers}``. ``text/plain`` body parts carry a decoded
      ``content`` string; ``text/html`` parts carry only ``content-length`` (no body)
      and are nested under a multipart container's ``content`` list — so HTML-only
      messages require reading the raw maildir file at ``filename[0]`` for MIME
      parsing.
    - Working query forms: free text, ``from:"..."``, ``folder:"<acct>/<path>"``
      (always double-quoted), ``id:<msgid>``, ``thread:<tid>``, ``date:YYYY*``.
    - **Unsupported in this build** (do not use; the builders refuse them): unknown
      query properties are *not* rejected by notmuch — they are silently reinterpreted
      as free-text terms (notmuch's documented fallback; verified 2026-10-20 on the
      live index: ``all:`` returns 5,678 matches, identical to the free-text word
      ``all``; date-style terms like ``after:1990-01-01``, ``before:2100-01-01``,
      ``last:30d`` match nothing) — no error, exit 0. The affected forms (``all:``,
      ``field:*`` wildcards, ``after:``, ``before:``, ``last:``) are forbidden because
      they can silently return large irrelevant result sets; the builders refuse them
      (see :data:`SUPPORTED_PREFIXES`); use the verified ``date:YYYY*`` prefix form for
      date ranges.

Usage:
    >>> from pathlib import Path
    >>> from agentic_scripts.mail.reader import NotmuchReader, q_from
    >>> reader = NotmuchReader(
    ...     index_path=Path("/path/index"), mail_root=Path("/path/mail"), work_dir=Path("work")
    ... )
    >>> reader.count(q_from("Alice"))
    2
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

# Query prefixes that are known to work in notmuch 0.38.3. The builder helpers emit
# only these forms; ``q_and`` rejects any clause whose first token starts with a
# prefix outside this set (the unsupported forms, which notmuch silently reinterprets
# as free text: all:, field: wildcards, after:, before:, last:). This constant is the
# single source of truth for that refusal contract.
SUPPORTED_PREFIXES = {"from", "folder", "id", "thread", "date"}

# Prefixes explicitly unsupported in this notmuch build: notmuch silently reinterprets
# them as free-text terms (its documented fallback) rather than rejecting them.
# Documented here (and in the module docstring) so the refusal contract is discoverable;
# ``q_and`` uses it to reject unsupported clauses with a precise message.
_UNSUPPORTED_PREFIXES = {"all", "field", "after", "before", "last"}

# The exact reader config body, with two path placeholders. Every generated reader
# config matches this byte-for-byte modulo the resolved absolute paths (asserted in
# tests). ``synchronize_flags=false`` is load-bearing: the reader must never flip
# maildir flags.
_READER_CONFIG_TEMPLATE = (
    "[database]\npath={index_path}\nmail_root={mail_root}\n[maildir]\nsynchronize_flags=false\n"
)


class NotmuchError(RuntimeError):
    """Raised when a notmuch invocation fails (non-zero exit or timeout).

    Attributes:
        message: A string of the form ``<op> failed (exit <code>): <stderr tail>``,
            suitable for display. For a timeout, the code is ``"timeout"`` and the
            stderr tail is empty.

    Example:
        >>> raise NotmuchError("count", 1, "Error: no such term")
        Traceback (most recent call last):
            ...
        agentic_scripts.mail.reader.NotmuchError: count failed (exit 1): Error: no such term
    """

    def __init__(self, op: str, code: int | str, stderr_tail: str) -> None:
        self.op = op
        self.code = code
        self.stderr_tail = stderr_tail
        self.message = f"{op} failed (exit {code}): {stderr_tail}"
        super().__init__(self.message)


def q_text(term: str) -> str:
    """Return a free-text query term unchanged.

    Purpose:
        Pass a caller-supplied safe phrase through as-is, since notmuch free-text
        terms need no quoting when the caller has already ensured they are safe.

    Args:
        term: A safe free-text search phrase (no special notmuch syntax expected).

    Returns:
        ``term`` unchanged.

    Example:
        >>> q_text("hello world")
        'hello world'
    """
    return term


def q_from(value: str) -> str:
    """Build a double-quoted ``from:`` query clause.

    Purpose:
        Emit the verified working form for matching an author, always double-quoted
        because author names contain spaces (e.g. ``Yuri Durodie``).

    Args:
        value: The author name or address to match. Embedded quotes are the caller's
            responsibility; they are not escaped here.

    Returns:
        ``from:"<value>"``.

    Example:
        >>> q_from("Yuri Durodie")
        'from:"Yuri Durodie"'
    """
    return f'from:"{value}"'


def q_folder(account: str, path: str) -> str:
    """Build a double-quoted ``folder:`` query clause for an account sub-path.

    Purpose:
        Emit the verified working form for matching a maildir folder. The whole
        ``<account>/<path>`` is wrapped in a single pair of double quotes because
        folder paths contain spaces (e.g. ``Sent Items``); the individual
        ``account``/``path`` values are NOT re-quoted internally.

    Args:
        account: The maildir account (top-level) directory name.
        path: The sub-path within the account (may be empty for the account root).

    Returns:
        ``folder:"<account>/<path>"``.

    Example:
        >>> q_folder("a@b", "Sent Items")
        'folder:"a@b/Sent Items"'
    """
    return f'folder:"{account}/{path}"'


def q_id(msgid: str) -> str:
    """Build an ``id:`` query clause for a single RFC 5322 Message-Id.

    Purpose:
        Emit the verified working form for matching one message by id. No quoting is
        applied because message-ids never need it (they contain no spaces).

    Args:
        msgid: The Message-Id value (without surrounding ``<...>`` as notmuch stores
            it, or with them — notmuch normalises either; pass the stored form for
            exact matches).

    Returns:
        ``id:<msgid>``.

    Example:
        >>> q_id("m1@example.com")
        'id:m1@example.com'
    """
    return f"id:{msgid}"


def q_thread(tid: str) -> str:
    """Build a ``thread:`` query clause for a notmuch thread id.

    Purpose:
        Emit the verified working form for matching every message in one thread.

    Args:
        tid: The notmuch thread id (e.g. ``0000000000000001``).

    Returns:
        ``thread:<tid>``.

    Example:
        >>> q_thread("0000000000000001")
        'thread:0000000000000001'
    """
    return f"thread:{tid}"


def q_date_prefix(year: int) -> str:
    """Build a ``date:<year>*`` prefix query clause.

    Purpose:
        Emit the verified working form for matching messages in a given year using
        notmuch's date prefix-star (the plain ``after:``/``before:`` forms are
        unsupported — notmuch silently reinterprets them as free text — so
        year-prefixing is the supported way to bound by time).

    Args:
        year: A four-digit calendar year.

    Returns:
        ``date:<year>*``.

    Example:
        >>> q_date_prefix(2026)
        'date:2026*'
    """
    return f"date:{year}*"


def _first_token_prefix(clause: str) -> str | None:
    """Return the prefix before the first ``:`` in a clause, or None if no colon.

    Purpose:
        Support :func:`q_and`'s refusal contract by identifying which notmuch field
        prefix a compound clause starts with (e.g. ``after:2026-...`` -> ``after``).

    Args:
        clause: A single query clause (already whitespace-free at its head).

    Returns:
        The lower-cased prefix token before the first colon, or None when the clause
        has no colon (a free-text term).
    """
    if ":" not in clause:
        return None
    return clause.split(":", 1)[0].strip().lower()


def q_and(*clauses: str) -> str:
    """Join query clauses with `` and ``, refusing broken-prefix and empty input.

    Purpose:
        Compose a compound notmuch query from already-built clauses (or safe free
        text), while enforcing the build's refusal contract: an empty argument list
        is a caller bug, and any clause whose first token starts with an unsupported
        prefix (``all:``, ``field:*``, ``after:``, ``before:``, ``last:``) is
        rejected.

    Rationale:
        The refused forms are NOT rejected by notmuch — they are silently reinterpreted
        as free-text terms (verified 2026-10-20 on the live index: ``all:`` returns
        5,678 matches, identical to the free-text word ``all``; date-style terms return
        0; never an error). A broken form at runtime would silently return a large,
        irrelevant result set — refusal at build time is the only safe guard.

    Args:
        *clauses: One or more clauses, each either the output of one of the ``q_*``
            builders or a safe free-text term. Must be non-empty.

    Returns:
        The clauses joined with ``" and "`` (e.g. ``from:"x" and date:2026*``).

    Raises:
        NotmuchError: If no clauses are given, or if any clause's first token starts
            with an unsupported prefix.

    Example:
        >>> q_and(q_from("x"), q_date_prefix(2026))
        'from:"x" and date:2026*'
        >>> q_and()
        Traceback (most recent call last):
            ...
        agentic_scripts.mail.reader.NotmuchError: ...
    """
    if not clauses:
        raise NotmuchError(
            "q_and",
            "empty",
            "at least one clause is required (an empty compound query is a caller bug)",
        )
    for clause in clauses:
        prefix = _first_token_prefix(clause)
        if prefix in _UNSUPPORTED_PREFIXES:
            raise NotmuchError(
                "q_and",
                "unsupported-prefix",
                f"clause '{clause}' uses unsupported prefix '{prefix}:' (broken in notmuch 0.38.3)",
            )
    return " and ".join(clauses)


def _extract_message_ids(query_clause: str | None) -> list[str]:
    """Extract message-ids from a space-joined ``id:<msgid>`` clause string.

    Purpose:
        Recover the per-thread message ids from ``search``'s ``query[0]`` element by
        whitespace-splitting and stripping the ``id:`` prefix. This is verified safe
        for this build's output because RFC 5322 Message-Ids never contain spaces.

    Args:
        query_clause: The ``query[0]`` string from a search thread object, or None /
            empty when there are no matched messages.

    Returns:
        A list of message-id strings in the order they appear in the clause (empty
        list for None/empty input).
    """
    if not query_clause:
        return []
    ids: list[str] = []
    for token in query_clause.split():
        if token.startswith("id:"):
            ids.append(token[3:])
    return ids


def _collect_message_objects(node: object) -> list[dict]:
    """Depth-first collect every message object (dict with an ``id`` key) in a doc.

    Purpose:
        Flatten notmuch's nested recursive ``show --format=json`` list into an
        ordered list of message objects, preserving document order so the first
        element is the primary message and the rest are thread-context messages.

    Args:
        node: Any node of the parsed JSON document (list or dict).

    Returns:
        A list of message-object dicts in depth-first document order.
    """
    found: list[dict] = []
    if isinstance(node, dict):
        if "id" in node:
            found.append(node)
    elif isinstance(node, list):
        for child in node:
            found.extend(_collect_message_objects(child))
    return found


def _iter_body_parts(parts: object) -> list[dict]:
    """Recursively flatten a message's ``body`` part tree into leaf parts.

    Purpose:
        Walk a notmuch body-part structure, descending into multipart containers
        (whose sub-parts live under a ``content`` key as a list) so that the actual
        ``text/plain`` / ``text/html`` leaf parts are reached regardless of nesting.

    Args:
        parts: The ``body`` list from a message object, or any nested part structure.

    Returns:
        A flat, ordered list of leaf body-part dicts (multipart containers excluded;
        their children included in place).
    """
    leaves: list[dict] = []
    if isinstance(parts, dict):
        parts = [parts]
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        content = part.get("content")
        if isinstance(content, list):
            # A multipart container: recurse into its sub-parts.
            leaves.extend(_iter_body_parts(content))
        else:
            leaves.append(part)
    return leaves


class NotmuchReader:
    """A read-only wrapper over the notmuch 0.38.3 CLI for workflow mail access.

    Purpose:
        Generate an isolated reader config (``synchronize_flags=false``), inject it
        via ``NOTMUCH_CONFIG``, and expose count/search/message-ids/show/body_text
        over the verified 0.38.3 JSON shapes without callers shelling out to notmuch
        directly.

    Rationale:
        Read-only by construction: the reader never mutates ``index_path`` or
        ``mail_root`` contents, never runs ``notmuch new``, and never sets
        ``synchronize_flags=true``. A per-instance generated config (0600) keeps it
        isolated from any ambient notmuch configuration and guarantees the no-flag-
        sync behaviour for every subprocess call.

    Attributes:
        index_path: The notmuch database (index) directory (read-only).
        mail_root: The maildir root the index was built over (read-only).
        work_dir: Directory where the generated reader config is written.
        notmuch_bin: Path/name of the notmuch binary to invoke.

    Example:
        >>> reader = NotmuchReader(
        ...     index_path=Path("idx"), mail_root=Path("mail"), work_dir=Path("work")
        ... )
        >>> reader.count()  # doctest: +SKIP
        3
    """

    def __init__(
        self,
        *,
        index_path: Path,
        mail_root: Path,
        work_dir: Path,
        logger: logging.Logger | None = None,
        notmuch_bin: str = "notmuch",
    ) -> None:
        """Create a reader and write its generated config into ``work_dir``.

        Args:
            index_path: The notmuch database (index) directory. Resolved to an
                absolute path in the generated config; never mutated by this class.
            mail_root: The maildir root. Resolved to an absolute path in the
                generated config; never mutated by this class.
            work_dir: Directory for the generated ``notmuch-reader-config`` file;
                created if it does not exist.
            logger: Optional logger for diagnostics (defaults to a module logger).
            notmuch_bin: The notmuch binary name/path (default ``"notmuch"``).

        Side Effects:
            Creates ``work_dir`` and writes ``<work_dir>/notmuch-reader-config``
            (0600) containing the canonical reader config. Does NOT touch
            ``index_path`` or ``mail_root``.
        """
        self.index_path = Path(index_path).resolve()
        self.mail_root = Path(mail_root).resolve()
        self.work_dir = Path(work_dir)
        self._logger = logger if logger is not None else logging.getLogger(__name__)
        self._bin = notmuch_bin

        self.work_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.work_dir / "notmuch-reader-config"
        config_text = _READER_CONFIG_TEMPLATE.format(
            index_path=str(self.index_path), mail_root=str(self.mail_root)
        )
        config_path.write_text(config_text, encoding="utf-8")
        config_path.chmod(0o600)

        self._env: dict[str, str] = {**os.environ, "NOTMUCH_CONFIG": str(config_path)}

    def _run(self, args: list[str], *, timeout: int = 120) -> str:
        """Run a notmuch subcommand and return its stdout.

        Purpose:
            Central subprocess wrapper that injects the reader config env, captures
            output, enforces a timeout, and converts failures into :class:`NotmuchError`.

        Args:
            args: The notmuch arguments (e.g. ``["count", 'from:"Alice"']``); the
                binary itself is prepended here.
            timeout: Per-invocation wall-clock limit in seconds.

        Returns:
            The command's stdout as a string. Decoded as UTF-8; on a decode error it falls
            back to latin-1 (lossless — it maps all 256 bytes), because this notmuch build
            emits raw message bodies into ``show --format=json`` and some carry non-UTF-8 bytes.

        Raises:
            NotmuchError: On non-zero exit (message includes the exit code and stderr
                tail) or on timeout (code ``"timeout"``).
        """
        op = args[0] if args else "notmuch"
        try:
            proc = subprocess.run(
                [self._bin] + args,
                capture_output=True,
                env=self._env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise NotmuchError(op, "timeout", "") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or b"").decode("utf-8", "replace").strip()[-500:]
            raise NotmuchError(op, proc.returncode, tail)
        out = proc.stdout or b""
        try:
            return out.decode("utf-8")
        except UnicodeDecodeError:
            return out.decode("latin-1")  # lossless fallback: latin-1 maps all 256 bytes

    def count(self, query: str = "") -> int:
        """Return the number of messages matching ``query`` (all if empty).

        Purpose:
            Run ``notmuch count [query]`` and parse the integer result. An empty
            query counts every message in the index.

        Args:
            query: A notmuch query string (e.g. from :func:`q_from`); default ``""``
                for the total message count.

        Returns:
            The integer count (first whitespace-separated token of stdout).

        Raises:
            NotmuchError: If the notmuch invocation fails.

        Example:
            >>> reader.count(q_from("Alice"))  # doctest: +SKIP
            2
        """
        args = ["count"] if not query else ["count", query]
        stdout = self._run(args)
        tokens = stdout.split()
        if not tokens:
            raise NotmuchError("count", "parse", f"no integer in output: {stdout!r}")
        return int(tokens[0])

    def search(self, query: str, limit: int = 25) -> list[dict]:
        """Return at most ``limit`` thread rows for ``query``, normalised.

        Purpose:
            Run ``notmuch search --format=json <query>`` and convert each thread
            object into a flat row with an extracted ``message_ids`` list.

        Rationale:
            ``limit`` bounds the number of *threads* returned, not messages — callers
            (e.g. the mail-keeper CLI) page on their own. Message-ids are recovered by
            whitespace-splitting ``query[0]`` (safe: ids contain no spaces).

        Args:
            query: A non-empty notmuch query string.
            limit: Maximum number of thread rows to return (default 25).

        Returns:
            A list of at most ``limit`` dicts, each with keys
            ``{thread, subject, authors, timestamp, tags, matched, total,
            message_ids}`` in the order notmuch returned them.

        Raises:
            NotmuchError: If the notmuch invocation fails or its output is not valid
                JSON.

        Example:
            >>> rows = reader.search(q_from("Alice"))  # doctest: +SKIP
            >>> [r["message_ids"] for r in rows]  # doctest: +SKIP
            [['m1@example.com'], ['m3@example.com']]
        """
        stdout = self._run(["search", "--format=json", query])
        try:
            threads = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise NotmuchError("search", "parse", f"invalid JSON from notmuch: {exc}") from exc
        if not isinstance(threads, list):
            raise NotmuchError("search", "parse", "expected a JSON array of thread objects")

        rows: list[dict] = []
        for thread in threads[:limit]:
            query_field = thread.get("query")
            if isinstance(query_field, list) and query_field:
                matched_clause = query_field[0]
            else:
                matched_clause = None
            rows.append(
                {
                    "thread": thread.get("thread"),
                    "subject": thread.get("subject"),
                    "authors": thread.get("authors"),
                    "timestamp": thread.get("timestamp"),
                    "tags": thread.get("tags"),
                    "matched": thread.get("matched"),
                    "total": thread.get("total"),
                    "message_ids": _extract_message_ids(matched_clause),
                }
            )
        return rows

    def message_ids(self, query: str) -> list[str]:
        """Return all matched message ids for ``query``, deduplicated.

        Purpose:
            Gather every message id across all matching threads (same extraction as
            :meth:`search`), removing duplicates while preserving first-seen order.

        Args:
            query: A non-empty notmuch query string.

        Returns:
            A list of unique message-id strings in first-seen order.

        Raises:
            NotmuchError: If the underlying search fails.

        Example:
            >>> reader.message_ids("alice")  # doctest: +SKIP
            ['m1@example.com', 'm3@example.com']
        """
        rows = self.search(query, limit=10**9)
        seen: dict[str, None] = {}
        for row in rows:
            for msg_id in row["message_ids"]:
                seen.setdefault(msg_id, None)
        return list(seen)

    def show(self, message_id: str) -> dict:
        """Return the primary message, its thread context, and the raw document.

        Purpose:
            Run ``notmuch show --format=json 'id:<msgid>'`` and split the nested
            recursive result into the primary message (first in document order), the
            remaining thread-context messages, and the full parsed document.

        Args:
            message_id: The Message-Id to show.

        Returns:
            A dict ``{"primary": <message object>, "context": [<message objects>],
            "raw": <full parsed doc>}``.

        Raises:
            NotmuchError: If the notmuch invocation fails, its output is invalid
                JSON, or no message object is found (no such message).

        Example:
            >>> doc = reader.show("m1@example.com")  # doctest: +SKIP
            >>> doc["primary"]["id"]  # doctest: +SKIP
            'm1@example.com'
        """
        stdout = self._run(["show", "--format=json", f"id:{message_id}"])
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise NotmuchError("show", "parse", f"invalid JSON from notmuch: {exc}") from exc

        messages = _collect_message_objects(raw)
        if not messages:
            raise NotmuchError("show", "not-found", f"no message found for id:{message_id}")
        primary, context = messages[0], messages[1:]
        return {"primary": primary, "context": context, "raw": raw}

    def body_text(self, message_id: str) -> tuple[str | None, Path | None]:
        """Return the plain-text body of a message, or a pointer to its raw file.

        Purpose:
            Walk the primary message's body parts (recursively, so multipart
            containers are descended into) and concatenate any ``text/plain``
            ``content``. If no plain text exists but an HTML part is present, return
            the raw maildir file path instead so the caller can MIME-parse it — this
            build stores only ``content-length`` for HTML parts, never the body.

        Args:
            message_id: The Message-Id whose body to extract.

        Returns:
            ``(plain_text, None)`` when plain text was found (UTF-8, errors replaced);
            ``(None, raw_file_path)`` when only an HTML part exists (the raw maildir
            file at ``filename[0]`` for caller-side MIME parsing); ``(None, None)``
            when neither plain text nor an HTML part is present.

        Raises:
            NotmuchError: If the underlying show fails or the message has no
                ``filename`` to fall back to.

        Example:
            >>> text, path = reader.body_text("m1@example.com")  # doctest: +SKIP
            >>> "Hello" in (text or "") and path is None  # doctest: +SKIP
            True
        """
        doc = self.show(message_id)
        primary = doc["primary"]
        leaves = _iter_body_parts(primary.get("body"))

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
            filename = primary.get("filename")
            if not (isinstance(filename, list) and filename):
                raise NotmuchError(
                    "body_text",
                    "no-filename",
                    f"HTML message {message_id} has no filename to fall back to",
                )
            return None, Path(filename[0])

        return None, None
