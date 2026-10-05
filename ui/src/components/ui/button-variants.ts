import { cva } from 'class-variance-authority'

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sm text-callout font-medium transition-[transform,background-color,border-color] duration-150 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 motion-reduce:transition-none motion-reduce:active:scale-100',
  {
    variants: {
      variant: {
        primary: 'bg-brand text-fg-onbrand hover:bg-brand-pressed',
        secondary: 'border border-hairline bg-surface text-fg hover:bg-muted',
        ghost: 'text-fg-secondary hover:bg-muted hover:text-fg',
        danger: 'border border-hairline bg-deny-tint text-deny hover:bg-surface',
      },
      size: { sm: 'h-8 px-3', md: 'h-9 px-4', lg: 'h-11 px-6 text-body', icon: 'h-8 w-8' },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)
