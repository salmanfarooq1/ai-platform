import { Moon, Sun } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useTheme } from '@/app/theme'
import { Logo } from '@/components/governance/logo'
import { buttonVariants } from '@/components/ui/button-variants'

/** The header and footer shared by the landing page and How it works. They load GSAP and WebGL never. */
export function MarketingShell({ children }: { children: ReactNode }) {
  const { isDark, toggle } = useTheme()
  return (
    <div className="min-h-screen bg-canvas">
      <a href="#content" className="skip-link">Skip to content</a>
      <header className="sticky top-0 z-30 border-b border-hairline bg-[var(--material-thin)] backdrop-blur-[var(--material-blur)]">
        <div className="mx-auto flex h-14 max-w-[1200px] items-center gap-4 px-4 md:px-8">
          <Logo />
          <nav aria-label="Page" className="ml-6 hidden items-center gap-5 text-callout text-fg-secondary md:flex">
            <Link className="rounded-sm transition-colors duration-fast hover:text-fg" to="/how-it-works">How it works</Link>
            <Link className="rounded-sm transition-colors duration-fast hover:text-fg" to="/#use-cases">Use cases</Link>
            <Link className="rounded-sm transition-colors duration-fast hover:text-fg" to="/#capabilities">Capabilities</Link>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button type="button" onClick={toggle} aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'} className="rounded-sm p-2 text-fg-secondary transition-colors duration-fast hover:bg-muted hover:text-fg">
              {isDark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
            </button>
            <Link to="/signin" className={`${buttonVariants({ size: 'sm', variant: 'ghost' })} hidden sm:inline-flex`}>Sign in</Link>
            <Link to="/app/walkthrough" className={buttonVariants({ size: 'sm' })}>
              <span className="sm:hidden">Walkthrough</span><span className="hidden sm:inline">Open the walkthrough</span>
            </Link>
          </div>
        </div>
      </header>
      <main id="content">{children}</main>
      <footer className="border-t border-hairline">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-3 px-4 py-6 text-footnote text-fg-secondary md:px-8">
          <span>Governed Agent Platform</span>
          <nav aria-label="Footer" className="flex gap-4">
            <Link className="rounded-sm hover:text-fg" to="/how-it-works">How it works</Link>
            <Link className="rounded-sm hover:text-fg" to="/signin">Sign in</Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}
