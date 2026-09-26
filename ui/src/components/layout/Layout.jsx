import { useState, useRef, useCallback } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import styles from './Layout.module.css'

export default function Layout({ health }) {
  const [scrolled, setScrolled] = useState(false)
  const scrollRef = useRef(null)

  const onScroll = useCallback(() => {
    setScrolled((scrollRef.current?.scrollTop ?? 0) > 4)
  }, [])

  return (
    <div className={styles.shell}>
      <Sidebar health={health} />
      <div className={styles.contentArea}>
        <main className={styles.scroll} id="main-content" ref={scrollRef} onScroll={onScroll}>
          <TopBar health={health} scrolled={scrolled} />
          <div className={styles.container}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
