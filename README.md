# ProjectCreationAutomation

ProjectCreationAutomation is a safety-first, cross-platform Python tool for
planning and creating bounded local Git projects, with explicit opt-in GitHub
repository creation and push.

## Stage 5 status

The `project-create` CLI validates every request and prints a deterministic,
redacted plan before execution. It can create one local project directory,
initialize Git with `main`, create two starter files, stage only those files,
and create one initial commit. With `--github`, it can additionally authenticate
to GitHub, fail closed if the repository exists, create one repository, add one
credential-free HTTPS `origin`, and push only `main`.

Local-only operation remains the default. It does not load credentials, contact
GitHub, configure remotes, or push unless `create --github` is explicitly used.
It never loads an environment file during import, help, validation, or planning.
An optional post-success IDE launch supports only Visual Studio Code and
PyCharm. The default is `none`; planning, cancellation, and failed or
manual-recovery creation never discover or launch an IDE. The retained legacy
scripts are never used.

Git author identity must already be available to Git. The application does not
change repository, global, or system identity settings.

## Supported Python versions

The new package targets Python 3.10 through 3.13.

For an isolated development installation:

```text
python -m pip install -e ".[dev]"
```

Print CLI help:

```text
project-create --help
```

Generate a local-only plan:

```text
project-create plan example-project --project-root /absolute/approved/root
```

Generate a GitHub-enabled dry-run without loading credentials:

```text
project-create plan example-project --root /absolute/approved/root --github
```

Create locally with an interactive default-no confirmation:

```text
project-create create example-project --root /absolute/approved/root
```

For deliberate noninteractive confirmation:

```text
project-create create example-project --root /absolute/approved/root --confirm
```

Create a private GitHub repository after the same local safeguards:

```text
project-create create example-project --root /absolute/approved/root --github
```

Public repositories require the additional explicit choice:

```text
project-create create example-project --root /absolute/approved/root --github --public
```

`--private` may restate the safe default. `--private` and `--public` are
mutually exclusive, and `--public` without `--github` is rejected.

## Optional IDE launch

The selected launcher must already be available on `PATH`. Arbitrary executable
paths and flags are not accepted.

```text
project-create create example-project --root /absolute/approved/root --ide vscode
project-create create example-project --root /absolute/approved/root --ide pycharm
```

VS Code discovery checks only `code`. PyCharm discovery checks only `pycharm`
and `pycharm64.exe`. The resolved executable and completed project directory
must be regular, unambiguous paths. Launch uses an argument list, no shell, and
passes the project directory as exactly one argument.

IDE launch occurs only after local creation—and, when requested, GitHub creation
and push—has succeeded. Launcher absence or process-start failure is reported as
a warning while the completed project remains successful and is never rolled
back.

## GitHub credentials

The API token is never accepted as a command-line value. Credential precedence
for an explicit `create --github` execution is:

1. the process environment variable `GITHUB_TOKEN`;
2. the deprecated legacy alias `gt`;
3. a file supplied explicitly with `--env-file PATH`.

An explicit file must be ignored by version control, a regular non-link file,
UTF-8, bounded in size, and contain exactly one recognized token definition.
Other records are not imported, interpolation is disabled, and `os.environ` is
not modified. The file path and token details are never printed.

Prefer a narrowly authorized, fine-grained token when the account and GitHub
policy support repository creation, with only the repository Administration
write permission required by GitHub's creation endpoint. Contents, workflows,
secrets, issues, and collaborators are not used. If account policy requires a
classic token, limit it to `public_repo` for public creation or `repo` for
private creation; note that classic scopes are broader than this tool's API use.

The API token is not placed in the remote URL, Git configuration, subprocess
arguments, or Git subprocess environment. Pushing uses the user's separately
configured Git credential manager.

The approved root must already exist, be a directory, and have no ambiguous
symlink, junction, or reparse-point components. The destination must not exist
in any form. The absolute root is deliberately redacted from output.

The generated files are exactly:

- `README.md`, containing the validated name and a minimal description placeholder;
- `.gitignore`, containing a small Python cache and virtual-environment baseline.

Both files use exclusive creation and are never overwritten. Git stages only
these explicit names; broad staging is not used.

## Safety model

Project names and destination containment are validated before a plan can be
created. Existing files, directories, links, and other destination entries fail
closed. Read-only filesystem, Git, and—when selected—GitHub availability
preflight run before mutation; the default confirmation response is no.

The operation journals completed steps in memory. On failure it removes only
paths whose identities prove they were created by that invocation. Cleanup is
non-recursive. If unexpected content, a replaced path, a symlink/reparse point,
or Git metadata makes cleanup ambiguous, the directory is preserved and manual
review is required. The approved project root is never removed.

Before GitHub creation, failures follow the existing bounded local rollback
rules. After GitHub creation, no automatic remote deletion is attempted. An
origin-add or push failure preserves both states and reports manual recovery.
Repeated execution fails closed instead of adopting either existing resource.

The core is cross-platform and requires a compatible `git` executable and
native path semantics. IDE discovery is intentionally limited to `PATH`; it
does not inspect registries, user profiles, JetBrains Toolbox directories, or
machine-specific installation paths.

## Continuous integration

CI runs on pull requests and pushes to `master`, `main`, and the modernization
development branch. Its matrix covers Linux and Windows with Python 3.10, 3.11,
3.12, and 3.13. Each isolated job installs the bounded development extra, runs
dependency checking, compileall, Ruff, strict mypy, and the complete pytest
suite, then builds and inspects the wheel metadata and contents.

Workflow permissions are limited to `contents: read`, and superseded runs on
the same workflow/ref are cancelled. CI does not load environment files, enable
live GitHub integration, create repositories or projects, push branches, launch
IDEs, execute legacy scripts, or upload environment-bearing logs or artifacts.
Dependabot proposes bounded weekly updates for pip and GitHub Actions.

Live integration testing and release publication remain deferred. Stage 6 will
complete release documentation and decide the reviewed removal or archival of
legacy files.

See [the behavior specification](docs/behavior-specification.md) for ordering,
failure reporting, confirmation, and future rollback boundaries.

## Legacy files

`script.py`, `requirements.txt`, and `batch/create.bat` are retained temporarily
for historical comparison. They are not part of the new package or CLI and
should not be used as the safe Stage 5 workflow.

## Attribution

This repository continues Tim Eichinger's Windows implementation, which was
inspired by Kalle Hallden's original project-automation concept. David Mevorah's
version is a substantial modernization and security-focused continuation; it
does not claim independent authorship of the inherited concept or implementation.

See [ATTRIBUTION.md](ATTRIBUTION.md) for the full modification notice.

## License

ProjectCreationAutomation is free software distributed under the GNU General
Public License, version 3 or later. See [LICENSE](LICENSE).
