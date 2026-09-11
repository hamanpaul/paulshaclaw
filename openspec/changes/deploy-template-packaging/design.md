## Context

The deploy planner owns the template catalog and the installed wheel is the production boundary.
The same asset set therefore needs two independent checks: archive contents must match source,
and install/upgrade must successfully read and render the assets before mutating host state.

## Goals / Non-Goals

**Goals:**

- Keep source, sdist, rebuilt wheel, and wheel template paths in exact set parity.
- Make release and PR artifact checks call one checker.
- Keep template preflight ahead of writes, checkpoints, loginctl, and systemctl.
- Make packaging acceptance executable in both CI and local preflight.

**Non-Goals:**

- No release publication, tag, merge, archive, or issue closure.
- No change to the planner's deployment catalog or systemd ownership.
- No claim that a host without systemd started a service.

## Decisions

1. `templates/**/*.tmpl` remains the package-data declaration, with `setuptools>=62.3` as the
   build-system floor required for recursive expansion.
2. `scripts/check-release-artifacts.py` compares paths as sets and rejects missing, unexpected,
   duplicate, non-template, forbidden-content, unreadable, corrupt, and genuinely empty assets.
   A directory containing a non-template file is not itself an empty directory.
3. `preflight_templates()` returns prepared renderings so the apply loop uses the content that
   crossed the preflight boundary. `TemplatePreflightError` is formatted by one installer helper
   for both runtime and plan-only CLI paths.
4. CI and `scripts/preflight-tests.sh` install `build` in the environment that invokes pytest;
   `build` stays a test/build tool and is not added to runtime dependencies.
5. Installed-wheel tests derive expected applied paths from the planner rather than hardcoding a
   template count, so future catalog changes fail only on an actual contract mismatch.

## Verification

- Run the focused deploy packaging tests and the complete repository pytest gate.
- Run the repository-declared OpenSpec and policy preflight when the corresponding local engine is
  available.
- Run the artifact checker through both release entry points without publishing an artifact.
