import styles from './StatusDot.module.css'
export default function StatusDot({ status = 'unknown', animated = true, size = 'md' }) {
  return (
    <span
      className={[styles.dot, styles[status], styles[size], animated ? styles.animated : ''].join(' ')}
      role="img"
      aria-label={`Status: ${status}`}
    />
  )
}
