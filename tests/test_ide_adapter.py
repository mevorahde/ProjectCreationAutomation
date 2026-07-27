from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from project_creation_automation.adapters.ide import (
    SafeIDEAdapter,
    SystemIDEProcessLauncher,
)
from project_creation_automation.domain import IDEChoice, IDELaunchStatus


@dataclass
class RecordingProcess:
    calls: list[tuple[Path, Path]] = field(default_factory=list)
    fail: bool = False

    def start(self, executable: Path, project_directory: Path) -> None:
        self.calls.append((executable, project_directory))
        if self.fail:
            raise OSError


def _executable(tmp_path: Path, name: str) -> Path:
    executable = tmp_path / name
    executable.write_text("synthetic launcher", encoding="utf-8")
    return executable


@pytest.mark.parametrize(
    ("ide", "available_name", "expected_candidates"),
    [
        (IDEChoice.VSCODE, "code", ["code"]),
        (IDEChoice.PYCHARM, "pycharm64.exe", ["pycharm", "pycharm64.exe"]),
    ],
)
def test_exact_reviewed_discovery_candidates_and_successful_nonblocking_launch(
    tmp_path: Path,
    ide: IDEChoice,
    available_name: str,
    expected_candidates: list[str],
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    executable = _executable(tmp_path, available_name)
    discovered: list[str] = []
    process = RecordingProcess()

    def finder(candidate: str) -> str | None:
        discovered.append(candidate)
        return str(executable) if candidate == available_name else None

    status = SafeIDEAdapter(finder=finder, process=process).launch(project, ide)

    assert status is IDELaunchStatus.LAUNCHED
    assert discovered == expected_candidates
    assert process.calls == [(executable, project)]


def test_missing_or_invalid_executable_is_reported_as_unavailable(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    invalid = tmp_path / "not-a-file"
    invalid.mkdir()
    process = RecordingProcess()

    missing = SafeIDEAdapter(finder=lambda candidate: None, process=process)
    invalid_adapter = SafeIDEAdapter(
        finder=lambda candidate: str(invalid),
        process=process,
    )

    assert missing.launch(project, IDEChoice.VSCODE) is IDELaunchStatus.UNAVAILABLE
    assert (
        invalid_adapter.launch(project, IDEChoice.VSCODE)
        is IDELaunchStatus.UNAVAILABLE
    )
    assert process.calls == []


def test_relative_path_result_is_normalized_before_validation_and_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    executable = _executable(tmp_path, "code")
    process = RecordingProcess()
    monkeypatch.chdir(tmp_path)

    status = SafeIDEAdapter(
        finder=lambda candidate: executable.name,
        process=process,
    ).launch(project, IDEChoice.VSCODE)

    assert status is IDELaunchStatus.LAUNCHED
    assert process.calls == [(executable, project)]


def test_replaced_executable_is_rejected_before_process_launch(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    original = _executable(tmp_path, "code")
    replacement = _executable(tmp_path, "replacement")
    process = RecordingProcess()
    executable_reads = 0

    def metadata_reader(path: Path) -> Any:
        nonlocal executable_reads
        if path == project:
            return path.lstat()
        executable_reads += 1
        return original.lstat() if executable_reads == 1 else replacement.lstat()

    adapter = SafeIDEAdapter(
        finder=lambda candidate: str(original),
        process=process,
        metadata_reader=metadata_reader,
    )

    assert adapter.launch(project, IDEChoice.VSCODE) is IDELaunchStatus.UNAVAILABLE
    assert process.calls == []


def test_reparse_executable_is_rejected_where_metadata_exposes_it(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    executable = _executable(tmp_path, "code")
    process = RecordingProcess()
    reparse_metadata = SimpleNamespace(
        st_mode=stat.S_IFREG,
        st_file_attributes=0x400,
    )

    def metadata_reader(path: Path) -> Any:
        return project.lstat() if path == project else reparse_metadata

    status = SafeIDEAdapter(
        finder=lambda candidate: str(executable),
        process=process,
        metadata_reader=metadata_reader,
    ).launch(project, IDEChoice.VSCODE)

    assert status is IDELaunchStatus.UNAVAILABLE
    assert process.calls == []


def test_process_failure_is_redacted(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    executable = _executable(tmp_path, "code")
    process = RecordingProcess(fail=True)

    status = SafeIDEAdapter(
        finder=lambda candidate: str(executable),
        process=process,
    ).launch(project, IDEChoice.VSCODE)

    assert status is IDELaunchStatus.FAILED
    assert process.calls == [(executable, project)]


def test_system_process_boundary_uses_exact_safe_arguments_and_filters_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    executable = _executable(tmp_path, "code")
    captured: dict[str, object] = {}

    def fake_popen(arguments: list[str], **kwargs: object) -> object:
        captured["arguments"] = arguments
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    launcher = SystemIDEProcessLauncher(
        environ={
            "PATH": "synthetic-path",
            "GITHUB_TOKEN": "synthetic-token",
            "gt": "synthetic-legacy-token",
            "SERVICE_PASSWORD": "synthetic-password",
        }
    )

    launcher.start(executable, project)

    assert captured["arguments"] == [str(executable), str(project)]
    assert captured["cwd"] == project
    assert captured["shell"] is False
    assert captured["stdin"] == subprocess.DEVNULL
    assert captured["stdout"] == subprocess.DEVNULL
    assert captured["stderr"] == subprocess.DEVNULL
    assert captured["close_fds"] is True
    assert captured["env"] == {"PATH": "synthetic-path"}
