# PrimeXarc — setup instructions

> **Historical document (2026-09-15).** This described the original 24-file governance scaffold placement.
> The scaffold has been placed and all three apps (`apps/structured`, `apps/unstructured`, `apps/shell`) have been migrated.
> Retained for reference only - see `docs/unification-runbook.md` for current execution plan.

---

Everything below already exists as real files in this folder. This document is
for placing them into wherever the actual repository will live (Azure DevOps,
GitHub Enterprise, etc.) if you're moving them by hand rather than having them
pushed directly.

## Repository tree

```
PrimeXarc/
├── .gitignore
├── CLAUDE.md
├── AGENTS.md
├── README.md
├── SETUP.md
├── primedata-vs-arc-platform-report.md
│
├── apps/
│   ├── shell/
│   │   └── NOTE.md
│   ├── structured/
│   │   └── NOTE.md
│   └── unstructured/
│       └── NOTE.md
│
├── packages/
│   └── shared-ui/
│       └── NOTE.md
│
└── .claude/
    ├── settings.json
    ├── agents/
    │   ├── artifactory-compliance.md
    │   ├── auth-unification-reviewer.md
    │   ├── boundary-guardian.md
    │   ├── ci-test-parity.md
    │   ├── llm-boundary-auditor.md
    │   ├── observability-agent.md
    │   ├── prompt-optimizer.md
    │   ├── repo-migration-agent.md
    │   └── shell-design-sync.md
    ├── skills/
    │   ├── claude-instructions-hygiene/
    │   │   └── SKILL.md
    │   └── merge-safety/
    │       └── SKILL.md
    └── hooks/
        ├── block-secrets.sh
        ├── enforce-artifactory.sh
        ├── enforce-boundary.sh
        ├── require-db-review.sh
        └── require-merge-safety.sh
```

24 files total. Nothing outside this tree needs to move.

## Placement steps

1. **Create the destination repo** (empty) wherever it will actually live —
   Azure DevOps project, GitHub Enterprise, etc. Clone it locally.

2. **Copy the entire tree above into the repo root**, preserving structure
   exactly. `.claude/` and `.gitignore` are dotfiles/dotfolders — if you're
   copying via Finder, enable hidden files first (`Cmd+Shift+.` on macOS) or
   copy via terminal (`cp -R`) so they aren't silently skipped.

3. **Re-apply executable permissions on the hook scripts.** Copy operations
   (especially through a zip, OneDrive sync, or a GUI file manager) commonly
   drop the executable bit:
   ```bash
   chmod +x .claude/hooks/*.sh
   ```

4. **Confirm `jq` is installed** wherever Claude Code will run — all five
   hooks depend on it (`brew install jq` on macOS, `apt-get install jq` on a
   Linux CI runner). If it's missing, the hooks fail *open* with a warning
   rather than blocking anything — so nothing breaks, but the guardrails go
   silently inert. Worth confirming rather than discovering later.

5. **Run Claude Code from the repo root.** The hook commands in
   `.claude/settings.json` are relative paths (`.claude/hooks/...`) — they
   only resolve correctly if the working directory is the repo root.

6. **Sanity-check the hooks fire** (optional but recommended — takes 30 seconds):
   ```bash
   cd <repo-root>
   echo '{"tool_name":"Write","tool_input":{"file_path":"apps/unstructured/backend/foo.py","content":"from apps.structured.core.scorer import score_table"}}' | .claude/hooks/enforce-boundary.sh
   # should print "BLOCKED: ..." and exit 2
   ```

7. **First commit:**
   ```bash
   git add -A
   git commit -m "Initial governance scaffold: CLAUDE.md, AGENTS.md, merger agents/skills/hooks"
   git push -u origin main
   ```

## Important: don't copy the source repos' `.gitignore` pattern

`ibu-ai-ready-data`, `primedata-ui`, and `primedata-backend` all ignore
`.claude/` (or `.claude/settings.json`) entirely — that's normal for a repo
where `.claude/` holds only personal/local config. **This repo is different: the
whole point of this deliverable is a `.claude/` that's checked into version
control and shared by the team**, per standard Claude Code practice. The
`.gitignore` already staged here only excludes `.claude/settings.local.json`
and the runtime freshness-marker files (`.last-validated`, `.last-db-review`,
`worktrees/`) — everything else in `.claude/` is meant to be committed. Don't
"clean this up" by adding a blanket `.claude/` ignore line later.

## After placement

Read `.claude/agents/repo-migration-agent.md` for the recommended sequencing
before importing code from the three source repos (governance first, then
`apps/structured`, then `apps/unstructured`, then `apps/shell`, then
`packages/shared-ui` last).
