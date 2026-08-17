import styles from './Toggle.module.css'
export default function Toggle({ label, checked, onChange, disabled = false, id }) {
  const tid = id || `toggle-${label?.replace(/\s+/g, '-').toLowerCase()}`
  return (
    <div className={styles.wrapper}>
      <label className={styles.label} htmlFor={tid}>{label}</label>
      <button id={tid} role="switch" aria-checked={checked} disabled={disabled}
        className={`${styles.track} ${checked ? styles.on : styles.off}`}
        onClick={() => onChange?.(!checked)} type="button">
        <span className={styles.thumb} />
        <span className="sr-only">{checked ? 'On' : 'Off'}</span>
      </button>
    </div>
  )
}
