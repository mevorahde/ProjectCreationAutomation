# Safe creation behavior specification

## Status

Stage 2 implements validation and deterministic planning only. It does not
create directories, run Git, contact GitHub, launch an IDE, or read credentials.
Mutation remains unavailable until later stages implement and verify adapters.

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

Before any future mutation, adapters must verify that:

1. The validated destination remains contained by the approved root.
2. The local destination does not already exist.
3. If GitHub creation was requested, the remote repository does not already
   exist.
4. All required tools and configuration are available.

An existing local directory, existing remote repository, unavailable preflight
check, ambiguous result, or invalid configuration must stop the operation.
Overwrite, reuse, adoption, and force behavior are not defaults.

## Dry-run and confirmation

A dry-run produces a deterministic, redacted creation plan without probing the
filesystem or network. The plan must not contain tokens, passwords, environment
values, or an absolute project-root path.

Future execution requires both:

1. A successfully reviewed dry-run for the same normalized request.
2. Explicit confirmation immediately before the first mutation.

GitHub creation requires the same confirmation; possession of a credential is
never consent. Imports, help, validation, and dry-run must never load `.env`,
authenticate, contact GitHub, or perform any mutation.

## Deterministic operation order

The intended sequence is:

1. Validate the request.
2. Verify local destination availability.
3. Verify remote availability when GitHub was requested.
4. Require explicit confirmation.
5. Create the local directory.
6. Initialize Git.
7. Create initial files.
8. Create the initial commit.
9. Create the remote repository when requested.
10. Add the remote.
11. Push.
12. Launch an optional IDE only after every required creation step succeeds.

The plan omits conditional steps that were not requested but never reorders
remaining steps.

## Failure and rollback boundary

Every completed step and failure must be reported through a redacting
operational reporter. Execution stops at the first failure.

Stage 3 must define rollback per adapter. Local files created by the operation
may eventually be eligible for carefully bounded cleanup. Published commits,
pre-existing paths, Git configuration not created by the operation, and remote
repositories are outside an automatic rollback boundary unless a later,
separately reviewed design proves the action safe. Partial failure must be
reported rather than concealed.
