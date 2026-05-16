import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/auth': 'http://localhost:8081',
      '/products': 'http://localhost:8081',
      '/runs': 'http://localhost:8081',
      '/spec-dirs': 'http://localhost:8081',
      '/health': 'http://localhost:8081',
    },
  },
})
