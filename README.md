# ProjectCreationAutomation

ProjectCreationAutomation is a safety-first command-line tool for creating one
bounded local Python project and Git repository, with explicit opt-in GitHub
creation/push and optional post-success IDE launch. It emphasizes reviewable
plans, conservative failure handling, narrow external boundaries, and
credential-safe diagnostics.

`1.0.0` finalizes the reviewed release candidate. Local project creation was
live-tested. Private GitHub repository creation, push, verification, and cleanup
were live-tested with the system-trust transport and local ignored credential
source. IDE launching remains verified through isolated test boundaries and was
not exercised by the live release test. Release publication remains deferred.

## Provenance and license

This GPL-3.0-or-later project is a substantial security-focused modernization
of Tim Eichinger's Windows implementation, which was inspired by Kalle
Hallden's original project-automation concept. David Mevorah leads the current
modernization. The original concept and historical implementation are not
claimed as independent work.

See [ATTRIBUTION.md](ATTRIBUTION.md) for the modification notice and
[LICENSE](LICENSE) for the GNU General Public License, version 3 or later.

## Features

- Python 3.10–3.13 on Linux and Windows.
- Deterministic, redacted plans with no external access.
- Local-only, private visibility, and no IDE by default.
- Explicit default-no confirmation before the first mutation.
- Direct-child destination validation and exclusive starter-file creation.
- Allowlisted Git commands, exact staging, and bounded diagnostics/timeouts.
- Explicit private-by-default GitHub repository creation and `main` push.
- Request-scoped native system certificate trust for GitHub HTTPS without
  global SSL injection or verification bypasses.
- Credential loading from process state or one explicit ignored environment
  file; tokens never appear in CLI arguments, remotes, or diagnostics.
- Optional VS Code or PyCharm launch only after all requested creation succeeds.
- Identity-aware rollback before remote creation and manual recovery afterward.
- Typed ports/adapters, in-memory fakes, strict static analysis, and isolated
  tests.

## Architecture and safety model

The package separates pure request validation/planning from side-effecting
adapters:

1. The CLI parses a fixed option set.
2. Domain models validate names, visibility, IDE choice, and direct-child path
   containment without filesystem access.
3. The planner renders a redacted, deterministic operation sequence.
4. The orchestrator performs fail-closed preflight and confirmation.
5. Injected filesystem, Git, GitHub, credential, and IDE adapters perform only
   their reviewed operations.

Help and `plan` never read credentials, discover an IDE, invoke Git, contact
GitHub, or create files. `create` rejects an existing or ambiguous destination.
Rollback removes only identities created by the current invocation and refuses
unsafe cleanup. After a GitHub repository may exist, automatic remote deletion
is forbidden and both states are preserved for manual recovery.

See [the architecture overview](docs/architecture.md),
[the behavior specification](docs/behavior-specification.md), and
[the security policy](SECURITY.md) for boundary details.

## Installation

From a checked-out source tree:

```text
python -m pip install .
```

For development:

```text
python -m pip install -e ".[dev]"
```

From a reviewed local wheel:

```text
python -m pip install project_creation_automation-1.0.0-py3-none-any.whl
```

Verify the console entry point:

```text
project-create --help
```

Git must already be available on `PATH`, with an author identity configured for
commits. The application never modifies Git identity configuration.

## Planning and local creation

Use harmless synthetic names and an approved absolute root:

```text
project-create plan sample-project --root /srv/projects
```

Planning is a dry-run: it prints `mutation_performed: no` and performs no
preflight or mutation.

Interactive creation prompts with a default-no confirmation:

```text
project-create create sample-project --root /srv/projects
```

Deliberate noninteractive confirmation is explicit:

```text
project-create create sample-project --root /srv/projects --confirm
```

The approved root must already exist. The destination must not exist. The
generated project contains only `README.md` and `.gitignore`, followed by one
initial commit on `main`.

## GitHub-enabled creation

GitHub behavior is never inferred from a token. Request it explicitly:

```text
project-create plan sample-project --root /srv/projects --github
project-create create sample-project --root /srv/projects --github
```

