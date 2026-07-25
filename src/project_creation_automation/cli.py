"""Planning-only command-line interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from project_creation_automation.domain import (
    DomainError,
    ExecutionUnavailableError,
    IDEChoice,
    PathFlavor,
    ProjectRequest,
    Visibility,
)
from project_creation_automation.planning import build_creation_plan

EXIT_INVALID_REQUEST = 2
EXIT_EXECUTION_UNAVAILABLE = 3


def build_parser() -> argparse.ArgumentParser:
    """Build the parser without reading configuration or external state."""

    parser = argparse.ArgumentParser(
        prog="project-create",
        description="Validate and plan project creation without performing mutations.",
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
        help="reserved for a future execution adapter",
        description="Execution is intentionally unavailable in Stage 2.",
    )
    _add_request_arguments(create_parser)
    create_parser.add_argument(
        "--confirm",
        action="store_true",
        help="record explicit intent; Stage 2 still performs no mutation",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run validation/planning and return an exit status."""

    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        request = ProjectRequest.create(
            project_name=arguments.project_name,
            project_root=arguments.project_root,
            visibility=Visibility(arguments.visibility),
            ide=IDEChoice(arguments.ide),
            create_github_repository=arguments.github,
            path_flavor=PathFlavor(arguments.path_flavor),
        )
        if arguments.command == "create":
            raise ExecutionUnavailableError("execution_unavailable")
        plan = build_creation_plan(request)
    except DomainError as error:
        errors.write(f"{error.code}: {error.message}\n")
        if isinstance(error, ExecutionUnavailableError):
            return EXIT_EXECUTION_UNAVAILABLE
        return EXIT_INVALID_REQUEST

    output.write(plan.render())
    output.write("\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console entry point."""

    return run(argv)


def _add_request_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project_name", help="safe project label")
    parser.add_argument(
        "--project-root",
        required=True,
        help="absolute approved project root (redacted from plan output)",
    )
    parser.add_argument(
        "--visibility",
        choices=[choice.value for choice in Visibility],
        default=Visibility.PRIVATE.value,
        help="future remote visibility (default: private)",
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
        help="include optional GitHub steps in the dry-run plan",
    )
    parser.add_argument(
        "--path-flavor",
        choices=[choice.value for choice in PathFlavor],
        default=PathFlavor.native().value,
        help=argparse.SUPPRESS,
    )
