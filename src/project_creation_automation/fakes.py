"""Deterministic in-memory fakes for isolated tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from project_creation_automation.adapters.filesystem import RollbackStatus
from project_creation_automation.domain import (
    GitIdentityError,
    GitOperationError,
    IDEChoice,
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

    def launch(self, location: ProjectLocation, ide: IDEChoice) -> None:
        self.calls.append(f"launch:{ide.value}")


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

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_at == name:
            if self.identity_failure:
                raise GitIdentityError("git_identity_unavailable")
            raise GitOperationError(f"{name}_failed")
