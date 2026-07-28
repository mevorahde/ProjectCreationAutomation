from __future__ import annotations

import os
from pathlib import Path

import pytest

from project_creation_automation.adapters.filesystem import (
    BoundedFilesystemAdapter,
    FilesystemMutationError,
    NativeLinkInspector,
    RollbackStatus,
)
from project_creation_automation.domain import (
    FilesystemSafetyError,
    PathFlavor,
    ProjectNameError,
    ProjectRequest,
)


def _request(root: Path, name: str = "safe-project") -> ProjectRequest:
    return ProjectRequest.create(
        project_name=name,
        project_root=str(root),
        path_flavor=PathFlavor.native(),
    )


def test_successful_local_creation_uses_exact_starter_files(tmp_path: Path) -> None:
    adapter = BoundedFilesystemAdapter()
    request = _request(tmp_path)

    adapter.preflight(request.location)
    created = adapter.create_project_directory(request.location)
    created = adapter.create_starter_files(
        request.location,
        request.project_name,
        created,
    )

    destination = tmp_path / "safe-project"
    assert {entry.name for entry in destination.iterdir()} == {"README.md", ".gitignore"}
    assert (destination / "README.md").read_bytes() == (
        b"# safe-project\n\nTODO: Describe this project.\n"
    )
    assert (destination / ".gitignore").read_bytes() == (
        b"__pycache__/\n"
        b"*.py[cod]\n"
        b".pytest_cache/\n"
        b".mypy_cache/\n"
        b".ruff_cache/\n"
        b".venv/\n"
    )
    assert [entry.kind for entry in created.entries] == ["directory", "file", "file"]


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_existing_destination_fails_closed(tmp_path: Path, kind: str) -> None:
    destination = tmp_path / "safe-project"
    if kind == "file":
        destination.write_text("pre-existing", encoding="utf-8")
    else:
        destination.mkdir()
    adapter = BoundedFilesystemAdapter()

    with pytest.raises(FilesystemSafetyError) as captured:
        adapter.preflight(_request(tmp_path).location)

    assert captured.value.code == "destination_already_exists"
    assert destination.exists()


def test_missing_or_non_directory_root_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    root_file = tmp_path / "root-file"
    root_file.write_text("not a directory", encoding="utf-8")
    adapter = BoundedFilesystemAdapter()

    with pytest.raises(FilesystemSafetyError):
        adapter.preflight(_request(missing).location)
    with pytest.raises(FilesystemSafetyError) as captured:
        adapter.preflight(_request(root_file).location)

    assert captured.value.code == "project_root_not_directory"


class RejectRootInspector:
    def __init__(self, rejected: Path) -> None:
        self.rejected = rejected
        self.native = NativeLinkInspector()

    def is_ambiguous(self, path: Path, result: os.stat_result) -> bool:
        return path == self.rejected or self.native.is_ambiguous(path, result)


def test_mocked_symlink_or_reparse_root_is_rejected(tmp_path: Path) -> None:
    adapter = BoundedFilesystemAdapter(link_inspector=RejectRootInspector(tmp_path))

    with pytest.raises(FilesystemSafetyError) as captured:
        adapter.preflight(_request(tmp_path).location)

    assert captured.value.code == "project_root_ambiguous"
    assert not (tmp_path / "safe-project").exists()


def test_exclusive_creation_never_overwrites_file(tmp_path: Path) -> None:
    adapter = BoundedFilesystemAdapter()
    request = _request(tmp_path)
    created = adapter.create_project_directory(request.location)
    readme = tmp_path / "safe-project" / "README.md"
    readme.write_text("pre-existing", encoding="utf-8")

    with pytest.raises(FilesystemMutationError) as captured:
        adapter.create_starter_files(request.location, request.project_name, created)

    assert captured.value.code == "starter_file_creation_failed"
    assert readme.read_text(encoding="utf-8") == "pre-existing"


def test_partial_file_failure_tracks_and_rolls_back_created_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = BoundedFilesystemAdapter()
    request = _request(tmp_path)
    created = adapter.create_project_directory(request.location)
    original = BoundedFilesystemAdapter._write_exclusive

    def fail_gitignore(path: Path, content: str) -> None:
        if path.name == ".gitignore":
            raise OSError("simulated")
        original(path, content)

    monkeypatch.setattr(BoundedFilesystemAdapter, "_write_exclusive", staticmethod(fail_gitignore))
    with pytest.raises(FilesystemMutationError) as captured:
        adapter.create_starter_files(request.location, request.project_name, created)

    assert len(captured.value.created.entries) == 2
    assert adapter.rollback(request.location, captured.value.created) == RollbackStatus.COMPLETED
    assert not (tmp_path / "safe-project").exists()


def test_safe_rollback_removes_only_recorded_paths(tmp_path: Path) -> None:
    adapter = BoundedFilesystemAdapter()
    request = _request(tmp_path)
    created = adapter.create_project_directory(request.location)
    created = adapter.create_starter_files(request.location, request.project_name, created)

    result = adapter.rollback(request.location, created)

    assert result == RollbackStatus.COMPLETED
    assert tmp_path.exists()
    assert not (tmp_path / "safe-project").exists()


def test_rollback_refuses_unexpected_content(tmp_path: Path) -> None:
    adapter = BoundedFilesystemAdapter()
    request = _request(tmp_path)
    created = adapter.create_project_directory(request.location)
    created = adapter.create_starter_files(request.location, request.project_name, created)
    unexpected = tmp_path / "safe-project" / "unexpected.txt"
    unexpected.write_text("preserve", encoding="utf-8")

    result = adapter.rollback(request.location, created)

    assert result == RollbackStatus.MANUAL_CLEANUP_REQUIRED
    assert unexpected.read_text(encoding="utf-8") == "preserve"
    assert (tmp_path / "safe-project" / "README.md").exists()


def test_project_name_traversal_is_rejected_before_adapter(tmp_path: Path) -> None:
    with pytest.raises(ProjectNameError):
        _request(tmp_path, "../escape")

    assert not (tmp_path.parent / "escape").exists()
