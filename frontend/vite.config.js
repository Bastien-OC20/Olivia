import { cpSync, createReadStream, existsSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Polices du tableau blanc (Excalidraw). Sans copie locale, Excalidraw les
// chercherait sur un CDN : Oliv'IA doit rester 100 % locale, et la politique de
// sécurité du backend (CSP) refuserait de toute façon ces requêtes. Elles sont
// servies sous excalidraw-assets/fonts/ (voir TableauBlanc.vue,
// window.EXCALIDRAW_ASSET_PATH).
const POLICES = fileURLToPath(
  new URL('./node_modules/@excalidraw/excalidraw/dist/prod/fonts', import.meta.url))
const PREFIXE = '/excalidraw-assets/fonts/'

function policesExcalidraw() {
  let sortie
  return {
    name: 'polices-excalidraw',
    configResolved(config) {
      sortie = path.resolve(config.root, config.build.outDir)
    },
    // Développement (npm run dev) : servies directement depuis node_modules.
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const chemin = decodeURIComponent((req.url || '').split('?')[0])
        if (!chemin.startsWith(PREFIXE)) return next()
        const fichier = path.join(POLICES, chemin.slice(PREFIXE.length))
        if (!fichier.startsWith(POLICES + path.sep) || !existsSync(fichier)
            || !statSync(fichier).isFile()) return next()
        res.setHeader('Content-Type', 'font/woff2')
        createReadStream(fichier).pipe(res)
      })
    },
    // Construction : copiées dans dist/, embarquées avec le reste de l'interface.
    closeBundle() {
      cpSync(POLICES, path.join(sortie, 'excalidraw-assets', 'fonts'), { recursive: true })
    },
  }
}

// Excalidraw ajoute à chaque police, après l'adresse locale, une adresse de
// secours sur le CDN esm.sh. La CSP du backend la bloque, mais Chromium signale
// une violation par police dès leur déclaration (230 au premier tableau). Le
// secours est remplacé, à la construction, par l'adresse locale : plus aucune
// tentative vers l'extérieur. Si une version d'Excalidraw change ce code, la
// construction échoue plutôt que de réintroduire le CDN en silence.
const SECOURS_CDN = /`https:\/\/esm\.sh\/\$\{[^`]*`[^`]*`[^}]*\}\/dist\/prod\/`/g
const SECOURS_LOCAL =
  '(window.EXCALIDRAW_ASSET_PATH||new URL("excalidraw-assets/",document.baseURI).href)'

function sansCdnExcalidraw() {
  let remplacements = 0
  return {
    name: 'sans-cdn-excalidraw',
    apply: 'build',
    transform(code, id) {
      if (!id.includes('@excalidraw/excalidraw/dist/prod/') || !code.includes('esm.sh')) return null
      const sortie = code.replace(SECOURS_CDN, () => { remplacements += 1; return SECOURS_LOCAL })
      return { code: sortie, map: null }
    },
    buildEnd() {
      if (remplacements !== 1) {
        this.error(`Adresse de secours du CDN d'Excalidraw : ${remplacements} remplacement(s) au lieu de 1. `
          + 'Le code d\'Excalidraw a changé : adapter SECOURS_CDN (vite.config.js).')
      }
    },
  }
}

// base relative './' : permet de servir l'UI buildée sous /ui/ derrière FastAPI
// (les chemins des assets restent relatifs à index.html).
export default defineConfig({
  base: './',
  plugins: [vue(), policesExcalidraw(), sansCdnExcalidraw()],
  build: {
    // Excalidraw (tableau blanc) est chargé à part, à l'ouverture d'un tableau :
    // ses gros morceaux n'alourdissent pas le démarrage d'Oliv'IA.
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      onwarn(avertissement, suite) {
        // Directives « use client » des composants React d'Excalidraw : propres
        // au rendu côté serveur, sans objet ici.
        if (avertissement.code === 'MODULE_LEVEL_DIRECTIVE') return
        suite(avertissement)
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
