"""Bounded GitHub REST API adapter with redacted failure translation."""

from __future__ import annotations

import http.client
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from project_creation_automation.credentials import SecretToken
from project_creation_automation.domain import (
    DomainError,
    GitHubAccount,
    GitHubCreationUncertainError,
    GitHubOperationError,
    GitHubRepository,
    Visibility,
    validate_project_name,
)

_API_HOST = "api.github.com"
_API_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"
_USER_AGENT = "project-creation-automation"
_BODY_LIMIT = 65_536
_LOGIN_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


@dataclass(frozen=True, slots=True)
class HttpTimeout:
    connect_seconds: float = 5.0
    read_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not (0 < self.connect_seconds <= 30 and 0 < self.read_seconds <= 30):
            raise ValueError("HTTP timeouts must be positive and bounded.")


class RedactedHeaders(Mapping[str, str]):
    """Headers mapping whose representation cannot reveal authorization data."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)

    def __getitem__(self, key: str) -> str:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return "RedactedHeaders(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class HttpResponse:
    status: int
    body: bytes = field(repr=False)
    rate_limit_remaining: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return f"HttpResponse(status={self.status}, body=<redacted>)"


class HttpTransportError(Exception):
    """Internal transport boundary error with no diagnostic payload."""


class HttpTimeoutError(HttpTransportError):
    """Internal timeout boundary error."""


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: HttpTimeout,
    ) -> HttpResponse: ...


@dataclass(frozen=True, slots=True)
class GitHubHttpsTransport:
    """HTTPS-only fixed-origin standard-library transport."""

    host: str = field(default=_API_HOST, init=False)
    body_limit: int = _BODY_LIMIT

    def request(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: HttpTimeout,
    ) -> HttpResponse:
        if self.host != _API_HOST or not path.startswith("/") or "?" in path or "#" in path:
            raise HttpTransportError
        connection = http.client.HTTPSConnection(self.host, timeout=timeout.connect_seconds)
        try:
            connection.request(method, path, body=body, headers=dict(headers))
            response = connection.getresponse()
            if connection.sock is not None:
                connection.sock.settimeout(timeout.read_seconds)
            payload = response.read(self.body_limit + 1)
            if len(payload) > self.body_limit:
                raise HttpTransportError
            return HttpResponse(
                status=response.status,
                body=payload,
                rate_limit_remaining=response.getheader("X-RateLimit-Remaining"),
            )
        except TimeoutError:
            raise HttpTimeoutError from None
        except (OSError, ValueError, UnicodeError, http.client.HTTPException):
            raise HttpTransportError from None
        finally:
            connection.close()


@dataclass(frozen=True, slots=True)
class GitHubApiAdapter:
    """Perform only account resolution, existence check, and one repository POST."""

    transport: HttpTransport = GitHubHttpsTransport()
    timeout: HttpTimeout = HttpTimeout()

    def resolve_account(self, token: SecretToken) -> GitHubAccount:
        response = self._request("GET", "/user", token, None)
        self._require_status(response, {200})
        payload = self._object(response)
        login = payload.get("login")
        if not isinstance(login, str) or not _LOGIN_PATTERN.fullmatch(login):
            raise GitHubOperationError("github_response_malformed")
        return GitHubAccount(login=login)

    def repository_exists(
        self,
        account: GitHubAccount,
        project_name: str,
        token: SecretToken,
    ) -> bool:
        self._validate_repository_request(account, project_name)
        response = self._request(
            "GET",
            f"/repos/{account.login}/{project_name}",
            token,
            None,
        )
        if response.status == 404:
            return False
        self._require_status(response, {200})
        return True

    def create_repository(
        self,
        account: GitHubAccount,
        project_name: str,
        visibility: Visibility,
        token: SecretToken,
    ) -> GitHubRepository:
        self._validate_repository_request(account, project_name)
        body = json.dumps(
            {
                "name": project_name,
                "private": visibility is Visibility.PRIVATE,
                "auto_init": False,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        try:
            response = self._request("POST", "/user/repos", token, body)
            self._require_status(response, {201}, creation=True)
        except GitHubOperationError as error:
            if error.code in {
                "github_timeout",
                "github_transport_failed",
                "github_server_failed",
                "github_unexpected_response",
            }:
                raise GitHubCreationUncertainError(error.code) from None
            raise
        try:
            payload = self._object(response)
        except GitHubOperationError:
            raise GitHubCreationUncertainError("github_creation_response_malformed") from None
        owner = payload.get("owner")
        owner_login = owner.get("login") if isinstance(owner, dict) else None
        name = payload.get("name")
        clone_url = payload.get("clone_url")
        expected_url = f"https://github.com/{account.login}/{project_name}.git"
        if (
            owner_login != account.login
            or name != project_name
            or clone_url != expected_url
        ):
            raise GitHubCreationUncertainError(
                "github_creation_response_malformed"
            )
        return GitHubRepository(
            owner=account.login,
            name=project_name,
            remote_url=expected_url,
        )

    def _request(
        self,
        method: str,
        path: str,
        token: SecretToken,
        body: bytes | None,
    ) -> HttpResponse:
        with token.reveal() as value:
            headers = RedactedHeaders(
                {
                    "Accept": _API_ACCEPT,
                    "Authorization": f"Bearer {value}",
                    "X-GitHub-Api-Version": _API_VERSION,
                    "User-Agent": _USER_AGENT,
                    "Content-Type": "application/json",
                }
            )
            try:
                return self.transport.request(method, path, headers, body, self.timeout)
            except HttpTimeoutError:
                raise GitHubOperationError("github_timeout") from None
            except HttpTransportError:
                raise GitHubOperationError("github_transport_failed") from None

    @staticmethod
    def _object(response: HttpResponse) -> dict[str, object]:
        if len(response.body) > _BODY_LIMIT:
            raise GitHubOperationError("github_response_malformed")
        try:
            parsed = json.loads(response.body.decode("utf-8", errors="strict"))
        except (UnicodeError, json.JSONDecodeError):
            raise GitHubOperationError("github_response_malformed") from None
        if not isinstance(parsed, dict):
            raise GitHubOperationError("github_response_malformed")
        return parsed

    @staticmethod
    def _validate_repository_request(
        account: GitHubAccount,
        project_name: str,
    ) -> None:
        if not _LOGIN_PATTERN.fullmatch(account.login):
            raise GitHubOperationError("github_request_invalid")
        try:
            validate_project_name(project_name)
        except DomainError:
            raise GitHubOperationError("github_request_invalid") from None

    @staticmethod
    def _require_status(
        response: HttpResponse,
        expected: set[int],
        *,
        creation: bool = False,
    ) -> None:
        if response.status in expected:
            return
        if response.status == 401:
            code = "github_authentication_failed"
        elif response.status == 403 and response.rate_limit_remaining == "0":
            code = "github_rate_limited"
        elif response.status == 403:
            code = "github_authorization_failed"
        elif response.status == 429:
            code = "github_rate_limited"
        elif response.status in {409, 422} and creation:
            code = "github_repository_conflict"
        elif 500 <= response.status <= 599:
            code = "github_server_failed"
        elif response.status == 404:
            code = "github_resource_not_found"
        else:
            code = "github_unexpected_response"
        raise GitHubOperationError(code)
