const path = require('path')
const { spawnSync } = require('child_process')
const { ROOT_DIR, BACKEND_DIR, ensureVenv } = require('./python-utils')

function run(cmd, args, cwd) {
  const isWinNpm = process.platform === 'win32' && cmd === 'npm'
  const actualCmd = isWinNpm ? 'npm.cmd' : cmd
  const res = spawnSync(actualCmd, args, {
    cwd,
    stdio: 'inherit',
    shell: isWinNpm,
  })
  if (res.status !== 0) {
    process.exit(res.status || 1)
  }
}

console.log('============================================')
console.log(' Pet Asistente - Instalacion (Windows/Linux)')
console.log('============================================\n')

console.log('[1/4] Configurando Python venv e instalando dependencias del backend...')
const py = ensureVenv()
run(py, ['-m', 'pip', 'install', '--upgrade', 'pip'], BACKEND_DIR)
run(py, ['-m', 'pip', 'install', '-r', 'requirements.txt'], BACKEND_DIR)
console.log('[OK] Backend listo.\n')

console.log('[2/4] Instalando dependencias raiz...')
run('npm', ['install'], ROOT_DIR)
console.log('[OK] Raiz lista.\n')

console.log('[3/4] Instalando dependencias de desktop (Electron)...')
run('npm', ['install'], path.join(ROOT_DIR, 'desktop'))
console.log('[OK] Desktop listo.\n')

console.log('[4/4] Instalando dependencias de renderer (React/Vite)...')
run('npm', ['install'], path.join(ROOT_DIR, 'desktop', 'renderer'))
console.log('[OK] Renderer listo.\n')

console.log('============================================')
console.log(' Instalacion completa!')
console.log(' Para iniciar en desarrollo: npm run dev')
console.log('============================================')
