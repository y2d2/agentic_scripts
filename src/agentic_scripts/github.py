"""Thin, stdlib-only GitHub REST client for workflows; owns PR plumbing (find-by-head,
create); the PAT comes from the environment, never from arguments or logs.

Purpose:
    Provide :class:`GitHubClient`, a small client exposing exactly two public
    operations — :meth:`GitHubClient.find_pr_by_head` and
    :meth:`GitHubClient.create_pr` — that the OC-todo workflow needs to check for an
    existing pull request (idempotency) and to open one. The personal access token is
    read from the ``GITHUB_PAT`` environment variable at construction time, never taken
    as a call argument and never written into logs or error bodies.

Rationale:
    The ``gh`` CLI is not installed on this machine (verified 2026-10-14), so PR
    mechanics go through the GitHub REST API with the configured PAT. Stdlib-only
    (``urllib.request``, ``urllib.error``, ``json``, ``os``) keeps the dependency
    footprint at zero — no ``requests`` and no new packages in ``pyproject.toml``. The
    module-level ``_urlopen = urllib.request.urlopen`` alias is the single test seam:
    tests patch ``agentic_scripts.github._urlopen`` with a fake, so every test runs
    with zero network access while production calls the real function unchanged.

Usage:
    >>> from agentic_scripts.github import GitHubClient, GitHubError
    >>> client = GitHubClient()  # reads GITHUB_PAT from the environment
    >>> pr = client.find_pr_by_head("owner", "name", "oc-todo/abc123def456")
    >>> if pr is None:
    ...     number, url = client.create_pr(
    ...         "owner", "name", title="OC: fix x", body="...",
    ...         head="owner:oc-todo/abc123def456", base="dev",
    ...     )
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# The single test seam for HTTP. Production uses the real function; tests monkeypatch
# ``agentic_scripts.github._urlopen`` with a fake that records calls and returns canned
# responses (or raises), so no test ever touches the network.
_urlopen = urllib.request.urlopen


class GitHubError(RuntimeError):
    """Raised when a GitHub REST call fails (HTTP error or transport error).

    Attributes:
        status: The HTTP status code, or None for transport errors (no response was
            received, e.g. connection refused) and for the no-PAT precondition failure.
        body: A bounded excerpt of the response body (or the transport reason / a
            directive naming ``GITHUB_PAT``), truncated to ~4 KB so it is safe to log or
            surface directly without re-issuing the request.

    Example:
        >>> raise GitHubError("POST /pulls", 422, '{"message": "Validation Failed"}')
        Traceback (most recent call last):
            ...
        agentic_scripts.github.GitHubError: POST /pulls: HTTP 422: {"message": "Validation Failed"}
    """

    def __init__(self, context: str, status: int | None, body: str) -> None:
        self.context = context
        self.status = status
        self.body = body
        if status is not None:
            message = f"{context}: HTTP {status}"
            if body:
                message += f": {body}"
        else:
            message = f"{context}: {body}"
        super().__init__(message)


class GitHubClient:
    """Stdlib-only client for the two GitHub REST operations the workflow needs.

    Purpose:
        Find a pull request by its head ref (idempotency check) and create one, using
        the PAT read from the ``GITHUB_PAT`` environment variable at construction time.

    Rationale:
        The class is deliberately dumb: it performs no retry, no rate-limit backoff, and
        no caching — the workflow layer decides what to do with a :class:`GitHubError`
        (e.g. skip-and-note on an API outage). Rate-limit 403/429 responses simply
        surface as ``GitHubError(status=403)`` / ``GitHubError(status=429)``. The PAT is
        read once, at construction (not per request), and appears only in the request's
        ``Authorization`` header — never in logs or error bodies.

    Note:
        Holds no mutable state; safe to share across workflows. Only two public
        operations exist (no close/merge/issue endpoints — those are out of scope).
    """

    def __init__(
        self, *, pat: str | None = None, base_url: str | None = None, timeout: int = 30
    ) -> None:
        """Create a client, reading the PAT from ``GITHUB_PAT`` when not given.

        Args:
            pat: The personal access token. When None (the default), it is read from
                ``os.environ["GITHUB_PAT"]`` (stripped). An empty/whitespace-only value
                is kept as-is and surfaces later as a :class:`GitHubError` naming
                ``GITHUB_PAT`` before any network call. Never log this value.
            base_url: The GitHub API base URL (default ``"https://api.github.com"``); a
                trailing slash, if present, is stripped so paths join with a single slash.
            timeout: Per-request wall-clock timeout in seconds (int >= 1).

        Raises:
            ValueError: If ``timeout`` is not an integer >= 1 (a programmer error — the
                value is fixed at construction and applied to every request).
        """
        self._pat = os.environ.get("GITHUB_PAT", "").strip() if pat is None else pat.strip()
        self._base_url = "https://api.github.com" if base_url is None else base_url.rstrip("/")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
            raise ValueError(f"timeout must be an integer >= 1 (got {timeout!r})")
        self._timeout = timeout

    def _request(
        self, method: str, path: str, *, payload: dict | None = None
    ) -> dict | list | None:
        """Issue one REST request and return its parsed JSON body.

        Purpose:
            Build the :class:`urllib.request.Request` (with auth + API-version headers),
            send it through the module-level ``_urlopen`` seam, and parse the response
            — returning None for an empty (204-style) body, else the decoded JSON object.

        Args:
            method: The HTTP method (e.g. ``"GET"``, ``"POST"``).
            path: The API path relative to ``base_url`` (e.g. ``/repos/o/r/pulls``); it
                must begin with a slash and carry any query string.
            payload: Optional JSON-serialisable body; when not None it is encoded as the
                request body and a ``Content-Type: application/json`` header is added.

        Returns:
            The parsed response (a dict or list), or None when the body is empty.

        Raises:
            GitHubError: If no PAT is configured (status None, message names
                ``GITHUB_PAT``) — raised before any network call; on an HTTP error
                (status set to the code, body a bounded excerpt of the response); on a
                transport error (status None, body the reason); or when a non-empty body
                is not valid JSON.
        """
        if not self._pat:
            raise GitHubError(
                f"{method} {path}",
                None,
                "no GITHUB_PAT configured; set it in the environment before running the workflow",
            )

        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Authorization": f"Bearer {self._pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agentic-scripts",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            self._base_url + path, data=data, method=method, headers=headers
        )
        try:
            with _urlopen(req, timeout=self._timeout) as resp:
                body_bytes = resp.read()
        except urllib.error.HTTPError as exc:
            excerpt = exc.read().decode("utf-8", "replace")[:4096]
            raise GitHubError(f"{method} {path}", exc.code, excerpt) from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"{method} {path}", None, str(exc.reason)) from exc

        if not body_bytes:
            return None
        try:
            return json.loads(body_bytes.decode("utf-8"))
        except json.JSONDecodeError as exc:
            excerpt = body_bytes.decode("utf-8", "replace")[:4096]
            raise GitHubError(
                f"{method} {path}", None, f"invalid JSON in response: {excerpt}"
            ) from exc

    def find_pr_by_head(self, owner: str, repo: str, head_branch: str) -> dict | None:
        """Return the pull request whose head is ``owner:head_branch``, or None.

        Purpose:
            The idempotency query for the workflow: a head ref is unique per
            owner:branch, so at most one PR matches; return it (or None when none).

        Rationale:
            Uses the documented list endpoint with ``state=all`` and a ``head=`` filter.
            ``owner``/``repo`` are validated ``owner/name`` tokens and ``head_branch`` is
            an ``oc-todo/<12 hex>`` ref, so no URL-encoding is required — the path is a
            simple f-string.

        Args:
            owner: The repository owner (a GitHub user or org name).
            repo: The repository name.
            head_branch: The head branch name (e.g. ``oc-todo/abc123def456``); sent as
                ``head={owner}:{head_branch}``.

        Returns:
            The first matching PR object, or None when no PR has that head ref.

        Raises:
            GitHubError: On any transport/HTTP failure (see :meth:`_request`).
        """
        path = f"/repos/{owner}/{repo}/pulls?state=all&head={owner}:{head_branch}"
        result = self._request("GET", path)
        if not result:
            return None
        return result[0]

    def create_pr(
        self, owner: str, repo: str, *, title: str, body: str, head: str, base: str
    ) -> tuple[int, str]:
        """Create a pull request and return ``(number, html_url)``.

        Purpose:
            Open a new PR from ``head`` into ``base`` and report its number and URL so
            the workflow can record them in state.

        Args:
            owner: The repository owner (a GitHub user or org name).
            repo: The repository name.
            title: The PR title.
            body: The PR description body.
            head: The source ref as ``owner:branch`` (e.g. ``owner:oc-todo/abc123def456``).
            base: The target branch name (e.g. ``dev``).

        Returns:
            A ``(number, html_url)`` tuple read from the 201 response.

        Raises:
            GitHubError: On any transport/HTTP failure (see :meth:`_request`), or when
                the 201 response is malformed and lacks ``number`` / ``html_url`` — a
                fault, not an expected outcome.
        """
        payload = {"title": title, "body": body, "head": head, "base": base}
        data = self._request("POST", f"/repos/{owner}/{repo}/pulls", payload=payload)
        if not isinstance(data, dict):
            raise GitHubError(
                f"POST /repos/{owner}/{repo}/pulls",
                None,
                "expected a JSON object in the 201 response",
            )
        try:
            return data["number"], data["html_url"]
        except KeyError as exc:
            raise GitHubError(
                f"POST /repos/{owner}/{repo}/pulls", None, f"malformed 201 response missing {exc!r}"
            ) from exc
