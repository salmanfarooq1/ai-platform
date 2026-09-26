import { createContext, useContext, useState, useCallback, useRef } from 'react'
import ToastViewport from '../components/ui/Toast'

// Shared toast system (BRANDING.md §8, §15) — replaces alert()/confirm() and
// ad hoc result banners everywhere in the app.
const ToastContext = createContext(null)

let uid = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef(new Map())

  const dismiss = useCallback((id) => {
    setToasts(t => t.filter(x => x.id !== id))
    const timer = timers.current.get(id)
    if (timer) { clearTimeout(timer); timers.current.delete(id) }
  }, [])

  const toast = useCallback(({ variant = 'info', title, message, duration }) => {
    const id = ++uid
    setToasts(t => [...t, { id, variant, title, message }])
    // Success/info auto-dismiss after 4s. Errors and warnings stay until dismissed.
    const auto = duration ?? (variant === 'success' || variant === 'info' ? 4000 : null)
    if (auto) timers.current.set(id, setTimeout(() => dismiss(id), auto))
    return id
  }, [dismiss])

  const api = useMemoApi(toast)

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}

// Small helper so consumers can call toast.success('msg') as well as
// toast({ variant, title, message }).
function useMemoApi(toast) {
  return {
    show: toast,
    success: (message, title) => toast({ variant: 'success', message, title }),
    error: (message, title) => toast({ variant: 'error', message, title }),
    warning: (message, title) => toast({ variant: 'warning', message, title }),
    info: (message, title) => toast({ variant: 'info', message, title }),
  }
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
