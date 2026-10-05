import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { composite, contrastRatio, parseColor } from '@/lib/contrast'

const ROOT = path.resolve(__dirname, '../..')
const tokens = JSON.parse(fs.readFileSync(path.join(ROOT, 'tokens/tokens.json'), 'utf8')) as Record<string, Record<string, { $value: string }>>
const doc = fs.readFileSync(path.resolve(ROOT, '../docs/design/ACCESSIBILITY.md'), 'utf8')

/** The rows of the "Contrast pairs" table: | `fg` | `bg` | minimum | use | */
function pairs(): Array<{ fg: string; bg: string; min: number; use: string }> {
  const section = doc.split('## Contrast pairs')[1]?.split('\n## ')[0] ?? ''
  const rows = [...section.matchAll(/^\|\s*`([\w-]+)`\s*\|\s*`([\w-]+)`\s*\|\s*([\d.]+)\s*\|\s*(.+?)\s*\|\s*$/gm)]
  return rows.map((m) => ({ fg: m[1] as string, bg: m[2] as string, min: Number(m[3]), use: m[4] as string }))
}

function value(set: 'light' | 'dark', name: string): string {
  const raw = tokens[set]?.[name]?.$value
  if (raw === undefined) throw new Error(`No token ${set}.${name}`)
  const alias = /^\{(light|dark)\.([\w-]+)\}$/.exec(raw)
  return alias ? value(alias[1] as 'light' | 'dark', alias[2] as string) : raw
}

const list = pairs()

describe('ACCESSIBILITY.md contrast pairs', () => {
  it('lists the pairs the product relies on', () => {
    expect(list.length).toBeGreaterThanOrEqual(20)
    for (const need of ['text-primary', 'text-secondary', 'text-tertiary', 'seal', 'allow', 'deny', 'escalate']) {
      expect(list.some((p) => p.fg === need), `a pair for ${need}`).toBe(true)
    }
  })

  for (const set of ['light', 'dark'] as const) {
    it(`every pair meets its minimum in the ${set} theme`, () => {
      const surface = parseColor(value(set, 'bg-surface'))
      const lines: string[] = []
      for (const p of list) {
        const bg = composite(parseColor(value(set, p.bg)), surface)
        const fg = composite(parseColor(value(set, p.fg)), bg)
        const ratio = contrastRatio(fg, bg)
        lines.push(`${set.padEnd(5)} ${p.fg.padEnd(15)} on ${p.bg.padEnd(14)} ${ratio.toFixed(2).padStart(5)}:1  (min ${p.min})  ${p.use}`)
        expect(ratio, `${set}: ${p.fg} on ${p.bg}`).toBeGreaterThanOrEqual(p.min)
      }
      console.log(`contrast, ${set} theme\n${lines.join('\n')}`)
    })
  }
})
