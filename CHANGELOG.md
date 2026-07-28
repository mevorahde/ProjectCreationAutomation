# Changelog

All notable changes are documented here. The project follows semantic version
intent, while release publication remains deferred.

## Unreleased

- Pull-request review, branch standardization, and release publication.

## 1.0.0 - 2026-07-28

- Finalized the reviewed release candidate after live local project creation
  and live private GitHub repository creation, `main` push, remote verification,
  and explicit remote/local cleanup.
- Enforced request-scoped native system certificate trust for GitHub HTTPS with
  mandatory certificate and hostname verification and a dedicated redacted
  TLS-verification failure result.
- Kept GitHub tokens local, explicitly sourced, ignored by Git, excluded from
  remotes and child-process environments, and redacted from diagnostics.
- Retained IDE launching as an isolated-boundary-tested feature; the Stage 7
  live release test deliberately used `--ide none` and did not launch an IDE.
- Promoted package, runtime, policy-test, and wheel metadata to final version
  `1.0.0`.

## 1.0.0rc1

- Replaced the historical batch/Python workflow with a typed, cross-platform
  `project-create` package and console entry point.
- Added deterministic redacted planning, default-no confirmation, bounded local
  filesystem creation, allowlisted Git operations, and conservative rollback.
- Added explicit private-by-default GitHub repository creation and push with
  bounded credential, HTTPS, and manual-recovery behavior.
- Added optional post-success VS Code and PyCharm launching through reviewed
  `PATH` candidates and a non-shell process boundary.
- Added Linux/Windows CI for Python 3.10–3.13, Dependabot, strict typing, lint,
  isolated tests, and real-wheel policy verification.
- Added release metadata, GPL and attribution packaging, security guidance,
  architecture documentation, migration notes, and reviewed legacy retirement.
