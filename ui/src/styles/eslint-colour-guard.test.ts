// @vitest-environment node
/* eslint-disable no-restricted-syntax -- this file holds colour literals only as probe input for the guard itself */
import path from 'node:path'
import { ESLint } from 'eslint'
import { describe, expect, it } from 'vitest'

const ROOT = path.resolve(__dirname, '../..')
const eslint = new ESLint({ cwd: ROOT, overrideConfigFile: path.join(ROOT, 'eslint.config.js') })

async function messages(code: string, file = 'src/probe.ts') {
  const [result] = await eslint.lintText(code, { filePath: path.join(ROOT, file) })
  return result!.messages.filter((m) => m.ruleId === 'no-restricted-syntax').map((m) => m.message)
}

describe('eslint colour guard', () => {
  it.each([
    ["const s = { color: '#fff' }", 'hex'],
    ["const s = { backgroundColor: '#1a2b3c' }", 'hex'],
    ["const s = { 'background-color': '#abcd' }", 'hex'],
    ["const s = { fill: '#12345678' }", 'hex'],
    ["const s = '1px solid #fff'", 'hex'],
    ["const s = 'color:#0b5d6e;'", 'hex'],
    ["const s = 'bg-[#fff]'", 'hex'],
    ['const s = `border: 1px solid #FFF`', 'hex'],
    ["const s = 'rgb(1, 2, 3)'", 'rgb'],
    ["const s = 'oklch(0.5 0.1 200)'", 'rgb'],
  ])('a real colour fails: %s', async (code) => {
    expect((await messages(code)).length).toBeGreaterThan(0)
  })

  it('a real hex in JSX colour attributes fails', async () => {
    expect((await messages('export const A = () => <path fill="#fff" />', 'src/probe.tsx')).length).toBeGreaterThan(0)
    expect((await messages("export const A = () => <path stroke={'#000000'} />", 'src/probe.tsx')).length).toBeGreaterThan(0)
  })

  it.each(['red', 'blue', 'green', 'black', 'white', 'gray', 'grey', 'orange', 'purple', 'yellow', 'pink', 'Red', ' white '])(
    'the named colour %j fails as a quoted value',
    async (name) => {
      expect(await messages(`const s = { color: '${name}' }`)).toEqual(['No named CSS colours. Use a design token (var(--...)) from tokens/tokens.json.'])
      expect((await messages(`const c = "${name}"`)).length).toBeGreaterThan(0)
    },
  )

  it.each([
    "const href = '#add'",
    "const a = { href: '#add' }",
    "const id = '#bad'",
    "const s = 'see #add for details'",
    "const link = `#${'face'}`",
    "const s = 'redirect'",
    "const s = 'greenhouse'",
    "const s = 'var(--ink)'",
  ])('an anchor or an ordinary word passes: %s', async (code) => {
    expect(await messages(code)).toEqual([])
  })
})
