# apps/shell — new, not migrated from either source repo

Owns: the landing page, the Structured/Unstructured split-screen toggle, the shared Help Center, the shared Support page, and auth-session bootstrap (reads Bouncer-injected identity once the auth unification in root `CLAUDE.md` §4 lands).

Contains no assessment or pipeline logic from either engine. See the `shell-design-sync` agent before building any page here, and `auth-unification-reviewer` before wiring the session bootstrap.

PrimeData's domain is the intended main hit point for this shell (per product decision) — confirm the exact routing/reverse-proxy design (path-based vs. subdomain-based split) before building the toggle's navigation targets.
