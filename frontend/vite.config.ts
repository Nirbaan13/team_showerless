import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'MOTION_')
  return {
    plugins: [react()],
    base: './',
    server: {
      proxy: {
        '/api/motion': process.env.MOTION_SERVICE_URL || env.MOTION_SERVICE_URL || 'http://127.0.0.1:8001',
        '/detect': process.env.MOTION_SERVICE_URL || env.MOTION_SERVICE_URL || 'http://127.0.0.1:8001',
      },
    },
  }
})
