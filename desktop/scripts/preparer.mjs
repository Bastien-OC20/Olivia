/**
 * Rassemble, avant l'empaquetage, tout ce qui part dans l'application de
 * bureau sous resources/backend/ :
 *
 *   - dist/ai-webapp/   backend + interface compilés par PyInstaller (OBLIGATOIRE ;
 *                       build.spec, lancé depuis la racine du dépôt) ;
 *   - ollama/           moteur d'IA portable + modèles   (facultatif) ;
 *   - tesseract/        moteur OCR portable              (facultatif) ;
 *   - modeles/          modèle Word commun               (facultatif).
 *
 * launch.py cherche Ollama et Tesseract À CÔTÉ de l'exécutable : ils sont donc
 * copiés dans le même dossier. Un moteur n'est retenu que s'il est compilé pour
 * le système de CETTE machine (ollama.exe sous Windows, ollama sous macOS) :
 * electron-builder ne fait pas de compilation croisée, chaque installeur se
 * construit sur son système (voir .github/workflows/bureau.yml). Sans Ollama
 * embarqué, l'application utilise celui installé sur le poste (port 11434).
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ici = path.dirname(fileURLToPath(import.meta.url))
const depot = path.resolve(ici, '..', '..')
const cible = path.resolve(ici, '..', 'build', 'ressources', 'backend')
const surWindows = process.platform === 'win32'
const exe = (nom) => (surWindows ? `${nom}.exe` : nom)

const backend = path.join(depot, 'dist', 'ai-webapp')
if (!fs.existsSync(path.join(backend, exe('ai-webapp')))) {
  console.error(`Backend compilé introuvable : ${path.join(backend, exe('ai-webapp'))}
Compilez-le d'abord, depuis la racine du dépôt :
  cd frontend && npm ci && npm run build && cd ..
  pyinstaller build.spec --clean --noconfirm`)
  process.exit(1)
}

fs.rmSync(cible, { recursive: true, force: true })
fs.mkdirSync(cible, { recursive: true })
fs.cpSync(backend, cible, { recursive: true, verbatimSymlinks: true })
console.log(`✓ backend       ${backend}`)

const facultatifs = [
  { dossier: 'ollama', temoin: exe('ollama'), role: "moteur d'IA" },
  { dossier: 'tesseract', temoin: exe('tesseract'), role: 'moteur OCR' },
  { dossier: 'modeles', temoin: null, role: 'modèle Word commun' },
]
for (const { dossier, temoin, role } of facultatifs) {
  const source = path.join(depot, dossier)
  if (!fs.existsSync(source)) {
    console.log(`– ${dossier.padEnd(12)}  absent (${role} non embarqué)`)
    continue
  }
  if (temoin && !fs.existsSync(path.join(source, temoin))) {
    console.log(`– ${dossier.padEnd(12)}  ignoré : pas de ${temoin} pour ce système (${role} non embarqué)`)
    continue
  }
  fs.cpSync(source, path.join(cible, dossier), { recursive: true, verbatimSymlinks: true })
  console.log(`✓ ${dossier.padEnd(12)}  ${source}`)
}
console.log(`Ressources prêtes : ${cible}`)
