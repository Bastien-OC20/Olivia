import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// base relative './' : permet de servir l'UI buildée sous /ui/ derrière FastAPI
// (les chemins des assets restent relatifs à index.html).
export default defineConfig({
  base: './',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
