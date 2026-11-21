"""Hermetic tests for the GitHub REST client — no network.

Every test monkeypatches ``agentic_scripts.github._urlopen`` with a fake that records
each call and returns canned responses (or raises), so no test can ever reach the real
network. The PAT is always supplied via the constructor or a controlled env var, never
from the ambient environment.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

import agentic_scripts.github as gh
from agentic_scripts.github import GitHubClient, GitHubError


class FakeResponse:
    """A stand-in for ``urlopen``'s response object (a context manager with .read()).

    Args:
        status: The HTTP status code (recorded but not asserted on by the client).
        body: The raw response body bytes returned by :meth:`read`.
    """

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        """Return the canned response body."""
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


class Recorder:
    """A recording stand-in for ``_urlopen`` that serves a canned response or raises.

    Attributes:
        calls: One ``(method, url, headers, payload_bytes)`` tuple per call, in order.
            ``headers`` is lower-cased; ``payload_bytes`` is None for GET requests.
        next: The value to serve on the next call — a :class:`FakeResponse` (returned)
            or an exception instance (raised). Set by each test before invoking the client.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, bytes | None]] = []
        self.next: FakeResponse | BaseException = FakeResponse(200, b"{}")

    def __call__(self, req: object, timeout: int | None = None) -> FakeResponse:
        """Record the call and return (or raise) the canned ``next`` value."""
        method = req.get_method()  # type: ignore[attr-defined]
        url = req.full_url  # type: ignore[attr-defined]
        headers = {k.lower(): v for k, v in req.header_items()}  # type: ignore[attr-defined]
        payload = req.data  # type: ignore[attr-defined]
        self.calls.append((method, url, headers, payload))
        if isinstance(self.next, BaseException):
            raise self.next
        return self.next


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """Install a :class:`Recorder` fake for ``_urlopen``; return it.

    The real function is replaced for the test's duration (restored afterwards), so no
    test can reach the network. Tests read ``recorder.calls`` and set ``recorder.next``.
    """
    rec = Recorder()
    monkeypatch.setitem(gh.__dict__, "_urlopen", rec)
    return rec


@pytest.fixture
def client(recorder: Recorder) -> GitHubClient:
    """A client with a fixed test PAT (never relying on the ambient environment)."""
    recorder.next = FakeResponse(200, b"{}")
    return GitHubClient(pat="test-pat")


def test_create_pr_sends_exact_request(client: GitHubClient, recorder: Recorder) -> None:
    """create_pr issues exactly one POST with the exact URL, headers, and payload."""
    recorder.next = FakeResponse(
        201, b'{"number": 7, "html_url": "https://github.com/owner/name/pull/7"}'
    )

    result = client.create_pr(
        "owner",
        "name",
        title="OC: fix x",
        body="BODY",
        head="owner:oc-todo/abc123def456",
        base="dev",
    )

    assert len(recorder.calls) == 1
    method, url, headers, payload = recorder.calls[0]
    assert method == "POST"
    assert url == "https://api.github.com/repos/owner/name/pulls"
    assert headers["authorization"] == "Bearer test-pat"
    assert headers["accept"] == "application/vnd.github+json"
    assert headers["x-github-api-version"] == "2022-11-28"
    assert headers["user-agent"] == "agentic-scripts"
    assert headers["content-type"] == "application/json"
    assert json.loads(payload) == {  # type: ignore[arg-type]
        "title": "OC: fix x",
        "body": "BODY",
        "head": "owner:oc-todo/abc123def456",
        "base": "dev",
    }
    assert result == (7, "https://github.com/owner/name/pull/7")


def test_find_pr_by_head_returns_pr(client: GitHubClient, recorder: Recorder) -> None:
    """find_pr_by_head GETs the exact URL (no payload / no Content-Type) and returns the PR."""
    pr = {"number": 3, "state": "open", "title": "OC: existing"}
    recorder.next = FakeResponse(200, json.dumps([pr]).encode("utf-8"))

    result = client.find_pr_by_head("owner", "name", "oc-todo/abc123def456")

    assert len(recorder.calls) == 1
    method, url, headers, payload = recorder.calls[0]
    assert method == "GET"
    assert (
        url
        == "https://api.github.com/repos/owner/name/pulls?state=all&head=owner:oc-todo/abc123def456"
    )
    assert payload is None
    assert "content-type" not in headers
    assert result == pr


def test_find_pr_by_head_empty(client: GitHubClient, recorder: Recorder) -> None:
    """find_pr_by_head returns None when the list endpoint yields an empty array."""
    recorder.next = FakeResponse(200, b"[]")

    assert client.find_pr_by_head("owner", "name", "oc-todo/abc123def456") is None


def test_http_error_mapped(client: GitHubClient, recorder: Recorder) -> None:
    """An HTTPError is mapped to a GitHubError carrying the status and body excerpt."""
    err = urllib.error.HTTPError(
        url="https://api.github.com/repos/owner/name/pulls",
        code=422,
        msg="Validation Failed",
        hdrs=None,
        fp=io.BytesIO(b'{"message": "Validation Failed"}'),
    )
    recorder.next = err

    with pytest.raises(GitHubError) as excinfo:
        client.create_pr("owner", "name", title="t", body="b", head="owner:b", base="dev")
    assert excinfo.value.status == 422
    assert "Validation Failed" in excinfo.value.body


def test_transport_error_mapped(client: GitHubClient, recorder: Recorder) -> None:
    """A URLError is mapped to a GitHubError with status None and the reason in the message."""
    recorder.next = urllib.error.URLError("connection refused")

    with pytest.raises(GitHubError) as excinfo:
        client.find_pr_by_head("owner", "name", "oc-todo/abc123def456")
    assert excinfo.value.status is None
    assert "connection refused" in str(excinfo.value)


def test_missing_pat_no_network(monkeypatch: pytest.MonkeyPatch, recorder: Recorder) -> None:
    """With no PAT, both methods raise a GitHubError naming GITHUB_PAT and make zero calls."""
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    client = GitHubClient(pat="")

    for call in (
        lambda: client.find_pr_by_head("owner", "name", "oc-todo/abc123def456"),
        lambda: client.create_pr("owner", "name", title="t", body="b", head="owner:b", base="dev"),
    ):
        with pytest.raises(GitHubError) as excinfo:
            call()
        assert "GITHUB_PAT" in str(excinfo.value)

    assert len(recorder.calls) == 0


def test_env_pat_default(monkeypatch: pytest.MonkeyPatch, recorder: Recorder) -> None:
    """With GITHUB_PAT set and no explicit pat, the client sends Bearer env-pat."""
    monkeypatch.setenv("GITHUB_PAT", "env-pat")
    recorder.next = FakeResponse(200, b"[]")
    client = GitHubClient()

    client.find_pr_by_head("owner", "name", "oc-todo/abc123def456")

    assert recorder.calls[0][2]["authorization"] == "Bearer env-pat"


def test_base_url_trailing_slash_stripped(recorder: Recorder) -> None:
    """A base_url with a trailing slash joins paths with a single slash."""
    recorder.next = FakeResponse(200, b"[]")
    client = GitHubClient(pat="test-pat", base_url="https://gh.example.test/api/")

    client.find_pr_by_head("owner", "name", "oc-todo/abc123def456")

    url = recorder.calls[0][1]
    assert url.startswith("https://gh.example.test/api/repos/")
    assert "//api/" not in url


def test_empty_body_returns_none(client: GitHubClient, recorder: Recorder) -> None:
    """A 204-style empty response body yields None from _request."""
    recorder.next = FakeResponse(204, b"")

    assert client._request("GET", "/repos/owner/name/pulls") is None
