from __future__ import annotations

import io

import pytest

import project_creation_automation.cli as cli_module
from project_creation_automation.cli import (
    EXIT_CANCELLED,
    EXIT_CREATION_FAILED,
    EXIT_INVALID_REQUEST,
    EXIT_MANUAL_CLEANUP_REQUIRED,
    build_parser,
    run,
)
from project_creation_automation.domain import Visibility
from project_creation_automation.execution import LocalCreationOrchestrator
from project_creation_automation.fakes import (
    FakeConfirmation,
    FakeCredentialProvider,
    FakeLocalFilesystem,
    FakeLocalGit,
    FakeOperationalReporter,
    FakeSecureGitHub,
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


def _orchestrator(
    *,
    answer: bool,
    git: FakeLocalGit | None = None,
    filesystem: FakeLocalFilesystem | None = None,
) -> LocalCreationOrchestrator:
    return LocalCreationOrchestrator(
        filesystem or FakeLocalFilesystem(),
        git or FakeLocalGit(),
        FakeConfirmation(answer=answer),
        FakeOperationalReporter(),
    )


def test_create_cancellation_returns_nonzero_without_mutation() -> None:
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

    filesystem = FakeLocalFilesystem()
    exit_code = run(
        arguments,
        stdout=output,
        stderr=errors,
        orchestrator=_orchestrator(answer=False, filesystem=filesystem),
    )

    assert exit_code == EXIT_CANCELLED
    assert "PROJECT CREATION PLAN (DRY RUN)" in output.getvalue()
    assert "result: cancelled-no-changes" in output.getvalue()
    assert "github: not-performed" in output.getvalue()
    assert "ide: not-performed" in output.getvalue()
    assert errors.getvalue() == ""
    assert filesystem.calls == ["preflight"]


def test_create_success_returns_zero() -> None:
    output = io.StringIO()
    errors = io.StringIO()

    exit_code = run(
        [
            "create",
            "safe-project",
            "--root",
            "/approved/projects",
            "--path-flavor",
            "posix",
            "--confirm",
        ],
        stdout=output,
        stderr=errors,
        orchestrator=_orchestrator(answer=True),
    )

    assert exit_code == 0
    assert "result: local-project-created" in output.getvalue()
    assert errors.getvalue() == ""


def test_create_failure_exit_codes_are_redacted() -> None:
    output = io.StringIO()
    errors = io.StringIO()
    failing_git = FakeLocalGit(fail_at="initialize")

    exit_code = run(
        [
            "create",
            "safe-project",
            "--root",
            "/approved/projects",
            "--path-flavor",
            "posix",
        ],
        stdout=output,
        stderr=errors,
        orchestrator=_orchestrator(answer=True, git=failing_git),
    )

    assert exit_code == EXIT_CREATION_FAILED
    assert "/approved/projects" not in errors.getvalue()
    assert "initialize_failed" in errors.getvalue()


def test_manual_cleanup_exit_code_is_distinct() -> None:
    output = io.StringIO()
    errors = io.StringIO()
    failing_git = FakeLocalGit(fail_at="create_initial_commit", identity_failure=True)
    filesystem = FakeLocalFilesystem(rollback_status="manual_cleanup_required")

    exit_code = run(
        [
            "create",
            "safe-project",
            "--root",
            "/approved/projects",
            "--path-flavor",
            "posix",
        ],
        stdout=output,
        stderr=errors,
        orchestrator=_orchestrator(
            answer=True,
            git=failing_git,
            filesystem=filesystem,
        ),
    )

    assert exit_code == EXIT_MANUAL_CLEANUP_REQUIRED
    assert "configure Git author identity separately" in errors.getvalue()
    assert "no identity setting was changed" in errors.getvalue()
    assert "manual_cleanup_required" in errors.getvalue()


@pytest.mark.parametrize(
    ("confirmed", "expected_exit", "expected_result"),
    [
        (False, EXIT_CANCELLED, "result: cancelled-no-changes"),
        (True, 0, "result: local-project-created"),
    ],
)
def test_default_cli_composition_requires_deliberate_confirmation(
    confirmed: bool,
    expected_exit: int,
    expected_result: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = FakeLocalFilesystem()
    git = FakeLocalGit()
    monkeypatch.setattr(cli_module, "BoundedFilesystemAdapter", lambda: filesystem)
    monkeypatch.setattr(cli_module, "GitProcessAdapter", lambda: git)
    arguments = [
        "create",
        "safe-project",
        "--root",
        "/approved/projects",
        "--path-flavor",
        "posix",
    ]
    if confirmed:
        arguments.append("--confirm")
    output = io.StringIO()

    exit_code = run(
        arguments,
        stdin=io.StringIO(""),
        stdout=output,
        stderr=io.StringIO(),
    )

    assert exit_code == expected_exit
    assert expected_result in output.getvalue()
    if confirmed:
        assert "create_project_directory" in filesystem.calls
    else:
        assert filesystem.calls == ["preflight"]


def test_cli_exposes_no_token_argument() -> None:
    help_text = build_parser().format_help().lower()

    assert "--token" not in help_text
    assert "--password" not in help_text


def _remote_orchestrator(
    *,
    github: FakeSecureGitHub | None = None,
    git: FakeLocalGit | None = None,
) -> LocalCreationOrchestrator:
    return LocalCreationOrchestrator(
        FakeLocalFilesystem(),
        git or FakeLocalGit(),
        FakeConfirmation(answer=True),
        FakeOperationalReporter(),
        FakeCredentialProvider(),
        github or FakeSecureGitHub(),
    )


def test_github_create_is_private_by_default_and_reports_success() -> None:
    output = io.StringIO()
    errors = io.StringIO()
    github = FakeSecureGitHub()

    exit_code = run(
        [
            "create",
            "safe-project",
            "--root",
            "/approved/projects",
            "--path-flavor",
            "posix",
            "--github",
            "--confirm",
        ],
        stdout=output,
        stderr=errors,
        orchestrator=_remote_orchestrator(github=github),
    )

    assert exit_code == 0
    assert github.visibilities == [Visibility.PRIVATE]
    assert "github: repository-created" in output.getvalue()
    assert "result: github-project-created-and-main-pushed" in output.getvalue()
    assert errors.getvalue() == ""


def test_public_github_create_requires_explicit_flag() -> None:
    github = FakeSecureGitHub()

    exit_code = run(
        [
            "create",
            "safe-project",
            "--root",
            "/approved/projects",
            "--path-flavor",
            "posix",
            "--github",
            "--public",
            "--confirm",
        ],
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        orchestrator=_remote_orchestrator(github=github),
    )

    assert exit_code == 0
    assert github.visibilities == [Visibility.PUBLIC]


def test_public_without_github_and_env_file_without_github_are_rejected() -> None:
    for option in ("--public", "--env-file"):
        arguments = [
            "plan",
            "safe-project",
            "--root",
            "/approved/projects",
            "--path-flavor",
            "posix",
            option,
        ]
        if option == "--env-file":
            arguments.append("not-opened.env")
        output = io.StringIO()
        errors = io.StringIO()

        exit_code = run(arguments, stdout=output, stderr=errors)

        assert exit_code == EXIT_INVALID_REQUEST
        assert output.getvalue() == ""
        assert "not-opened.env" not in errors.getvalue()


def test_conflicting_visibility_flags_are_rejected_by_parser() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as captured:
        parser.parse_args(
            [
                "plan",
                "safe-project",
                "--root",
                "/approved/projects",
                "--github",
                "--public",
                "--private",
            ]
        )

    assert captured.value.code == 2


def test_plan_with_env_file_never_composes_or_executes_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_module,
        "_compose_orchestrator",
        lambda **kwargs: pytest.fail("execution adapters were composed"),
    )
    output = io.StringIO()

    exit_code = run(
        [
            "plan",
            "safe-project",
            "--root",
            "/approved/projects",
            "--path-flavor",
            "posix",
            "--github",
            "--env-file",
            "never-opened.env",
        ],
        stdout=output,
        stderr=io.StringIO(),
    )

    assert exit_code == 0
    assert "never-opened.env" not in output.getvalue()


def test_remote_manual_recovery_output_is_redacted() -> None:
    output = io.StringIO()
    errors = io.StringIO()

    exit_code = run(
        [
            "create",
            "safe-project",
            "--root",
            "/approved/projects",
            "--path-flavor",
            "posix",
            "--github",
            "--confirm",
        ],
        stdout=output,
        stderr=errors,
        orchestrator=_remote_orchestrator(git=FakeLocalGit(fail_at="push_main")),
    )

    assert exit_code == EXIT_MANUAL_CLEANUP_REQUIRED
    assert "github: repository-created" in output.getvalue()
    assert "automatic remote deletion was not attempted" in errors.getvalue()
    assert "/approved/projects" not in errors.getvalue()
