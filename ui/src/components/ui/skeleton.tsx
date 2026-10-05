// Source: shadcn/ui "skeleton" (https://ui.shadcn.com/docs/components/skeleton), written by hand.
import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn('skeleton h-4 w-full', className)} {...props} />
}
