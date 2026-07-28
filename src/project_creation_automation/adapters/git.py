"""Bounded local and remote Git process adapter with explicit argument vectors."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from project_creation_automation.credentials import CANONICAL_TOKEN_NAME, LEGACY_TOKEN_NAME
from project_creation_automation.domain import GitIdentityError, GitOperationError

_OUTPUT_LIMIT = 4096
_TIMEOUT_SECONDS = 20.0
_EXPECTED_STARTER_FILES = frozenset({"README.md", ".gitignore"})
_REMOTE_OUTPUT_LIMIT = 1024
_GITHUB_OWNER_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
)
_GITHUB_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class ProcessRunner(Protocol):
    """Injectable subprocess boundary."""

    def run(self, arguments: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]: ...


@dataclass(frozen=True, slots=True)
class SystemProcessRunner:
    """Run a bounded, non-shell child process."""

    timeout_seconds: float = _TIMEOUT_SECONDS

    def run(self, arguments: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        child_environment = dict(os.environ)
        child_environment.pop(CANONICAL_TOKEN_NAME, None)
        child_environment.pop(LEGACY_TOKEN_NAME, None)
        return subprocess.run(
            list(arguments),
            cwd=cwd,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout_seconds,
            stdin=subprocess.DEVNULL,
            env=child_environment,
        )


@dataclass(slots=True)
class GitProcessAdapter:
    """Perform only the approved local Git operations."""

    runner: ProcessRunner = SystemProcessRunner()

    def verify_available(self, cwd: Path) -> None:
        result = self._run(("git", "--version"), cwd=cwd, code="git_unavailable")
        if not self._bounded(result.stdout).lower().startswith("git version "):
            raise GitOperationError("git_version_unrecognized")

    def initialize(self, cwd: Path) -> None:
        self._run(
            ("git", "init", "--initial-branch=main", "--template="),
            cwd=cwd,
            code="git_init_failed",
        )

    def stage_exact(self, cwd: Path, paths: tuple[str, ...]) -> None:
        if frozenset(paths) != _EXPECTED_STARTER_FILES or len(paths) != 2:
            raise GitOperationError("git_stage_allowlist_invalid")
        self._run(("git", "add", "--", *paths), cwd=cwd, code="git_stage_failed")

    def verify_staged_exact(self, cwd: Path, paths: tuple[str, ...]) -> None:
        result = self._run(
            ("git", "diff", "--cached", "--name-only", "-z"),
            cwd=cwd,
            code="git_index_verification_failed",
        )
        staged = frozenset(name for name in self._bounded(result.stdout).split("\0") if name)
        if staged != frozenset(paths) or len(staged) != len(paths):
            raise GitOperationError("git_index_contains_unexpected_paths")

    def create_initial_commit(self, cwd: Path) -> None:
        arguments = (
            "git",
            "-c",
            "core.hooksPath=",
            "commit",
            "--no-gpg-sign",
            "--no-verify",
            "-m",
            "Initial commit",
        )
        self._run(
            arguments,
            cwd=cwd,
            code="git_commit_failed",
            classify_identity=True,
        )

    def verify_origin_absent(self, cwd: Path) -> None:
        result = self._run(("git", "remote"), cwd=cwd, code="git_remote_check_failed")
        remotes = {
            value.strip()
            for value in self._bounded(result.stdout, _REMOTE_OUTPUT_LIMIT).splitlines()
            if value.strip()
        }
        if "origin" in remotes:
            raise GitOperationError("git_origin_already_exists")

    def add_origin(self, cwd: Path, remote_url: str) -> None:
        if not self._is_canonical_github_url(remote_url):
            raise GitOperationError("git_remote_url_invalid")
        self._run(
            ("git", "remote", "add", "origin", remote_url),
            cwd=cwd,
            code="git_remote_add_failed",
        )

    def push_main(self, cwd: Path) -> None:
        self._run(
            ("git", "push", "--set-upstream", "origin", "main"),
            cwd=cwd,
            code="git_push_failed",
        )

    def _run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path,
        code: str,
        classify_identity: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = self.runner.run(arguments, cwd=cwd)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            raise GitOperationError(code) from None
        if result.returncode != 0:
            diagnostic = self._bounded(f"{result.stdout}\n{result.stderr}").lower()
            identity_markers = (
                "author identity unknown",
                "please tell me who you are",
                "unable to auto-detect email address",
                "empty ident name",
            )
            if classify_identity and any(marker in diagnostic for marker in identity_markers):
                raise GitIdentityError("git_identity_unavailable") from None
            raise GitOperationError(code)
        return result

    @staticmethod
    def _bounded(output: str | None, limit: int = _OUTPUT_LIMIT) -> str:
        return (output or "")[:limit]

    @staticmethod
    def _is_canonical_github_url(remote_url: str) -> bool:
        parsed = urlsplit(remote_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
        ):
            return False
        parts = parsed.path.split("/")
        return (
            len(parts) == 3
            and _GITHUB_OWNER_PATTERN.fullmatch(parts[1]) is not None
            and parts[2].endswith(".git")
            and _GITHUB_REPOSITORY_PATTERN.fullmatch(parts[2][:-4]) is not None
        )
