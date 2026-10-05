// A slide-over panel on Radix Dialog (modal, focus trap, Escape closes). Same primitive as dialog.tsx, anchored right.
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from '@phosphor-icons/react'
import { forwardRef, type ComponentPropsWithoutRef, type ElementRef } from 'react'
import { cn } from '@/lib/utils'

export const Sheet = DialogPrimitive.Root
export const SheetTitle = DialogPrimitive.Title
export const SheetDescription = DialogPrimitive.Description

export const SheetContent = forwardRef<ElementRef<typeof DialogPrimitive.Content>, ComponentPropsWithoutRef<typeof DialogPrimitive.Content>>(
  ({ className, children, ...props }, ref) => (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-[var(--scrim)] data-[state=open]:animate-[sheet-fade_var(--motion-duration-base)_var(--motion-ease-out)]" />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex w-full max-w-[var(--layout-drawer-width)] flex-col overflow-y-auto border-l border-hairline bg-surface p-5 shadow-lg',
          'data-[state=open]:animate-[sheet-in_var(--motion-duration-slow)_var(--motion-ease-out)]',
          className,
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close aria-label="Close" className="absolute right-3 top-3 rounded-sm p-1.5 text-fg-secondary transition-colors duration-fast hover:bg-muted hover:text-fg">
          <X size={16} aria-hidden="true" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  ),
)
SheetContent.displayName = 'SheetContent'
