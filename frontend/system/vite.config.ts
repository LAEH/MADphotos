import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiPort = process.env.API_PORT || '3000'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  base: '/system/',
  server: {
    port: 5173,
    proxy: {
      '/api': `http://localhost:${apiPort}`,
      '/rendered': `http://localhost:${apiPort}`,
      '/ai_variants': `http://localhost:${apiPort}`,
    },
  },
}))
