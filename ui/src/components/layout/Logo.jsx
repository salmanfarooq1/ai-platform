import { BRAND } from '../../brand'
import styles from './Logo.module.css'

// Logo mark: a rounded square with three stacked lines, the last ending in a
// dot — "a paragraph, with its source marked" (BRANDING.md §2).
export function LogoMark({ size = 32 }) {
  return (
    <div className={styles.mark} style={{ width: size, height: size, borderRadius: size * (9 / 32) }} aria-hidden="true">
      <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none">
        <line x1="2" y1="6" x2="22" y2="6" stroke="var(--bg-surface)" strokeWidth="2" strokeLinecap="round" />
        <line x1="2" y1="12" x2="22" y2="12" stroke="var(--bg-surface)" strokeWidth="2" strokeLinecap="round" />
        <line x1="2" y1="18" x2="16" y2="18" stroke="var(--bg-surface)" strokeWidth="2" strokeLinecap="round" />
        <circle cx="20" cy="18" r="1.6" fill="var(--brand)" />
      </svg>
    </div>
  )
}

/** Full lockup: mark + name + tagline. `collapsed` shows the mark only. */
export default function Logo({ collapsed = false }) {
  return (
    <div className={styles.lockup}>
      <LogoMark />
      {!collapsed && (
        <div className={styles.text}>
          <span className={styles.name}>{BRAND.name}</span>
          <span className={styles.tagline}>{BRAND.taglineCaption}</span>
        </div>
      )}
    </div>
  )
}
