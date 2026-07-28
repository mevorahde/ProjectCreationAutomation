from __future__ import annotations

from pathlib import Path

from project_creation_automation.domain import IDEChoice, PathFlavor, ProjectRequest, Visibility
from project_creation_automation.fakes import (
    FakeConfirmation,
    FakeFilesystem,
    FakeGit,
    FakeGitHub,
    FakeIDELauncher,
    FakeOperationalReporter,
)
from project_creation_automation.planning import build_creation_plan


def _request() -> ProjectRequest:
    return ProjectRequest.create(
        project_name="safe-project",
        project_root="/approved/projects",
        path_flavor=PathFlavor.POSIX,
    )


def test_fakes_are_deterministic_and_in_memory() -> None:
    request = _request()
    filesystem = FakeFilesystem()
    git = FakeGit()
    github = FakeGitHub()
    ide = FakeIDELauncher()
    confirmation = FakeConfirmation(answer=True)
    reporter = FakeOperationalReporter()

    assert filesystem.destination_exists(request.location) is False
    filesystem.create_directory(request.location)
    filesystem.create_initial_files(request.location)
    git.initialize(request.location)
    git.create_initial_commit(request.location)
    remote = github.create_repository(request.project_name, Visibility.PRIVATE)
    git.add_remote(request.location, remote)
    git.push(request.location)
    ide.launch(Path("/approved/projects/safe-project"), IDEChoice.VSCODE)
    assert confirmation.confirm(build_creation_plan(request)) is True
    reporter.report("completed")

    assert filesystem.calls == [
        "destination_exists",
        "create_directory",
        "create_initial_files",
    ]
    assert git.calls == ["initialize", "create_initial_commit", "add_remote", "push"]
    assert github.calls == ["create_repository"]
    assert ide.calls == ["launch:vscode"]
    assert confirmation.calls == 1
    assert reporter.events == ["completed"]
