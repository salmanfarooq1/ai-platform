// Does NOT use apiFetch — multipart requires browser to set Content-Type boundary.
// Does NOT import from client.js — BASE_URL is not exported there.
export async function ingestFile({ file, namespace = 'legal', documentId }) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('namespace', namespace)
  if (documentId) formData.append('document_id', documentId)

  const base = import.meta.env.VITE_API_URL ?? '/api'
  const response = await fetch(`${base}/ingest`, { method: 'POST', body: formData })

  if (!response.ok) {
    let body
    try { body = await response.json() } catch { body = { detail: `HTTP ${response.status}` } }
    const err = new Error(body.detail || 'Ingest failed')
    err.status = response.status
    err.body = body
    throw err
  }
  return response.json()
  // { document_id, namespace, total_chunks, total_time_seconds,
  //   throughput_chunks_per_second, status, content_hash, chunks_deleted }
}
