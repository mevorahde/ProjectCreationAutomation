"""Bounded, exclusive local project creation."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from project_creation_automation.domain import (
    FilesystemSafetyError,
    PathFlavor,
    ProjectLocation,
)

README_NAME = "README.md"
GITIGNORE_NAME = ".gitignore"
STARTER_NAMES = (README_NAME, GITIGNORE_NAME)
_GITIGNORE_CONTENT = (
    "__pycache__/\n"
    "*.py[cod]\n"
    ".pytest_cache/\n"
    ".mypy_cache/\n"
    ".ruff_cache/\n"
    ".venv/\n"
)


class LinkInspector(Protocol):
    """Classify symlinks, junctions, and other reparse points."""

    def is_ambiguous(self, path: Path, result: os.stat_result) -> bool: ...


@dataclass(frozen=True, slots=True)
class NativeLinkInspector:
    """Native link/reparse classification using lstat metadata."""

    def is_ambiguous(self, path: Path, result: os.stat_result) -> bool:
        del path
        if stat.S_ISLNK(result.st_mode):
            return True
        attributes = getattr(result, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_flag)


@dataclass(frozen=True, slots=True)
class CreatedEntry:
    """Identity of one path created by this invocation."""

    path: Path
    kind: str
    device: int
    inode: int

    def __repr__(self) -> str:
        return f"CreatedEntry(path=<redacted>, kind={self.kind!r})"


@dataclass(frozen=True, slots=True)
class CreatedPaths:
    """Ordered identities of paths created by this invocation."""

    project_directory: Path
    entries: tuple[CreatedEntry, ...]
    directory_created: bool

    @classmethod
    def empty(cls, project_directory: Path) -> CreatedPaths:
        return cls(
            project_directory=project_directory,
            entries=(),
            directory_created=False,
        )

    def mark_directory_created(self) -> CreatedPaths:
        return CreatedPaths(
            project_directory=self.project_directory,
            entries=self.entries,
            directory_created=True,
        )

    def append(self, entry: CreatedEntry) -> CreatedPaths:
        return CreatedPaths(
            project_directory=self.project_directory,
            entries=(*self.entries, entry),
            directory_created=self.directory_created,
        )

    def __repr__(self) -> str:
        return f"CreatedPaths(project_directory=<redacted>, entries={len(self.entries)})"


class FilesystemMutationError(FilesystemSafetyError):
    """A mutation failed and carries only internal rollback identities."""

    def __init__(self, code: str, created: CreatedPaths) -> None:
        self.created = created
        super().__init__(code)


class RollbackStatus:
    """Stable rollback result names used by orchestration."""

    COMPLETED = "rollback_completed"
    NOT_NEEDED = "rollback_not_needed"
    MANUAL_CLEANUP_REQUIRED = "manual_cleanup_required"


@dataclass(slots=True)
class BoundedFilesystemAdapter:
    """Create one direct child and two exclusive starter files."""

    link_inspector: LinkInspector = NativeLinkInspector()

    def preflight(self, location: ProjectLocation) -> None:
        root, destination = self._validated_native_paths(location)
        self._assert_root_safe(root)
        self._assert_destination_absent(destination)

    def create_project_directory(self, location: ProjectLocation) -> CreatedPaths:
        root, destination = self._validated_native_paths(location)
        self._assert_root_safe(root)
        self._assert_destination_absent(destination)
        created = CreatedPaths.empty(destination)
        try:
            os.mkdir(destination)
            created = created.mark_directory_created()
            created = created.append(self._record(destination, "directory"))
            self._fsync_directory(root)
            return created
        except (OSError, FilesystemSafetyError):
            raise FilesystemMutationError("project_directory_creation_failed", created) from None

    def create_starter_files(
        self,
        location: ProjectLocation,
        project_name: str,
        created: CreatedPaths,
    ) -> CreatedPaths:
        _, destination = self._validated_native_paths(location)
        self._assert_creation_record(created, destination)
        contents = (
            (README_NAME, f"# {project_name}\n\nTODO: Describe this project.\n"),
            (GITIGNORE_NAME, _GITIGNORE_CONTENT),
        )
        current = created
        try:
            for filename, content in contents:
                target = destination / filename
                self._write_exclusive(target, content)
                current = current.append(self._record(target, "file"))
            self._fsync_directory(destination)
            return current
        except (OSError, FilesystemSafetyError):
            raise FilesystemMutationError("starter_file_creation_failed", current) from None

    def rollback(self, location: ProjectLocation, created: CreatedPaths) -> str:
        if not created.directory_created:
            return RollbackStatus.NOT_NEEDED
        if not created.entries:
            return RollbackStatus.MANUAL_CLEANUP_REQUIRED
        try:
            root, destination = self._validated_native_paths(location)
            if created.project_directory != destination:
                return RollbackStatus.MANUAL_CLEANUP_REQUIRED
            directory_entry = created.entries[0]
            if directory_entry.kind != "directory" or directory_entry.path != destination:
                return RollbackStatus.MANUAL_CLEANUP_REQUIRED
            self._verify_record(directory_entry)
            expected_files = {
                entry.path.name
                for entry in created.entries[1:]
                if entry.kind == "file" and entry.path.parent == destination
            }
            if len(expected_files) != len(created.entries) - 1:
                return RollbackStatus.MANUAL_CLEANUP_REQUIRED
            with os.scandir(destination) as entries:
                actual_names = {entry.name for entry in entries}
            if actual_names != expected_files:
                return RollbackStatus.MANUAL_CLEANUP_REQUIRED
            for entry in reversed(created.entries[1:]):
                self._verify_record(entry)
            for entry in reversed(created.entries[1:]):
                os.unlink(entry.path)
            self._fsync_directory(destination)
            os.rmdir(destination)
            self._fsync_directory(root)
            return RollbackStatus.COMPLETED
        except (OSError, FilesystemSafetyError):
            return RollbackStatus.MANUAL_CLEANUP_REQUIRED

    def destination_path(self, location: ProjectLocation) -> Path:
        """Return the validated native destination without touching it."""

        _, destination = self._validated_native_paths(location)
        return destination

    def _validated_native_paths(self, location: ProjectLocation) -> tuple[Path, Path]:
        if location.flavor is not PathFlavor.native():
            raise FilesystemSafetyError("project_root_non_native")
        root = Path(str(location.root))
        destination = Path(str(location.destination))
        if not root.is_absolute() or destination.parent != root:
            raise FilesystemSafetyError("destination_outside_approved_root")
        try:
            common = Path(os.path.commonpath((root, destination)))
        except ValueError:
            raise FilesystemSafetyError("destination_outside_approved_root") from None
        if common != root:
            raise FilesystemSafetyError("destination_outside_approved_root")
        return root, destination

    def _assert_root_safe(self, root: Path) -> None:
        for component in (*reversed(root.parents), root):
            try:
                result = os.lstat(component)
            except OSError:
                raise FilesystemSafetyError("project_root_unavailable") from None
            if self.link_inspector.is_ambiguous(component, result):
                raise FilesystemSafetyError("project_root_ambiguous")
        if not stat.S_ISDIR(os.lstat(root).st_mode):
            raise FilesystemSafetyError("project_root_not_directory")

    def _assert_destination_absent(self, destination: Path) -> None:
        try:
            os.lstat(destination)
        except FileNotFoundError:
            return
        except OSError:
            raise FilesystemSafetyError("destination_availability_unknown") from None
        raise FilesystemSafetyError("destination_already_exists")

    def _assert_creation_record(self, created: CreatedPaths, destination: Path) -> None:
        if (
            len(created.entries) != 1
            or created.project_directory != destination
            or created.entries[0].kind != "directory"
        ):
            raise FilesystemSafetyError("creation_journal_invalid")
        self._verify_record(created.entries[0])

    def _record(self, path: Path, kind: str) -> CreatedEntry:
        result = os.lstat(path)
        if self.link_inspector.is_ambiguous(path, result):
            raise FilesystemSafetyError("created_path_ambiguous")
        expected = (
            stat.S_ISDIR(result.st_mode)
            if kind == "directory"
            else stat.S_ISREG(result.st_mode)
        )
        if not expected:
            raise FilesystemSafetyError("created_path_type_changed")
        return CreatedEntry(
            path=path,
            kind=kind,
            device=result.st_dev,
            inode=result.st_ino,
        )

    def _verify_record(self, entry: CreatedEntry) -> None:
        result = os.lstat(entry.path)
        if self.link_inspector.is_ambiguous(entry.path, result):
            raise FilesystemSafetyError("created_path_ambiguous")
        if result.st_dev != entry.device or result.st_ino != entry.inode:
            raise FilesystemSafetyError("created_path_identity_changed")
        if entry.kind == "directory" and not stat.S_ISDIR(result.st_mode):
            raise FilesystemSafetyError("created_path_type_changed")
        if entry.kind == "file" and not stat.S_ISREG(result.st_mode):
            raise FilesystemSafetyError("created_path_type_changed")

    @staticmethod
    def _write_exclusive(path: Path, content: str) -> None:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor: int | None = None
        try:
            descriptor = os.open(path, flags)
            os.fsync(descriptor)
        except OSError:
            return
        finally:
            if descriptor is not None:
                os.close(descriptor)
