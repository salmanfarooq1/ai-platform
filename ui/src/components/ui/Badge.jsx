import styles from './Badge.module.css'
export default function Badge({ children, variant = 'neutral', size = 'md', title, className = '' }) {
  return (
    <span className={[styles.badge, styles[variant], styles[size], className].join(' ')} title={title}>
      {children}
    </span>
  )
}
