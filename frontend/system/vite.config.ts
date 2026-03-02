import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiPort = process.env.API_PORT || '3000'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  base: '/system/',
  server: {
    port: parseInt(process.env.VITE_PORT || '5173'),
    proxy: {
      '/api': `http://localhost:${apiPort}`,
      '/rendered': `http://localhost:${apiPort}`,
      '/ai_variants': `http://localhost:${apiPort}`,
      '/generated': `http://localhost:${apiPort}`,
      '/images': `http://localhost:${apiPort}`,
    },
  },
}))
