"""Offline wheel metadata and contents policy verification."""

from __future__ import annotations

import argparse
import email
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

_EXPECTED_NAME = "project-creation-automation"
_EXPECTED_LICENSE = "GPL-3.0-or-later"
_EXPECTED_PYTHON = frozenset({">=3.10", "<3.14"})
_ENTRY_POINT = "project-create = project_creation_automation.cli:main"
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
        entry_points_name = _one_matching(names, ".dist-info/entry_points.txt")
        metadata = email.message_from_bytes(archive.read(metadata_name))
        entry_points = archive.read(entry_points_name).decode("utf-8", errors="strict")

    if metadata["Name"] != _EXPECTED_NAME:
        raise ValueError("wheel_name_invalid")
    if metadata["License-Expression"] != _EXPECTED_LICENSE:
        raise ValueError("wheel_license_invalid")
    python_range = metadata["Requires-Python"]
    if python_range is None or frozenset(python_range.split(",")) != _EXPECTED_PYTHON:
        raise ValueError("wheel_python_range_invalid")
    if _ENTRY_POINT not in entry_points.splitlines():
        raise ValueError("wheel_entry_point_invalid")
    if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
        raise ValueError("wheel_license_file_missing")
    if not any(name.endswith(".dist-info/licenses/ATTRIBUTION.md") for name in names):
        raise ValueError("wheel_attribution_missing")
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
        if not (
            name.startswith("project_creation_automation/")
            or ".dist-info/" in name
        ):
            raise ValueError("wheel_unexpected_top_level_content")


def _one_matching(names: tuple[str, ...], suffix: str) -> str:
    matches = tuple(name for name in names if name.endswith(suffix))
    if len(matches) != 1:
        raise ValueError("wheel_metadata_layout_invalid")
    return matches[0]


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
