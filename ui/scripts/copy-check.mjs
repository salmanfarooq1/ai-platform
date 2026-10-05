// A8: copy check. Run with `npm run copy-check` (it needs Node 22 with --experimental-strip-types for claims.ts).
//
// 1. The headline and subline are exact.
// 2. No long dash (U+2014) or en dash (U+2013) in the UI source, index.html or the design docs.
// 3. No banned words and no "demo" wording in the UI source and index.html.
// 4. Every claim on the landing page maps to an item of the may-claim list in docs/design/CONTENT_STYLE.md.
// 5. The landing and How it works source name nothing from the must-not-claim list.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const REPO = path.resolve(UI, '..')
const { CAPABILITIES, USE_CASES, WHY_OUTSIDE, HEADLINE, SUBLINE } = await import(pathToFileURL(path.join(UI, 'src/landing/claims.ts')).href)

let failures = 0
const fail = (m) => { failures += 1; console.log(`FAIL ${m}`) }
const ok = (m) => console.log(`ok   ${m}`)

function walk(dir, test) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) return e.name === 'node_modules' ? [] : walk(p, test)
    return test(p) ? [p] : []
  })
}
const rel = (p) => path.relative(REPO, p)
const uiFiles = [
  ...walk(path.join(UI, 'src'), (p) => /\.(ts|tsx|css)$/.test(p) && !/schema\.d\.ts$|\.test\.tsx?$/.test(p)),
  path.join(UI, 'index.html'),
  ...walk(path.join(UI, 'public'), (p) => /\.(svg|html|json|txt)$/.test(p)),
]
const docFiles = [...walk(path.join(REPO, 'docs/design'), (p) => p.endsWith('.md')), path.join(REPO, 'docs/UI_GUIDELINES.md'), path.join(REPO, 'docs/adr/0010-design-tokens-and-ink-paper-palette.md')]

console.log('1. Headline and subline')
const EXPECT_H = 'Your agents can only ever do less.'
const EXPECT_S = 'Control what your agents can do. See everything they did.'
HEADLINE === EXPECT_H ? ok(`headline: "${HEADLINE}"`) : fail(`headline is "${HEADLINE}"`)
SUBLINE === EXPECT_S ? ok(`subline: "${SUBLINE}"`) : fail(`subline is "${SUBLINE}"`)
const landing = fs.readFileSync(path.join(UI, 'src/landing/landing-page.tsx'), 'utf8')
landing.includes('{HEADLINE}') && landing.includes('{SUBLINE}') ? ok('landing-page.tsx renders HEADLINE and SUBLINE from claims.ts') : fail('landing-page.tsx does not render the headline and subline constants')
const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf8')
if (/<h1/i.test(html)) fail('index.html has its own h1')

console.log('\n2. No long dash or en dash')
const DASH = /[\u2014\u2013]/
let dashHits = 0
for (const f of [...uiFiles, ...docFiles]) {
  fs.readFileSync(f, 'utf8').split('\n').forEach((line, i) => { if (DASH.test(line)) { dashHits += 1; fail(`${rel(f)}:${i + 1}: ${line.trim().slice(0, 90)}`) } })
}
if (dashHits === 0) ok(`${uiFiles.length + docFiles.length} files scanned, none holds U+2014 or U+2013`)

console.log('\n3. Banned words and "demo" wording')
const BANNED = /\b(elevate[sd]?|seamless(ly)?|unleash(es|ed)?|next-gen(eration)?)\b/i
const DEMO = /\bdemo/i
let wordHits = 0
for (const f of uiFiles) {
  fs.readFileSync(f, 'utf8').split('\n').forEach((line, i) => {
    if (BANNED.test(line) || DEMO.test(line)) { wordHits += 1; fail(`${rel(f)}:${i + 1}: ${line.trim().slice(0, 90)}`) }
  })
}
if (wordHits === 0) ok(`${uiFiles.length} UI files scanned for ${BANNED.source} and ${DEMO.source}`)

console.log('\n4. Every landing claim maps to the may-claim list')
const style = fs.readFileSync(path.join(REPO, 'docs/design/CONTENT_STYLE.md'), 'utf8')
const section = style.split('## What content may claim')[1]?.split('\n## ')[0] ?? ''
const mayClaim = new Map([...section.matchAll(/^(\d+)\.\s+(.+)$/gm)].map((m) => [Number(m[1]), m[2]]))
mayClaim.size >= 8 ? ok(`may-claim list has ${mayClaim.size} items`) : fail(`may-claim list has ${mayClaim.size} items`)
const all = [
  ...CAPABILITIES.map((c) => ({ where: 'capabilities', ...c })),
  ...USE_CASES.map((c) => ({ where: 'use cases', ...c })),
  { where: 'why outside the agent', ...WHY_OUTSIDE },
]
for (const c of all) {
  const item = mayClaim.get(c.claim)
  if (!item) { fail(`${c.where}: "${c.title}" maps to item ${c.claim}, which does not exist`); continue }
  console.log(`ok   [${c.where}] "${c.title}"\n       -> may-claim ${c.claim}: ${item.slice(0, 100)}${item.length > 100 ? '...' : ''}`)
}

console.log('\n5. Nothing from the must-not-claim list on the public pages')
const MUST_NOT = /\b(approvals?|approve[sd]?|uptime|availability|customers?|testimonials?|customer logos?|logo wall|kafka|openshell|sandbox(ed)?|pii|redaction|opa|enterprise-grade|trusted by)\b/i
const publicFiles = [...walk(path.join(UI, 'src/landing'), (p) => /\.(ts|tsx)$/.test(p) && !/\.test\./.test(p))]
let mustHits = 0
for (const f of publicFiles) {
  fs.readFileSync(f, 'utf8').split('\n').forEach((line, i) => { if (MUST_NOT.test(line)) { mustHits += 1; fail(`${rel(f)}:${i + 1}: ${line.trim().slice(0, 100)}`) } })
}
if (mustHits === 0) ok(`${publicFiles.length} landing files scanned for ${MUST_NOT.source}`)

console.log(failures === 0 ? '\nPASS' : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
