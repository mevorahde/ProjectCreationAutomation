# Safe creation behavior specification

## Status

Stage 4 implements validated planning, confirmed local project creation, and
explicit opt-in GitHub repository creation plus push. Local-only remains the
default. IDE execution remains unavailable. Imports, help, validation, and
planning perform no external access or mutation.

## Request invariants

- A project name is normalized to Unicode NFC and must be a non-empty ASCII
  identifier composed only of letters, digits, `_`, `-`, and `.`.
- A name must begin with a letter or digit and must not end in a space or dot.
- Absolute names, separators, dot segments, control characters, shell
  metacharacters, and Windows reserved device names are rejected.
- Project roots are absolute and lexically normalized using explicit POSIX or
  Windows path semantics. Normalization does not access the filesystem.
- The destination must be a direct child contained by the approved project root.
- Visibility defaults to private. Public visibility must be requested explicitly.
- The absence of an IDE choice means that no IDE will be launched.
- GitHub repository creation is optional and is never inferred from credentials
  or environment variables.

## Preflight and fail-closed policy

Before local mutation, adapters verify that:

1. The validated destination remains contained by the approved root.
2. The approved root already exists, is a directory, and has no ambiguous
   symlink, junction, or reparse-point component.
3. The local destination does not exist as a file, directory, link, junction,
   reparse point, or other entry.
4. Git is available.
5. When `--github` is selected, a recognized credential is available, the
   current account identity is valid, and repository absence is certain.

An existing destination, unavailable preflight check, ambiguous result, or
invalid configuration stops the operation. Overwrite, reuse, adoption, and
force behavior are unavailable.

## Dry-run and confirmation

A dry-run produces a deterministic, redacted creation plan without probing the
filesystem or network. The plan must not contain tokens, passwords, environment
values, or an absolute project-root path.

Local execution requires both:

1. A successfully reviewed dry-run for the same normalized request.
2. Explicit confirmation immediately before the first mutation.

The interactive confirmation defaults to no. `--confirm` is the deliberate
noninteractive confirmation. Imports, help, validation, and dry-run never load
credentials or environment files, contact GitHub, invoke Git, or mutate state.

GitHub is enabled only by `--github`. Visibility defaults to private; public
creation additionally requires `--public`. Conflicting public/private choices
are rejected.

The canonical process variable is `GITHUB_TOKEN`. The tracked legacy alias `gt`
is supported narrowly and is deprecated. Process state takes precedence over
an explicit `--env-file`. Environment-file parsing is literal, bounded,
UTF-8-only, non-interpolating, and accepts exactly one recognized token field.
It rejects directories, links/reparse points, malformed records, duplicates,
empty values, and unsafe encoding without exposing values or paths.

## Deterministic operation order

The intended sequence is:

1. Validate the request.
2. Verify local destination availability.
3. Verify Git availability.
4. If selected, authenticate and verify remote repository absence.
5. Require explicit confirmation.
6. Create exactly one direct-child local directory.
7. Exclusively create `README.md` and `.gitignore`.
8. Initialize Git with `main` as the initial branch.
9. Stage exactly `README.md` and `.gitignore`.
10. Verify that the index contains exactly those files.
11. Create one initial commit.
12. If selected, create one GitHub repository with `auto_init=false`.
13. Verify no `origin` exists and add exactly one canonical HTTPS `origin`.
14. Push only `main` and establish its upstream.

`README.md` contains only the validated project display name and a minimal
description placeholder. `.gitignore` contains a reviewed Python baseline.
No environment, credential, license, package, or IDE files are generated.

## Failure and rollback boundary

Every completed step and failure is reported using predefined redacted event
names. Execution stops at the first failure.

The filesystem adapter records path type, device, and inode identities for
created paths. Rollback removes only matching recorded starter files and then
uses non-recursive directory removal. Any unexpected content, replacement,
symlink/reparse point, partial Git metadata, or unjournaled entry causes cleanup
refusal and a manual-review result. The approved root and pre-existing content
are never removed or altered.

Git is invoked with argument lists, `shell=False`, explicit working directories,
captured bounded output, timeouts, and explicit starter-file staging. Hooks and
commit signing are disabled for the generated commit without changing
configuration. If author identity is unavailable, no identity is configured.

The GitHub API origin is fixed to HTTPS. Requests use Bearer authentication,
versioned API headers, bounded connect/read timeouts and response bodies, and no
automatic retry of repository-creation POST requests. Authentication,
authorization, rate-limit, conflict, timeout, transport, malformed response,
and server failures become predefined redacted errors.

Before repository creation, failures use the bounded local rollback policy.
Once GitHub reports successful creation, automatic remote deletion is forbidden.
Failures while checking/adding `origin` or pushing preserve local and remote
state and return manual recovery required. Existing local or remote resources
are never replaced, renamed, removed, or adopted.
