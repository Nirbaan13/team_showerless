import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv, searchForWorkspaceRoot } from 'vite'

const mlFrontend = fileURLToPath(new URL('../ml/pvusatov/frontend', import.meta.url))

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'MOTION_')
  return {
    plugins: [react()],
    base: './',
    resolve: {
      dedupe: ['react', 'react-dom', 'lucide-react'],
    },
    server: {
      fs: {
        allow: [searchForWorkspaceRoot(process.cwd()), mlFrontend],
      },
      proxy: {
        '/api/motion': process.env.MOTION_SERVICE_URL || env.MOTION_SERVICE_URL || 'http://127.0.0.1:8001',
        '/detect': process.env.MOTION_SERVICE_URL || env.MOTION_SERVICE_URL || 'http://127.0.0.1:8001',
        '/backend': {
          target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
          changeOrigin: true,
          rewrite: path => path.replace(/^\/backend/, ''),
        },
        '/api': {
          target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
