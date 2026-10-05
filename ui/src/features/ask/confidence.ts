export type ConfidenceLevel = 'high' | 'medium' | 'low'

export function confidenceLevel(score: number, floor = 0.45): ConfidenceLevel {
  if (score >= 0.75) return 'high'
  if (score >= floor) return 'medium'
  return 'low'
}
