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
      '/auth': { target: 'http://localhost:8081', changeOrigin: true },
      '/products': {
        target: 'http://localhost:8081',
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) return '/index.html'
        },
      },
      '/runs': {
        target: 'http://localhost:8081',
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) return '/index.html'
        },
      },
      '/me': { target: 'http://localhost:8081', changeOrigin: true },
      '/spec-dirs': { target: 'http://localhost:8081', changeOrigin: true },
      '/health': { target: 'http://localhost:8081', changeOrigin: true },
      '/waitlist': { target: 'http://localhost:8081', changeOrigin: true },
      '/growth': { target: 'http://localhost:8081', changeOrigin: true },
    },
  },
})
