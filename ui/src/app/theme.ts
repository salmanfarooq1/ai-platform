import { useCallback, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark' | 'auto'
const KEY = 'theme'

function read(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'auto'
  } catch {
    return 'auto'
  }
}

function apply(theme: Theme): void {
  if (theme === 'auto') document.documentElement.removeAttribute('data-theme')
  else document.documentElement.setAttribute('data-theme', theme)
}

export function resolvedIsDark(theme: Theme): boolean {
  if (theme === 'dark') return true
  if (theme === 'light') return false
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(read)
  useEffect(() => { apply(theme) }, [theme])
  const setTheme = useCallback((next: Theme) => {
    try {
      if (next === 'auto') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, next)
    } catch {
      // Storage can be blocked. The choice still applies for this page view.
    }
    setThemeState(next)
  }, [])
  const toggle = useCallback(() => setTheme(resolvedIsDark(theme) ? 'light' : 'dark'), [theme, setTheme])
  return { theme, isDark: resolvedIsDark(theme), setTheme, toggle }
}
