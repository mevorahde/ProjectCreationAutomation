"""Confirmed local and opt-in GitHub creation orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TextIO

from project_creation_automation.adapters.filesystem import (
    FilesystemMutationError,
    RollbackStatus,
)
from project_creation_automation.domain import (
    DomainError,
    GitHubAccount,
    GitHubCreationUncertainError,
    GitHubOperationError,
    IDEChoice,
    ProjectRequest,
    UnsupportedExecutionError,
)
from project_creation_automation.planning import CreationPlan, build_creation_plan
from project_creation_automation.ports import (
    ConfirmationPort,
    CredentialProviderPort,
    LocalFilesystemPort,
    LocalGitPort,
    OperationalReporterPort,
    SecureGitHubPort,
)

STARTER_PATHS = ("README.md", ".gitignore")


class OperationStep(str, Enum):
    """Stable journal entries that never contain user or process values."""

    FILESYSTEM_PREFLIGHT = "filesystem_preflight"
    GIT_PREFLIGHT = "git_preflight"
    REMOTE_PREFLIGHT_COMPLETE = "remote_preflight_complete"
    CONFIRMATION = "confirmation"
    CREATE_DIRECTORY = "create_directory"
    CREATE_STARTER_FILES = "create_starter_files"
    INITIALIZE_GIT = "initialize_git"
    STAGE_STARTER_FILES = "stage_starter_files"
    VERIFY_GIT_INDEX = "verify_git_index"
    CREATE_INITIAL_COMMIT = "create_initial_commit"
    LOCAL_PROJECT_CREATED = "local_project_created"
    LOCAL_GIT_COMMIT_CREATED = "local_git_commit_created"
    GITHUB_REPOSITORY_CREATED = "github_repository_created"
    ORIGIN_ADDED = "origin_added"
    MAIN_PUSHED = "main_pushed"


class OperationEvent(str, Enum):
    """Predefined reporter values."""

    PREFLIGHT_COMPLETED = "preflight_completed"
    CONFIRMATION_ACCEPTED = "confirmation_accepted"
    OPERATION_CANCELLED = "operation_cancelled"
    DIRECTORY_CREATED = "directory_created"
    STARTER_FILES_CREATED = "starter_files_created"
    GIT_INITIALIZED = "git_initialized"
    STARTER_FILES_STAGED = "starter_files_staged"
    GIT_INDEX_VERIFIED = "git_index_verified"
    INITIAL_COMMIT_CREATED = "initial_commit_created"
    REMOTE_PREFLIGHT_COMPLETED = "remote_preflight_completed"
    GITHUB_REPOSITORY_CREATED = "github_repository_created"
    ORIGIN_ADDED = "origin_added"
    MAIN_PUSHED = "main_pushed"
    OPERATION_SUCCEEDED = "operation_succeeded"
    OPERATION_FAILED = "operation_failed"
    ROLLBACK_COMPLETED = "rollback_completed"
    MANUAL_CLEANUP_REQUIRED = "manual_cleanup_required"


class ExecutionStatus(str, Enum):
    """Stable execution outcomes for CLI mapping."""

    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"
    MANUAL_CLEANUP_REQUIRED = "manual_cleanup_required"


@dataclass(slots=True)
class OperationJournal:
    """In-memory record of completed predefined steps."""

    completed_steps: list[OperationStep] = field(default_factory=list)

    def complete(self, step: OperationStep) -> None:
        self.completed_steps.append(step)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Redacted local execution result."""

    status: ExecutionStatus
    completed_steps: tuple[OperationStep, ...]
    error_code: str | None = None
    remote_repository_created: bool = False
    remote_state_requires_recovery: bool = False


