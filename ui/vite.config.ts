/// <reference types="vitest/config" />
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API runs on :8000. Proxying /v1 keeps the session cookie same-site (blueprint section 4).
const apiTarget = process.env.API_URL ?? 'http://localhost:8000'
const proxy = { '/v1': { target: apiTarget, changeOrigin: false } }

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // The WebGL chunk (three.js) is about 880 kB. It is lazy-loaded on the landing page only, so the warning does not apply.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // Keep WebGL and animation code out of every /app chunk: they live only in the landing chunks.
        manualChunks(id) {
          // Vite's dynamic-import helper is shared by every lazy chunk. Pin it to the vendor chunk, or it can end up
          // inside the WebGL chunk and pull that chunk in with the landing page.
          if (id.includes('vite/preload-helper') || id.includes('vite/modulepreload-polyfill')) return 'react'
          if (id.includes('node_modules/three/') || id.includes('@react-three') || id.includes('node_modules/three-stdlib')) return 'webgl'
          if (id.includes('node_modules/gsap')) return 'gsap'
          if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/') || id.includes('node_modules/react-router') || id.includes('node_modules/scheduler')) return 'react'
          return undefined
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
})
