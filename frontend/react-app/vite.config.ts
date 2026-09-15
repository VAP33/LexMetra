import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  // FastAPI mounts the built SPA under /app/ (see backend/main.py StaticFiles
  // mount). Without this base, Vite emits root-absolute /assets/... URLs that
  // 404 when the app is served from /app/.
  base: '/app/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: true,
  },
})
