import { Sun, Moon } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import CollectionPicker from './CollectionPicker'
import styles from './TopBar.module.css'

export default function TopBar({ scrolled }) {
  const { isDark, toggleDark } = useTheme()

  return (
    <header className={[styles.topBar, scrolled ? styles.scrolled : ''].join(' ')} role="banner">
      <div className={styles.left}>
        <CollectionPicker />
      </div>
      <div className={styles.right}>
        <button
          type="button"
          className={styles.themeBtn}
          onClick={toggleDark}
          aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
        >
          {isDark ? <Moon size={18} strokeWidth={1.75} /> : <Sun size={18} strokeWidth={1.75} />}
        </button>
      </div>
    </header>
  )
}
