// The agent runtime (ADR-0009) keeps a run's status in memory, so an older run, or one that was refused before it
// started, has none: it says "Not tracked" rather than guessing.
const RUN_STATUS: Record<string, string> = { running: 'Running', succeeded: 'Finished', failed: 'Failed', stopped: 'Stopped' }

export function runStatusWord(status: string | null | undefined): string {
  return (status && RUN_STATUS[status]) || 'Not tracked'
}
