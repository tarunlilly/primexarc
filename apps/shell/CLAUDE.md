# CLAUDE.md - apps/shell

This file provides guidance to Claude Code (claude.ai/code) when working in `apps/shell/`.

> Scoped to the PrimeXarc shell: landing page, split-screen toggle, Help Center, Support, Account, and auth bootstrap.
> The root `CLAUDE.md` takes precedence on any cross-cutting rule.

---

## What this app is

The shared front door for PrimeXarc. It lets users choose between Structured (ARC) and Unstructured (PrimeData), provides unified Help and Support, and bootstraps the Bouncer auth session. It contains **no assessment logic, no pipeline logic, and no scoring/dimension/rule definitions** from either engine.

Clicking "Structured" or "Unstructured" navigates to that app (separate URL/port in dev, path-prefixed in prod). The shell does not embed or render either app's internal pages.

## Tech stack

- Vite + React 18 + TypeScript (strict) + Tailwind 3
- Port 4000 in dev (avoids 3000 and 5173)
- Bouncer auth only - no MSAL, no in-app login flow
- No TanStack Query (no server state to manage)
- No telemetry (deferred to a later phase)

## Commands

```bash
cd apps/shell
npm run dev          # dev server on port 4000
npm run build        # production build to dist/
npm run preview      # serve production build locally
npm run type-check   # tsc --noEmit (strict mode, zero errors required)
npm run lint         # ESLint
```

## Design tokens

ARC's tokens are the baseline (root `CLAUDE.md` section 6). This app uses the same:

- **Fonts:** Fraunces (display), Bricolage Grotesque (sans/body), Apple system stack (nav), JetBrains Mono (mono). **No Inter, Roboto, Lato, or Open Sans.**
- **Colors:** HSL CSS variables only. No hardcoded hex anywhere in `src/`.
- **Surface modes:** `red-mode`, `crimson-mode`, or no class (white). The `Layout` component's `variant` prop controls which mode is active.

## Auth model

Bouncer only. The shell reads identity from `/_apps_system/session/user` (the CATS ingress auth proxy). In dev, a sentinel fallback provides `shell-dev@lilly.com`.

- `src/lib/bouncer-auth.ts` - session fetch with 50-min TTL cache
- `src/lib/user-context.tsx` - React context that blocks render until user resolves
- `src/main.tsx` - calls `getCachedUser()` before React mounts (early fetch)

Do not add MSAL, do not add a backend auth endpoint, do not trust identity from any source other than Bouncer headers.

## Routing

| Path | Page | Layout variant |
|------|------|----------------|
| `/` | Landing (split-screen toggle) | `white` |
| `/help` | Help Center (tabbed by product) | `white` |
| `/support` | Support (ticket form) | `white` |
| `/account` | Account (Bouncer session info) | `white` |
| `*` | NotFound (404) | `white` |

## App links

- Structured (ARC): `http://localhost:5173` (dev) / `/structured` (prod)
- Unstructured (PrimeData): `http://localhost:3000` (dev) / `/unstructured` (prod)

These are plain `<a href>` tags, not react-router `<Link>`. The two engines are separate apps.

## Hard rules

1. **No product logic.** Never add scoring, dimension, pipeline, chunking, embedding, or ingestion code here.
2. **No cross-app imports.** Do not import from `apps/structured/` or `apps/unstructured/`. The `enforce-boundary.sh` hook blocks this.
3. **No hardcoded hex.** All colors via CSS variables and Tailwind utilities.
4. **No inline styles.** No `style={{}}`. Tailwind utilities only.
5. **No emoji in UI text.**
6. **No Inter font.** The Google Fonts link loads Fraunces, Bricolage Grotesque, and JetBrains Mono only.
7. **Bouncer auth only.** No MSAL, no bearer tokens, no in-app login.
8. **TypeScript strict.** Zero type errors at all times.

## What NOT to do

| Anti-pattern | Why |
|---|---|
| Import from `apps/structured/**` or `apps/unstructured/**` | Violates boundary rule, blocked by hook |
| Add scoring/pipeline/dimension logic | Shell is chrome only |
| Use Inter, Roboto, or other AI-default fonts | Violates design system |
| Add MSAL or in-app login | Auth is Bouncer-only |
| Use `<Link to>` for app doors | These are separate apps, not shell routes |
| Add a backend/API | Shell is frontend-only, served statically |
| Use `npm install` against public registry | Artifactory only (org policy) |
