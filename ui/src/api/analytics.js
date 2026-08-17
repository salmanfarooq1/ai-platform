import { apiFetch } from './client'
export async function getAnalyticsSummary(days = 7) {
  const { data } = await apiFetch(`/analytics/summary?days=${days}`, { method: 'GET' })
  return data
}
