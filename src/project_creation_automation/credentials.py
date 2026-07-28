"""Explicit, redacted GitHub credential loading."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from project_creation_automation.domain import CredentialError

CANONICAL_TOKEN_NAME = "GITHUB_TOKEN"
LEGACY_TOKEN_NAME = "gt"
_MAX_ENV_FILE_BYTES = 65_536
_REPARSE_POINT = 0x400


class SecretToken:
    """A best-effort mutable token container with permanently redacted repr.

    Python and the HTTP standard library necessarily create short-lived immutable
    strings while constructing a request. The owned byte buffer is cleared
    deterministically; Python cannot guarantee erasure of every interpreter copy.
    """

    __slots__ = ("_buffer", "_source_name")

    def __init__(self, buffer: bytearray, source_name: str) -> None:
        self._buffer = buffer
        self._source_name = source_name

    @classmethod
    def from_text(cls, value: str, source_name: str) -> SecretToken:
        if (
            not value
            or len(value) > 1024
            or value != value.strip()
            or any(not 33 <= ord(character) <= 126 for character in value)
        ):
            raise CredentialError("github_token_invalid")
        try:
            encoded = value.encode("utf-8", errors="strict")
        except UnicodeError:
            raise CredentialError("github_token_invalid") from None
        return cls(bytearray(encoded), source_name)

    @property
    def source_name(self) -> str:
        return self._source_name

    @contextmanager
    def reveal(self) -> Iterator[str]:
        """Yield a temporary request value; never use it in logs or process calls."""

        if not self._buffer:
            raise CredentialError("github_token_unavailable")
        value = self._buffer.decode("utf-8", errors="strict")
        try:
            yield value
        finally:
            value = ""

    def clear(self) -> None:
        for index in range(len(self._buffer)):
            self._buffer[index] = 0
        self._buffer.clear()

    @property
    def is_cleared(self) -> bool:
        return not self._buffer

    def __repr__(self) -> str:
        return "SecretToken(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


class EnvironmentCredentialProvider:
    """Load only an explicitly recognized token from process state or a file."""

    __slots__ = ("_environ", "max_file_bytes")

    def __init__(
        self,
        environ: Mapping[str, str] | None = None,
        max_file_bytes: int = _MAX_ENV_FILE_BYTES,
    ) -> None:
        self._environ = environ
        self.max_file_bytes = max_file_bytes

    def load(self, env_file: str | None = None) -> SecretToken:
        environment = self._environ if self._environ is not None else os.environ
        canonical = environment.get(CANONICAL_TOKEN_NAME)
        if canonical is not None:
            return SecretToken.from_text(canonical, CANONICAL_TOKEN_NAME)
        legacy = environment.get(LEGACY_TOKEN_NAME)
        if legacy is not None:
            return SecretToken.from_text(legacy, LEGACY_TOKEN_NAME)
        if env_file is None:
            raise CredentialError("github_token_unavailable")
        return self._load_file(Path(env_file))

    def __repr__(self) -> str:
        return "EnvironmentCredentialProvider(<redacted>)"

    def _load_file(self, path: Path) -> SecretToken:
        absolute_path = Path(os.path.abspath(path))
        self._validate_parent_chain(absolute_path)
        try:
            metadata = absolute_path.lstat()
        except OSError:
            raise CredentialError("github_env_file_unavailable") from None
        attributes = getattr(metadata, "st_file_attributes", 0)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or attributes & _REPARSE_POINT
            or metadata.st_size > self.max_file_bytes
        ):
            raise CredentialError("github_env_file_unsafe")
        try:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(absolute_path, flags)
        except OSError:
            raise CredentialError("github_env_file_unavailable") from None
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or getattr(opened, "st_file_attributes", 0) & _REPARSE_POINT
                or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
            ):
                raise CredentialError("github_env_file_unsafe")
            raw = os.read(descriptor, self.max_file_bytes + 1)
        except OSError:
            raise CredentialError("github_env_file_unavailable") from None
        finally:
            os.close(descriptor)
        if len(raw) > self.max_file_bytes:
            raise CredentialError("github_env_file_unsafe")
        try:
            content = raw.decode("utf-8", errors="strict")
        except UnicodeError:
            raise CredentialError("github_env_file_encoding") from None
        return self._parse(content)

    @staticmethod
    def _validate_parent_chain(path: Path) -> None:
        for parent in path.parents:
            try:
                metadata = parent.lstat()
            except OSError:
                raise CredentialError("github_env_file_unavailable") from None
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
            ):
                raise CredentialError("github_env_file_unsafe")

    @staticmethod
    def _parse(content: str) -> SecretToken:
        candidates: list[tuple[str, str]] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise CredentialError("github_env_file_malformed")
            key, value = line.split("=", maxsplit=1)
            key = key.strip()
            if not key or key != raw_line.lstrip().split("=", maxsplit=1)[0].strip():
                raise CredentialError("github_env_file_malformed")
            if key in {CANONICAL_TOKEN_NAME, LEGACY_TOKEN_NAME}:
                candidates.append((key, value))
        if not candidates:
            raise CredentialError("github_token_unavailable")
        if len(candidates) != 1:
            raise CredentialError("github_token_duplicate")
        key, value = candidates[0]
        return SecretToken.from_text(value, key)
