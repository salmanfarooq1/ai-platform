import { useModuleAvailability } from '@/app/modules'
import { ErrorState, PageHeader } from '@/components/governance/states'
import { Skeleton } from '@/components/ui/skeleton'

const PILLARS = [
  ['platform', 'Platform'],
  ['gateway', 'Gateway'],
  ['data', 'Data'],
  ['agents', 'Agents'],
] as const

export default function ModulesPage() {
  const { modules } = useModuleAvailability()
  const data = modules.data
  return (
    <div>
      <PageHeader title="Modules">What each module does and whether it is on for this deployment.</PageHeader>
      {modules.isLoading ? <div role="status" aria-label="Loading modules" className="flex flex-col gap-3">{PILLARS.map(([pillar]) => <Skeleton key={pillar} className="h-24" />)}</div> : null}
      {modules.error ? <ErrorState error={modules.error} title="Could not load module availability." onRetry={() => void modules.refetch()} /> : null}
      {data ? (
        <div className="flex flex-col gap-5">
          <dl className="grid max-w-2xl grid-cols-[max-content_1fr] gap-x-4 gap-y-1 rounded-sm border border-hairline bg-surface p-4 text-callout">
            <dt className="text-fg-secondary">Edition</dt><dd>{data.edition ?? 'Custom modules'}</dd>
            <dt className="text-fg-secondary">Deployment shape</dt><dd>{data.deploy_shape === 'single_tenant' ? 'Single tenant' : 'Multi tenant'}</dd>
          </dl>
          {data.modules.some((module) => !module.enabled) ? (
            <p className="max-w-2xl text-callout text-fg-secondary">
              Modules are chosen at deploy time with the{' '}
              <a className="text-seal underline underline-offset-2" href="/docs/deployment.md#modules">ENABLED_MODULES setting</a>.
            </p>
          ) : null}
          {PILLARS.map(([key, label]) => {
            const items = data.modules.filter((item) => item.pillar === key)
            if (!items.length) return null
            return (
              <section key={key} aria-labelledby={`pillar-${key}`} className="overflow-hidden rounded-sm border border-hairline bg-surface">
                <h2 id={`pillar-${key}`} className="border-b border-hairline bg-muted px-4 py-3 text-title-2">{label}</h2>
                <ul className="m-0 list-none divide-y divide-hairline p-0">
                  {items.map((module) => (
                    <li key={module.name} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                      <div>
                        <h3 className="text-callout font-medium">{module.label}</h3>
                        <p className="mt-1 text-callout text-fg-secondary">{(module as typeof module & { description: string }).description}</p>
                        <p className="mono mt-0.5 text-footnote text-fg-secondary">{module.name}{module.always_on ? ' · always on' : ''}</p>
                      </div>
                      <span className="rounded-full border border-hairline px-2.5 py-1 text-footnote font-medium" aria-label={`${module.label}: ${module.enabled ? 'on' : 'off for this deployment'}`}>
                        {module.enabled ? 'On' : 'Off for this deployment'}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
