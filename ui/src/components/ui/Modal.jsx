import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { X } from 'lucide-react'
import styles from './Modal.module.css'

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'

// Branded modal: focus trap, Esc, restores focus, opens from its trigger's
// origin and closes back toward it (BRANDING.md §8, §12, apple-design §7).
export default function Modal({ open, onClose, title, children, triggerRef, closeOnEsc = true }) {
  const modalRef = useRef(null)
  const previouslyFocused = useRef(null)
  const reduce = useReducedMotion()

  useEffect(() => {
    if (!open) return
    previouslyFocused.current = document.activeElement
    document.body.style.overflow = 'hidden' // page behind does not scroll

    const first = modalRef.current?.querySelector(FOCUSABLE)
    first?.focus()

    function onKeyDown(e) {
      if (e.key === 'Escape' && closeOnEsc) { onClose(); return }
      if (e.key !== 'Tab') return
      const focusables = modalRef.current?.querySelectorAll(FOCUSABLE)
      if (!focusables?.length) return
      const list = Array.from(focusables)
      const idx = list.indexOf(document.activeElement)
      if (e.shiftKey && (idx <= 0)) { e.preventDefault(); list[list.length - 1].focus() }
      else if (!e.shiftKey && idx === list.length - 1) { e.preventDefault(); list[0].focus() }
    }
    document.addEventListener('keydown', onKeyDown)

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
      // Focus returns to the trigger.
      ;(triggerRef?.current ?? previouslyFocused.current)?.focus?.()
    }
  }, [open, onClose, closeOnEsc, triggerRef])

  // Scale out from the trigger's screen position, scale back toward it on close.
  function originStyle() {
    const rect = triggerRef?.current?.getBoundingClientRect?.()
    if (!rect) return {}
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    return { transformOrigin: `${cx}px ${cy}px` }
  }

  const spring = { type: 'spring', bounce: 0, duration: 0.3 }

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className={styles.scrim}
          onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={reduce ? { duration: 0.15 } : spring}
        >
          <motion.div
            ref={modalRef}
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            style={originStyle()}
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.9 }}
            transition={reduce ? { duration: 0.15 } : spring}
          >
            <div className={styles.header}>
              <h2 className={styles.title}>{title}</h2>
              <button className={styles.close} onClick={onClose} aria-label="Close">
                <X size={18} strokeWidth={1.75} />
              </button>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  )
}
