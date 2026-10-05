// Source: shadcn/ui "input" and "textarea" (https://ui.shadcn.com/docs/components/input), written by hand.
import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const field =
  'w-full rounded-sm border border-hairline bg-muted px-3 text-callout text-fg placeholder:text-fg-tertiary focus-visible:outline-2 focus-visible:outline-brand disabled:opacity-50'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(field, 'h-9', className)} {...props} />
))
Input.displayName = 'Input'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn(field, 'min-h-[88px] resize-y py-2 text-body', className)} {...props} />
))
Textarea.displayName = 'Textarea'
