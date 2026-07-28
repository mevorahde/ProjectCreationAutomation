from __future__ import annotations

import http.client
import json
import ssl
from collections.abc import Mapping
from typing import ClassVar

import pytest

from project_creation_automation.adapters.github import (
    GitHubApiAdapter,
    GitHubHttpsTransport,
    HttpResponse,
    HttpTimeout,
    HttpTimeoutError,
    HttpTlsVerificationError,
    HttpTransportError,
)
from project_creation_automation.credentials import SecretToken
from project_creation_automation.domain import (
    GitHubAccount,
    GitHubCreationUncertainError,
    GitHubOperationError,
    Visibility,
)

_TOKEN_VALUE = "synthetic-token-never-sent"


class RecordingTransport:
    def __init__(self, responses: list[HttpResponse | BaseException]) -> None:
        self.responses = responses
        self.calls: list[
            tuple[str, str, Mapping[str, str], bytes | None, HttpTimeout]
        ] = []

    def request(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: HttpTimeout,
    ) -> HttpResponse:
        self.calls.append((method, path, headers, body, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _token() -> SecretToken:
    return SecretToken.from_text(_TOKEN_VALUE, "synthetic")


def _json_response(status: int, value: object, *, rate: str | None = None) -> HttpResponse:
    return HttpResponse(
        status,
        json.dumps(value).encode("utf-8"),
        rate_limit_remaining=rate,
    )


def test_authentication_uses_exact_headers_endpoint_and_timeout() -> None:
    transport = RecordingTransport([_json_response(200, {"login": "safe-owner"})])
    timeout = HttpTimeout(connect_seconds=3.0, read_seconds=7.0)
    adapter = GitHubApiAdapter(transport=transport, timeout=timeout)

    account = adapter.resolve_account(_token())

    method, path, headers, body, actual_timeout = transport.calls[0]
    assert account.login == "safe-owner"
    assert method == "GET"
    assert path == "/user"
    assert body is None
    assert actual_timeout == timeout
    assert headers["Authorization"] == f"Bearer {_TOKEN_VALUE}"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert _TOKEN_VALUE not in repr(headers)


@pytest.mark.parametrize(
    ("status", "rate", "code"),
    [
        (401, None, "github_authentication_failed"),
        (403, None, "github_authorization_failed"),
        (403, "0", "github_rate_limited"),
        (429, None, "github_rate_limited"),
        (404, None, "github_resource_not_found"),
        (500, None, "github_server_failed"),
        (503, None, "github_server_failed"),
    ],
)
def test_safe_http_error_translation(status: int, rate: str | None, code: str) -> None:
    transport = RecordingTransport(
        [_json_response(status, {"message": "raw-sensitive-body"}, rate=rate)]
    )

    with pytest.raises(GitHubOperationError) as captured:
        GitHubApiAdapter(transport=transport).resolve_account(_token())

    assert captured.value.code == code
    assert "raw-sensitive-body" not in str(captured.value)
    assert _TOKEN_VALUE not in repr(captured.value)


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (HttpTimeoutError(), "github_timeout"),
        (HttpTlsVerificationError(), "github_tls_verification_failed"),
        (HttpTransportError(), "github_transport_failed"),
    ],
)
def test_transport_failures_are_redacted(
    failure: BaseException,
    code: str,
) -> None:
    with pytest.raises(GitHubOperationError) as captured:
        GitHubApiAdapter(transport=RecordingTransport([failure])).resolve_account(
            _token()
        )

    assert captured.value.code == code


class _FakeSocket:
    def __init__(self) -> None:
        self.timeout: float | None = None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout


class _FakeHttpsResponse:
    status = 200

    def read(self, limit: int) -> bytes:
        assert limit == 65_537
        return b"{}"

    def getheader(self, name: str) -> None:
        assert name == "X-RateLimit-Remaining"
        return None


class _FakeHttpsConnection:
    instances: ClassVar[list[_FakeHttpsConnection]] = []

    def __init__(
        self,
        host: str,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        self.host = host
        self.connect_timeout = timeout
        self.context = context
        self.sock = _FakeSocket()
        self.request_call: tuple[str, str, bytes | None, dict[str, str]] | None = None
        self.closed = False
        self.instances.append(self)

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict[str, str],
    ) -> None:
        self.request_call = (method, path, body, headers)

    def getresponse(self) -> _FakeHttpsResponse:
        return _FakeHttpsResponse()

    def close(self) -> None:
        self.closed = True


def test_transport_uses_scoped_system_context_and_preserves_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeHttpsConnection.instances.clear()
    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeHttpsConnection)
    original_ssl_context = ssl.SSLContext
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    timeout = HttpTimeout(connect_seconds=2.0, read_seconds=4.0)

    response = GitHubHttpsTransport(
        context_factory=lambda: context
    ).request("GET", "/", {}, None, timeout)

    connection = _FakeHttpsConnection.instances[0]
    assert response.status == 200
    assert connection.host == "api.github.com"
    assert connection.context is context
    assert connection.connect_timeout == 2.0
    assert connection.sock.timeout == 4.0
    assert connection.request_call == ("GET", "/", None, {})
    assert connection.closed is True
    assert ssl.SSLContext is original_ssl_context


