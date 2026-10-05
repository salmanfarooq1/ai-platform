import { cva } from 'class-variance-authority'

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sm text-callout font-medium transition-[transform,background-color,border-color,color] duration-fast ease-out active:scale-[var(--motion-press-scale)] disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none motion-reduce:active:scale-100',
  {
    variants: {
      variant: {
        primary: 'bg-ink text-fg-onink hover:bg-ink-hover',
        secondary: 'border border-hairline bg-surface text-fg hover:bg-muted active:bg-selected',
        ghost: 'text-fg-secondary hover:bg-muted hover:text-fg active:bg-selected',
        danger: 'border border-hairline bg-deny-tint text-deny hover:bg-surface',
      },
      size: { sm: 'h-8 px-3', md: 'h-9 px-4', lg: 'h-11 px-6 text-body', icon: 'h-8 w-8' },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)
