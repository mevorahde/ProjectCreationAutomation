# ProjectCreationAutomation

ProjectCreationAutomation is a safety-first, cross-platform Python tool for
planning and creating bounded local Git projects. Optional GitHub and IDE
execution are planned for later stages.

## Stage 3 status

The `project-create` CLI validates every request and prints a deterministic,
redacted plan before execution. Stage 3 can create one local project directory,
initialize Git with `main`, create two starter files, stage only those files,
and create one initial commit.

It does not contact or authenticate to GitHub, configure remotes, push, read
`.env`, launch an IDE, or execute the retained legacy Python or batch scripts.

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

Create locally with an interactive default-no confirmation:

```text
project-create create example-project --root /absolute/approved/root
```

For deliberate noninteractive confirmation:

```text
project-create create example-project --root /absolute/approved/root --confirm
```

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
closed. Read-only filesystem and Git preflight run before confirmation; the
default confirmation response is no.

The operation journals completed steps in memory. On failure it removes only
paths whose identities prove they were created by that invocation. Cleanup is
non-recursive. If unexpected content, a replaced path, a symlink/reparse point,
or Git metadata makes cleanup ambiguous, the directory is preserved and manual
review is required. The approved project root is never removed.

The core is cross-platform. Stage 3 requires a compatible `git` executable and
native path semantics. Windows IDE integration and all GitHub behavior remain
unimplemented.

See [the behavior specification](docs/behavior-specification.md) for ordering,
failure reporting, confirmation, and future rollback boundaries.

## Legacy files

`script.py`, `requirements.txt`, and `batch/create.bat` are retained temporarily
for historical comparison. They are not part of the new package or CLI and
should not be used as the safe Stage 3 workflow.

## Attribution

This repository continues Tim Eichinger's Windows implementation, which was
inspired by Kalle Hallden's original project-automation concept. David Mevorah's
version is a substantial modernization and security-focused continuation; it
does not claim independent authorship of the inherited concept or implementation.

See [ATTRIBUTION.md](ATTRIBUTION.md) for the full modification notice.

## License

ProjectCreationAutomation is free software distributed under the GNU General
Public License, version 3 or later. See [LICENSE](LICENSE).
