"""Import-safe local and opt-in GitHub command-line interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from project_creation_automation.adapters.filesystem import BoundedFilesystemAdapter
from project_creation_automation.adapters.git import GitProcessAdapter
from project_creation_automation.domain import (
    DomainError,
    IDEChoice,
    PathFlavor,
    ProjectRequest,
    Visibility,
)
from project_creation_automation.execution import (
    ConsoleConfirmation,
    ExecutionStatus,
    ExplicitConfirmation,
    LocalCreationOrchestrator,
    StreamOperationalReporter,
)
from project_creation_automation.planning import build_creation_plan

EXIT_INVALID_REQUEST = 2
EXIT_CANCELLED = 4
EXIT_CREATION_FAILED = 5
EXIT_MANUAL_CLEANUP_REQUIRED = 6


def build_parser() -> argparse.ArgumentParser:
    """Build the parser without reading configuration or external state."""

    parser = argparse.ArgumentParser(
        prog="project-create",
        description="Plan or create a confirmed project; GitHub is explicit opt-in.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser(
        "plan",
        help="print a deterministic dry-run plan",
        description="Validate a request and print a redacted plan. No changes are made.",
    )
    _add_request_arguments(plan_parser)

    create_parser = subparsers.add_parser(
        "create",
        help="create one confirmed local project and Git repository",
        description=(
            "Create a local project after fail-closed preflight and confirmation. "
            "GitHub is optional; IDE execution remains unavailable."
        ),
    )
    _add_request_arguments(create_parser)
    create_parser.add_argument(
        "--confirm",
        action="store_true",
        help="explicitly confirm noninteractive local creation",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: TextIO | None = None,
    orchestrator: LocalCreationOrchestrator | None = None,
) -> int:
    """Run validation/planning and return an exit status."""

    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    input_stream = stdin or sys.stdin
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        request = ProjectRequest.create(
            project_name=arguments.project_name,
            project_root=arguments.project_root,
            visibility=(
                Visibility.PUBLIC if arguments.public else Visibility.PRIVATE
            ),
            ide=IDEChoice(arguments.ide),
            create_github_repository=arguments.github,
            path_flavor=PathFlavor(arguments.path_flavor),
        )
        if arguments.public and not arguments.github:
            raise DomainError("public_requires_github")
        if arguments.env_file is not None and not arguments.github:
            raise DomainError("env_file_requires_github")
        plan = build_creation_plan(request)
    except DomainError as error:
        errors.write(f"{error.code}: {error.message}\n")
        return EXIT_INVALID_REQUEST

    output.write(plan.render())
    output.write("\n")
    if arguments.command == "create":
        local_orchestrator = orchestrator or _compose_orchestrator(
            request=request,
            confirmed=arguments.confirm,
            input_stream=input_stream,
            output=output,
        )
        result = local_orchestrator.execute(request, plan, env_file=arguments.env_file)
        if result.remote_repository_created:
            output.write("github: repository-created\n")
        elif result.remote_state_requires_recovery:
            output.write("github: state-uncertain-manual-recovery-required\n")
        else:
            output.write("github: not-performed\n")
        output.write("ide: not-performed\n")
        if result.status is ExecutionStatus.SUCCEEDED:
            output.write(
                "result: github-project-created-and-main-pushed\n"
                if request.create_github_repository
                else "result: local-project-created\n"
            )
            return 0
        if result.status is ExecutionStatus.CANCELLED:
            output.write("result: cancelled-no-changes\n")
            return EXIT_CANCELLED
        error_code = result.error_code or "local_creation_failed"
        if error_code == "git_identity_unavailable":
            errors.write(
                "git_identity_unavailable: configure Git author identity separately; "
                "no identity setting was changed.\n"
            )
        else:
            errors.write(f"{error_code}: project creation failed safely.\n")
        if result.status is ExecutionStatus.MANUAL_CLEANUP_REQUIRED:
            if result.remote_state_requires_recovery:
                errors.write(
                    "manual_recovery_required: preserve both local and remote state; "
                    "automatic remote deletion was not attempted.\n"
                )
            else:
                errors.write(
                    "manual_cleanup_required: preserve the project directory for review.\n"
                )
            return EXIT_MANUAL_CLEANUP_REQUIRED
        return EXIT_CREATION_FAILED
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console entry point."""

    return run(argv)


def _add_request_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project_name", help="safe project label")
    parser.add_argument(
        "--project-root",
        "--root",
        dest="project_root",
        required=True,
        help="absolute approved project root (redacted from plan output)",
    )
    visibility = parser.add_mutually_exclusive_group()
    visibility.add_argument(
        "--public",
        action="store_true",
        help="explicitly create a public GitHub repository (requires --github)",
    )
    visibility.add_argument(
        "--private",
        action="store_true",
        help="explicitly retain the private GitHub default",
    )
    parser.add_argument(
        "--ide",
        choices=[choice.value for choice in IDEChoice],
        default=IDEChoice.NONE.value,
        help="optional future post-success IDE launch",
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="opt in to GitHub repository creation and push",
    )
    parser.add_argument(
        "--env-file",
        help=(
            "explicit ignored token file; read only during GitHub create execution "
            "(path is never printed)"
        ),
    )
    parser.add_argument(
        "--path-flavor",
        choices=[choice.value for choice in PathFlavor],
        default=PathFlavor.native().value,
        help=argparse.SUPPRESS,
    )


def _compose_orchestrator(
    *,
    request: ProjectRequest,
    confirmed: bool,
    input_stream: TextIO,
    output: TextIO,
) -> LocalCreationOrchestrator:
    """Construct production adapters only inside a create execution path."""

    credential_provider = None
    github = None
    if request.create_github_repository:
        from project_creation_automation.adapters.github import (
            GitHubApiAdapter,
            GitHubHttpsTransport,
        )
        from project_creation_automation.credentials import EnvironmentCredentialProvider

        credential_provider = EnvironmentCredentialProvider()
        github = GitHubApiAdapter(transport=GitHubHttpsTransport())
    return LocalCreationOrchestrator(
        filesystem=BoundedFilesystemAdapter(),
        git=GitProcessAdapter(),
        confirmation=(
            ExplicitConfirmation()
            if confirmed
            else ConsoleConfirmation(input_stream, output)
        ),
        reporter=StreamOperationalReporter(output),
        credential_provider=credential_provider,
        github=github,
    )
