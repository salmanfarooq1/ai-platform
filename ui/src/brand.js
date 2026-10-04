// src/brand.js
// Single source of truth for the platform name and page-title format.
// Never hardcode these strings in components.

export const BRAND = {
  name: 'Governed Agent Platform',
}

/** `Governed Agent Platform — <Page name>` */
export function pageTitle(page) {
  return page ? `${BRAND.name} — ${page}` : BRAND.name
}

// Mode badge copy + meaning (docs/UI_GUIDELINES.md §2)
export const MODES = {
  'public-preview': { label: 'Public preview', dotVar: '--warning', meaning: 'Free tier, reduced pipeline (no reranker)' },
  local: { label: 'Local', dotVar: '--brand', meaning: 'Developer machine' },
  prod: { label: 'Production', dotVar: '--success', meaning: 'Full pipeline' },
}

// Confidence scale (docs/UI_GUIDELINES.md §3) — used by gauges, badges, citation cards, analytics.
export function confidenceLevel(score, floor = 0.45) {
  if (score == null) return null
  if (score >= 0.75) return 'high'
  if (score >= floor) return 'medium'
  return 'low'
}

export const CONFIDENCE_LABEL = { high: 'HIGH', medium: 'MEDIUM', low: 'LOW' }
