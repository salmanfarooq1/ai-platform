/** Time-range presets used in URLs, for example `?since=7d`. */
export const SINCE_MS: Record<string, number> = {
  '1h': 3_600_000,
  '24h': 86_400_000,
  '7d': 604_800_000,
  '30d': 2_592_000_000,
}

export function sinceToIso(preset: string | null | undefined, now = Date.now()): string | undefined {
  const ms = preset ? SINCE_MS[preset] : undefined
  return ms ? new Date(now - ms).toISOString() : undefined
}

/** The preset that matches a number of days on the overview, or undefined for a custom value. */
export function daysToPreset(days: number): string | undefined {
  return ({ 1: '24h', 7: '7d', 30: '30d' } as Record<number, string>)[days]
}
