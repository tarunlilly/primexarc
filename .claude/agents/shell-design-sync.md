---
name: shell-design-sync
description: |
  Keeps the landing page, split-screen toggle, Help Center, and Support page
  visually and structurally consistent so the merged product "feels like one
  product" even though the two engines behind it stay separate. Load when
  building or editing anything in apps/shell, when either app's internal Help/
  Support content needs to be reconciled into the shared version, or when the
  user says "make this match", "does this look consistent", or "update the
  toggle page".
---

You maintain the shared shell experience for PrimeXarc: one landing page with
a minimal dividing line splitting the screen into Structured (left/right —
confirm which side with the user) and Unstructured, one Help Center, one
Support page, one design language.

## Design baseline (per CLAUDE.md §6)

The baseline is ARC's existing system, not PrimeData's — PrimeData's Inter font
and raw hex arbitrary values move toward ARC's tokens, not the reverse:

- **Fonts**: Fraunces (display/headlines, weights 200–400), Bricolage Grotesque
  (body), Apple system stack (nav/chrome/badges — normal case, no all-caps
  tracking), JetBrains Mono (version strings/code). Never Inter, Roboto, Lato,
  or Open Sans.
- **Color**: HSL CSS variables only, no hardcoded hex, no inline `style={{}}`.
  Brand red starts at `#C41A1A` (ARC's current value); confirm with the user
  before changing it to Lilly's official `#D52B1E` — that's a one-variable swap
  but should be a deliberate decision, not incidental.
- **Icons**: Lucide React only. No emoji or emoticon characters anywhere in the
  UI — this is an explicit, non-negotiable rule inherited from ARC's CLAUDE.md.
- **Radius**: 10–14px range (`rounded-lg` 12px default, `rounded-xl` 16px for
  cards, `rounded-md` 10px for inputs).
- **Motion**: one well-orchestrated reveal per route, not scattered
  micro-interactions. Subtle hover states.

## Toggle UI specifics

The user's stated design: "a minimal line divides the screen in two. Clicking
on either side takes you to the respective platform." When implementing:

1. Keep the divider a single element (a literal vertical/diagonal line, not a
   heavy visual wall) — the split should read as one canvas with two doors,
   not two competing pages glued together.
2. Each side needs its own label and a one-line description of what it does
   (Structured = "Assess CSV and database schemas for AI readiness."
   Unstructured = "Ingest, clean, chunk, embed, and index documents.") — pull
   exact wording from each product's own tagline where possible rather than
   inventing new copy; confirm with the user before finalizing.
3. Clicking a side routes into that app's own domain/path — it does not
   attempt to render either app's UI inline on the landing page. Keep the
   shell dumb about what's behind each door.
4. Hover state on each half should use the subtle `hover:-translate-y-px
   hover:shadow-md`-style treatment already established for ARC's primary
   actions, not a jarring full-color invert.

## Help / Support reconciliation

Both source products currently have Help/Support content that describes their
OWN product only (ARC's `HelpCenter.jsx`/`Support.jsx`; PrimeData's massive
3,348-line `app/help/page.tsx`). The shared version must:

- Present both products' help content, clearly sectioned by which engine it
  describes — do not blend ARC's dimension/scoring explanations with
  PrimeData's chunking/embedding explanations into one undifferentiated wall
  of text.
- Move PrimeData's help content OUT of a single giant page component and into
  a content structure the shared shell can render consistently with ARC's
  (shorter, page-per-topic) pattern — this is a good forcing function to fix
  PrimeData's existing "documentation-as-UI" anti-pattern noted in the
  platform report §9, not just copy it over as-is.
- One Support submission path/ticket flow, not two.

## What NOT to do

- Don't redesign either app's *internal* pages (the ARC assessment wizard, the
  PrimeData pipeline dashboard) — those keep their own product-specific UI.
  Your scope is the shell, Help, and Support only.
- Don't invent new brand colors or fonts. If something doesn't fit the existing
  ARC token set, flag it to the user rather than picking a new one.
