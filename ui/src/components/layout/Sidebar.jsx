import { NavLink } from 'react-router-dom'
import { MessageSquareText, Library, ChartNoAxesColumn, Activity } from 'lucide-react'
import Logo from './Logo'
import ModeBadge from './ModeBadge'
import styles from './Sidebar.module.css'

const NAV = [
  { to: '/',         icon: MessageSquareText,  label: 'Ask' },
  { to: '/library',  icon: Library,            label: 'Library' },
  { to: '/insights', icon: ChartNoAxesColumn,  label: 'Insights' },
  { to: '/system',   icon: Activity,           label: 'System' },
]

// Sidebar (desktop) / bottom tab bar (< 900px). Health dot next to System
// when a service is down — wayfinding: problems visible from anywhere (§6).
export default function Sidebar({ health }) {
  const unhealthy = health != null && health.status !== 'ok'
  return (
    <nav className={styles.sidebar} aria-label="Main navigation">
      <div className={styles.logoRow}><Logo /></div>
      <div className={styles.badgeRow}><ModeBadge mode={health?.mode} /></div>
      <ul className={styles.navList} role="list">
        {NAV.map(item => {
          const Icon = item.icon
          return (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
              >
                <span className={styles.navIcon} aria-hidden="true"><Icon size={18} strokeWidth={1.75} /></span>
                <span>{item.label}</span>
                {item.to === '/system' && unhealthy && (
                  <span className={styles.healthDot} aria-label="Service degraded" />
                )}
              </NavLink>
            </li>
          )
        })}
      </ul>
      <div className={styles.footer}>{health?.version ? `v${health.version}` : ''}</div>
    </nav>
  )
}
