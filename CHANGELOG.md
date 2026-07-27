# Changelog

All notable changes are documented here. The project follows semantic version
intent, while release publication remains deferred.

## Unreleased

- Live GitHub/Git/IDE integration review.
- Pull-request review, branch standardization, and release publication.

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
