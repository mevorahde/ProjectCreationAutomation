"""Protocols for future side-effecting adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from project_creation_automation.credentials import SecretToken
from project_creation_automation.domain import (
    GitHubAccount,
    GitHubRepository,
    IDEChoice,
    ProjectLocation,
    Visibility,
)
from project_creation_automation.planning import CreationPlan


class FilesystemPort(Protocol):
    """Filesystem checks and mutations required by a future executor."""

    def destination_exists(self, location: ProjectLocation) -> bool: ...

    def create_directory(self, location: ProjectLocation) -> None: ...

    def create_initial_files(self, location: ProjectLocation) -> None: ...


class GitPort(Protocol):
    """Git operations required by a future executor."""

    def initialize(self, location: ProjectLocation) -> None: ...

    def create_initial_commit(self, location: ProjectLocation) -> None: ...

    def add_remote(self, location: ProjectLocation, remote_reference: str) -> None: ...

    def push(self, location: ProjectLocation) -> None: ...


class GitHubPort(Protocol):
    """Remote repository checks and creation required by a future executor."""

    def repository_exists(self, project_name: str) -> bool: ...

    def create_repository(self, project_name: str, visibility: Visibility) -> str: ...


class IDELauncherPort(Protocol):
    """Optional post-success IDE launch."""

    def launch(self, location: ProjectLocation, ide: IDEChoice) -> None: ...


class ConfirmationPort(Protocol):
    """Explicit user confirmation immediately before future mutation."""

    def confirm(self, plan: CreationPlan) -> bool: ...


class OperationalReporterPort(Protocol):
    """Redacted operational event reporting."""

    def report(self, event: str) -> None: ...


class LocalFilesystemPort(Protocol):
    """Bounded local filesystem operations for Stage 3."""

    def preflight(self, location: ProjectLocation) -> None: ...

    def create_project_directory(self, location: ProjectLocation) -> Any: ...

    def create_starter_files(
        self,
        location: ProjectLocation,
        project_name: str,
        created: Any,
    ) -> Any: ...

    def rollback(self, location: ProjectLocation, created: Any) -> str: ...


class LocalGitPort(Protocol):
    """Allowlisted local and remote Git operations."""

    def verify_available(self, cwd: Path) -> None: ...

    def initialize(self, cwd: Path) -> None: ...

    def stage_exact(self, cwd: Path, paths: tuple[str, ...]) -> None: ...

    def verify_staged_exact(self, cwd: Path, paths: tuple[str, ...]) -> None: ...

    def create_initial_commit(self, cwd: Path) -> None: ...

    def verify_origin_absent(self, cwd: Path) -> None: ...

    def add_origin(self, cwd: Path, remote_url: str) -> None: ...

    def push_main(self, cwd: Path) -> None: ...


class CredentialProviderPort(Protocol):
    """Explicit GitHub credential loading boundary."""

    def load(self, env_file: str | None = None) -> SecretToken: ...


class SecureGitHubPort(Protocol):
    """Narrow GitHub account and repository boundary."""

    def resolve_account(self, token: SecretToken) -> GitHubAccount: ...

    def repository_exists(
        self,
        account: GitHubAccount,
        project_name: str,
        token: SecretToken,
    ) -> bool: ...

    def create_repository(
        self,
        account: GitHubAccount,
        project_name: str,
        visibility: Visibility,
        token: SecretToken,
    ) -> GitHubRepository: ...
