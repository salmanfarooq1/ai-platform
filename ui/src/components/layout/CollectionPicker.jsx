import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Library } from 'lucide-react'
import { useCollection } from '../../context/CollectionContext'
import styles from './CollectionPicker.module.css'

// The one Collection (namespace) picker, in the top bar (BRANDING.md §6, §7).
export default function CollectionPicker() {
  const { namespace, setNamespace, namespaces, descriptions } = useCollection()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    function onDocClick(e) { if (!ref.current?.contains(e.target)) setOpen(false) }
    function onKey(e) { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDocClick); document.removeEventListener('keydown', onKey) }
  }, [open])

  if (namespaces.length === 0) return null

  return (
    <div className={styles.picker} ref={ref}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setOpen(o => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Library size={16} strokeWidth={1.75} aria-hidden="true" />
        <span className={styles.label}>{namespace || 'Collection'}</span>
        <ChevronDown size={14} strokeWidth={1.75} className={styles.chevron} aria-hidden="true" />
      </button>
      {open && (
        <ul className={styles.menu} role="listbox" aria-label="Collection">
          {namespaces.map(ns => (
            <li key={ns}>
              <button
                type="button"
                role="option"
                aria-selected={ns === namespace}
                className={[styles.option, ns === namespace ? styles.active : ''].join(' ')}
                onClick={() => { setNamespace(ns); setOpen(false) }}
              >
                <span className={styles.optName}>{ns}</span>
                {descriptions[ns] && <span className={styles.optDesc}>{descriptions[ns]}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
