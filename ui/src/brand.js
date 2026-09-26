// src/brand.js
// Single source of truth for product name, tagline and page-title format.
// BRANDING.md §1 — never hardcode these strings in components.

export const BRAND = {
  name: 'Verity',
  tagline: 'Answers you can trace.',
  taglineCaption: 'ANSWERS YOU CAN TRACE',
}

/** `Verity — <Page name>` (BRANDING.md §1) */
export function pageTitle(page) {
  return page ? `${BRAND.name} — ${page}` : BRAND.name
}

// Mode badge copy + meaning (BRANDING.md §3)
export const MODES = {
  demo: { label: 'Demo', dotVar: '--warning', meaning: 'Free tier, reduced pipeline (no reranker)' },
  local: { label: 'Local', dotVar: '--brand', meaning: 'Developer machine' },
  prod: { label: 'Production', dotVar: '--success', meaning: 'Full pipeline' },
}

// Confidence scale (BRANDING.md §4) — used by gauges, badges, citation cards, analytics.
export function confidenceLevel(score, floor = 0.45) {
  if (score == null) return null
  if (score >= 0.75) return 'high'
  if (score >= floor) return 'medium'
  return 'low'
}

export const CONFIDENCE_LABEL = { high: 'HIGH', medium: 'MEDIUM', low: 'LOW' }
