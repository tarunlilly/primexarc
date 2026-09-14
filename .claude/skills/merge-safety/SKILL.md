---
name: merge-safety
description: >
  Use this skill before any git commit or push in this repo, or when verifying
  a merger PR is ready. Triggers on phrases like "ready to push", "safe to
  commit", "ready to merge", "validate before commit", "pre-push check", "is
  this ready". Also triggers automatically via the require-merge-safety.sh
  PreToolUse hook when git commit or push is attempted. Especially important
  when changes touch auth (Bouncer/MSAL), apps/structured/**/db/**,
  apps/unstructured/**/db/**, package registries, Dockerfiles, .gitignore, or
  anything under packages/shared-ui. This is the root-repo equivalent of ARC's
  own deploy-safety skill (which still governs apps/structured internally
  after migration) — this one adds the merger-specific checks: boundary
  violations and dual-schema collisions.
version: 1.0.0
user-invocable: true
tools: Read, Bash, Agent
---

# Merge Safety Validation

Run these steps in order. Stop and report clearly on the first FAIL before
continuing to the next step — don't let a later PASS paper over an earlier FAIL.

## 1. Boundary check

```bash
git diff --cached --name-only
```

For every changed file under `apps/structured/**`, grep its diff for references
to `apps/unstructured` (paths, `apps.unstructured` dotted imports, `../unstructured/`
relative imports). Do the mirror check for `apps/unstructured/**` referencing
`apps/structured`. This duplicates what `enforce-boundary.sh` already blocks at
write-time — it exists here as a whole-diff sweep in case multiple small edits
combined to create a violation the per-write hook didn't catch (e.g. a new
import added in one file that only becomes a violation once a second file
exports the wrong thing).

- **PASS**: no cross-app references found.
- **FAIL**: list file:line. If the change is a legitimate shared-code proposal,
  it must go through the `boundary-guardian` agent first — this is not
  something to wave through manually.

## 2. Package registry check

```bash
git diff --cached --name-only | grep -E '\.npmrc$|requirements.*\.txt$|pip\.(conf|ini)$|Dockerfile'
```

For each matched file, confirm it points at an `elilillyco.jfrog.io` /
`elilillyco-lilly-docker.jfrog.io` registry, not `registry.npmjs.org` or
`pypi.org`, and that Dockerfile `FROM` lines aren't unpinned public images.
This mirrors `enforce-artifactory.sh`'s logic as a diff-level sweep.

- **PASS**: no non-Artifactory registry references in changed files.
- **FAIL**: route to the `artifactory-compliance` agent for the fix.

## 3. DB schema collision check

```bash
git diff --cached --name-only | grep -E '(^|/)(db|migrations)/|\.sql$'
```

If files under BOTH `apps/structured/**/db/**` (or migrations) AND
`apps/unstructured/**/db/**` (or migrations) appear in the same diff, stop and
ask the user to confirm this is intentional — the two apps use different
Postgres schemas (`history_assessment` fixed for ARC, configurable/`public`-
default for PrimeData) and should almost never need coordinated schema changes
in one commit.

- **PASS**: DB changes touch at most one app, or the cross-app change was
  explicitly confirmed by the user with a stated reason.
- **FAIL**: split into separate commits/PRs, or get explicit confirmation.

## 4. Env / secret hygiene (repo-wide)

```bash
git diff --cached --name-only | xargs -I{} sh -c 'echo {}; git diff --cached -- {}' 2>/dev/null | grep -nE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9+/]{32,}'
```

Check any matches are inside `*.example` template files only (and are
placeholder-shaped, not real-looking) — never in a real `.env` or a non-example
config file.

```bash
git diff --cached --name-only | grep -E '^\.env|\.env$'
```

- **PASS**: no real `.env` file staged; any GUID/token-shaped strings found are
  in `*.example` files and look like placeholders.
- **FAIL**: unstage the file (`git restore --staged <file>`) and report it.

## 5. Auth-change check

```bash
git diff --cached --name-only | grep -iE 'bouncer|msal|auth|dependencies\.py|middleware'
```

If any match, confirm the `auth-unification-reviewer` agent has reviewed this
specific change (ask the user, or look for review notes in the commit message
/ PR description). Do not treat "it's a small change" as an exemption — the
auth model migration is exactly where small changes cause the most damage
(see that agent's description for why).

- **PASS**: no auth-relevant files changed, or reviewer sign-off confirmed.
- **FAIL**: route to `auth-unification-reviewer` before proceeding.

## 6. Test parity spot-check

If the diff touches `apps/structured/backend/**`, confirm
`test_scorer_is_deterministic()` still exists and hasn't been modified in a way
that weakens its assertions (it should still run the scorer multiple times and
assert identical output). If the diff touches CI workflow files, confirm no
test job was newly commented out or disabled (see `ci-test-parity` agent for
the pre-existing debt list — don't let new debt get added on top of it).

- **PASS**: determinism test intact; no new CI test-skipping introduced.
- **FAIL**: report exactly what changed and why it's a regression.

## 7. Final report + validation token

Summarize all six steps as PASS / FAIL / SKIP with one line of detail each.

If all steps pass:
```bash
date +%s > .claude/.last-validated
```
Tell the user: **"Merge-safety checks passed — safe to commit/push. (Validation
token written; the git hook will allow commit/push for the next 30 minutes.)"**

If any step fails, list exactly what to fix before retrying. Do not write the
validation token on a partial pass.
