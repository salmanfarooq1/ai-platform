import { Check, Copy } from '@phosphor-icons/react'
import { useState } from 'react'
import { cn } from '@/lib/utils'

/** A monospace value with a copy button. */
export function CopyValue({ value, label, className }: { value: string; label: string; className?: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-1.5', className)}>
      <code className="mono min-w-0 break-all text-footnote">{value}</code>
      <button
        type="button"
        onClick={copy}
        aria-label={copied ? `${label} copied` : `Copy ${label}`}
        className="shrink-0 rounded-sm p-1 text-fg-secondary hover:bg-muted hover:text-fg"
      >
        {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
      </button>
    </span>
  )
}
