# PrimeXarc

One product, two engines: **ARC** (structured — CSV/DB AI-readiness assessment) and **PrimeData** (unstructured — ingest/clean/chunk/embed/index), behind one landing page, one toggle, and one auth model.

Start here:

- **`CLAUDE.md`** — the governance file. Read this first; it explains why the two engines stay separate under the hood, what "one product" means in practice, and the hard rules that protect both products' existing guarantees.
- **`AGENTS.md`** — tool-agnostic mirror of the same rules for non-Claude assistants.
- **`primedata-vs-arc-platform-report.md`** — the full technical comparison this merger is based on: tech stacks, architecture, auth models, deployment, and every known risk found by direct code inspection.
- **`.claude/`** — the agents, skills, and hooks that enforce the governance rules (boundary separation, JFrog Artifactory compliance, auth-migration safety, DB schema isolation, CI test parity, and more).

## Status

This is the governance scaffold only. No product code has been migrated yet. See `apps/*/NOTE.md` for what each directory will contain and the `repo-migration-agent` for how the migration is sequenced.

## Structure

```
PrimeXarc/
├── CLAUDE.md / AGENTS.md
├── primedata-vs-arc-platform-report.md
├── apps/
│   ├── shell/           # landing, toggle, Help, Support — new
│   ├── structured/       # ARC — migrating from ibu-ai-ready-data
│   └── unstructured/     # PrimeData — migrating from primedata-ui + primedata-backend
├── packages/
│   └── shared-ui/        # design tokens + chrome only — extracted last
└── .claude/
    ├── settings.json      # hooks wiring
    ├── agents/            # 9 merger-specific reviewers/workers
    ├── skills/             # merge-safety, claude-instructions-hygiene
    └── hooks/              # deterministic PreToolUse guardrails
```

## Not yet done

- No remote repository configured. This exists as local files only — creating the actual Azure DevOps (or other) remote is a decision for the user to make (which project/org it lands in) before pushing anywhere.
- No code has moved from the three source repos.
