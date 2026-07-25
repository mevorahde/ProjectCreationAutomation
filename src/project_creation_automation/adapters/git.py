"""Local-only Git process adapter with explicit argument vectors."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from project_creation_automation.domain import GitIdentityError, GitOperationError

_OUTPUT_LIMIT = 4096
_TIMEOUT_SECONDS = 20.0
_EXPECTED_STARTER_FILES = frozenset({"README.md", ".gitignore"})


class ProcessRunner(Protocol):
    """Injectable subprocess boundary."""

    def run(self, arguments: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]: ...


@dataclass(frozen=True, slots=True)
class SystemProcessRunner:
    """Run a bounded, non-shell child process."""

    timeout_seconds: float = _TIMEOUT_SECONDS

    def run(self, arguments: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
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
    def _bounded(output: str | None) -> str:
        return (output or "")[:_OUTPUT_LIMIT]
