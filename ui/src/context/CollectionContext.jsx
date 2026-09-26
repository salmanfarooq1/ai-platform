import { createContext, useContext, useState, useEffect, useMemo } from 'react'

// One Collection (namespace) picker, shared everywhere (BRANDING.md §6) —
// every page reads it here instead of repeating a namespace <select>.
const CollectionContext = createContext(null)

const STORAGE_KEY = 'collection'

export function CollectionProvider({ config, children }) {
  const namespaces = useMemo(
    () => (config?.namespaces ? Object.keys(config.namespaces) : []),
    [config]
  )

  const [namespace, setNamespaceState] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) || '' } catch { return '' }
  })

  // Once namespaces load, make sure the stored/selected one is still valid;
  // otherwise fall back to the first available collection.
  useEffect(() => {
    if (namespaces.length === 0) return
    if (!namespace || !namespaces.includes(namespace)) {
      setNamespaceState(namespaces[0])
    }
  }, [namespaces]) // eslint-disable-line react-hooks/exhaustive-deps

  function setNamespace(ns) {
    setNamespaceState(ns)
    try { localStorage.setItem(STORAGE_KEY, ns) } catch { /* ignore */ }
  }

  const value = { namespace, setNamespace, namespaces, descriptions: config?.namespaces ?? {} }
  return <CollectionContext.Provider value={value}>{children}</CollectionContext.Provider>
}

export function useCollection() {
  const ctx = useContext(CollectionContext)
  if (!ctx) throw new Error('useCollection must be used within CollectionProvider')
  return ctx
}
