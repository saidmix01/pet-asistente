const fs = require('fs')
const path = require('path')
const { spawnSync } = require('child_process')
const { BACKEND_DIR, ensureVenv } = require('./python-utils')

const py = ensureVenv()

console.log(`[Build Backend] Usando Python: ${py}`)
console.log('[Build Backend] Verificando dependencias y PyInstaller...')

const pipDeps = spawnSync(py, ['-m', 'pip', 'install', '-r', 'requirements.txt', 'pyinstaller'], {
  cwd: BACKEND_DIR,
  stdio: 'inherit',
})
if (pipDeps.status !== 0) {
  process.exit(pipDeps.status || 1)
}

console.log('[Build Backend] Compilando asistente-core con PyInstaller...')
const build = spawnSync(py, ['-m', 'PyInstaller', 'asistente-core.spec', '--noconfirm', '--clean'], {
  cwd: BACKEND_DIR,
  stdio: 'inherit',
})
if (build.status !== 0) {
  process.exit(build.status || 1)
}

const binName = process.platform === 'win32' ? 'asistente-core.exe' : 'asistente-core'
const outPath = path.join(BACKEND_DIR, 'dist', binName)
if (!fs.existsSync(outPath)) {
  console.error(`[ERROR] No se generó el binario esperado: ${outPath}`)
  process.exit(1)
}

if (process.platform !== 'win32') {
  try { fs.chmodSync(outPath, 0o755) } catch {}
}

console.log(`[OK] Backend compilado: ${outPath}`)
