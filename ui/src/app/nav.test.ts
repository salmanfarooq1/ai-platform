import { describe, expect, it } from 'vitest'
import { visibleNav } from './nav'

describe('visibleNav', () => {
  it('hides items of disabled modules', () => {
    const disabled = visibleNav(new Set(['gateway']))
    expect(disabled.flatMap((group) => group.items).some((item) => item.to === '/app/runs')).toBe(false)

    const enabled = visibleNav(new Set(['gateway', 'agents']))
    expect(enabled.flatMap((group) => group.items).some((item) => item.to === '/app/runs')).toBe(true)
  })

  it('hides optional items while metadata is unknown', () => {
    for (const enabled of [undefined, new Set<string>()]) {
      const items = visibleNav(enabled).flatMap((group) => group.items)
      expect(items.some((item) => item.to === '/app/runs')).toBe(false)
      expect(items.some((item) => item.to === '/app/requests')).toBe(true)
      expect(items.some((item) => item.to === '/app/trust')).toBe(true)
      expect(items.some((item) => item.to === '/app/modules')).toBe(true)
    }
  })
})
