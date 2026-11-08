import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ModuleList } from '@/api/types'
import { renderWithProviders } from '@/test/render'
import ModulesPage from './modules-page'

type ModuleWithDescription = ModuleList['modules'][number] & { description: string }

const modules: Omit<ModuleList, 'modules'> & { modules: ModuleWithDescription[] } = {
  edition: 'Custom modules',
  deploy_shape: 'single_tenant',
  modules: [
    { name: 'gateway', label: 'Gateway', pillar: 'gateway', enabled: true, nav_group: 'Governance', always_on: true, description: 'Checks requests against identity, scope, policy and budgets.' },
    { name: 'agents', label: 'Agents', pillar: 'agents', enabled: false, nav_group: 'Governance', always_on: false, description: 'Runs governed agent workflows with approved tools.' },
  ],
}

describe('ModulesPage', () => {
  it('explains each module and how to change it', () => {
    renderWithProviders(<ModulesPage />, { modules })

    expect(screen.getByText('Checks requests against identity, scope, policy and budgets.')).toBeInTheDocument()
    expect(screen.getByText('Runs governed agent workflows with approved tools.')).toBeInTheDocument()
    expect(screen.getByText('Off for this deployment')).toBeInTheDocument()

    const settingNote = screen.getByText(/Modules are chosen at deploy time with the/)
    expect(settingNote).toHaveTextContent('ENABLED_MODULES setting')
    expect(screen.getAllByRole('link', { name: 'ENABLED_MODULES setting' })).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'ENABLED_MODULES setting' })).toHaveAttribute('href', '/docs/deployment.md#modules')
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /enable|disable|toggle/i })).not.toBeInTheDocument()
  })
})
