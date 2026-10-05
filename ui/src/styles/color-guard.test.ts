import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = path.resolve(__dirname, '..')
const LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|hwb|oklch|oklab)\(/

function cssFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name)
    return e.isDirectory() ? cssFiles(p) : p.endsWith('.css') ? [p] : []
  })
}

// ESLint guards the TypeScript files. This test guards the stylesheets: only the generated tokens file may hold a colour literal.
describe('colour literals', () => {
  it('appear in no stylesheet except the generated tokens.css', () => {
    const offenders = cssFiles(SRC)
      .filter((f) => path.basename(f) !== 'tokens.css')
      .filter((f) => LITERAL.test(fs.readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')))
    expect(offenders).toEqual([])
  })

  it('tokens.css does hold them, so the check above is not vacuous', () => {
    expect(LITERAL.test(fs.readFileSync(path.join(SRC, 'styles/tokens.css'), 'utf8'))).toBe(true)
  })
})
