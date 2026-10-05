import { defineConfig, devices } from '@playwright/test'

// Cross-stack tests: the real API with LLM and embedding fakes (scripts/e2e/serve.py), real Postgres and Redis,
// and the built UI served by `vite preview`, which proxies /v1 to the API so cookies are same-site.
// Run `npm run build` first (the `npm run e2e` script does).
// Postgres and Redis must be up: `docker compose up -d postgres redis`.
// Chromium comes from PLAYWRIGHT_BROWSERS_PATH. Playwright is pinned to the version that matches /opt/pw-browsers here.
const API_PORT = 8000
const UI_PORT = 4173
// A second API in MODE=public-preview, for the read-only preview test.
const PREVIEW_API_PORT = 8001
const PREVIEW_UI_PORT = 4174

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['json', { outputFile: 'test-results/results.json' }]],
  use: {
    baseURL: `http://127.0.0.1:${UI_PORT}`,
    trace: 'retain-on-failure',
  },
  projects: [
    // Signs in once through the real sign-in screen and saves the cookie. Sign-in is rate limited by client IP
    // (10 a minute), so the other tests reuse this session instead of signing in again.
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'chromium',
      dependencies: ['setup'],
      testIgnore: /auth\.setup\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'e2e/.state/auth.json',
        // Software WebGL, so the landing hero can load in headless Chromium.
        launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] },
      },
    },
  ],
  webServer: [
    {
      command: `poetry run python scripts/e2e/serve.py --port ${API_PORT}`,
      cwd: '..',
      url: `http://127.0.0.1:${API_PORT}/v1/health`,
      timeout: 180_000,
      reuseExistingServer: !!process.env.E2E_REUSE,
    },
    {
      command: `npx vite preview --host 127.0.0.1 --port ${UI_PORT} --strictPort`,
      env: { API_URL: `http://127.0.0.1:${API_PORT}` },
      url: `http://127.0.0.1:${UI_PORT}/`,
      timeout: 60_000,
      reuseExistingServer: !!process.env.E2E_REUSE,
    },
    {
      command: `poetry run python scripts/e2e/serve.py --preview --port ${PREVIEW_API_PORT} --state-dir ui/e2e/.state/preview`,
      cwd: '..',
      url: `http://127.0.0.1:${PREVIEW_API_PORT}/v1/health`,
      timeout: 180_000,
      reuseExistingServer: !!process.env.E2E_REUSE,
    },
    {
      command: `npx vite preview --host 127.0.0.1 --port ${PREVIEW_UI_PORT} --strictPort`,
      env: { API_URL: `http://127.0.0.1:${PREVIEW_API_PORT}` },
      url: `http://127.0.0.1:${PREVIEW_UI_PORT}/`,
      timeout: 60_000,
      reuseExistingServer: !!process.env.E2E_REUSE,
    },
  ],
})
