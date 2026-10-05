/** History is a client-side list of this browser's asks (blueprint section 4). It lives in localStorage only. */
import type { Verdict } from '@/api/types'

export interface AskRecord {
  id: string
  at: string
  mode: 'search' | 'agent'
  kb: string
  question: string
  requestId: string | null
  verdict: Verdict
  reason: string | null
}

const KEY = 'ask-history'
const MAX = 50

export function readHistory(): AskRecord[] {
  try {
    const raw = localStorage.getItem(KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? (parsed as AskRecord[]) : []
  } catch {
    return []
  }
}

export function addHistory(rec: Omit<AskRecord, 'id' | 'at'>): void {
  try {
    const next: AskRecord[] = [{ ...rec, id: crypto.randomUUID(), at: new Date().toISOString() }, ...readHistory()].slice(0, MAX)
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // Storage can be blocked. History is a convenience, so ignoring the write is fine.
  }
}

export function clearHistory(): void {
  try { localStorage.removeItem(KEY) } catch { /* nothing to clear */ }
}
