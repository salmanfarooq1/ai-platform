import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/endpoints'
import type { ModuleList } from '@/api/types'
import { useSession } from './session'

/** Module metadata is scoped to the verified browser identity and shared by navigation, Ask and System. */
export function useModuleAvailability() {
  const { session } = useSession()
  const tenantId = session?.tenant.id
  const principalId = session?.principal.id
  const modules = useQuery<ModuleList>({
    queryKey: ['system-modules', tenantId, principalId],
    queryFn: api.modules,
    enabled: !!tenantId && !!principalId,
    staleTime: 30_000,
    retry: false,
  })
  const ready = modules.isSuccess
  const enabledModules = ready ? new Set(modules.data.modules.filter((item) => item.enabled).map((item) => item.name)) : undefined
  return { session, modules, ready, enabledModules, agentEnabled: ready && enabledModules?.has('agents') === true }
}
