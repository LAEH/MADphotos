import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  base: '/system/',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:3003',
      '/rendered': 'http://localhost:3003',
      '/ai_variants': 'http://localhost:3003',
    },
  },
}))
