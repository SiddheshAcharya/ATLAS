import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Ports are overridable so ATLAS can run beside another project on the defaults:
//   ATLAS_WEB_PORT=5180 ATLAS_API_URL=http://127.0.0.1:8010 npm run dev
const apiTarget = process.env.ATLAS_API_URL ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Routes are lazy-loaded (App.tsx); the one chunk over Vite's 500 kB default is the graph
  // view, which is Cytoscape + fcose themselves (~570 kB) and loads only on /runs/:id.
  build: { chunkSizeWarningLimit: 650 },
  server: {
    port: Number(process.env.ATLAS_WEB_PORT ?? 5173),
    strictPort: process.env.ATLAS_WEB_PORT !== undefined,
    proxy: {
      // dev-only convenience: same-origin relative fetches, no CORS round trip.
      '/api': { target: apiTarget, changeOrigin: true },
      '/health': { target: apiTarget, changeOrigin: true },
    },
  },
})
