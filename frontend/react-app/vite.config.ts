import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => ({
  // FastAPI mounts the production bundle at /app. Vite development remains at
  // / so `npm run dev` continues to work at http://localhost:5173/.
  base: mode === 'production' ? '/app/' : '/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/regulatory': 'http://127.0.0.1:8000',
      '/inspections': 'http://127.0.0.1:8000',
      '/extract-preview': 'http://127.0.0.1:8000',
      '/scan': 'http://127.0.0.1:8000',
      '/auth': 'http://127.0.0.1:8000',
    },
  },
}))
