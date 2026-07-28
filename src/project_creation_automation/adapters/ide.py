"""Narrow, injectable, nonblocking IDE discovery and launch adapter."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from project_creation_automation.domain import IDEChoice, IDELaunchStatus

_REPARSE_POINT = 0x400
_CANDIDATES: Mapping[IDEChoice, tuple[str, ...]] = {
    IDEChoice.VSCODE: ("code",),
    IDEChoice.PYCHARM: ("pycharm", "pycharm64.exe"),
}
_SENSITIVE_ENVIRONMENT_MARKERS = (
    "token",
    "secret",
    "password",
    "credential",
    "api_key",
    "apikey",
)

ExecutableFinder = Callable[[str], str | None]
MetadataReader = Callable[[Path], os.stat_result]


class IDEProcessLauncher(Protocol):
    """Small nonblocking process boundary."""

    def start(self, executable: Path, project_directory: Path) -> None: ...


@dataclass(frozen=True, slots=True)
class SystemIDEProcessLauncher:
    """Start one validated executable without a shell and without waiting."""

    environ: Mapping[str, str] | None = field(default=None, repr=False)

    def start(self, executable: Path, project_directory: Path) -> None:
        source_environment = self.environ if self.environ is not None else os.environ
        child_environment = {
            key: value
            for key, value in source_environment.items()
            if not _is_sensitive_environment_name(key)
        }
        subprocess.Popen(
            [str(executable), str(project_directory)],
            cwd=project_directory,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            env=child_environment,
        )


@dataclass(frozen=True, slots=True)
class SafeIDEAdapter:
    """Discover only reviewed launcher names and validate before nonblocking launch."""

    finder: ExecutableFinder = field(default=shutil.which, repr=False)
    process: IDEProcessLauncher = field(default_factory=SystemIDEProcessLauncher, repr=False)
    metadata_reader: MetadataReader = field(
        default=lambda path: path.lstat(),
        repr=False,
    )

    def launch(self, project_directory: Path, ide: IDEChoice) -> IDELaunchStatus:
        candidates = _CANDIDATES.get(ide)
        if candidates is None:
            return IDELaunchStatus.UNAVAILABLE
        if self._read_safe_metadata(project_directory, directory=True) is None:
            return IDELaunchStatus.UNAVAILABLE

        for candidate in candidates:
            discovered = self.finder(candidate)
            if discovered is None:
                continue
            executable = Path(os.path.abspath(discovered))
            first = self._read_safe_metadata(executable, directory=False)
            if first is None:
                continue
            second = self._read_safe_metadata(executable, directory=False)
            if second is None or _identity(first) != _identity(second):
                continue
            try:
                self.process.start(executable, project_directory)
            except (OSError, ValueError):
                return IDELaunchStatus.FAILED
            return IDELaunchStatus.LAUNCHED
        return IDELaunchStatus.UNAVAILABLE

    def _read_safe_metadata(
        self,
        path: Path,
        *,
        directory: bool,
    ) -> os.stat_result | None:
        try:
            metadata = self.metadata_reader(path)
        except OSError:
            return None
        expected_type = stat.S_ISDIR if directory else stat.S_ISREG
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not expected_type(metadata.st_mode)
            or getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
        ):
            return None
        return metadata


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _is_sensitive_environment_name(name: str) -> bool:
    normalized = name.casefold()
    return normalized == "gt" or any(
        marker in normalized for marker in _SENSITIVE_ENVIRONMENT_MARKERS
    )
