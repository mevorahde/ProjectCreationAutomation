"""Deterministic in-memory fakes for isolated tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from project_creation_automation.adapters.filesystem import RollbackStatus
from project_creation_automation.credentials import SecretToken
from project_creation_automation.domain import (
    CredentialError,
    GitHubAccount,
    GitHubCreationUncertainError,
    GitHubOperationError,
    GitHubRepository,
    GitIdentityError,
    GitOperationError,
    IDEChoice,
    IDELaunchStatus,
    ProjectLocation,
    Visibility,
)
from project_creation_automation.planning import CreationPlan


@dataclass(slots=True)
class FakeFilesystem:
    existing_labels: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    def destination_exists(self, location: ProjectLocation) -> bool:
        self.calls.append("destination_exists")
        return location.destination.name in self.existing_labels

    def create_directory(self, location: ProjectLocation) -> None:
        self.calls.append("create_directory")
        self.existing_labels.add(location.destination.name)

    def create_initial_files(self, location: ProjectLocation) -> None:
        self.calls.append("create_initial_files")


@dataclass(slots=True)
class FakeGit:
    calls: list[str] = field(default_factory=list)

    def initialize(self, location: ProjectLocation) -> None:
        self.calls.append("initialize")

    def create_initial_commit(self, location: ProjectLocation) -> None:
        self.calls.append("create_initial_commit")

    def add_remote(self, location: ProjectLocation, remote_reference: str) -> None:
        self.calls.append("add_remote")

    def push(self, location: ProjectLocation) -> None:
        self.calls.append("push")


@dataclass(slots=True)
class FakeGitHub:
    existing_labels: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    def repository_exists(self, project_name: str) -> bool:
        self.calls.append("repository_exists")
        return project_name in self.existing_labels

    def create_repository(self, project_name: str, visibility: Visibility) -> str:
        self.calls.append("create_repository")
        self.existing_labels.add(project_name)
        return "<redacted-remote-reference>"


@dataclass(slots=True)
class FakeIDELauncher:
    calls: list[str] = field(default_factory=list)
    status: IDELaunchStatus = IDELaunchStatus.LAUNCHED
    raises: bool = False

    def launch(self, project_directory: Path, ide: IDEChoice) -> IDELaunchStatus:
        del project_directory
        self.calls.append(f"launch:{ide.value}")
        if self.raises:
            raise OSError
        return self.status


@dataclass(slots=True)
class FakeConfirmation:
    answer: bool = False
    calls: int = 0

    def confirm(self, plan: CreationPlan) -> bool:
        self.calls += 1
        return self.answer


@dataclass(slots=True)
class FakeOperationalReporter:
    events: list[str] = field(default_factory=list)

    def report(self, event: str) -> None:
        self.events.append(event)


@dataclass(slots=True)
class FakeLocalFilesystem:
    """Deterministic opaque local-filesystem fake."""

    calls: list[str] = field(default_factory=list)
    created_marker: object = field(default_factory=object)
    rollback_status: str = RollbackStatus.COMPLETED

    def preflight(self, location: ProjectLocation) -> None:
        self.calls.append("preflight")

    def create_project_directory(self, location: ProjectLocation) -> object:
        self.calls.append("create_project_directory")
        return self.created_marker

    def create_starter_files(
        self,
        location: ProjectLocation,
        project_name: str,
        created: object,
    ) -> object:
        self.calls.append("create_starter_files")
        return created

    def rollback(self, location: ProjectLocation, created: object) -> str:
        self.calls.append("rollback")
        return self.rollback_status


@dataclass(slots=True)
class FakeLocalGit:
    """Deterministic local-Git fake with selectable failure points."""

    calls: list[str] = field(default_factory=list)
    fail_at: str | None = None
    identity_failure: bool = False

    def verify_available(self, cwd: Path) -> None:
        self._call("verify_available")

    def initialize(self, cwd: Path) -> None:
        self._call("initialize")

    def stage_exact(self, cwd: Path, paths: tuple[str, ...]) -> None:
        self._call("stage_exact")

    def verify_staged_exact(self, cwd: Path, paths: tuple[str, ...]) -> None:
        self._call("verify_staged_exact")

    def create_initial_commit(self, cwd: Path) -> None:
        self._call("create_initial_commit")

    def verify_origin_absent(self, cwd: Path) -> None:
        self._call("verify_origin_absent")

    def add_origin(self, cwd: Path, remote_url: str) -> None:
        del remote_url
        self._call("add_origin")

    def push_main(self, cwd: Path) -> None:
        self._call("push_main")

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_at == name:
            if self.identity_failure:
                raise GitIdentityError("git_identity_unavailable")
            raise GitOperationError(f"{name}_failed")


@dataclass(slots=True)
class FakeCredentialProvider:
    """Credential fake that never depends on process state."""

    calls: list[str] = field(default_factory=list)
    fail: bool = False
    issued_token: SecretToken | None = None

    def load(self, env_file: str | None = None) -> SecretToken:
        self.calls.append("load_file" if env_file is not None else "load_environment")
        if self.fail:
            raise CredentialError("github_token_unavailable")
        token = SecretToken.from_text("synthetic-test-token", "synthetic")
        self.issued_token = token
        return token


@dataclass(slots=True)
class FakeSecureGitHub:
    """Deterministic GitHub fake with selectable remote failures."""

    calls: list[str] = field(default_factory=list)
    visibilities: list[Visibility] = field(default_factory=list)
    exists: bool = False
    fail_at: str | None = None
    uncertain_failure: bool = False

    def resolve_account(self, token: SecretToken) -> GitHubAccount:
        del token
        self._call("resolve_account")
        return GitHubAccount("test-owner")

    def repository_exists(
        self,
        account: GitHubAccount,
        project_name: str,
        token: SecretToken,
    ) -> bool:
        del account, project_name, token
        self._call("repository_exists")
        return self.exists

    def create_repository(
        self,
        account: GitHubAccount,
        project_name: str,
        visibility: Visibility,
        token: SecretToken,
    ) -> GitHubRepository:
        del token
        self._call("create_repository")
        self.visibilities.append(visibility)
        return GitHubRepository(
            owner=account.login,
            name=project_name,
            remote_url=f"https://github.com/{account.login}/{project_name}.git",
        )

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_at == name:
            if self.uncertain_failure and name == "create_repository":
                raise GitHubCreationUncertainError("github_timeout")
            code = (
                "github_repository_conflict"
                if name == "create_repository"
                else f"github_{name}_failed"
            )
            raise GitHubOperationError(code)
