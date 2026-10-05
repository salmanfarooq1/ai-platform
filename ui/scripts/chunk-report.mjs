// A7: code splitting. Run after `npm run build`.
//
//   npm run chunk-report
//
// Prints every JavaScript chunk with its size, checks that each route is its own chunk, and greps the chunks that
// load under /app for GSAP and WebGL code. Exits 1 on any violation.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const DIST = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../dist')
const ASSETS = path.join(DIST, 'assets')
const files = fs.readdirSync(ASSETS).filter((f) => f.endsWith('.js')).sort()

// The marketing group is the only code allowed to name or contain GSAP and three.js.
const MARKETING = /^(landing-page|how-it-works-page|marketing-shell|gsap|webgl|hero-scene)-/
const ROUTES = [
  ['/', 'landing-page'], ['/how-it-works', 'how-it-works-page'], ['/signin', 'signin-page'],
  ['/app', 'overview-page'], ['/app/walkthrough', 'walkthrough-page'], ['/app/ask', 'ask-page'], ['/app/library', 'library-page'],
  ['/app/history', 'history-page'], ['/app/requests', 'requests-page'], ['/app/decisions', 'decisions-page'],
  ['/app/policies', 'policies-page'], ['/app/keys', 'keys-page'], ['/app/usage', 'usage-page'], ['/app/runs', 'runs-page'],
  ['/app/trust', 'trust-page'], ['/app/system', 'system-page'],
]
const BAD_CODE = /WebGLRenderer|@react-three|THREE\.|ScrollTrigger|SplitText|gsap\.registerPlugin|getContext\(["']webgl/
const BAD_NAME = /(?:^|\/)(webgl|gsap|hero-scene)-[\w-]+\.js/

let failures = 0
const fail = (m) => { failures += 1; console.log(`FAIL ${m}`) }
const kb = (n) => `${(n / 1024).toFixed(1)} kB`

console.log('Chunks (raw and gzip), largest last')
const rows = files.map((f) => {
  const buf = fs.readFileSync(path.join(ASSETS, f))
  return { f, raw: buf.length, gz: gzipSync(buf).length, group: MARKETING.test(f) ? 'marketing' : 'app/shared', text: buf.toString('utf8') }
}).sort((a, b) => a.raw - b.raw)
for (const r of rows) console.log(`${r.group.padEnd(11)} ${r.f.padEnd(44)} ${kb(r.raw).padStart(10)} ${kb(r.gz).padStart(10)}`)
const sum = (g) => rows.filter((r) => r.group === g).reduce((s, r) => s + r.raw, 0)
console.log(`\ntotal app/shared ${kb(sum('app/shared'))}, total marketing ${kb(sum('marketing'))}, ${rows.length} chunks`)

console.log('\nEach route is its own chunk')
for (const [route, name] of ROUTES) {
  const hit = rows.filter((r) => r.f.startsWith(`${name}-`))
  if (hit.length === 1) console.log(`ok   ${route.padEnd(18)} ${hit[0].f} (${kb(hit[0].raw)})`)
  else fail(`${route} has ${hit.length} chunks named ${name}-*`)
}

console.log('\nNo GSAP or WebGL in the chunks that load under /app (every chunk outside the marketing group)')
const appChunks = rows.filter((r) => r.group === 'app/shared')
for (const r of appChunks) {
  if (BAD_CODE.test(r.text)) fail(`${r.f} contains GSAP or WebGL code`)
  else if (BAD_NAME.test(r.text)) fail(`${r.f} names the gsap, webgl or hero-scene chunk`)
}
console.log(`checked ${appChunks.length} chunks, grep for: ${BAD_CODE.source}`)
const html = fs.readFileSync(path.join(DIST, 'index.html'), 'utf8')
if (/webgl|gsap|hero-scene|landing-page|how-it-works/.test(html)) fail('index.html preloads a marketing chunk')
else console.log('ok   index.html preloads no marketing chunk')

console.log('\nWhere GSAP and WebGL live')
for (const r of rows.filter((x) => BAD_CODE.test(x.text))) console.log(`     ${r.f}`)
const webglOnly = rows.filter((r) => BAD_CODE.test(r.text) && !MARKETING.test(r.f))
if (webglOnly.length > 0) fail(`non-marketing chunks with GSAP or WebGL: ${webglOnly.map((r) => r.f).join(', ')}`)

console.log(failures === 0 ? '\nPASS' : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
