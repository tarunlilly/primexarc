# packages/shared-ui — extract last, not first

Per `repo-migration-agent`'s sequencing recommendation, this package should be extracted only after `apps/structured` and `apps/unstructured` both exist side by side and it's clear what's genuinely shared versus what only looks shared today.

Scope allowed here: design tokens, typography, the Help/Support page shell, nav chrome, the auth-session hook. Nothing else — see the `boundary-guardian` agent, which reviews every proposed addition to this package before it lands.

Design baseline: ARC's existing token system (Fraunces/Bricolage Grotesque/Apple system stack/JetBrains Mono, HSL CSS variables, no hardcoded hex, no emoji) — see `shell-design-sync` for the full rationale on why this direction and not PrimeData's current Inter/raw-hex setup.
