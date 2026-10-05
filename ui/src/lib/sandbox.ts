import type { SandboxEvent } from '@/api/types'

/** What each sandbox event kind is called. A person sees the word and the icon, never the color alone. */
export const SANDBOX_WORDS: Record<SandboxEvent['kind'], string> = {
  start: 'Sandbox started',
  exit: 'Sandbox exited',
  network_denied: 'Network call blocked',
  file_denied: 'File access blocked',
  limit_hit: 'Limit reached',
  log: 'Sandbox log',
}

/** A network or file denial is a deny state: the same emphasis as a gateway deny. */
export function isSandboxDeny(kind: SandboxEvent['kind']): boolean {
  return kind === 'network_denied' || kind === 'file_denied'
}

/** One plain line from the event's detail. It never holds a secret or input text (the server cleans it). */
export function sandboxDetail(event: SandboxEvent): string {
  const d = event.detail as Record<string, unknown>
  const text = (key: string): string | null => (typeof d[key] === 'string' || typeof d[key] === 'number' ? String(d[key]) : null)
  switch (event.kind) {
    case 'network_denied': {
      const host = text('host')
      const port = text('port')
      return host ? `Tried to reach ${host}${port ? `:${port}` : ''}. The sandbox may only reach the gateway.` : 'A connection outside the gateway was stopped.'
    }
    case 'file_denied': {
      const path = text('path')
      return path ? `Tried to read ${path}. The sandbox may only use its work directory.` : 'A file outside the work directory was stopped.'
    }
    case 'limit_hit': {
      const limit = text('limit')
      return limit ? `Hit the ${limit.replace(/_/g, ' ')} limit.` : 'A run limit was reached.'
    }
    case 'exit': {
      const code = text('code')
      const reason = text('reason')
      if (code !== null) return code === '0' ? 'The agent finished (exit code 0).' : `The agent stopped (exit code ${code}).`
      return reason ? `The run ended: ${reason.replace(/_/g, ' ')}.` : 'The sandbox was removed.'
    }
    case 'start': {
      const limit = text('limit')
      return limit ? `Limits: ${limit}.` : 'The agent runs in an isolated sandbox.'
    }
    default:
      return text('message') ?? 'No detail.'
  }
}

/** "2 network calls blocked, 1 file access blocked", or null when the sandbox stopped nothing. */
export function sandboxSummary(events: SandboxEvent[]): string | null {
  const net = events.filter((e) => e.kind === 'network_denied').length
  const files = events.filter((e) => e.kind === 'file_denied').length
  const parts = [
    net ? `${net} network ${net === 1 ? 'call' : 'calls'} blocked` : null,
    files ? `${files} file ${files === 1 ? 'access' : 'accesses'} blocked` : null,
  ].filter((p): p is string => p !== null)
  return parts.length ? parts.join(', ') : null
}
