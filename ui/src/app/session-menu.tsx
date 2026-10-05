import * as Menu from '@radix-ui/react-dropdown-menu'
import { CaretDown, Check, SignOut } from '@phosphor-icons/react'
import { cn } from '@/lib/utils'
import { useSession } from './session'
import { useTheme, type Theme } from './theme'

const THEMES: Array<{ value: Theme; label: string }> = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'auto', label: 'Match system' },
]

const item = 'flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-callout outline-none data-[highlighted]:bg-selected'

/** Who you are, your tenant and scopes, the theme, and sign out. */
export function SessionMenu() {
  const { session, signOut } = useSession()
  const { theme, setTheme } = useTheme()
  const name = session?.principal.name ?? 'Signed in'
  return (
    <Menu.Root modal={false}>
      <Menu.Trigger
        aria-label="Session menu"
        className="inline-flex h-8 items-center gap-1.5 rounded-sm px-2 text-callout text-fg-secondary transition-colors duration-fast hover:bg-muted hover:text-fg data-[state=open]:bg-muted"
      >
        <span aria-hidden="true" className="flex h-5 w-5 items-center justify-center rounded-full bg-ink text-caption font-semibold text-fg-onink">{name.slice(0, 1).toUpperCase()}</span>
        <span className="hidden max-w-[10rem] truncate sm:inline">{name}</span>
        <CaretDown size={12} aria-hidden="true" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content align="end" sideOffset={6} className="z-50 w-72 rounded-sm border border-hairline bg-surface p-1 shadow-md">
          <Menu.Group aria-label="Signed in as" className="px-2 py-2" data-testid="session-identity">
            <p className="text-callout font-medium">{name}</p>
            <p className="text-footnote text-fg-secondary">{session?.principal.kind}{session?.preview ? ', read-only preview' : ''}</p>
            <div className="mt-2 grid grid-cols-[60px_minmax(0,1fr)] gap-x-2 gap-y-1 text-footnote">
              <span className="text-fg-secondary">Tenant</span><span className="mono truncate">{session?.tenant.slug}</span>
              <span className="text-fg-secondary">Scopes</span>
              <span className="flex flex-wrap gap-1">
                {(session?.scopes ?? []).map((s) => <code key={s} className="mono rounded-sm bg-muted px-1.5">{s}</code>)}
              </span>
            </div>
          </Menu.Group>
          <Menu.Separator className="my-1 h-px bg-[var(--hairline)]" />
          <Menu.RadioGroup aria-label="Theme" value={theme} onValueChange={(v) => setTheme(v as Theme)}>
            <Menu.Label className="eyebrow px-2 pb-1 pt-1.5">Theme</Menu.Label>
            {THEMES.map((t) => (
              <Menu.RadioItem key={t.value} value={t.value} className={cn(item, 'justify-between')}>
                {t.label}
                <Menu.ItemIndicator><Check size={14} aria-hidden="true" /></Menu.ItemIndicator>
              </Menu.RadioItem>
            ))}
          </Menu.RadioGroup>
          <Menu.Separator className="my-1 h-px bg-[var(--hairline)]" />
          <Menu.Item className={item} onSelect={() => void signOut()}>
            <SignOut size={16} aria-hidden="true" /> Sign out
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  )
}
