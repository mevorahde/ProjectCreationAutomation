from __future__ import annotations

import pytest

from project_creation_automation.domain import PathFlavor, ProjectRequest, Visibility
from project_creation_automation.execution import (
    ExecutionStatus,
    LocalCreationOrchestrator,
    OperationStep,
)
from project_creation_automation.fakes import (
    FakeConfirmation,
    FakeCredentialProvider,
    FakeLocalFilesystem,
    FakeLocalGit,
    FakeOperationalReporter,
    FakeSecureGitHub,
)
from project_creation_automation.planning import build_creation_plan


def _request(visibility: Visibility = Visibility.PRIVATE) -> ProjectRequest:
    return ProjectRequest.create(
        project_name="safe-project",
        project_root="/approved/projects",
        create_github_repository=True,
        visibility=visibility,
        path_flavor=PathFlavor.POSIX,
    )


def _orchestrator(
    *,
    filesystem: FakeLocalFilesystem | None = None,
    git: FakeLocalGit | None = None,
    credential: FakeCredentialProvider | None = None,
    github: FakeSecureGitHub | None = None,
    answer: bool = True,
) -> tuple[
    LocalCreationOrchestrator,
    FakeLocalFilesystem,
    FakeLocalGit,
    FakeCredentialProvider,
    FakeSecureGitHub,
]:
    fs = filesystem or FakeLocalFilesystem()
    git_adapter = git or FakeLocalGit()
    credential_provider = credential or FakeCredentialProvider()
    github_adapter = github or FakeSecureGitHub()
    return (
        LocalCreationOrchestrator(
            fs,
            git_adapter,
            FakeConfirmation(answer=answer),
            FakeOperationalReporter(),
            credential_provider,
            github_adapter,
        ),
        fs,
        git_adapter,
        credential_provider,
        github_adapter,
    )


def test_successful_remote_flow_and_journal_order() -> None:
    request = _request()
    orchestrator, filesystem, git, credential, github = _orchestrator()

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.remote_repository_created is True
    assert result.completed_steps == (
        OperationStep.FILESYSTEM_PREFLIGHT,
        OperationStep.GIT_PREFLIGHT,
        OperationStep.REMOTE_PREFLIGHT_COMPLETE,
        OperationStep.CONFIRMATION,
        OperationStep.CREATE_DIRECTORY,
        OperationStep.CREATE_STARTER_FILES,
        OperationStep.LOCAL_PROJECT_CREATED,
        OperationStep.INITIALIZE_GIT,
        OperationStep.STAGE_STARTER_FILES,
        OperationStep.VERIFY_GIT_INDEX,
        OperationStep.CREATE_INITIAL_COMMIT,
        OperationStep.LOCAL_GIT_COMMIT_CREATED,
        OperationStep.GITHUB_REPOSITORY_CREATED,
        OperationStep.ORIGIN_ADDED,
        OperationStep.MAIN_PUSHED,
    )
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
        "verify_origin_absent",
        "add_origin",
        "push_main",
    ]
    assert credential.calls == ["load_environment"]
    assert github.calls == [
        "resolve_account",
        "repository_exists",
        "create_repository",
    ]
    assert credential.issued_token is not None
    assert repr(credential.issued_token) == "SecretToken(<redacted>)"
    assert credential.issued_token.is_cleared is True


def test_local_only_mode_never_requests_credentials_or_github() -> None:
    credential = FakeCredentialProvider(fail=True)
    github = FakeSecureGitHub(fail_at="resolve_account")
    orchestrator, _, _, _, _ = _orchestrator(
        credential=credential,
        github=github,
    )
    request = ProjectRequest.create(
        project_name="safe-project",
        project_root="/approved/projects",
        path_flavor=PathFlavor.POSIX,
    )

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.SUCCEEDED
    assert credential.calls == []
    assert github.calls == []


@pytest.mark.parametrize("visibility", [Visibility.PRIVATE, Visibility.PUBLIC])
def test_visibility_is_forwarded_explicitly(visibility: Visibility) -> None:
    request = _request(visibility)
    orchestrator, _, _, _, github = _orchestrator()

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.SUCCEEDED
    assert github.visibilities == [visibility]


def test_remote_existing_at_preflight_fails_before_confirmation_or_mutation() -> None:
    github = FakeSecureGitHub(exists=True)
    orchestrator, filesystem, git, _, _ = _orchestrator(github=github)
    request = _request()

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.FAILED
    assert result.error_code == "github_repository_already_exists"
    assert filesystem.calls == ["preflight"]
    assert git.calls == ["verify_available"]
    assert github.calls == ["resolve_account", "repository_exists"]


def test_remote_race_conflict_rolls_back_only_local_creation() -> None:
    github = FakeSecureGitHub(fail_at="create_repository")
    orchestrator, filesystem, _, _, _ = _orchestrator(github=github)
    request = _request()

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.FAILED
    assert result.error_code == "github_repository_conflict"
    assert result.remote_repository_created is False
    assert filesystem.calls[-1] == "rollback"


def test_ambiguous_creation_result_preserves_local_state_for_recovery() -> None:
    github = FakeSecureGitHub(
        fail_at="create_repository",
        uncertain_failure=True,
    )
    orchestrator, filesystem, _, _, _ = _orchestrator(github=github)
    request = _request()

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.MANUAL_CLEANUP_REQUIRED
    assert result.remote_repository_created is False
    assert result.remote_state_requires_recovery is True
    assert "rollback" not in filesystem.calls


@pytest.mark.parametrize("failure", ["verify_origin_absent", "add_origin", "push_main"])
def test_failure_after_remote_creation_preserves_local_and_remote(
    failure: str,
) -> None:
    git = FakeLocalGit(fail_at=failure)
    orchestrator, filesystem, _, _, github = _orchestrator(git=git)
    request = _request()

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.MANUAL_CLEANUP_REQUIRED
    assert result.remote_repository_created is True
    assert "rollback" not in filesystem.calls
    assert github.calls[-1] == "create_repository"


def test_cancelled_remote_flow_has_no_mutation() -> None:
    orchestrator, filesystem, git, _, github = _orchestrator(answer=False)
    request = _request()

    result = orchestrator.execute(request, build_creation_plan(request))

    assert result.status is ExecutionStatus.CANCELLED
    assert filesystem.calls == ["preflight"]
    assert git.calls == ["verify_available"]
    assert github.calls == ["resolve_account", "repository_exists"]


def test_explicit_env_file_reference_is_forwarded_without_journaling_path() -> None:
    orchestrator, _, _, credential, _ = _orchestrator()
    request = _request()
    marker = "private-location.env"

    result = orchestrator.execute(
        request,
        build_creation_plan(request),
        env_file=marker,
    )

    assert credential.calls == ["load_file"]
    assert marker not in repr(result)
    assert marker not in str(result.completed_steps)