Repositories are private by default. Public creation requires both flags:

```text
project-create create sample-project --root /srv/projects --github --public
```

The GitHub API token is used for account/repository API calls only. Prefer a
fine-grained token whose repository Administration permission allows repository
creation under the account's policy. Contents, workflows, secrets, issues, and
collaborator permissions are not used by the API adapter. If account policy
requires a classic token, `public_repo` supports public creation while `repo`
is required for private creation and is broader than this tool's API use.

GitHub API requests use a request-scoped native system trust context supplied
by the bounded `truststore` runtime dependency. Certificate and hostname
verification remain mandatory; certificate failures return the redacted
`github_tls_verification_failed` result. The application never injects a global
SSL context or loads bundled/private certificate files.

Pushing does not place the API token in the remote URL or Git environment.
Configure a Git credential manager separately for the HTTPS push.

## Credential configuration

For explicit `create --github`, precedence is:

1. `GITHUB_TOKEN` in the process environment;
2. deprecated compatibility alias `gt`;
3. a file passed with `--env-file`.

Copy [.env.example](.env.example) to an ignored `.env`, set exactly one
recognized value, restrict its permissions, and pass it explicitly:

```text
project-create create sample-project --root /srv/projects --github --env-file .env
```

The parser is UTF-8-only, bounded, literal, and non-interpolating. It rejects
links/reparse points, directories, duplicates, malformed records, and unsafe
encoding. Environment files are never loaded during import, help, validation,
or planning.

## Optional IDE launch

Supported choices are exactly:

- `none` (default)
- `vscode`, discovered as `code`
- `pycharm`, discovered as `pycharm` or `pycharm64.exe`

The launcher must be on `PATH`; arbitrary executable paths and flags are not
accepted.

```text
project-create create sample-project --root /srv/projects --ide vscode
project-create create sample-project --root /srv/projects --ide pycharm
```

IDE discovery and launch occur only after local creation and any requested
GitHub push succeed. Missing or failed launch is a post-success warning and
never rolls back the completed project.

## Failure and recovery

Before remote creation, failures use identity-aware rollback when cleanup can be
proven safe. Unexpected content, replaced paths, symlink/reparse ambiguity, or
partial Git state causes preservation for manual review.

After remote creation, origin-add or push failure preserves both the local and
remote repositories and returns a distinct manual-recovery result. Ambiguous
repository-creation responses are not retried automatically. Existing local or
remote resources are never adopted, overwritten, or deleted.

## Development and verification

```text
python -m pip check
python -m compileall -q src tools
python -m ruff check src tests tools
python -m mypy --strict src tests tools
python -m pytest -q -p no:cacheprovider
python -m build --wheel --outdir dist
python tools/verify_wheel.py dist
```

CI runs the same policy on Linux and Windows with Python 3.10, 3.11, 3.12, and
3.13. Workflow permission is limited to `contents: read`; superseded runs are
cancelled. CI does not enable live integration, execute project creation, push,
launch IDEs, publish releases, or upload environment-bearing artifacts.
Dependabot proposes bounded weekly pip and GitHub Actions updates.

## Limitations and non-goals

- Stage 7 live-tested local creation and private GitHub creation, push,
  verification, and cleanup; it deliberately selected `--ide none`.
- IDE discovery and launching are verified through isolated adapter/process
  boundaries, not through the Stage 7 live release test.
- Release publication and branch standardization are deferred.
- Only GitHub HTTPS remotes are supported.
- Only VS Code and PyCharm are supported IDE choices.
- Existing projects and repositories are never imported or adopted.
- The operating system certificate store must trust the GitHub API connection.
- Automatic remote deletion and force cleanup are intentionally unavailable.
- This project has not received an independent professional security audit.
- Screenshots and claims beyond reviewed automated and Stage 7 live evidence
  are intentionally omitted.

The historical batch/Python runtime was retired from the current tree and
remains available in Git history. See
[the migration notes](docs/migration-from-legacy.md) and
[CHANGELOG.md](CHANGELOG.md).
