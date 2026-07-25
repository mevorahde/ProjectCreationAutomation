"""Concrete Stage 3 adapters.

Importing adapters does not inspect the filesystem or start processes.
"""

from project_creation_automation.adapters.filesystem import BoundedFilesystemAdapter
from project_creation_automation.adapters.git import GitProcessAdapter, SystemProcessRunner

__all__ = [
    "BoundedFilesystemAdapter",
    "GitProcessAdapter",
    "SystemProcessRunner",
]
