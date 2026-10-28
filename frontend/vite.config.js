import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const certDir = path.resolve(__dirname, '../certs')
const certPath = path.join(certDir, 'cert.pem')
const keyPath = path.join(certDir, 'key.pem')

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 30001,
    https: {
      key: fs.readFileSync(keyPath),
      cert: fs.readFileSync(certPath),
    },
    proxy: {
      '/api': {
        target: 'https://127.0.0.1:30000',
        changeOrigin: true,
        secure: false,
      },
      '/charts': {
        target: 'https://127.0.0.1:30000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
