import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  base: '/state/',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/rendered': 'http://localhost:3000',
      '/ai_variants': 'http://localhost:3000',
    },
  },
}))
