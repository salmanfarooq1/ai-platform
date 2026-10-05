import type { Config } from 'tailwindcss'

// Tailwind reads the CSS variables in src/styles/tokens.css. No hex values live here.
const v = (name: string) => `var(--${name})`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        canvas: v('bg-canvas'),
        surface: v('bg-surface'),
        muted: v('bg-muted'),
        hairline: v('hairline'),
        seal: { DEFAULT: v('seal'), pressed: v('seal-pressed'), tint: v('seal-tint') },
        ink: { DEFAULT: v('ink'), hover: v('ink-hover') },
        selected: v('bg-selected'),
        fg: { DEFAULT: v('text-primary'), secondary: v('text-secondary'), tertiary: v('text-tertiary'), onink: v('text-on-ink') },
        success: { DEFAULT: v('success'), tint: v('success-tint') },
        warning: { DEFAULT: v('warning'), tint: v('warning-tint') },
        danger: { DEFAULT: v('danger'), tint: v('danger-tint') },
        allow: { DEFAULT: v('allow'), tint: v('allow-tint') },
        deny: { DEFAULT: v('deny'), tint: v('deny-tint') },
        escalate: { DEFAULT: v('escalate'), tint: v('escalate-tint') },
      },
      fontSize: {
        display: ['var(--text-display)', { lineHeight: 'var(--leading-display)', letterSpacing: 'var(--tracking-display)' }],
        'title-1': ['var(--text-title-1)', { lineHeight: 'var(--leading-title-1)', letterSpacing: 'var(--tracking-title-1)' }],
        'title-2': ['var(--text-title-2)', { lineHeight: 'var(--leading-title-2)', letterSpacing: 'var(--tracking-title-2)' }],
        headline: ['var(--text-headline)', { lineHeight: 'var(--leading-headline)', letterSpacing: 'var(--tracking-headline)' }],
        body: ['var(--text-body)', { lineHeight: 'var(--leading-body)' }],
        callout: ['var(--text-callout)', { lineHeight: 'var(--leading-callout)' }],
        footnote: ['var(--text-footnote)', { lineHeight: 'var(--leading-footnote)', letterSpacing: 'var(--tracking-footnote)' }],
        caption: ['var(--text-caption)', { lineHeight: 'var(--leading-caption)', letterSpacing: 'var(--tracking-caption)' }],
      },
      fontFamily: { sans: v('font-sans'), mono: v('font-mono') },
      borderRadius: { sm: v('radius-sm'), md: v('radius-md'), lg: v('radius-lg'), xl: v('radius-xl') },
      transitionDuration: { press: v('motion-duration-press'), fast: v('motion-duration-fast'), base: v('motion-duration-base'), slow: v('motion-duration-slow') },
      transitionTimingFunction: { out: v('motion-ease-out'), 'in-out': v('motion-ease-in-out') },
      boxShadow: { sm: v('shadow-sm'), md: v('shadow-md'), lg: v('shadow-lg') },
      borderColor: { DEFAULT: v('hairline') },
    },
  },
  plugins: [],
} satisfies Config
