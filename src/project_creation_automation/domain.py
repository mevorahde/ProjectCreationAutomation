"""Immutable domain models and lexical path validation."""

from __future__ import annotations

import ntpath
import os
import posixpath
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath, PurePosixPath, PureWindowsPath

_PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_SHELL_METACHARACTERS = frozenset("&|;<>($)`'\"!^%*?[]{}~")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


class Visibility(str, Enum):
    """Supported remote repository visibility."""

    PRIVATE = "private"
    PUBLIC = "public"


class IDEChoice(str, Enum):
    """Narrowly supported optional post-success IDE selections."""

    NONE = "none"
    PYCHARM = "pycharm"
    VSCODE = "vscode"


class IDELaunchStatus(str, Enum):
    """Predefined, redacted outcomes for optional IDE launching."""

    NOT_REQUESTED = "not_requested"
    NOT_PERFORMED = "not_performed"
    LAUNCHED = "launched"
    UNAVAILABLE = "launcher_unavailable"
    FAILED = "launch_failed"


class PathFlavor(str, Enum):
    """Lexical path rules used without filesystem access."""

    POSIX = "posix"
    WINDOWS = "windows"

    @classmethod
    def native(cls) -> PathFlavor:
        """Return the host's lexical path flavor without filesystem access."""

        return cls.WINDOWS if os.name == "nt" else cls.POSIX


class DomainError(Exception):
    """Base exception whose representation never includes request values."""

    default_message = "The project request is invalid."

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or self.default_message
        super().__init__(self.message)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r})"


class ProjectNameError(DomainError):
    """A project label failed safety validation."""


class ProjectRootError(DomainError):
    """An approved root failed lexical validation."""


class ContainmentError(DomainError):
    """A destination was not contained by its approved root."""


class ExecutionUnavailableError(DomainError):
    """Real mutation is intentionally unavailable in Stage 2."""

    default_message = "Real project creation is not implemented in Stage 2; no changes were made."


class FilesystemSafetyError(DomainError):
    """A local filesystem operation could not be proven safe."""

    default_message = "The local project could not be created safely."


class GitOperationError(DomainError):
    """A local Git operation failed without exposing process diagnostics."""

    default_message = "The local Git operation failed."


class CredentialError(DomainError):
    """A GitHub credential could not be loaded safely."""

    default_message = "A GitHub credential could not be loaded safely."


class GitHubOperationError(DomainError):
    """A GitHub operation failed without exposing transport diagnostics."""

    default_message = "The GitHub operation failed safely."


class GitHubCreationUncertainError(GitHubOperationError):
    """A creation request may have succeeded and must not be retried or rolled back."""


class GitIdentityError(GitOperationError):
    """Git could not create a commit with the available identity."""

    default_message = (
        "Git author identity is unavailable. Configure it separately and try again; "
        "no identity setting was changed."
    )


class UnsupportedExecutionError(DomainError):
    """A request includes execution that is unavailable in this stage."""

    default_message = "The requested integration is not available."


@dataclass(frozen=True, slots=True)
class GitHubAccount:
    """Validated GitHub account identity."""

    login: str

    def __repr__(self) -> str:
        return "GitHubAccount(login=<redacted>)"


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    """Validated created-repository identity and credential-free remote URL."""

    owner: str
    name: str
    remote_url: str

    def __repr__(self) -> str:
        return (
            "GitHubRepository(owner=<redacted>, name=<project>, "
            "remote_url=<canonical-https-url>)"
        )


@dataclass(frozen=True, slots=True)
class ProjectLocation:
    """Lexically normalized root and direct-child destination."""

    root: PurePath
    destination: PurePath
    flavor: PathFlavor

    def __repr__(self) -> str:
        return (
            "ProjectLocation(root=<approved-root>, "
            "destination=<approved-root>/<project>, "
            f"flavor={self.flavor.value!r})"
        )


