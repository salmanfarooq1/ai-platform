// Source: shadcn/ui "card" (https://ui.shadcn.com/docs/components/card), written by hand. Restyled to the project tokens.
// Radius follows the surface: 8px in the console, 12px in the workspace.
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const card = cva('border border-hairline bg-surface text-fg', {
  variants: { surface: { console: 'rounded-sm', workspace: 'rounded-md' } },
  defaultVariants: { surface: 'console' },
})

export interface CardProps extends HTMLAttributes<HTMLDivElement>, VariantProps<typeof card> {}

export const Card = forwardRef<HTMLDivElement, CardProps>(({ className, surface, ...props }, ref) => (
  <div ref={ref} className={cn(card({ surface }), className)} {...props} />
))
Card.displayName = 'Card'

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col gap-1 p-4 pb-2', className)} {...props} />
}
export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn('text-headline font-semibold', className)} {...props} />
}
export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('p-4 pt-2', className)} {...props} />
}
