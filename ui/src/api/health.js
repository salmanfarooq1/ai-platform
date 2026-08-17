import { apiFetch } from './client'
export async function getHealth() {
  const { data } = await apiFetch('/health', { method: 'GET' })
  return data  // { status, db, redis, version, mode, uptime_seconds }
}
