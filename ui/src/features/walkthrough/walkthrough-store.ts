/** The walkthrough opens first for a new browser. The flag is remembered in localStorage. */
const KEY = 'walkthrough-seen'

export function walkthroughSeen(): boolean {
  try { return localStorage.getItem(KEY) === '1' } catch { return false }
}

export function markWalkthroughSeen(): void {
  try { localStorage.setItem(KEY, '1') } catch { /* the walkthrough may open again, which is harmless */ }
}

/** Where to go after sign-in or a new preview session. */
export function firstRunPath(): string {
  return walkthroughSeen() ? '/app' : '/app/walkthrough'
}
