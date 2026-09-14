---
name: claude-instructions-hygiene
description: >
  Audits CLAUDE.md/AGENTS.md (root and any nested per-app copies) for drift
  against actual code, and keeps them lean. Use periodically, after a
  significant migration step lands, or when the user says "check the docs",
  "is CLAUDE.md still accurate", or "audit doc drift". ARC's own CLAUDE.md
  already accumulated 14 documented drifts before this merger began (see
  primedata-vs-arc-platform-report.md §9) — this skill exists so PrimeXarc
  doesn't repeat that pattern, especially since PrimeData's repos currently
  have no CLAUDE.md/README at all and will need one written from scratch
  during migration, not copied stale from day one.
version: 1.0.0
user-invocable: true
tools: Read, Grep, Glob, Bash, Agent
---

# CLAUDE.md / AGENTS.md Hygiene Audit

## 1. Inventory every governance file

```bash
find . -iname "CLAUDE.md" -o -iname "AGENTS.md" | grep -v node_modules
```

For each one found, note its scope (root, or which `apps/*`) and its
approximate token count (`wc -w` × ~1.3 is a reasonable proxy). Root should
stay lean — if it's grown past roughly 150–200 lines, look for content that
belongs in a nested `apps/*/CLAUDE.md` instead and propose moving it.

## 2. Extract concrete, checkable claims

For each governance file, pull out statements that name a specific number,
file path, function name, threshold, or count — these are the claims that rot.
Examples of the pattern to look for (not an exhaustive list): "N routes", "N
tables", "N tests", tier thresholds, "the only agent allowed to do X", a named
file path, a version number, a schema name.

## 3. Verify each claim against the actual code

Spawn an Explore subagent (or check directly) for each extracted claim:

- Route counts → count actual `@router.get/post/patch/delete` decorators or
  route registrations in the named app.
- Table/schema names → check the ORM models and migration files.
- Test counts → `grep -rc "^def test_\|^    def test_"` in the relevant test dirs.
- Thresholds (tier bands, weights, caps) → check the actual constants in the
  scoring/threshold code they describe.
- "Only X may do Y" rules → grep for other call sites that would violate it.

Report each claim as MATCH or DRIFT, with the current actual value if it drifted.

## 4. Cross-check against the platform report

`primedata-vs-arc-platform-report.md` at repo root already documents ARC's 14
known drifts as of the merger's start (tier thresholds in `context.md`/
`testing.md`, phase-status tables, route/model counts in `spec.md`, hybrid-rule
count, archetype count, `llm_max_output_tokens` reference, Cortex base URL
default, dev-bypass trigger, missing e2e suite, mutable-tag claim, logo
reference, dual metadata formulas). When auditing `apps/structured`'s migrated
docs, check whether each of these has been fixed, is still open, or was
accidentally reintroduced by the migration — don't treat the report as
permanently authoritative; it's a snapshot from the day the merger began.

## 5. Check nested-file discipline

Per the monorepo pattern, the root `CLAUDE.md` should hold only cross-cutting
rules (boundary, auth, package policy, shared design). Product-specific rules
(ARC's scoring formula details, PrimeData's chunking defaults) belong in that
app's own nested `CLAUDE.md`, not duplicated at root. Flag any root-level
content that's really about only one app.

## 6. Report

```
Governance file audit — <date>

Root CLAUDE.md: <line count> — <within budget / over budget, suggest trims>
apps/structured/CLAUDE.md: <line count> — <status>
apps/unstructured/CLAUDE.md: <line count / MISSING>

Claims checked: <N>
  MATCH: <N>
  DRIFT: <N> — <list each with current actual value>

Nested-file discipline: <clean / N items to move>
```

If `apps/unstructured/CLAUDE.md` doesn't exist yet, that's expected before its
migration step — flag it as a to-do for that migration PR (see
`repo-migration-agent`), not as an error.

## What NOT to do

- Don't auto-generate a bloated CLAUDE.md by dumping every fact you can find
  about the codebase into it "for completeness." Progressive disclosure — put
  depth in `docs/` or a nested skill, keep the governance file itself to hard
  rules and pointers.
- Don't silently fix drift by rewriting the doc without flagging what changed
  and why — the user should see the diff between "what the doc claimed" and
  "what's actually true" before it's corrected.
