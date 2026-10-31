import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In docker compose the API and tile server are reachable by service name
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'
const tilesTarget = process.env.TILES_PROXY_TARGET ?? 'http://localhost:3000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/api': apiTarget,
      '/tiles': { target: tilesTarget, rewrite: (path) => path.replace(/^\/tiles/, '') },
    },
  },
})
