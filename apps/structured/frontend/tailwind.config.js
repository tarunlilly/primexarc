/** @type {import('tailwindcss').Config} */
import tailwindAnimate from 'tailwindcss-animate';

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: '1.5rem', md: '2rem', lg: '3rem' },
      screens: { '2xl': '1240px' },
    },
    extend: {
      // ─── Colors ──────────────────────────────────────────────────────────
      // All colors flow through CSS variables (defined in globals.css) so
      // shadcn primitives auto-theme. Tailwind reads them via hsl(var(--x)).
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
        popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },

        // Brand — semantic, not just "red"
        lilly: {
          red: 'hsl(var(--lilly-red))',
          dred: 'hsl(var(--lilly-dred))',
          crimson: 'hsl(var(--lilly-crimson))',
        },

        // Tier palette — only used on Dashboard
        tier: {
          'green-base': 'hsl(var(--tier-green-base))',
          'green-light': 'hsl(var(--tier-green-light))',
          'amber-base': 'hsl(var(--tier-amber-base))',
          'amber-light': 'hsl(var(--tier-amber-light))',
          'red-base': 'hsl(var(--tier-red-base))',
          'red-light': 'hsl(var(--tier-red-light))',
        },

        // Flow diagram step colors — only used on Help Center
        flow: {
          'raw-bg':        'hsl(var(--flow-raw-bg))',
          'raw-border':    'hsl(var(--flow-raw-border))',
          'raw-text':      'hsl(var(--flow-raw-text))',
          'profile-bg':    'hsl(var(--flow-profile-bg))',
          'profile-border':'hsl(var(--flow-profile-border))',
          'profile-text':  'hsl(var(--flow-profile-text))',
          'ai-bg':         'hsl(var(--flow-ai-bg))',
          'ai-border':     'hsl(var(--flow-ai-border))',
          'ai-text':        'hsl(var(--flow-ai-text))',
        },

        // Dimension classification tags — Help Center
        tag: {
          'data-bg':   'hsl(var(--tag-data-bg))',
          'data-text': 'hsl(var(--tag-data-text))',
          'ml-bg':     'hsl(var(--tag-ml-bg))',
          'ml-text':   'hsl(var(--tag-ml-text))',
          'ai-bg':     'hsl(var(--tag-ai-bg))',
          'ai-text':   'hsl(var(--tag-ai-text))',
        },
      },

      // ─── Typography ──────────────────────────────────────────────────────
      fontFamily: {
        // Display — Fraunces, refined serif with character
        display: ['Fraunces', 'ui-serif', 'Georgia', 'serif'],
        // Sans — Bricolage Grotesque for body
        sans: ['"Bricolage Grotesque"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        // Nav/UI chrome — Apple system stack. Used for header, nav links,
        // eyebrow labels, badges. Falls back to SF Pro / Helvetica Neue.
        nav: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"SF Pro Text"',
          '"SF Pro Display"',
          '"Helvetica Neue"',
          'Helvetica',
          'Arial',
          'sans-serif',
        ],
        // Mono — JetBrains Mono for code/data
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },

      // ─── Radius ──────────────────────────────────────────────────────────
      // Medium softness per design decision.
      borderRadius: {
        lg: 'var(--radius)',       // 12px — default
        md: 'calc(var(--radius) - 2px)',  // 10px — inputs
        sm: 'calc(var(--radius) - 4px)',  // 8px — small chips
        xl: 'calc(var(--radius) + 4px)',  // 16px — cards
        '2xl': 'calc(var(--radius) + 8px)', // 20px — hero blocks
      },

      // ─── Animation ───────────────────────────────────────────────────────
      keyframes: {
        cardRise: {
          from: { opacity: '0', transform: 'translateY(40px) scale(0.96)' },
          to:   { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(16px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'card-rise': 'cardRise 0.6s cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-in':   'fadeIn 0.4s ease-out both',
        'slide-up':  'slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) both',
      },
    },
  },
  plugins: [tailwindAnimate],
};