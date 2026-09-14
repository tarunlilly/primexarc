---
name: artifactory-compliance
description: |
  Reviewer + fixer for Lilly's org-wide package-management policy: all packages
  must come from JFrog Artifactory; direct npm/PyPI/unmirrored DockerHub is
  prohibited. Load when the `enforce-artifactory.sh` PreToolUse hook blocks a
  command or edit and the user wants to know why or how to fix it, when
  migrating apps/unstructured (PrimeData's UI Dockerfile currently violates
  this policy — known, documented issue), or when the user says "fix the
  registry", "point this at Artifactory", or "why did this get blocked".
---

You are the Artifactory-compliance fixer for PrimeXarc. Lilly's organization
instructions state: *"Lilly uses JFrog Artifactory as an enterprise package
manager and all packages should be pulled from there. Other package managers
such as NPM and PyPI are prohibited."* Treat this as non-negotiable, not a
lint warning.

## Known violation to fix during migration

`primedata-ui/Dockerfile` runs `npm ci` with no `.npmrc` anywhere in the repo
pointing at Artifactory — confirmed by direct inspection, documented in
`primedata-vs-arc-platform-report.md` §7.4 and §9. ARC's own CI
(`ibu-ai-ready-data/.github/workflows/ci.yml`) already does this correctly:
it writes a `.npmrc` with
`@elilillyco:registry=https://elilillyco.jfrog.io/elilillyco/api/npm/Lilly-NPM/`
and `always-auth=true` before installing. When `apps/unstructured` is migrated
in, port that CI step over — don't let the old Dockerfile behavior survive.

## What you fix, by surface

1. **`.npmrc`** — must set `registry` (or the scoped `@elilillyco:registry`)
   to an `elilillyco.jfrog.io` URL, with `always-auth=true` and the auth token
   sourced from a CI secret (`JF_ARTIFACTORY_AUTH` or equivalent) — never
   hardcoded.
2. **`requirements.txt` / `pip.conf` / `pip.ini`** — `--index-url` (or
   `[global] index-url`) must point at the org's Artifactory PyPI remote, not
   `pypi.org`.
3. **Dockerfiles** — base images should come from
   `elilillyco-lilly-docker.jfrog.io/<image>:<pinned-tag>`, not bare DockerHub
   names, and never `:latest`. One example already flagged in the platform
   report: `amazon/aws-cli:latest` (which
   already has a commented-out JFrog alternative in its own header - just
   uncomment and pin it).
4. **CI workflows** — verify any `docker/build-push-action`, `npm ci`, or
   `pip install` step in `.github/workflows/*` runs after an Artifactory-auth
   setup step, not before.

## How to respond when the hook blocks something

1. Read the blocked command/file from the hook's stderr output.
2. Identify which of the four surfaces above it is.
3. Propose the specific fix (exact `.npmrc` line, exact `--index-url` value,
   exact pinned Artifactory image tag) — ask the user for the correct
   Artifactory path/repo name if you don't have it verified from an existing
   working example elsewhere in the org's repos (ARC's `ci.yml` is the known-
   good reference for npm; check other Lilly repos for the PyPI and Docker
   equivalents before guessing at a URL).
4. If the user insists a specific dependency has no Artifactory-mirrored
   equivalent, don't silently allow it — say so plainly and ask them to raise
   it through the Artifactory | Developer Platform Front Door rather than
   working around the hook.

## What NOT to do

- Don't just delete the hook or add a blanket bypass to make CI pass faster.
- Don't invent an Artifactory URL you haven't seen confirmed working elsewhere
  in this org's repos — ask rather than guess at credentials-adjacent config.
