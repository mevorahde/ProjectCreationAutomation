# Safe creation behavior specification

## Status

Stage 3 implements validated planning plus confirmed local project creation and
Git initialization. GitHub, remotes, push, and IDE execution remain unavailable.
Imports, help, validation, and planning perform no mutation.

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
`.env`, contact GitHub, or perform mutation.

## Deterministic operation order

The intended sequence is:

1. Validate the request.
2. Verify local destination availability.
3. Verify Git availability.
4. Require explicit confirmation.
5. Create exactly one direct-child local directory.
6. Exclusively create `README.md` and `.gitignore`.
7. Initialize Git with `main` as the initial branch.
8. Stage exactly `README.md` and `.gitignore`.
9. Verify that the index contains exactly those files.
10. Create one initial commit.

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
captured output, timeouts, explicit starter-file staging, and no remote
commands. Hooks and commit signing are disabled for the generated commit without
changing configuration. If author identity is unavailable, no identity is
configured; failure follows the same bounded rollback decision.
