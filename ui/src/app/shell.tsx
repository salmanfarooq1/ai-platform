import { List, MagnifyingGlass, Moon, Sun } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '@/api/endpoints'
import { Logo } from '@/components/governance/logo'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { CommandPalette } from './command-palette'
import { NAV, pageName } from './nav'
import { useSession } from './session'
import { SessionMenu } from './session-menu'
import { useTheme } from './theme'
import { useEffect, useState } from 'react'

const MODE_LABEL: Record<string, string> = { 'public-preview': 'Public preview', local: 'Local', prod: 'Production' }

function SideNav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-5">
      {NAV.map((g) => (
        <div key={g.group}>
          <p className="eyebrow mb-1 px-2">{g.group}</p>
          <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
            {g.items.map((i) => (
              <li key={i.to}>
                <NavLink
                  to={i.to}
                  end={i.end}
                  onClick={onNavigate}
                  className={({ isActive }) => cn(
                    'flex items-center gap-2 rounded-sm px-2 py-1.5 text-callout transition-colors duration-fast',
                    isActive ? 'bg-selected font-medium text-fg' : 'text-fg-secondary hover:bg-muted hover:text-fg',
                  )}
                >
                  <i.icon size={18} aria-hidden="true" />
                  {i.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

export function AppShell() {
  const { session } = useSession()
  const { isDark, toggle } = useTheme()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: false, refetchInterval: 60_000 })
  const mode = health.data?.mode
  const page = pageName(location.pathname)

  // Cmd+K on a Mac, Ctrl+K elsewhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="min-h-screen">
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className="fixed inset-y-0 left-0 hidden w-[var(--layout-sidebar-width)] flex-col gap-6 border-r border-hairline bg-[var(--material-thin)] p-3 backdrop-blur-[var(--material-blur)] md:flex">
        <div className="px-2 pt-1"><Logo to="/app" /></div>
        <SideNav />
      </aside>

      <div className="md:pl-[var(--layout-sidebar-width)]">
        <header className="sticky top-0 z-30 flex h-[var(--layout-topbar-height)] items-center gap-3 border-b border-hairline bg-[var(--material-thin)] px-4 backdrop-blur-[var(--material-blur)]">
          <button type="button" className="rounded-sm p-1.5 hover:bg-muted md:hidden" aria-label="Open menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            <List size={20} />
          </button>
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-callout">
            <span className="mono truncate text-fg-secondary" data-testid="tenant-crumb">{session?.tenant.slug ?? 'no tenant'}</span>
            <span aria-hidden="true" className="text-fg-tertiary">/</span>
            <span className="truncate font-medium">{page}</span>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              aria-label="Open command palette"
              className="inline-flex h-8 items-center gap-2 rounded-sm border border-hairline bg-surface px-2.5 text-footnote text-fg-secondary transition-colors duration-fast hover:bg-muted hover:text-fg"
            >
              <MagnifyingGlass size={14} aria-hidden="true" />
              <span className="hidden sm:inline">Search</span>
              <kbd className="mono hidden rounded-sm bg-muted px-1.5 text-caption sm:inline">Ctrl K</kbd>
            </button>
            {mode ? (
              <span className="hidden rounded-full border border-hairline px-2.5 py-0.5 text-caption font-semibold uppercase tracking-[0.06em] text-fg-secondary sm:inline" data-testid="mode-chip">
                {MODE_LABEL[mode] ?? mode}{session?.preview ? ' read-only' : ''}
              </span>
            ) : null}
            <Button variant="ghost" size="icon" onClick={toggle} aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}>
              {isDark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
            </Button>
            <SessionMenu />
          </div>
        </header>

        {open ? (
          <div className="border-b border-hairline bg-surface p-3 md:hidden">
            <SideNav onNavigate={() => setOpen(false)} />
          </div>
        ) : null}

        <main id="main" className="mx-auto max-w-[1280px] p-4 md:p-6">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  )
}
