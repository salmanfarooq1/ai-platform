import { useEffect } from 'react'
import { pageTitle } from '../brand'

/** Sets `document.title` to `Verity — <page>` (BRANDING.md §1). */
export function usePageTitle(page) {
  useEffect(() => {
    document.title = pageTitle(page)
  }, [page])
}
