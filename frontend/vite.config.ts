import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: process.env.FRONTEND_HOST || '127.0.0.1',
    port: Number(process.env.FRONTEND_PORT || 5173),
    strictPort: true,
    proxy: {
      '/rpc': {
        target: process.env.ENVOY_ADDRESS || 'http://127.0.0.1:8080',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/rpc/, ''),
      },
    },
  },
})
