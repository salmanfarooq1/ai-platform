import styles from './Card.module.css'
export default function Card({ children, className = '', title, accent = false }) {
  return (
    <section className={[styles.card, accent ? styles.accent : '', className].join(' ')} aria-label={title}>
      {title && <h3 className={styles.title}>{title}</h3>}
      {children}
    </section>
  )
}
