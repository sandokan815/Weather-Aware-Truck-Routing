import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In dev, /api is proxied to Django so no CORS setup is needed.
// For a hosted build set VITE_API_BASE to the backend URL instead.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1', // explicit IPv4 so localhost and 127.0.0.1 both work
    port: 5173,
    proxy: {
      '/api': { target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
