# AGENTS.md — PrimeXarc

Tool-agnostic mirror of `CLAUDE.md` for non-Claude coding assistants (Codex, Cursor, Copilot, Cline, OpenCode, Roo Code). Claude Code should treat `CLAUDE.md` as authoritative and this file as a portable summary; keep both in sync — see the `claude-instructions-hygiene` skill.

## What this repo is

PrimeXarc merges two Lilly-internal platforms behind one landing experience:

- **Structured** (ARC) — assesses CSV/DB data for AI readiness. Read-only against user data. Deterministic scoring. Migrating from `ibu-ai-ready-data`.
- **Unstructured** (PrimeData) — ingests/cleans/chunks/embeds/indexes documents. Mutates and stores derived data. Migrating from `primedata-ui` + `primedata-backend`.

## General Guidelines


1. Never use the em dash "—" , instead use "-" or ":"
2. when writting commit messages, Never auto-add as your agent as co author
3. When writing or substantially editing long Markdown files, put each full sentence on its own line.Preserve normal Markdown structure, but avoid wrapping multiple sentences onto one physical line.
4. When making technical decisions, do not give much weight to development cost.Instead, prefer quality, simplicity, robustness, scalability, and long term maintainability.
5. When doing bug fixes, always start with reproducing the bug in an EZE setting as closely aligned with how an end use.This makes sure you find the real problem so your fix will actually solve it.
6. When end-to-end testing a product, be picky about the UI you see and be obsessed with pixel perfection. If something clearly looks off, even if it is not directly related to what you are doing, try to get it fixed along
7. Apply that same high standard to engineering excellence: lint, test failures, and test flakiness. If you see one, even if it is not caused by what you are working on right now, still get it fixed.

## Non-negotiable rules

1. **No cross-app imports** between `apps/structured/**` and `apps/unstructured/**`, except through `packages/shared-ui`.
2. **ARC's scorer stays pure**: no I/O, no LLM calls, deterministic output. Any LLM use in ARC goes through its `llm/` package only and is additive-only — it may add narrative/recommendations but must never write a score, tier, or gating decision.
3. **PrimeData's pipeline keeps its own model** — do not force it into ARC's no-mutation discipline.
4. **Two DB schemas, not one.** ARC uses `history_assessment`; PrimeData uses a configurable schema (default `public`). Never let them collide in one Postgres instance.
5. **Auth target: Bouncer (CATS ingress proxy) for both apps**, ingress-injected identity headers, no in-app MSAL long-term. This is a security-sensitive migration — verify network isolation (ingress must strip client-supplied identity headers) before cutting ARC over. Don't remove ARC's MSAL path until the replacement is verified.
6. **Packages come from JFrog Artifactory only.** No direct npm/PyPI. PrimeData's UI Dockerfile currently violates this (`npm ci` against the public registry) — fix during migration, don't carry it forward.
7. **Shared design system lives only in `packages/shared-ui`** and covers chrome/Help/Support — never product logic. Baseline moves toward ARC's existing type/color system (Fraunces/Bricolage/Apple system stack/JetBrains Mono; no Inter, no emoji, no hardcoded hex).
8. **Simplicity first, surgical changes.** State assumptions before large structural moves. Ask before big refactors.

## Reference

Full technical comparison, versions, and risk list: `primedata-vs-arc-platform-report.md` at repo root.
