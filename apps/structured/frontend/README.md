# ARC Evaluator — Frontend

Internal Lilly web application. Evaluates CSV datasets and database schemas
against a 9-dimension AI readiness framework.

## Quick start

```bash
cd app/frontend
npm install
npm run dev    # http://localhost:5173
```

The Vite dev server proxies `/api/v1/*` → `http://localhost:8000` so the
FastAPI backend can run alongside without CORS configuration.

If `npm install` hangs on `ECONNRESET`, switch to a faster mirror:

```bash
npm config set registry https://registry.npmmirror.com
npm install
```

## Tech

React 18 · Vite · React Router 6 · **Tailwind CSS 3** · **shadcn/ui**
(Radix primitives + cva) · **Bricolage Grotesque / Fraunces / JetBrains Mono**
via Google Fonts · Lucide icons · Recharts (planned) · PapaParse (planned)

## Structure

```
src/
├── main.jsx                Entry · BrowserRouter
├── App.jsx                 Routes
├── Layout.jsx              Persistent header + footer; red/crimson/white surface flip
├── globals.css             Tailwind layers + CSS variable design tokens
│
├── pages/
│   ├── Home.jsx            Landing
│   ├── Assess.jsx          4-step wizard
│   ├── Dashboard.jsx       Results view
│   └── Support.jsx         Ticket form + contact
│
├── components/ui/          shadcn primitives — Button, Card, Input, Tabs, Progress, Label, Textarea
│   ├── button.jsx
│   ├── card.jsx
│   ├── input.jsx
│   ├── label.jsx
│   ├── progress.jsx
│   ├── tabs.jsx
│   └── textarea.jsx
│
└── lib/
    ├── api.js              Single fetch client → /api/v1
    ├── dimensions.js       9-dimension metadata + TIER_STYLES lookup
    └── utils.js            cn() — clsx + tailwind-merge
```

## Conventions

See `app/CLAUDE.md` for the full set. The non-negotiables:

- **Tailwind classes only.** No inline styles. No CSS modules.
- **Use shadcn/ui primitives** for any Button, Card, Input, Tabs, Progress, etc.
  Don't hand-roll a component that exists in `components/ui/`.
- **No business logic in pages.** Pages render and call `lib/api.js`. Scoring
  lives in the backend.
- **No hardcoded hex colors.** Colors come from CSS variables in `globals.css`
  (consumed via Tailwind's `bg-primary`, `text-tier-red-base`, etc.).
- **Surface flip via CSS classes.** Layout sets `red-mode` / `crimson-mode` on
  the wrapper; tokens automatically remap so child components stay theme-aware.

## Design tokens

All hex values flow through CSS variables in `globals.css`. The brand palette
(`--lilly-red`, `--lilly-dred`, `--lilly-crimson`) and tier palette (`green-base`,
`amber-base`, `red-base` + `*-light` variants) are exposed as Tailwind colors:

```jsx
<div className="bg-lilly-red text-white" />
<div className="bg-tier-green-light text-tier-green-base" />
```

To change the brand red (e.g. to the official `#D52B1E`), update **one line**
in `globals.css`:

```css
--lilly-red: 4 73% 47%;   /* HSL of #D52B1E */
```

## Build

```bash
npm run build      # → dist/
npm run preview    # serves the build at :4173
```

## Phase status

Frontend scaffold: **complete with new Tailwind + shadcn design system.**
Real CSV parsing, the radar chart, the export-to-markdown panel, and the SSO
header arrive after the backend lands.
