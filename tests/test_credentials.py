from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from project_creation_automation.credentials import (
    CANONICAL_TOKEN_NAME,
    LEGACY_TOKEN_NAME,
    EnvironmentCredentialProvider,
    SecretToken,
)
from project_creation_automation.domain import CredentialError

_TOKEN = "synthetic-token-for-isolated-tests"


def _revealed(token: SecretToken) -> str:
    with token.reveal() as value:
        return value


def test_process_environment_canonical_name_has_precedence(tmp_path: Path) -> None:
    token_file = tmp_path / "token.env"
    token_file.write_text(f"{CANONICAL_TOKEN_NAME}=file-value\n", encoding="utf-8")
    provider = EnvironmentCredentialProvider(
        environ={CANONICAL_TOKEN_NAME: _TOKEN, LEGACY_TOKEN_NAME: "legacy-value"}
    )

    token = provider.load(str(token_file))

    assert _revealed(token) == _TOKEN
    assert token.source_name == CANONICAL_TOKEN_NAME
    assert _TOKEN not in repr(provider)


def test_deprecated_legacy_environment_alias_is_narrowly_supported() -> None:
    provider = EnvironmentCredentialProvider(environ={LEGACY_TOKEN_NAME: _TOKEN})

    token = provider.load()

    assert _revealed(token) == _TOKEN
    assert token.source_name == LEGACY_TOKEN_NAME


@pytest.mark.parametrize("value", ["", " surrounded ", "non-ascii-\u00e9", "x" * 1025])
def test_invalid_process_token_values_fail_closed(value: str) -> None:
    provider = EnvironmentCredentialProvider(environ={CANONICAL_TOKEN_NAME: value})

    with pytest.raises(CredentialError) as captured:
        provider.load()

    assert captured.value.code == "github_token_invalid"
    if value:
        assert value not in str(captured.value)


def test_explicit_file_loads_only_recognized_field(tmp_path: Path) -> None:
    token_file = tmp_path / "token.env"
    token_file.write_text(
        f"UNRELATED=value\n{CANONICAL_TOKEN_NAME}={_TOKEN}\n",
        encoding="utf-8",
    )

    token = EnvironmentCredentialProvider(environ={}).load(str(token_file))

    assert _revealed(token) == _TOKEN


def test_env_file_values_are_literal_without_interpolation(tmp_path: Path) -> None:
    token_file = tmp_path / "token.env"
    literal = "synthetic-$UNEXPANDED-value"
    token_file.write_text(f"{CANONICAL_TOKEN_NAME}={literal}\n", encoding="utf-8")

    token = EnvironmentCredentialProvider(environ={}).load(str(token_file))

    assert _revealed(token) == literal


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("malformed\n", "github_env_file_malformed"),
        (f"{CANONICAL_TOKEN_NAME}=\n", "github_token_invalid"),
        (
            f"{CANONICAL_TOKEN_NAME}=one\n{CANONICAL_TOKEN_NAME}=two\n",
            "github_token_duplicate",
        ),
        (
            f"{CANONICAL_TOKEN_NAME}=one\n{LEGACY_TOKEN_NAME}=two\n",
            "github_token_duplicate",
        ),
        ("UNRELATED=value\n", "github_token_unavailable"),
    ],
)
def test_env_file_rejections_are_redacted(
    tmp_path: Path,
    content: str,
    code: str,
) -> None:
    token_file = tmp_path / "token.env"
    token_file.write_text(content, encoding="utf-8")

    with pytest.raises(CredentialError) as captured:
        EnvironmentCredentialProvider(environ={}).load(str(token_file))

    assert captured.value.code == code
    assert str(token_file) not in str(captured.value)
    if "=" in content:
        assert content.strip() not in repr(captured.value)


def test_directory_is_rejected_as_env_file(tmp_path: Path) -> None:
    with pytest.raises(CredentialError) as captured:
        EnvironmentCredentialProvider(environ={}).load(str(tmp_path))

    assert captured.value.code == "github_env_file_unsafe"


def test_oversized_env_file_is_rejected(tmp_path: Path) -> None:
    token_file = tmp_path / "token.env"
    token_file.write_bytes(b"x" * 33)

    with pytest.raises(CredentialError) as captured:
        EnvironmentCredentialProvider(environ={}, max_file_bytes=32).load(
            str(token_file)
        )

    assert captured.value.code == "github_env_file_unsafe"


def test_unsafe_encoding_is_rejected(tmp_path: Path) -> None:
    token_file = tmp_path / "token.env"
    token_file.write_bytes(b"GITHUB_TOKEN=\xff")

    with pytest.raises(CredentialError) as captured:
        EnvironmentCredentialProvider(environ={}).load(str(token_file))

    assert captured.value.code == "github_env_file_encoding"


@pytest.mark.parametrize(
    ("mode", "attributes"),
    [(stat.S_IFLNK, 0), (stat.S_IFREG, 0x400)],
)
def test_symlink_or_reparse_file_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    mode: int,
    attributes: int,
) -> None:
    metadata = SimpleNamespace(
        st_mode=mode,
        st_file_attributes=attributes,
        st_size=10,
    )
    monkeypatch.setattr(Path, "lstat", lambda self: metadata)

    with pytest.raises(CredentialError) as captured:
        EnvironmentCredentialProvider(environ={}).load("redacted.env")

    assert captured.value.code == "github_env_file_unsafe"


def test_missing_file_and_missing_token_are_distinct_and_redacted(
    tmp_path: Path,
) -> None:
    provider = EnvironmentCredentialProvider(environ={})
    with pytest.raises(CredentialError) as missing_token:
        provider.load()
    with pytest.raises(CredentialError) as missing_file:
        provider.load(str(tmp_path / "not-present.env"))

    assert missing_token.value.code == "github_token_unavailable"
    assert missing_file.value.code == "github_env_file_unavailable"
    assert str(tmp_path) not in str(missing_file.value)


def test_provider_never_modifies_process_environment(tmp_path: Path) -> None:
    token_file = tmp_path / "token.env"
    token_file.write_text(f"{CANONICAL_TOKEN_NAME}={_TOKEN}\n", encoding="utf-8")
    before = dict(os.environ)

    EnvironmentCredentialProvider(environ={}).load(str(token_file))

    assert dict(os.environ) == before


def test_token_repr_string_and_clear_are_redacted() -> None:
    token = SecretToken.from_text(_TOKEN, CANONICAL_TOKEN_NAME)

    assert _TOKEN not in repr(token)
    assert _TOKEN not in str(token)
    token.clear()
    with pytest.raises(CredentialError):
        _revealed(token)
