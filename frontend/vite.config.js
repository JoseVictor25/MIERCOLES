/* import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
})
*/

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const proxy = {
  '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  '/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  '/ws': { target: 'ws://127.0.0.1:8000', ws: true, changeOrigin: true },
}

export default defineConfig({
  plugins: [react()],
  server: { host: true, allowedHosts: true, proxy },
  preview: { host: true, allowedHosts: true, proxy },
})