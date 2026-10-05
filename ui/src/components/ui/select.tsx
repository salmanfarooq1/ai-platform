// A styled native select. shadcn's Select wraps Radix Select; a native element keeps keyboard and mobile behavior
// for free and is enough for the short lists in this app.
import { forwardRef, type SelectHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(({ className, ...props }, ref) => (
  <select
    ref={ref}
    className={cn('h-9 rounded-sm border border-hairline bg-muted px-2 text-callout text-fg focus-visible:outline-2 focus-visible:outline-brand', className)}
    {...props}
  />
))
Select.displayName = 'Select'
