"""Offline wheel metadata and contents policy verification."""

from __future__ import annotations

import argparse
import email
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

_EXPECTED_NAME = "project-creation-automation"
_EXPECTED_VERSION = "1.0.0"
_EXPECTED_LICENSE = "GPL-3.0-or-later"
_EXPECTED_PYTHON = frozenset({">=3.10", "<3.14"})
_EXPECTED_DEPENDENCIES = frozenset(
    {
        "truststore<0.11,>=0.10.4",
        'build<2,>=1.2; extra == "dev"',
        'mypy<2,>=1.15; extra == "dev"',
        'pytest<10,>=8.3; extra == "dev"',
        'ruff<1,>=0.11; extra == "dev"',
        'tomli<3,>=2; python_version < "3.11" and extra == "dev"',
    }
)
_ENTRY_POINT = "project-create = project_creation_automation.cli:main"
_EXPECTED_URLS = frozenset(
    {
        "Homepage, https://github.com/mevorahde/ProjectCreationAutomation",
        "Issues, https://github.com/mevorahde/ProjectCreationAutomation/issues",
        "Repository, https://github.com/mevorahde/ProjectCreationAutomation",
    }
)
_EXPECTED_PACKAGE_FILES = frozenset(
    {
        "project_creation_automation/__init__.py",
        "project_creation_automation/__main__.py",
        "project_creation_automation/adapters/__init__.py",
        "project_creation_automation/adapters/filesystem.py",
        "project_creation_automation/adapters/git.py",
        "project_creation_automation/adapters/github.py",
        "project_creation_automation/adapters/ide.py",
        "project_creation_automation/cli.py",
        "project_creation_automation/credentials.py",
        "project_creation_automation/domain.py",
        "project_creation_automation/execution.py",
        "project_creation_automation/fakes.py",
        "project_creation_automation/planning.py",
        "project_creation_automation/ports.py",
        "project_creation_automation/py.typed",
    }
)
_DIST_INFO_FILES = frozenset(
    {
        "METADATA",
        "RECORD",
        "WHEEL",
        "entry_points.txt",
        "top_level.txt",
    }
)
_LICENSE_FILES = frozenset({"ATTRIBUTION.md", "LICENSE"})
_FORBIDDEN_PARTS = frozenset(
    {
        ".env",
        ".git",
        ".github",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "batch",
        "build",
        "dist",
        "tests",
        "tools",
    }
)


def verify_wheel(wheel_path: Path) -> None:
    """Raise a generic policy error when a wheel violates release boundaries."""

    with ZipFile(wheel_path) as archive:
        names = tuple(archive.namelist())
        metadata_name = _one_matching(names, ".dist-info/METADATA")
        _one_matching(names, ".dist-info/WHEEL")
        _one_matching(names, ".dist-info/RECORD")
        entry_points_name = _one_matching(names, ".dist-info/entry_points.txt")
        metadata = email.message_from_bytes(archive.read(metadata_name))
        entry_points = archive.read(entry_points_name).decode("utf-8", errors="strict")

    if metadata["Name"] != _EXPECTED_NAME:
        raise ValueError("wheel_name_invalid")
    if metadata["Version"] != _EXPECTED_VERSION:
        raise ValueError("wheel_version_invalid")
    if metadata["License-Expression"] != _EXPECTED_LICENSE:
        raise ValueError("wheel_license_invalid")
    if frozenset(metadata.get_all("Project-URL", [])) != _EXPECTED_URLS:
        raise ValueError("wheel_project_urls_invalid")
    python_range = metadata["Requires-Python"]
    if python_range is None or frozenset(python_range.split(",")) != _EXPECTED_PYTHON:
        raise ValueError("wheel_python_range_invalid")
    if frozenset(metadata.get_all("Requires-Dist", [])) != _EXPECTED_DEPENDENCIES:
        raise ValueError("wheel_dependencies_invalid")
    if _ENTRY_POINT not in entry_points.splitlines():
        raise ValueError("wheel_entry_point_invalid")
    if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
        raise ValueError("wheel_license_file_missing")
    if not any(name.endswith(".dist-info/licenses/ATTRIBUTION.md") for name in names):
        raise ValueError("wheel_attribution_missing")
    package_files = frozenset(
        name for name in names if name.startswith("project_creation_automation/")
    )
    if package_files != _EXPECTED_PACKAGE_FILES:
        raise ValueError("wheel_package_contents_invalid")
    for name in names:
        path = PurePosixPath(name)
        lowered_parts = {part.casefold() for part in path.parts}
        if lowered_parts.intersection(_FORBIDDEN_PARTS):
            raise ValueError("wheel_private_or_generated_artifact")
        if path.name.casefold() == "script.py" or path.suffix.casefold() in {
            ".pyc",
            ".pyo",
        }:
            raise ValueError("wheel_legacy_or_generated_artifact")
        if not _is_allowed_content(path):
            raise ValueError("wheel_unexpected_top_level_content")


def _one_matching(names: tuple[str, ...], suffix: str) -> str:
    matches = tuple(name for name in names if name.endswith(suffix))
    if len(matches) != 1:
        raise ValueError("wheel_metadata_layout_invalid")
    return matches[0]


def _is_allowed_content(path: PurePosixPath) -> bool:
    if not path.parts:
        return False
    if path.parts[0] == "project_creation_automation":
        return path.name == "py.typed" or path.suffix == ".py"
    if len(path.parts) < 2 or not path.parts[0].endswith(".dist-info"):
        return False
    relative = path.parts[1:]
    if len(relative) == 1:
        return relative[0] in _DIST_INFO_FILES
    return (
        len(relative) == 2
        and relative[0] == "licenses"
        and relative[1] in _LICENSE_FILES
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel_directory", type=Path)
    arguments = parser.parse_args()
    wheels = tuple(arguments.wheel_directory.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("expected exactly one wheel")
    verify_wheel(wheels[0])
    print("wheel policy: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
