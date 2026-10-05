import { useCallback, useState } from 'react'

export type Density = 'compact' | 'comfortable'
const KEY = 'density'

function read(): Density {
  try { return localStorage.getItem(KEY) === 'comfortable' ? 'comfortable' : 'compact' } catch { return 'compact' }
}

/** Console table density. Compact (32px rows) is the default. The choice is remembered in this browser. */
export function useDensity(): [Density, (d: Density) => void] {
  const [density, setState] = useState<Density>(read)
  const set = useCallback((d: Density) => {
    setState(d)
    try { localStorage.setItem(KEY, d) } catch { /* the choice still applies for this page view */ }
  }, [])
  return [density, set]
}