def test_certificate_failure_has_dedicated_redacted_translation() -> None:
    raw_diagnostic = "synthetic certificate detail"

    def fail_context() -> ssl.SSLContext:
        raise ssl.SSLCertVerificationError(1, raw_diagnostic)

    with pytest.raises(HttpTlsVerificationError) as captured:
        GitHubHttpsTransport(context_factory=fail_context).request(
            "GET",
            "/",
            {},
            None,
            HttpTimeout(),
        )

    assert raw_diagnostic not in repr(captured.value)
    assert raw_diagnostic not in str(captured.value)


def test_default_transport_context_is_native_scoped_and_does_not_patch_ssl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeHttpsConnection.instances.clear()
    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeHttpsConnection)
    original_ssl_context = ssl.SSLContext

    GitHubHttpsTransport().request("GET", "/", {}, None, HttpTimeout())

    context = _FakeHttpsConnection.instances[0].context
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert ssl.SSLContext is original_ssl_context
    assert type(context).__module__.startswith("truststore")


def test_repository_existence_distinguishes_present_and_absent() -> None:
    account = GitHubAccount("safe-owner")
    present = GitHubApiAdapter(
        transport=RecordingTransport([_json_response(200, {"id": 1})])
    )
    absent = GitHubApiAdapter(
        transport=RecordingTransport([_json_response(404, {"message": "not found"})])
    )

    assert present.repository_exists(account, "safe-project", _token()) is True
    assert absent.repository_exists(account, "safe-project", _token()) is False


@pytest.mark.parametrize(
    ("visibility", "is_private"),
    [(Visibility.PRIVATE, True), (Visibility.PUBLIC, False)],
)
def test_create_repository_exact_post_and_validated_result(
    visibility: Visibility,
    is_private: bool,
) -> None:
    response = {
        "owner": {"login": "safe-owner"},
        "name": "safe-project",
        "clone_url": "https://github.com/safe-owner/safe-project.git",
    }
    transport = RecordingTransport([_json_response(201, response)])
    adapter = GitHubApiAdapter(transport=transport)

    repository = adapter.create_repository(
        GitHubAccount("safe-owner"),
        "safe-project",
        visibility,
        _token(),
    )

    method, path, headers, body, _ = transport.calls[0]
    assert method == "POST"
    assert path == "/user/repos"
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body or b"{}") == {
        "name": "safe-project",
        "private": is_private,
        "auto_init": False,
    }
    assert repository.remote_url == "https://github.com/safe-owner/safe-project.git"
    assert _TOKEN_VALUE not in repr(repository)


@pytest.mark.parametrize("status", [409, 422])
def test_creation_conflict_is_not_retried(status: int) -> None:
    transport = RecordingTransport([_json_response(status, {"message": "conflict"})])

    with pytest.raises(GitHubOperationError) as captured:
        GitHubApiAdapter(transport=transport).create_repository(
            GitHubAccount("safe-owner"),
            "safe-project",
            Visibility.PRIVATE,
            _token(),
        )

    assert captured.value.code == "github_repository_conflict"
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        HttpResponse(200, b"not-json"),
        _json_response(200, []),
        _json_response(200, {"login": "../unsafe"}),
    ],
)
def test_malformed_authentication_response_fails_closed(response: HttpResponse) -> None:
    with pytest.raises(GitHubOperationError) as captured:
        GitHubApiAdapter(transport=RecordingTransport([response])).resolve_account(
            _token()
        )

    assert captured.value.code == "github_response_malformed"


def test_oversized_response_fails_closed() -> None:
    response = HttpResponse(200, b"x" * 65_537)

    with pytest.raises(GitHubOperationError) as captured:
        GitHubApiAdapter(transport=RecordingTransport([response])).resolve_account(
            _token()
        )

    assert captured.value.code == "github_response_malformed"


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (HttpTimeoutError(), "github_timeout"),
        (HttpTlsVerificationError(), "github_tls_verification_failed"),
    ],
)
def test_ambiguous_creation_transport_failure_is_not_retried(
    failure: BaseException,
    code: str,
) -> None:
    transport = RecordingTransport([failure])

    with pytest.raises(GitHubCreationUncertainError) as captured:
        GitHubApiAdapter(transport=transport).create_repository(
            GitHubAccount("safe-owner"),
            "safe-project",
            Visibility.PRIVATE,
            _token(),
        )

    assert captured.value.code == code
    assert len(transport.calls) == 1


def test_created_repository_identity_mismatch_fails_closed() -> None:
    response = {
        "owner": {"login": "different-owner"},
        "name": "safe-project",
        "clone_url": "https://github.com/different-owner/safe-project.git",
    }

    with pytest.raises(GitHubCreationUncertainError) as captured:
        GitHubApiAdapter(
            transport=RecordingTransport([_json_response(201, response)])
        ).create_repository(
            GitHubAccount("safe-owner"),
            "safe-project",
            Visibility.PRIVATE,
            _token(),
        )

    assert captured.value.code == "github_creation_response_malformed"


def test_transport_origin_is_fixed_and_rejects_parameterized_paths() -> None:
    transport = GitHubHttpsTransport()

    assert transport.host == "api.github.com"
    with pytest.raises(HttpTransportError):
        transport.request(
            "GET",
            "/user?unexpected=value",
            {},
            None,
            HttpTimeout(),
        )
