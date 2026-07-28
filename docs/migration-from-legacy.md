# Migration from the legacy workflow

The historical `script.py`, `batch/create.bat`, and obsolete
`requirements.txt` workflow was retired for the `1.0.0` release.
Those files remain available in Git history and the reviewed batch
customization has a separate recovery patch. Neither is part of the supported
runtime or wheel.

Use the modern entry point:

```text
project-create plan sample-project --root /srv/projects
project-create create sample-project --root /srv/projects
```

Important differences:

- local-only, private visibility, and no IDE are defaults;
- every request renders a redacted plan;
- creation requires interactive default-no or explicit `--confirm`
  confirmation;
- GitHub behavior requires `--github`;
- tokens are never command-line arguments;
- only VS Code and PyCharm launchers are supported, and only from `PATH`;
- partial or ambiguous state is preserved rather than forcefully overwritten
  or deleted.

Do not copy commands or dependency instructions from historical revisions into
the supported `1.0.0` workflow.
