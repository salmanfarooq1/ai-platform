import { forwardRef } from 'react'
import styles from './Button.module.css'

const Button = forwardRef(function Button(
  { children, variant = 'primary', size = 'md', disabled = false, loading = false, onClick, type = 'button', className = '', ...props },
  ref
) {
  return (
    <button ref={ref} type={type} className={[styles.btn, styles[variant], styles[size], className].join(' ')} disabled={disabled || loading} onClick={onClick} aria-busy={loading} {...props}>
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : null}
      {children}
    </button>
  )
})

export default Button
