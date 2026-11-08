import * as DialogPrimitive from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { MagnifyingGlass, Stack } from '@phosphor-icons/react'
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { cn } from '@/lib/utils'
import { buildPaletteItems, type PaletteItem } from './palette-items'
import { useModuleAvailability } from './modules'

interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Cmd+K or Ctrl+K. Go to a screen, or find a request by id. A combobox over a listbox, on Radix Dialog. */
export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const listId = useId()
  const listRef = useRef<HTMLUListElement>(null)
  const { enabledModules } = useModuleAvailability()

  const recent = useQuery({
    queryKey: ['requests', 'palette'],
    queryFn: () => api.requests({ include_console_reads: true }, undefined, 25),
    enabled: open,
    staleTime: 10_000,
    retry: false,
  })
  const items = useMemo(() => buildPaletteItems(query, recent.data?.items, enabledModules), [query, recent.data, enabledModules])

  useEffect(() => { setActive(0) }, [query])
  useEffect(() => { if (!open) setQuery('') }, [open])
  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: 'nearest' })
  }, [active])

  function go(item: PaletteItem | undefined) {
    if (!item) return
    onOpenChange(false)
    navigate(item.to)
  }
  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(items.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); go(items[active]) }
  }

  let lastGroup = ''
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-[var(--scrim)]" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[15vh] z-50 w-[calc(100%-32px)] max-w-lg -translate-x-1/2 overflow-hidden rounded-md border border-hairline bg-surface shadow-lg"
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <div className="flex items-center gap-2 border-b border-hairline px-3">
            <MagnifyingGlass size={16} aria-hidden="true" className="text-fg-secondary" />
            <input
              role="combobox"
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={items[active] ? `${listId}-${active}` : undefined}
              aria-label="Go to a screen or find a request id"
              autoComplete="off"
              spellCheck={false}
              placeholder="Go to a screen or paste a request id"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              className="h-11 w-full bg-transparent text-callout text-fg outline-none placeholder:text-fg-tertiary"
            />
          </div>
          <ul ref={listRef} id={listId} role="listbox" aria-label="Results" className="m-0 max-h-[50vh] list-none overflow-y-auto p-1">
            {items.length === 0 ? <li role="presentation" className="px-3 py-6 text-center text-callout text-fg-secondary">Nothing matches. Paste a request id to open it.</li> : null}
            {items.map((item, i) => {
              const header = item.group !== lastGroup
              lastGroup = item.group
              return (
                <li key={item.id} role="presentation">
                  {header ? <p aria-hidden="true" className="eyebrow px-3 pb-1 pt-2">{item.group}</p> : null}
                  <div
                    id={`${listId}-${i}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseMove={() => setActive(i)}
                    onClick={() => go(item)}
                    className={cn('flex cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-callout', i === active ? 'bg-selected text-fg' : 'text-fg-secondary')}
                  >
                    {item.group === 'Requests' ? <Stack size={16} aria-hidden="true" /> : null}
                    <span className={cn('min-w-0 truncate', item.group === 'Requests' && 'mono text-footnote')}>{item.label}</span>
                    {item.hint ? <span className="ml-auto shrink-0 text-footnote text-fg-secondary">{item.hint}</span> : null}
                  </div>
                </li>
              )
            })}
          </ul>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
