from __future__ import annotations

import http.client
import importlib
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

import pytest


def _unexpected_effect(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("external side effect attempted during import")


def test_package_import_has_no_external_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for module_name in tuple(sys.modules):
        if (
            module_name == "project_creation_automation"
            or module_name.startswith("project_creation_automation.")
            or module_name == "tools.verify_wheel"
            or module_name == "truststore"
            or module_name.startswith("truststore.")
        ):
            del sys.modules[module_name]

    monkeypatch.setattr(os, "system", _unexpected_effect)
    monkeypatch.setattr(os, "getenv", _unexpected_effect)
    monkeypatch.setattr(socket, "create_connection", _unexpected_effect)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", _unexpected_effect)
    monkeypatch.setattr(subprocess, "Popen", _unexpected_effect)
    monkeypatch.setattr(subprocess, "run", _unexpected_effect)
    monkeypatch.setattr(shutil, "which", _unexpected_effect)
    monkeypatch.setattr(sys, "exit", _unexpected_effect)
    monkeypatch.setattr(Path, "mkdir", _unexpected_effect)
    monkeypatch.setattr(Path, "open", _unexpected_effect)
    monkeypatch.setattr(Path, "read_text", _unexpected_effect)
    monkeypatch.setattr(Path, "read_bytes", _unexpected_effect)
    monkeypatch.setattr(Path, "write_text", _unexpected_effect)
    monkeypatch.setattr(Path, "write_bytes", _unexpected_effect)

    imported = importlib.import_module("project_creation_automation")
    importlib.import_module("project_creation_automation.adapters.filesystem")
    importlib.import_module("project_creation_automation.adapters.git")
    importlib.import_module("project_creation_automation.adapters.github")
    importlib.import_module("project_creation_automation.adapters.ide")
    importlib.import_module("project_creation_automation.credentials")
    importlib.import_module("project_creation_automation.execution")
    importlib.import_module("project_creation_automation.cli")
    importlib.import_module("tools.verify_wheel")

    assert imported.__version__ == "1.0.0"
    assert "dotenv" not in sys.modules
    assert "requests" not in sys.modules
    assert "truststore" not in sys.modules
    assert not {
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide6",
        "wx",
    }.intersection(sys.modules)


def test_cli_import_does_not_import_legacy_or_adapter_dependencies() -> None:
    importlib.import_module("project_creation_automation.cli")

    assert "dotenv" not in sys.modules
    assert "requests" not in sys.modules
    assert "github" not in sys.modules