@dataclass(slots=True)
class LocalCreationOrchestrator:
    """Coordinate preflight, confirmation, bounded mutation, and rollback."""

    filesystem: LocalFilesystemPort
    git: LocalGitPort
    confirmation: ConfirmationPort
    reporter: OperationalReporterPort
    credential_provider: CredentialProviderPort | None = None
    github: SecureGitHubPort | None = None

    def execute(
        self,
        request: ProjectRequest,
        plan: CreationPlan,
        *,
        env_file: str | None = None,
    ) -> ExecutionResult:
        journal = OperationJournal()
        created: object | None = None
        token = None
        account: GitHubAccount | None = None
        remote_created = False
        try:
            if plan != build_creation_plan(request):
                raise UnsupportedExecutionError("creation_plan_mismatch")
            self._reject_unavailable_actions(request)
            root = Path(str(request.location.root))
            destination = Path(str(request.location.destination))

            self.filesystem.preflight(request.location)
            journal.complete(OperationStep.FILESYSTEM_PREFLIGHT)
            self.git.verify_available(root)
            journal.complete(OperationStep.GIT_PREFLIGHT)
            if request.create_github_repository:
                if self.credential_provider is None or self.github is None:
                    raise UnsupportedExecutionError("github_adapter_unavailable")
                token = self.credential_provider.load(env_file)
                account = self.github.resolve_account(token)
                if self.github.repository_exists(account, request.project_name, token):
                    raise GitHubOperationError("github_repository_already_exists")
                journal.complete(OperationStep.REMOTE_PREFLIGHT_COMPLETE)
                self.reporter.report(OperationEvent.REMOTE_PREFLIGHT_COMPLETED.value)
            self.reporter.report(OperationEvent.PREFLIGHT_COMPLETED.value)

            if not self.confirmation.confirm(plan):
                self.reporter.report(OperationEvent.OPERATION_CANCELLED.value)
                return self._result(ExecutionStatus.CANCELLED, journal)
            journal.complete(OperationStep.CONFIRMATION)
            self.reporter.report(OperationEvent.CONFIRMATION_ACCEPTED.value)

            created = self.filesystem.create_project_directory(request.location)
            journal.complete(OperationStep.CREATE_DIRECTORY)
            self.reporter.report(OperationEvent.DIRECTORY_CREATED.value)

            created = self.filesystem.create_starter_files(
                request.location,
                request.project_name,
                created,
            )
            journal.complete(OperationStep.CREATE_STARTER_FILES)
            journal.complete(OperationStep.LOCAL_PROJECT_CREATED)
            self.reporter.report(OperationEvent.STARTER_FILES_CREATED.value)

            self.git.initialize(destination)
            journal.complete(OperationStep.INITIALIZE_GIT)
            self.reporter.report(OperationEvent.GIT_INITIALIZED.value)

            self.git.stage_exact(destination, STARTER_PATHS)
            journal.complete(OperationStep.STAGE_STARTER_FILES)
            self.reporter.report(OperationEvent.STARTER_FILES_STAGED.value)

            self.git.verify_staged_exact(destination, STARTER_PATHS)
            journal.complete(OperationStep.VERIFY_GIT_INDEX)
            self.reporter.report(OperationEvent.GIT_INDEX_VERIFIED.value)

            self.git.create_initial_commit(destination)
            journal.complete(OperationStep.CREATE_INITIAL_COMMIT)
            journal.complete(OperationStep.LOCAL_GIT_COMMIT_CREATED)
            self.reporter.report(OperationEvent.INITIAL_COMMIT_CREATED.value)

            if request.create_github_repository:
                if token is None or account is None or self.github is None:
                    raise UnsupportedExecutionError("github_adapter_unavailable")
                repository = self.github.create_repository(
                    account,
                    request.project_name,
                    request.visibility,
                    token,
                )
                remote_created = True
                journal.complete(OperationStep.GITHUB_REPOSITORY_CREATED)
                self.reporter.report(OperationEvent.GITHUB_REPOSITORY_CREATED.value)

                self.git.verify_origin_absent(destination)
                self.git.add_origin(destination, repository.remote_url)
                journal.complete(OperationStep.ORIGIN_ADDED)
                self.reporter.report(OperationEvent.ORIGIN_ADDED.value)

                self.git.push_main(destination)
                journal.complete(OperationStep.MAIN_PUSHED)
                self.reporter.report(OperationEvent.MAIN_PUSHED.value)
            self.reporter.report(OperationEvent.OPERATION_SUCCEEDED.value)
            return self._result(
                ExecutionStatus.SUCCEEDED,
                journal,
                remote_repository_created=remote_created,
            )
        except FilesystemMutationError as error:
            created = error.created
            return self._failed(request, journal, created, error, remote_created)
        except GitHubCreationUncertainError as error:
            return self._failed(
                request,
                journal,
                created,
                error,
                remote_created=False,
                preserve_remote_state=True,
            )
        except DomainError as error:
            return self._failed(request, journal, created, error, remote_created)
        finally:
            if token is not None:
                token.clear()

    @staticmethod
    def _reject_unavailable_actions(request: ProjectRequest) -> None:
        if request.ide is not IDEChoice.NONE:
            raise UnsupportedExecutionError("ide_execution_unavailable")

    def _failed(
        self,
        request: ProjectRequest,
        journal: OperationJournal,
        created: object | None,
        error: DomainError,
        remote_created: bool,
        preserve_remote_state: bool = False,
    ) -> ExecutionResult:
        self.reporter.report(OperationEvent.OPERATION_FAILED.value)
        if remote_created or preserve_remote_state:
            self.reporter.report(OperationEvent.MANUAL_CLEANUP_REQUIRED.value)
            return self._result(
                ExecutionStatus.MANUAL_CLEANUP_REQUIRED,
                journal,
                error.code,
                remote_repository_created=remote_created,
                remote_state_requires_recovery=True,
            )
        if created is None:
            return self._result(ExecutionStatus.FAILED, journal, error.code)
        rollback = self.filesystem.rollback(request.location, created)
        if rollback == RollbackStatus.COMPLETED:
            self.reporter.report(OperationEvent.ROLLBACK_COMPLETED.value)
            return self._result(ExecutionStatus.FAILED, journal, error.code)
        self.reporter.report(OperationEvent.MANUAL_CLEANUP_REQUIRED.value)
        return self._result(
            ExecutionStatus.MANUAL_CLEANUP_REQUIRED,
            journal,
            error.code,
        )

    @staticmethod
    def _result(
        status: ExecutionStatus,
        journal: OperationJournal,
        error_code: str | None = None,
        remote_repository_created: bool = False,
        remote_state_requires_recovery: bool = False,
    ) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            completed_steps=tuple(journal.completed_steps),
            error_code=error_code,
            remote_repository_created=remote_repository_created,
            remote_state_requires_recovery=remote_state_requires_recovery,
        )


@dataclass(slots=True)
class ConsoleConfirmation:
    """Default-no interactive confirmation."""

    input_stream: TextIO
    output_stream: TextIO

    def confirm(self, plan: CreationPlan) -> bool:
        del plan
        self.output_stream.write("Proceed with the planned creation? [y/N]: ")
        self.output_stream.flush()
        answer = self.input_stream.readline().strip().casefold()
        return answer in {"y", "yes"}


@dataclass(frozen=True, slots=True)
class ExplicitConfirmation:
    """Deliberate noninteractive confirmation."""

    def confirm(self, plan: CreationPlan) -> bool:
        del plan
        return True


@dataclass(slots=True)
class StreamOperationalReporter:
    """Report only predefined redacted event names."""

    stream: TextIO

    def report(self, event: str) -> None:
        allowed = frozenset(item.value for item in OperationEvent)
        if event not in allowed:
            raise ValueError("Reporter received a non-predefined event.")
        self.stream.write(f"event: {event}\n")
