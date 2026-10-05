// A run's status is read from its job (durable since Sprint 007). A run that was refused before it started has no
// job and no status: it says "Not tracked" rather than guessing.
const RUN_STATUS: Record<string, string> = { queued: 'Queued', running: 'Running', succeeded: 'Finished', failed: 'Failed', stopped: 'Stopped' }

export function runStatusWord(status: string | null | undefined): string {
  return (status && RUN_STATUS[status]) || 'Not tracked'
}

/** The run time in plain units, or "Running" while it has not finished. None when the run has no times. */
export function runDuration(startedAt: string | null | undefined, finishedAt: string | null | undefined): string {
  if (!startedAt) return 'None'
  if (!finishedAt) return 'Running'
  const seconds = Math.max(0, (Date.parse(finishedAt) - Date.parse(startedAt)) / 1000)
  return seconds < 10 ? `${seconds.toFixed(1)} s` : seconds < 120 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`
}
