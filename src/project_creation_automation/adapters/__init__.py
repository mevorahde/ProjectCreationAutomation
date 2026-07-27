"""Concrete Stage 4 adapters.

Importing adapters does not inspect configuration, access external systems, or
start processes.
"""

from project_creation_automation.adapters.filesystem import BoundedFilesystemAdapter
from project_creation_automation.adapters.git import GitProcessAdapter, SystemProcessRunner
from project_creation_automation.adapters.github import (
    GitHubApiAdapter,
    GitHubHttpsTransport,
)

__all__ = [
    "BoundedFilesystemAdapter",
    "GitHubApiAdapter",
    "GitHubHttpsTransport",
    "GitProcessAdapter",
    "SystemProcessRunner",
]
