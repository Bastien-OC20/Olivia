import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { appliquerTheme, themeEffectif } from './theme.js'
import './style.css'

// Thème posé avant le premier affichage : l'écran de connexion suit Windows tout
// de suite, sans attendre les réglages (chargés seulement après la connexion).
const prefereSombre = typeof window.matchMedia === 'function'
  ? window.matchMedia('(prefers-color-scheme: dark)').matches
  : true
appliquerTheme(document.documentElement, themeEffectif('systeme', prefereSombre))

createApp(App).use(createPinia()).mount('#app')
