import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { CircleCheck, TriangleAlert, CircleAlert, Info, X } from 'lucide-react'
import styles from './Toast.module.css'

const ICONS = { success: CircleCheck, warning: TriangleAlert, error: CircleAlert, info: Info }

// Toasts enter from below with a critically damped spring and leave the same
// way they came (BRANDING.md §12, §8). Reduced motion: opacity cross-fade only.
export default function ToastViewport({ toasts, onDismiss }) {
  const reduce = useReducedMotion()
  const spring = { type: 'spring', bounce: 0, duration: 0.25 }

  return (
    <div className={styles.viewport} aria-live="polite">
      <AnimatePresence>
        {toasts.map(t => {
          const Icon = ICONS[t.variant] ?? Info
          return (
            <motion.div
              key={t.id}
              role={t.variant === 'success' || t.variant === 'info' ? 'status' : 'alert'}
              className={[styles.toast, styles[t.variant]].join(' ')}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, y: 24 }}
              transition={reduce ? { duration: 0.15 } : spring}
            >
              <Icon size={18} strokeWidth={1.75} className={styles.icon} aria-hidden="true" />
              <div className={styles.body}>
                {t.title && <div className={styles.title}>{t.title}</div>}
                {t.message && <div className={styles.message}>{t.message}</div>}
              </div>
              <button className={styles.close} onClick={() => onDismiss(t.id)} aria-label="Dismiss notification">
                <X size={14} strokeWidth={1.75} />
              </button>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
