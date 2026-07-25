from __future__ import annotations

import io
from pathlib import Path

from project_creation_automation.adapters.filesystem import (
    BoundedFilesystemAdapter,
    RollbackStatus,
)
from project_creation_automation.domain import (
    GitOperationError,
    IDEChoice,
    PathFlavor,
    ProjectRequest,
)
from project_creation_automation.execution import (
    ConsoleConfirmation,
    ExecutionStatus,
    ExplicitConfirmation,
    LocalCreationOrchestrator,
    OperationEvent,
    OperationStep,
)
from project_creation_automation.fakes import (
    FakeConfirmation,
    FakeLocalFilesystem,
    FakeLocalGit,
    FakeOperationalReporter,
)
from project_creation_automation.planning import build_creation_plan


def _request(
    *,
    github: bool = False,
    ide: IDEChoice = IDEChoice.NONE,
) -> ProjectRequest:
    return ProjectRequest.create(
        project_name="safe-project",
        project_root="/approved/projects",
        create_github_repository=github,
        ide=ide,
        path_flavor=PathFlavor.POSIX,
    )


def _orchestrator(
    *,
    answer: bool = True,
    git: FakeLocalGit | None = None,
    filesystem: FakeLocalFilesystem | None = None,
) -> tuple[
    LocalCreationOrchestrator,
    FakeLocalFilesystem,
    FakeLocalGit,
    FakeConfirmation,
    FakeOperationalReporter,
]:
    fs = filesystem or FakeLocalFilesystem()
    git_fake = git or FakeLocalGit()
    confirmation = FakeConfirmation(answer=answer)
    reporter = FakeOperationalReporter()
    return (
        LocalCreationOrchestrator(fs, git_fake, confirmation, reporter),
        fs,
        git_fake,
        confirmation,
        reporter,
    )


def test_successful_orchestration_and_journal_order() -> None:
    request = _request()
    orchestrator, filesystem, git, confirmation, reporter = _orchestrator()

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.completed_steps == tuple(OperationStep)
    assert filesystem.calls == [
        "preflight",
        "create_project_directory",
        "create_starter_files",
    ]
    assert git.calls == [
        "verify_available",
        "initialize",
        "stage_exact",
        "verify_staged_exact",
        "create_initial_commit",
    ]
    assert confirmation.calls == 1
    assert reporter.events[-1] == OperationEvent.OPERATION_SUCCEEDED.value
    assert "rollback" not in filesystem.calls


def test_cancellation_occurs_before_first_mutation() -> None:
    request = _request()
    orchestrator, filesystem, git, confirmation, reporter = _orchestrator(answer=False)

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.CANCELLED
    assert result.completed_steps == (
        OperationStep.FILESYSTEM_PREFLIGHT,
        OperationStep.GIT_PREFLIGHT,
    )
    assert filesystem.calls == ["preflight"]
    assert git.calls == ["verify_available"]
    assert confirmation.calls == 1
    assert reporter.events[-1] == OperationEvent.OPERATION_CANCELLED.value


def test_git_failure_rolls_back_when_filesystem_proves_safety() -> None:
    request = _request()
    failing_git = FakeLocalGit(fail_at="initialize")
    orchestrator, filesystem, _, _, reporter = _orchestrator(git=failing_git)

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.FAILED
    assert filesystem.calls[-1] == "rollback"
    assert reporter.events[-1] == OperationEvent.ROLLBACK_COMPLETED.value


def test_git_identity_failure_can_require_manual_cleanup() -> None:
    request = _request()
    failing_git = FakeLocalGit(fail_at="create_initial_commit", identity_failure=True)
    filesystem = FakeLocalFilesystem(
        rollback_status=RollbackStatus.MANUAL_CLEANUP_REQUIRED
    )
    orchestrator, _, _, _, reporter = _orchestrator(
        git=failing_git,
        filesystem=filesystem,
    )

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.MANUAL_CLEANUP_REQUIRED
    assert result.error_code == "git_identity_unavailable"
    assert reporter.events[-1] == OperationEvent.MANUAL_CLEANUP_REQUIRED.value


def test_github_and_ide_requests_never_reach_adapters() -> None:
    for request in (
        _request(github=True),
        _request(ide=IDEChoice.VISUAL_STUDIO_CODE),
    ):
        orchestrator, filesystem, git, confirmation, reporter = _orchestrator()

        result = orchestrator.execute(request, build_creation_plan(request))

        assert result.status is ExecutionStatus.FAILED
        assert result.error_code == "non_local_execution_unavailable"
        assert filesystem.calls == []
        assert git.calls == []
        assert confirmation.calls == 0
        assert reporter.events == [OperationEvent.OPERATION_FAILED.value]


def test_reporter_and_results_never_contain_paths_or_diagnostics() -> None:
    request = _request()
    failing_git = FakeLocalGit(fail_at="stage_exact")
    orchestrator, _, _, _, reporter = _orchestrator(git=failing_git)

    result = orchestrator.execute(request, build_creation_plan(request))
    combined = "\n".join((*reporter.events, result.error_code or ""))

    assert "/approved/projects" not in combined
    assert "safe-project" not in combined
    assert all(event in {item.value for item in OperationEvent} for event in reporter.events)


def test_confirmation_defaults_no_and_accepts_explicit_yes() -> None:
    request = _request()
    plan = build_creation_plan(request)
    output = io.StringIO()

    assert ConsoleConfirmation(io.StringIO("\n"), output).confirm(plan) is False
    assert ConsoleConfirmation(io.StringIO("yes\n"), output).confirm(plan) is True
    assert ExplicitConfirmation().confirm(plan) is True
    assert "[y/N]" in output.getvalue()


def test_orchestrator_creates_real_files_only_in_pytest_temp_directory(
    tmp_path: Path,
) -> None:
    request = ProjectRequest.create(
        project_name="safe-project",
        project_root=str(tmp_path),
        path_flavor=PathFlavor.native(),
    )
    reporter = FakeOperationalReporter()
    orchestrator = LocalCreationOrchestrator(
        BoundedFilesystemAdapter(),
        FakeLocalGit(),
        FakeConfirmation(answer=True),
        reporter,
    )

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.SUCCEEDED
    destination = tmp_path / "safe-project"
    assert {entry.name for entry in destination.iterdir()} == {"README.md", ".gitignore"}


class PartialInitGit(FakeLocalGit):
    def initialize(self, cwd: Path) -> None:
        self.calls.append("initialize")
        (cwd / ".git").mkdir()
        raise GitOperationError("git_init_failed")


def test_partial_git_metadata_forces_preservation_for_manual_review(
    tmp_path: Path,
) -> None:
    request = ProjectRequest.create(
        project_name="safe-project",
        project_root=str(tmp_path),
        path_flavor=PathFlavor.native(),
    )
    orchestrator = LocalCreationOrchestrator(
        BoundedFilesystemAdapter(),
        PartialInitGit(),
        FakeConfirmation(answer=True),
        FakeOperationalReporter(),
    )

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.MANUAL_CLEANUP_REQUIRED
    assert (tmp_path / "safe-project" / ".git").is_dir()
    assert (tmp_path / "safe-project" / "README.md").is_file()
