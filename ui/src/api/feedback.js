import { apiFetch } from './client'

export async function submitFeedback({ requestId, endpoint, rating, comment = null }) {
  const { data } = await apiFetch('/feedback', {
    method: 'POST',
    body: JSON.stringify({ request_id: requestId, endpoint, rating, comment }),
  })
  return data  // { status: "recorded" }
  // NOTE: server returns HTTP 201 — apiFetch treats any 2xx as success, so this works fine.
}

export async function getQualityReport(days = 30) {
  const { data } = await apiFetch(`/quality-report?days=${days}`, { method: 'GET' })
  return data
}
