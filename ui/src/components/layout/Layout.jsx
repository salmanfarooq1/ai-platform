import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import styles from './Layout.module.css'

export default function Layout({ health }) {
  return (
    <div className={styles.shell}>
      <TopBar health={health} />
      <div className={styles.body}>
        <Sidebar health={health} />
        <main className={styles.main} id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
