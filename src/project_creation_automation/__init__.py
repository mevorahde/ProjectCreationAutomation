"""Safety-first local project creation and planning.

Importing this package performs no configuration loading, filesystem access,
network access, subprocess launch, or mutation.
"""

from project_creation_automation.domain import (
    IDEChoice,
    PathFlavor,
    ProjectRequest,
    Visibility,
)
from project_creation_automation.planning import CreationPlan, build_creation_plan

__all__ = [
    "CreationPlan",
    "IDEChoice",
    "PathFlavor",
    "ProjectRequest",
    "Visibility",
    "build_creation_plan",
]

__version__ = "1.0.0"
