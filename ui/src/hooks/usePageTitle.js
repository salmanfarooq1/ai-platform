import { useEffect } from 'react'
import { pageTitle } from '../brand'

/** Sets `document.title` to `<platform name> — <page>`. */
export function usePageTitle(page) {
  useEffect(() => {
    document.title = pageTitle(page)
  }, [page])
}
