from __future__ import annotations

from project_creation_automation.domain import IDEChoice, PathFlavor, ProjectRequest
from project_creation_automation.planning import PlanAction, build_creation_plan


def _request(
    *,
    github: bool = False,
    ide: IDEChoice = IDEChoice.NONE,
) -> ProjectRequest:
    return ProjectRequest.create(
        project_name="safe-project",
        project_root="/private/approved/projects",
        create_github_repository=github,
        ide=ide,
        path_flavor=PathFlavor.POSIX,
    )


def test_local_only_plan_is_deterministic() -> None:
    first = build_creation_plan(_request())
    second = build_creation_plan(_request())

    assert first == second
    assert [step.action for step in first.steps] == [
        PlanAction.VALIDATE_REQUEST,
        PlanAction.VERIFY_DESTINATION_AVAILABLE,
        PlanAction.VERIFY_GIT_AVAILABLE,
        PlanAction.REQUIRE_EXPLICIT_CONFIRMATION,
        PlanAction.CREATE_LOCAL_DIRECTORY,
        PlanAction.CREATE_INITIAL_FILES,
        PlanAction.INITIALIZE_GIT,
        PlanAction.STAGE_STARTER_FILES,
        PlanAction.VERIFY_GIT_INDEX,
        PlanAction.CREATE_INITIAL_COMMIT,
    ]


def test_github_steps_are_optional_and_ordered() -> None:
    plan = build_creation_plan(_request(github=True))
    actions = [step.action for step in plan.steps]

    assert actions == [
        PlanAction.VALIDATE_REQUEST,
        PlanAction.VERIFY_DESTINATION_AVAILABLE,
        PlanAction.VERIFY_GIT_AVAILABLE,
        PlanAction.VERIFY_REMOTE_AVAILABLE,
        PlanAction.REQUIRE_EXPLICIT_CONFIRMATION,
        PlanAction.CREATE_LOCAL_DIRECTORY,
        PlanAction.CREATE_INITIAL_FILES,
        PlanAction.INITIALIZE_GIT,
        PlanAction.STAGE_STARTER_FILES,
        PlanAction.VERIFY_GIT_INDEX,
        PlanAction.CREATE_INITIAL_COMMIT,
        PlanAction.CREATE_REMOTE_REPOSITORY,
        PlanAction.ADD_REMOTE,
        PlanAction.PUSH,
    ]


def test_ide_launch_is_last_and_optional() -> None:
    without_ide = build_creation_plan(_request())
    with_ide = build_creation_plan(_request(ide=IDEChoice.VISUAL_STUDIO_CODE))

    assert PlanAction.LAUNCH_IDE not in [step.action for step in without_ide.steps]
    assert with_ide.steps[-1].action is PlanAction.LAUNCH_IDE


def test_rendered_plan_is_redacted_and_reports_no_mutation() -> None:
    plan = build_creation_plan(_request(github=True))
    rendered = plan.render()

    assert "/private/approved/projects" not in rendered
    assert "<approved-project-root>/<project>" in rendered
    assert "visibility: private" in rendered
    assert "mutation_performed: no" in rendered
    assert "github_repository: requested" in rendered
