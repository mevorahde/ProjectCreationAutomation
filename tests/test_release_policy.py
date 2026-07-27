from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path
from typing import cast

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

from project_creation_automation import __version__
from project_creation_automation.cli import build_parser

ROOT = Path(__file__).parents[1]
RELEASE_VERSION = "1.0.0rc1"
LEGACY_PATHS = (
    ROOT / "script.py",
    ROOT / "batch" / "create.bat",
    ROOT / "requirements.txt",
)


def _configuration() -> dict[str, object]:
    return cast(
        dict[str, object],
        tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8")),
    )


def test_release_version_is_consistent_and_not_final() -> None:
    project = _configuration()["project"]
    assert isinstance(project, dict)

    assert project["version"] == RELEASE_VERSION
    assert __version__ == RELEASE_VERSION
    assert RELEASE_VERSION in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "1.0.0rc1" in (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "final `1.0.0` release is intentionally deferred" in (
        ROOT / "SECURITY.md"
    ).read_text(encoding="utf-8")


def test_legacy_runtime_is_absent_and_history_migration_is_documented() -> None:
    assert all(not path.exists() for path in LEGACY_PATHS)
    migration = (ROOT / "docs" / "migration-from-legacy.md").read_text(
        encoding="utf-8"
    )

    for name in ("script.py", "batch/create.bat", "requirements.txt"):
        assert name in migration
    assert "Git history" in migration
    assert (ROOT / "ATTRIBUTION.md").is_file()


def test_readme_project_create_commands_match_the_parser() -> None:
    parser = build_parser()
    commands = [
        line.strip()
        for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("project-create ")
    ]
    assert commands

    for command in commands:
        arguments = shlex.split(command)[1:]
        if arguments == ["--help"]:
            with pytest.raises(SystemExit) as captured:
                parser.parse_args(arguments)
            assert captured.value.code == 0
        else:
            parsed = parser.parse_args(arguments)
            assert parsed.project_name == "sample-project"


def test_environment_example_is_empty_and_real_environment_file_is_ignored() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assignments = [
        line
        for line in example.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    ignore_rules = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert assignments == ["GITHUB_TOKEN="]
    assert not re.search(
        r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{8,}",
        example,
        flags=re.IGNORECASE,
    )
    assert ".env" in ignore_rules
    assert ".env.example" not in ignore_rules


def test_release_documents_and_issue_templates_are_present_and_accurate() -> None:
    required = (
        ROOT / "SECURITY.md",
        ROOT / "CHANGELOG.md",
        ROOT / "docs" / "architecture.md",
        ROOT / "docs" / "migration-from-legacy.md",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.md",
    )
    assert all(path.is_file() for path in required)

    feature = required[-1].read_text(encoding="utf-8")
    assert 'title: "[Feature] "' in feature
    assert "Screenshots" not in feature


def test_ci_builds_and_audits_real_wheel_without_publication() -> None:
    workflow = json.loads(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["test"]["steps"]
    commands = {
        step["run"]
        for step in steps
        if isinstance(step, dict) and "run" in step
    }
    serialized = json.dumps(workflow).casefold()

    assert "python -m build --wheel --outdir .ci-dist" in commands
    assert "python tools/verify_wheel.py .ci-dist" in commands
    assert workflow["permissions"] == {"contents": "read"}
    for forbidden in (
        "pypi",
        "publish",
        "release",
        "upload-artifact",
        "workflow_dispatch",
        "id-token",
    ):
        assert forbidden not in serialized


def test_authored_release_content_contains_no_private_or_generated_artifacts() -> None:
    authored_paths = [
        ROOT / "README.md",
        ROOT / "SECURITY.md",
        ROOT / "CHANGELOG.md",
        ROOT / "ATTRIBUTION.md",
        ROOT / "CODE_OF_CONDUCT.md",
        ROOT / ".env.example",
        ROOT / "pyproject.toml",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "src").rglob("*.py")),
        ROOT / "src" / "project_creation_automation" / "py.typed",
        *sorted((ROOT / ".github").rglob("*.md")),
        *sorted((ROOT / ".github").rglob("*.yml")),
        ROOT / "tools" / "verify_wheel.py",
    ]
    forbidden_suffixes = {
        ".db",
        ".dll",
        ".exe",
        ".log",
        ".pyc",
        ".pyo",
        ".sqlite",
    }
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in authored_paths
        if path.suffix not in forbidden_suffixes
    )

    assert all(path.suffix.casefold() not in forbidden_suffixes for path in authored_paths)
    assert not re.search(r"(?i)C:\\Users\\|/home/[A-Za-z0-9._-]+", combined)
    assert not re.search(r"(?i)https?://[^\s/@]+:[^\s/@]+@", combined)
    assert not re.search(
        r"(?i)(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{8,}",
        combined,
    )
    assert not re.search(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", combined)
    assert "shell=True" not in combined
    assert "git reset --hard" not in combined
    assert "rm -rf" not in combined
    assert "has not received an independent professional security audit" in combined
