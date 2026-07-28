# Security policy

## Supported versions

Security fixes currently target the `1.0.0` release line on the active
modernization branch. Earlier development stages and the retired legacy
scripts are unsupported. The final version has completed reviewed live local
and private GitHub integration testing. Release publication remains deferred.

## Reporting

If GitHub displays a private **Report a vulnerability** option for this
repository, use it for a suspected vulnerability. Otherwise use a non-public
repository-owner contact channel available through GitHub. If no private
channel is available, open a sanitized public issue requesting private
coordination without including exploit details. Do not place tokens, private
repository names, real paths, environment files, or exploit details in a public
issue.

Include the affected version, platform, a minimal synthetic reproduction, the
expected safety boundary, and the observed impact. No response-time guarantee
or paid support commitment is made.

## Threat boundaries

The application validates project names and direct-child containment, defaults
to local-only/private/no-IDE behavior, requires confirmation before mutation,
and uses injected boundaries for testing. It does not protect against a
malicious operating system, compromised Python or Git installation, hostile
administrator, compromised GitHub account, or concurrent privileged process
that can replace files after validation.

GitHub access is explicit opt-in. API tokens are accepted only from the process
environment or an explicit ignored environment file, are redacted from
representations and diagnostics, and are removed from Git and IDE child
environments. Python cannot guarantee erasure of every immutable in-memory
copy. Git pushes use the user's separately configured credential manager.

GitHub API HTTPS uses a request-scoped native system certificate-store context
through a bounded `truststore` dependency. Certificate and hostname validation
remain required. The application does not globally patch SSL, disable
verification, trust arbitrary private certificates, bypass hostnames, or pin
server certificates. The operating-system trust store and its administrators
remain external security boundaries.

Subprocesses use argument vectors and `shell=False`. Git operations are
allowlisted and bounded; IDE discovery accepts only reviewed launcher names
from `PATH`. Even with these controls, Git, credential managers, HTTPS/TLS,
GitHub, and IDE executables remain external trust boundaries.

Rollback removes only identities created by the current invocation. Ambiguous
or replaced paths, unexpected content, partial Git state, and any failure after
remote creation are preserved for manual recovery. Automatic GitHub deletion
is never attempted.

This project has automated tests and a documented threat model, but it has not
received an independent professional security audit.
