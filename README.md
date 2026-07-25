# ProjectCreationAutomation

ProjectCreationAutomation is being rebuilt as a safety-first, cross-platform
Python tool for planning and, in later stages, creating local Git projects and
optional GitHub repositories.

## Stage 2 status

The new `project-create` CLI is **planning only**. It validates a request and
prints a deterministic, redacted dry-run plan. It does not:

- create or overwrite files or directories;
- invoke Git;
- contact or authenticate to GitHub;
- read `.env`;
- launch an IDE; or
- execute the retained legacy Python or batch scripts.

Real Git, GitHub, filesystem, and IDE adapters are not implemented yet. The
reserved `create` command fails safely and reports that no changes were made.

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

Include optional future GitHub and IDE steps:

```text
project-create plan example-project --project-root /absolute/approved/root --github --ide visual-studio-code
```

The absolute project root is deliberately redacted from plan output. Remote
visibility defaults to `private`; `public` must be selected explicitly.

## Safety model

Project names and destination containment are validated before a plan can be
created. Existing local directories and existing remote repositories are
specified to fail closed. Future execution will require a reviewed dry-run and
explicit confirmation before the first mutation.

See [the behavior specification](docs/behavior-specification.md) for ordering,
failure reporting, confirmation, and future rollback boundaries.

## Legacy files

`script.py`, `requirements.txt`, and `batch/create.bat` are retained temporarily
for historical comparison. They are not part of the new package or CLI and
should not be used as the safe Stage 2 workflow.

## Attribution

This repository continues Tim Eichinger's Windows implementation, which was
inspired by Kalle Hallden's original project-automation concept. David Mevorah's
version is a substantial modernization and security-focused continuation; it
does not claim independent authorship of the inherited concept or implementation.

See [ATTRIBUTION.md](ATTRIBUTION.md) for the full modification notice.

## License

ProjectCreationAutomation is free software distributed under the GNU General
Public License, version 3 or later. See [LICENSE](LICENSE).