@dataclass(frozen=True, slots=True)
class ProjectRequest:
    """A validated, immutable project-creation request."""

    project_name: str
    location: ProjectLocation
    visibility: Visibility = Visibility.PRIVATE
    ide: IDEChoice = IDEChoice.NONE
    create_github_repository: bool = False

    @classmethod
    def create(
        cls,
        *,
        project_name: str,
        project_root: str,
        visibility: Visibility = Visibility.PRIVATE,
        ide: IDEChoice = IDEChoice.NONE,
        create_github_repository: bool = False,
        path_flavor: PathFlavor | None = None,
    ) -> ProjectRequest:
        """Validate values and construct an immutable request."""

        normalized_name = validate_project_name(project_name)
        location = resolve_project_location(
            project_root=project_root,
            project_name=normalized_name,
            flavor=path_flavor or PathFlavor.native(),
        )
        return cls(
            project_name=normalized_name,
            location=location,
            visibility=visibility,
            ide=ide,
            create_github_repository=create_github_repository,
        )


def validate_project_name(project_name: str) -> str:
    """Return a normalized safe label or raise a redacted domain error."""

    if not isinstance(project_name, str) or not project_name:
        raise ProjectNameError("project_name_empty")
    normalized = unicodedata.normalize("NFC", project_name)
    if not normalized or normalized != normalized.strip():
        raise ProjectNameError("project_name_whitespace")
    if normalized.endswith((".", " ")):
        raise ProjectNameError("project_name_unsafe_suffix")
    if normalized in {".", ".."}:
        raise ProjectNameError("project_name_dot_segment")
    if PurePosixPath(normalized).is_absolute() or PureWindowsPath(normalized).is_absolute():
        raise ProjectNameError("project_name_absolute")
    if "/" in normalized or "\\" in normalized:
        raise ProjectNameError("project_name_separator")
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise ProjectNameError("project_name_control_character")
    if any(character in _SHELL_METACHARACTERS for character in normalized):
        raise ProjectNameError("project_name_shell_metacharacter")
    if not _PROJECT_NAME_PATTERN.fullmatch(normalized):
        raise ProjectNameError("project_name_unsupported_character")
    windows_stem = normalized.split(".", maxsplit=1)[0].upper()
    if windows_stem in _WINDOWS_RESERVED_NAMES:
        raise ProjectNameError("project_name_windows_reserved")
    return normalized


def resolve_project_location(
    *, project_root: str, project_name: str, flavor: PathFlavor
) -> ProjectLocation:
    """Resolve a direct-child destination lexically, without filesystem access."""

    safe_name = validate_project_name(project_name)
    root = _normalize_absolute_root(project_root, flavor)
    destination = root / safe_name
    if not _is_direct_child(root=root, destination=destination, flavor=flavor):
        raise ContainmentError("destination_outside_approved_root")
    return ProjectLocation(root=root, destination=destination, flavor=flavor)


def _normalize_absolute_root(project_root: str, flavor: PathFlavor) -> PurePath:
    invalid_root = (
        not isinstance(project_root, str)
        or not project_root
        or project_root != project_root.strip()
    )
    if invalid_root:
        raise ProjectRootError("project_root_invalid")
    if any(unicodedata.category(character).startswith("C") for character in project_root):
        raise ProjectRootError("project_root_control_character")

    if flavor is PathFlavor.WINDOWS:
        normalized = ntpath.normpath(project_root)
        root: PurePath = PureWindowsPath(normalized)
    else:
        normalized = posixpath.normpath(project_root)
        root = PurePosixPath(normalized)

    if not root.is_absolute():
        raise ProjectRootError("project_root_not_absolute")
    if ".." in root.parts:
        raise ProjectRootError("project_root_unresolved_parent")
    return root


def _is_direct_child(*, root: PurePath, destination: PurePath, flavor: PathFlavor) -> bool:
    if destination.parent != root:
        return False
    if flavor is PathFlavor.WINDOWS:
        return str(destination.parent).casefold() == str(root).casefold()
    return destination.parent == root
