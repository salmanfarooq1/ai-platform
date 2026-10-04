import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // PREVIEW_API_KEY comes from ui/.env.local (git-ignored). loadEnv with the '' prefix reads it for
  // this config only: Vite exposes just VITE_-prefixed variables to the browser bundle, so the key
  // is added by the dev proxy and never reaches client code.
  const env = loadEnv(mode, process.cwd(), '')
  const headers = env.PREVIEW_API_KEY ? { Authorization: `Bearer ${env.PREVIEW_API_KEY}` } : {}

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          headers,
          rewrite: path => path.replace(/^\/api/, ''),
        },
      },
    },
    build: { outDir: 'dist', rollupOptions: { output: { manualChunks: undefined } } },
  }
})
