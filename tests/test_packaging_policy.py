from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast
from zipfile import ZipFile

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

from tools.verify_wheel import verify_wheel

ROOT = Path(__file__).parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
DEPENDABOT_PATH = ROOT / ".github" / "dependabot.yml"


def _configuration() -> dict[str, object]:
    return cast(
        dict[str, object],
        tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8")),
    )


def _json_yaml(path: Path) -> dict[str, object]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_python_license_attribution_and_entry_point_metadata() -> None:
    configuration = _configuration()
    project = configuration["project"]
    build_system = configuration["build-system"]
    assert isinstance(project, dict)
    assert isinstance(build_system, dict)

    assert project["version"] == "1.0.0"
    assert project["requires-python"] == ">=3.10,<3.14"
    assert project["license"] == "GPL-3.0-or-later"
    assert project["license-files"] == ["LICENSE", "ATTRIBUTION.md"]
    assert project["scripts"] == {
        "project-create": "project_creation_automation.cli:main"
    }
    assert project["dependencies"] == ["truststore>=0.10.4,<0.11"]
    assert "Development Status :: 5 - Production/Stable" in project["classifiers"]
    assert "Development Status :: 4 - Beta" not in project["classifiers"]
    assert project["urls"] == {
        "Homepage": "https://github.com/mevorahde/ProjectCreationAutomation",
        "Repository": "https://github.com/mevorahde/ProjectCreationAutomation",
        "Issues": "https://github.com/mevorahde/ProjectCreationAutomation/issues",
    }
    assert build_system["requires"] == ["setuptools>=77,<82"]
    assert "build>=1.2,<2" in project["optional-dependencies"]["dev"]
    assert (ROOT / "LICENSE").is_file()
    assert (ROOT / "ATTRIBUTION.md").is_file()


def test_ci_json_compatible_yaml_is_least_privilege_and_complete() -> None:
    workflow = _json_yaml(WORKFLOW_PATH)
    triggers = workflow["on"]
    permissions = workflow["permissions"]
    concurrency = workflow["concurrency"]
    jobs = workflow["jobs"]
    assert isinstance(triggers, dict)
    assert isinstance(permissions, dict)
    assert isinstance(concurrency, dict)
    assert isinstance(jobs, dict)

    expected_branches = [
        "master",
        "main",
        "modernize-project-creation-automation",
    ]
    assert triggers == {
        "push": {"branches": expected_branches},
        "pull_request": {"branches": expected_branches},
    }
    assert permissions == {"contents": "read"}
    assert concurrency["cancel-in-progress"] is True

    test_job = jobs["test"]
    assert isinstance(test_job, dict)
    strategy = test_job["strategy"]
    assert isinstance(strategy, dict)
    matrix = strategy["matrix"]
    assert isinstance(matrix, dict)
    assert matrix == {
        "os": ["ubuntu-latest", "windows-latest"],
        "python-version": ["3.10", "3.11", "3.12", "3.13"],
    }

    steps = test_job["steps"]
    assert isinstance(steps, list)
    uses = {
        step["uses"]
        for step in steps
        if isinstance(step, dict) and "uses" in step
    }
    assert uses == {"actions/checkout@v4", "actions/setup-python@v5"}
    commands = {
        step["run"]
        for step in steps
        if isinstance(step, dict) and "run" in step
    }
    assert {
        'python -m pip install ".[dev]"',
        "python -m pip check",
        "python -m compileall -q src",
        "python -m ruff check src tests tools",
        "python -m mypy --strict src tests tools",
        "python -m pytest -q -p no:cacheprovider",
        "python -m build --wheel --outdir .ci-dist",
        "python tools/verify_wheel.py .ci-dist",
    }.issubset(commands)


def test_ci_has_no_live_secrets_integrations_legacy_execution_or_uploads() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    lowered = workflow_text.casefold()

    for forbidden in (
        "secrets.",
        "github_token",
        "pull_request_target",
        "actions/upload-artifact",
        "script.py",
        "create.bat",
        "project-create create",
        "git push",
        "repository_dispatch",
    ):
        assert forbidden not in lowered


def test_dependabot_updates_are_weekly_and_bounded() -> None:
    configuration = _json_yaml(DEPENDABOT_PATH)
    assert configuration["version"] == 2
    updates = configuration["updates"]
    assert isinstance(updates, list)
    assert {item["package-ecosystem"] for item in updates} == {
        "pip",
        "github-actions",
    }
    for item in updates:
        assert item["directory"] == "/"
        assert item["schedule"] == {"interval": "weekly"}
        assert item["open-pull-requests-limit"] == 3


def _synthetic_wheel(path: Path, *, include_legacy: bool = False) -> None:
    dist_info = "project_creation_automation-1.0.0.dist-info"
    metadata = "\n".join(
        [
            "Metadata-Version: 2.4",
            "Name: project-creation-automation",
            "Version: 1.0.0",
            "License-Expression: GPL-3.0-or-later",
            "Requires-Python: >=3.10,<3.14",
            "Requires-Dist: truststore<0.11,>=0.10.4",
            'Requires-Dist: build<2,>=1.2; extra == "dev"',
            'Requires-Dist: mypy<2,>=1.15; extra == "dev"',
            'Requires-Dist: pytest<10,>=8.3; extra == "dev"',
            'Requires-Dist: ruff<1,>=0.11; extra == "dev"',
            'Requires-Dist: tomli<3,>=2; python_version < "3.11" and extra == "dev"',
            "Project-URL: Homepage, https://github.com/mevorahde/ProjectCreationAutomation",
            "Project-URL: Issues, https://github.com/mevorahde/ProjectCreationAutomation/issues",
            "Project-URL: Repository, https://github.com/mevorahde/ProjectCreationAutomation",
            "",
        ]
    )
    package_files = (
        "__init__.py",
        "__main__.py",
        "adapters/__init__.py",
        "adapters/filesystem.py",
        "adapters/git.py",
        "adapters/github.py",
        "adapters/ide.py",
        "cli.py",
        "credentials.py",
        "domain.py",
        "execution.py",
        "fakes.py",
        "planning.py",
        "ports.py",
    )
    with ZipFile(path, "w") as archive:
        for package_file in package_files:
            archive.writestr(f"project_creation_automation/{package_file}", "")
        archive.writestr("project_creation_automation/py.typed", "")
        archive.writestr(f"{dist_info}/METADATA", metadata)
        archive.writestr(f"{dist_info}/WHEEL", "Wheel-Version: 1.0\n")
        archive.writestr(f"{dist_info}/RECORD", "")
        archive.writestr(
            f"{dist_info}/entry_points.txt",
            "[console_scripts]\n"
            "project-create = project_creation_automation.cli:main\n",
        )
        archive.writestr(f"{dist_info}/licenses/LICENSE", "GPL test fixture")
        archive.writestr(
            f"{dist_info}/licenses/ATTRIBUTION.md",
            "Attribution test fixture",
        )
        if include_legacy:
            archive.writestr("script.py", "legacy test fixture")


def test_wheel_policy_accepts_metadata_and_excludes_private_runtime_artifacts(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "project_creation_automation-1.0.0-py3-none-any.whl"
    _synthetic_wheel(wheel)

    verify_wheel(wheel)


def test_wheel_policy_rejects_legacy_runtime_artifacts(tmp_path: Path) -> None:
    wheel = tmp_path / "project_creation_automation-1.0.0-py3-none-any.whl"
    _synthetic_wheel(wheel, include_legacy=True)

    with pytest.raises(ValueError, match="wheel_legacy_or_generated_artifact"):
        verify_wheel(wheel)
