import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'theme'
const VALID_THEMES = new Set(['dark', 'light', 'auto'])

function applyTheme(theme) {
  const root = document.documentElement
  if (theme === 'auto') {
    root.removeAttribute('data-theme')
  } else {
    root.setAttribute('data-theme', theme)
  }
}

function readStorage() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return VALID_THEMES.has(stored) ? stored : 'auto'
  } catch {
    return 'auto'
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState(() => {
    const initial = readStorage()
    applyTheme(initial)
    return initial
  })

  useEffect(() => {
    function onStorage(e) {
      if (e.key !== STORAGE_KEY) return
      const next = VALID_THEMES.has(e.newValue) ? e.newValue : 'auto'
      applyTheme(next)
      setThemeState(next)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const setTheme = useCallback((next) => {
    if (!VALID_THEMES.has(next)) return
    try { localStorage.setItem(STORAGE_KEY, next) } catch { }
    applyTheme(next)
    setThemeState(next)
  }, [])

  const toggleDark = useCallback(() => {
    const resolved =
      theme === 'auto'
        ? window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
        : theme
    setTheme(resolved === 'dark' ? 'light' : 'dark')
  }, [theme, setTheme])

  const isDark =
    theme === 'dark' ||
    (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  return { theme, setTheme, toggleDark, isDark }
}
