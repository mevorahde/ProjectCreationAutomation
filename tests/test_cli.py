from __future__ import annotations

import io

import pytest

from project_creation_automation.cli import (
    EXIT_EXECUTION_UNAVAILABLE,
    EXIT_INVALID_REQUEST,
    build_parser,
    run,
)


def test_top_level_help_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(["--help"])

    assert captured.value.code == 0
    assert "project-create" in capsys.readouterr().out


def test_plan_prints_redacted_deterministic_output() -> None:
    output = io.StringIO()
    errors = io.StringIO()
    sensitive_root = "/private/user/projects"

    exit_code = run(
        [
            "plan",
            "safe-project",
            "--project-root",
            sensitive_root,
            "--path-flavor",
            "posix",
            "--github",
        ],
        stdout=output,
        stderr=errors,
    )

    assert exit_code == 0
    assert errors.getvalue() == ""
    assert sensitive_root not in output.getvalue()
    assert "PROJECT CREATION PLAN (DRY RUN)" in output.getvalue()
    assert "visibility: private" in output.getvalue()
    assert "mutation_performed: no" in output.getvalue()


def test_invalid_request_is_not_reflected_in_error() -> None:
    output = io.StringIO()
    errors = io.StringIO()
    hostile_name = "unsafe&command"

    exit_code = run(
        [
            "plan",
            hostile_name,
            "--project-root",
            "/approved/projects",
            "--path-flavor",
            "posix",
        ],
        stdout=output,
        stderr=errors,
    )

    assert exit_code == EXIT_INVALID_REQUEST
    assert output.getvalue() == ""
    assert hostile_name not in errors.getvalue()
    assert "/approved/projects" not in errors.getvalue()


@pytest.mark.parametrize("confirmed", [False, True])
def test_create_mode_is_unavailable_and_never_mutates(confirmed: bool) -> None:
    output = io.StringIO()
    errors = io.StringIO()
    arguments = [
        "create",
        "safe-project",
        "--project-root",
        "/approved/projects",
        "--path-flavor",
        "posix",
    ]
    if confirmed:
        arguments.append("--confirm")

    exit_code = run(arguments, stdout=output, stderr=errors)

    assert exit_code == EXIT_EXECUTION_UNAVAILABLE
    assert output.getvalue() == ""
    assert "not implemented" in errors.getvalue()
    assert "no changes were made" in errors.getvalue()


def test_cli_exposes_no_token_argument() -> None:
    help_text = build_parser().format_help().lower()

    assert "--token" not in help_text
    assert "--password" not in help_text
