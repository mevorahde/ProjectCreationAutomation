from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from project_creation_automation.adapters.git import (
    GitProcessAdapter,
    SystemProcessRunner,
)
from project_creation_automation.domain import GitIdentityError, GitOperationError


class RecordingRunner:
    def __init__(
        self,
        responses: list[subprocess.CompletedProcess[str] | BaseException] | None = None,
    ) -> None:
        self.responses = responses or []
        self.calls: list[tuple[tuple[str, ...], Path]] = []

    def run(
        self,
        arguments: Sequence[str],
        *,
        cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((tuple(arguments), cwd))
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, BaseException):
                raise response
            return response
        return subprocess.CompletedProcess(list(arguments), 0, "", "")


def _completed(
    returncode: int = 0,
    *,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], returncode, stdout, stderr)


def test_exact_git_argument_lists_and_cwd() -> None:
    cwd = Path("project")
    runner = RecordingRunner(
        [
            _completed(stdout="git version 2.49.0"),
            _completed(),
            _completed(),
            _completed(stdout=".gitignore\0README.md\0"),
            _completed(),
        ]
    )
    adapter = GitProcessAdapter(runner=runner)

    adapter.verify_available(cwd)
    adapter.initialize(cwd)
    adapter.stage_exact(cwd, ("README.md", ".gitignore"))
    adapter.verify_staged_exact(cwd, ("README.md", ".gitignore"))
    adapter.create_initial_commit(cwd)

    assert runner.calls == [
        (("git", "--version"), cwd),
        (("git", "init", "--initial-branch=main", "--template="), cwd),
        (("git", "add", "--", "README.md", ".gitignore"), cwd),
        (("git", "diff", "--cached", "--name-only", "-z"), cwd),
        (
            (
                "git",
                "-c",
                "core.hooksPath=",
                "commit",
                "--no-gpg-sign",
                "--no-verify",
                "-m",
                "Initial commit",
            ),
            cwd,
        ),
    ]
    flattened = [argument for call, _ in runner.calls for argument in call]
    assert "remote" not in flattened
    assert "push" not in flattened
    assert "fetch" not in flattened
    assert "clone" not in flattened
    assert "-A" not in flattened
    assert "." not in flattened


def test_system_runner_uses_shell_false_and_bounded_process_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["arguments"] = arguments
        captured.update(kwargs)
        return _completed(stdout="git version 2.49.0")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = SystemProcessRunner(timeout_seconds=7.0)
    cwd = Path("project")

    runner.run(("git", "--version"), cwd=cwd)

    assert captured["arguments"] == ["git", "--version"]
    assert captured["cwd"] == cwd
    assert captured["shell"] is False
    assert captured["check"] is False
    assert captured["capture_output"] is True
    assert captured["timeout"] == 7.0
    assert captured["stdin"] == subprocess.DEVNULL


def test_missing_git_is_redacted() -> None:
    adapter = GitProcessAdapter(runner=RecordingRunner([FileNotFoundError("sensitive")]))

    with pytest.raises(GitOperationError) as captured:
        adapter.verify_available(Path("project"))

    assert captured.value.code == "git_unavailable"
    assert "sensitive" not in str(captured.value)
    assert "sensitive" not in repr(captured.value)


@pytest.mark.parametrize(
    ("method", "code"),
    [
        ("initialize", "git_init_failed"),
        ("stage_exact", "git_stage_failed"),
    ],
)
def test_git_command_failure_is_redacted(method: str, code: str) -> None:
    adapter = GitProcessAdapter(
        runner=RecordingRunner([_completed(1, stderr="raw sensitive diagnostic")])
    )

    with pytest.raises(GitOperationError) as captured:
        if method == "initialize":
            adapter.initialize(Path("project"))
        else:
            adapter.stage_exact(Path("project"), ("README.md", ".gitignore"))

    assert captured.value.code == code
    assert "raw sensitive diagnostic" not in str(captured.value)


def test_unexpected_staged_file_is_rejected() -> None:
    adapter = GitProcessAdapter(
        runner=RecordingRunner([_completed(stdout=".gitignore\0README.md\0secret.txt\0")])
    )

    with pytest.raises(GitOperationError) as captured:
        adapter.verify_staged_exact(Path("project"), ("README.md", ".gitignore"))

    assert captured.value.code == "git_index_contains_unexpected_paths"


def test_missing_git_identity_is_specific_and_redacted() -> None:
    adapter = GitProcessAdapter(
        runner=RecordingRunner(
            [_completed(128, stderr="Author identity unknown\nsensitive diagnostic")]
        )
    )

    with pytest.raises(GitIdentityError) as captured:
        adapter.create_initial_commit(Path("project"))

    assert captured.value.code == "git_identity_unavailable"
    assert "sensitive diagnostic" not in str(captured.value)


def test_generic_commit_failure_is_redacted() -> None:
    adapter = GitProcessAdapter(
        runner=RecordingRunner([_completed(1, stderr="raw commit diagnostic")])
    )

    with pytest.raises(GitOperationError) as captured:
        adapter.create_initial_commit(Path("project"))

    assert captured.value.code == "git_commit_failed"
    assert "raw commit diagnostic" not in str(captured.value)


def test_stage_allowlist_rejects_broad_or_extra_paths() -> None:
    adapter = GitProcessAdapter(runner=RecordingRunner())

    with pytest.raises(GitOperationError):
        adapter.stage_exact(Path("project"), (".",))
    with pytest.raises(GitOperationError):
        adapter.stage_exact(Path("project"), ("README.md", ".gitignore", "extra"))
