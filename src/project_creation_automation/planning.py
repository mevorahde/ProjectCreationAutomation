"""Deterministic, non-mutating project-creation plans."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from project_creation_automation.domain import IDEChoice, ProjectRequest


class PlanAction(str, Enum):
    """Ordered actions that a future execution use case may perform."""

    VALIDATE_REQUEST = "validate_request"
    VERIFY_DESTINATION_AVAILABLE = "verify_destination_available"
    VERIFY_REMOTE_AVAILABLE = "verify_remote_available"
    REQUIRE_EXPLICIT_CONFIRMATION = "require_explicit_confirmation"
    CREATE_LOCAL_DIRECTORY = "create_local_directory"
    INITIALIZE_GIT = "initialize_git"
    CREATE_INITIAL_FILES = "create_initial_files"
    CREATE_INITIAL_COMMIT = "create_initial_commit"
    CREATE_REMOTE_REPOSITORY = "create_remote_repository"
    ADD_REMOTE = "add_remote"
    PUSH = "push"
    LAUNCH_IDE = "launch_ide"


@dataclass(frozen=True, slots=True)
class PlanStep:
    """One deterministic future operation."""

    number: int
    action: PlanAction
    mutates: bool


@dataclass(frozen=True, slots=True)
class CreationPlan:
    """A redacted plan; building or rendering it has no external effects."""

    project_label: str
    visibility: str
    github_requested: bool
    ide: str
    steps: tuple[PlanStep, ...]

    def render(self) -> str:
        """Render deterministic output without absolute paths or credentials."""

        lines = [
            "PROJECT CREATION PLAN (DRY RUN)",
            f"project: {self.project_label}",
            "destination: <approved-project-root>/<project>",
            f"visibility: {self.visibility}",
            f"github_repository: {'requested' if self.github_requested else 'not-requested'}",
            f"ide: {self.ide}",
            "mutation_performed: no",
            "steps:",
        ]
        lines.extend(
            f"{step.number}. {step.action.value} [{'mutation' if step.mutates else 'check'}]"
            for step in self.steps
        )
        return "\n".join(lines)


def build_creation_plan(request: ProjectRequest) -> CreationPlan:
    """Return a deterministic plan without probing or changing external state."""

    actions: list[tuple[PlanAction, bool]] = [
        (PlanAction.VALIDATE_REQUEST, False),
        (PlanAction.VERIFY_DESTINATION_AVAILABLE, False),
    ]
    if request.create_github_repository:
        actions.append((PlanAction.VERIFY_REMOTE_AVAILABLE, False))
    actions.extend(
        [
            (PlanAction.REQUIRE_EXPLICIT_CONFIRMATION, False),
            (PlanAction.CREATE_LOCAL_DIRECTORY, True),
            (PlanAction.INITIALIZE_GIT, True),
            (PlanAction.CREATE_INITIAL_FILES, True),
            (PlanAction.CREATE_INITIAL_COMMIT, True),
        ]
    )
    if request.create_github_repository:
        actions.extend(
            [
                (PlanAction.CREATE_REMOTE_REPOSITORY, True),
                (PlanAction.ADD_REMOTE, True),
                (PlanAction.PUSH, True),
            ]
        )
    if request.ide is not IDEChoice.NONE:
        actions.append((PlanAction.LAUNCH_IDE, True))

    steps = tuple(
        PlanStep(number=index, action=action, mutates=mutates)
        for index, (action, mutates) in enumerate(actions, start=1)
    )
    return CreationPlan(
        project_label=request.project_name,
        visibility=request.visibility.value,
        github_requested=request.create_github_repository,
        ide=request.ide.value,
        steps=steps,
    )
