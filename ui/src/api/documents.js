import { apiFetch } from './client'
export async function listDocuments(namespace) {
  const qs = namespace ? `?namespace=${encodeURIComponent(namespace)}` : ''
  const { data } = await apiFetch(`/documents${qs}`, { method: 'GET' })
  return data  // { documents: [...], count: N }
}
