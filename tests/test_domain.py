from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from project_creation_automation.domain import (
    IDEChoice,
    PathFlavor,
    ProjectNameError,
    ProjectRequest,
    ProjectRootError,
    Visibility,
    resolve_project_location,
    validate_project_name,
)


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        ".",
        "..",
        "../escape",
        r"..\escape",
        "/absolute",
        r"C:\absolute",
        "nested/project",
        r"nested\project",
        "unsafe name",
        "unsafe.",
        "unsafe ",
        "name&command",
        "name|command",
        "name;command",
        "name$(command)",
        "name`command`",
        "name%PATH%",
        "line\nbreak",
        "control\x00character",
        "CON",
        "con.txt",
        "LPT9",
        "COM1.log",
        "name\u200bhidden",
        "é",
    ],
)
def test_rejects_hostile_or_ambiguous_project_names(name: str) -> None:
    with pytest.raises(ProjectNameError) as captured:
        validate_project_name(name)

    assert str(captured.value) == "The project request is invalid."
    assert repr(captured.value).startswith("ProjectNameError(code=")


@pytest.mark.parametrize("name", ["example", "Example-2", "safe_name", "safe.name"])
def test_accepts_safe_project_names(name: str) -> None:
    assert validate_project_name(name) == name


def test_request_defaults_are_private_and_have_no_ide() -> None:
    request = ProjectRequest.create(
        project_name="safe-project",
        project_root="/approved/projects",
        path_flavor=PathFlavor.POSIX,
    )

    assert request.visibility is Visibility.PRIVATE
    assert request.ide is IDEChoice.NONE
    assert request.create_github_repository is False


def test_only_reviewed_ide_choices_are_supported() -> None:
    assert [choice.value for choice in IDEChoice] == ["none", "pycharm", "vscode"]


def test_request_is_immutable() -> None:
    request = ProjectRequest.create(
        project_name="safe-project",
        project_root="/approved/projects",
        path_flavor=PathFlavor.POSIX,
    )

    with pytest.raises(FrozenInstanceError):
        request.project_name = "changed"  # type: ignore[misc]


def test_resolves_posix_destination_as_direct_child_without_io() -> None:
    location = resolve_project_location(
        project_root="/approved/./projects/../projects",
        project_name="safe-project",
        flavor=PathFlavor.POSIX,
    )

    assert location.root == PurePosixPath("/approved/projects")
    assert location.destination == PurePosixPath("/approved/projects/safe-project")
    assert location.destination.parent == location.root


def test_resolves_windows_destination_as_direct_child_without_io() -> None:
    location = resolve_project_location(
        project_root=r"C:\Approved\.\Projects\..\Projects",
        project_name="safe-project",
        flavor=PathFlavor.WINDOWS,
    )

    assert location.root == PureWindowsPath(r"C:\Approved\Projects")
    assert location.destination == PureWindowsPath(r"C:\Approved\Projects\safe-project")
    assert location.destination.parent == location.root


@pytest.mark.parametrize(
    ("root", "flavor"),
    [
        ("relative/projects", PathFlavor.POSIX),
        (r"relative\projects", PathFlavor.WINDOWS),
        ("", PathFlavor.POSIX),
        (" /approved/projects", PathFlavor.POSIX),
        ("/approved/projects ", PathFlavor.POSIX),
    ],
)
def test_rejects_unapproved_relative_or_ambiguous_roots(
    root: str, flavor: PathFlavor
) -> None:
    with pytest.raises(ProjectRootError) as captured:
        resolve_project_location(
            project_root=root,
            project_name="safe-project",
            flavor=flavor,
        )

    assert str(captured.value) == "The project request is invalid."
    assert repr(captured.value).startswith("ProjectRootError(code=")


def test_location_repr_redacts_paths() -> None:
    sensitive_root = "/private/example/projects"
    location = resolve_project_location(
        project_root=sensitive_root,
        project_name="safe-project",
        flavor=PathFlavor.POSIX,
    )

    assert sensitive_root not in repr(location)
    assert "<approved-root>" in repr(location)
