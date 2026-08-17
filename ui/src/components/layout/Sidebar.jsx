import { NavLink } from 'react-router-dom'
import styles from './Sidebar.module.css'

const NAV = [
  { to: '/',          icon: '◈', label: 'Dashboard',  desc: 'System health & overview' },
  { to: '/search',    icon: '⌕', label: 'Search',     desc: 'RAG search interface' },
  { to: '/agent',     icon: '⟳', label: 'Agent',      desc: 'Multi-step reasoning' },
  { to: '/ingest',    icon: '⇑', label: 'Ingest',     desc: 'Upload documents' },
  { to: '/analytics', icon: '▲', label: 'Analytics',  desc: 'Cost & usage analytics' },
  { to: '/documents', icon: '▤', label: 'Documents',  desc: 'Ingested document registry' },
]

export default function Sidebar({ health }) {
  return (
    <nav className={styles.sidebar} aria-label="Main navigation">
      <div className={styles.logo}>
        <span className={styles.logoMark}>AI</span>
        <span className={styles.logoText}>Platform</span>
      </div>
      <ul className={styles.navList} role="list">
        {NAV.map(item => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
              title={item.desc}
            >
              <span className={styles.icon} aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
      <div className={styles.footer}>
        <span className={styles.version}>{health?.version ?? '—'}</span>
      </div>
    </nav>
  )
}
