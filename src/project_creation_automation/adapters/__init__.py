"""Concrete Stage 5 adapters.

Importing adapters does not inspect configuration, access external systems, or
start processes.
"""

from project_creation_automation.adapters.filesystem import BoundedFilesystemAdapter
from project_creation_automation.adapters.git import GitProcessAdapter, SystemProcessRunner
from project_creation_automation.adapters.github import (
    GitHubApiAdapter,
    GitHubHttpsTransport,
)
from project_creation_automation.adapters.ide import (
    SafeIDEAdapter,
    SystemIDEProcessLauncher,
)

__all__ = [
    "BoundedFilesystemAdapter",
    "GitHubApiAdapter",
    "GitHubHttpsTransport",
    "GitProcessAdapter",
    "SafeIDEAdapter",
    "SystemIDEProcessLauncher",
    "SystemProcessRunner",
]
