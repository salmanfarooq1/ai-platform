import { MODES } from '../../brand'
import styles from './ModeBadge.module.css'

// Small pill showing the running mode (public-preview/local/prod) from /health
// (docs/UI_GUIDELINES.md §2) — sidebar and System page.
export default function ModeBadge({ mode }) {
  if (!mode) return null
  const cfg = MODES[mode] ?? { label: mode, dotVar: '--text-tertiary', meaning: '' }
  return (
    <span className={styles.pill} title={cfg.meaning}>
      <span className={styles.dot} style={{ background: `var(${cfg.dotVar})` }} aria-hidden="true" />
      {cfg.label}
    </span>
  )
}
