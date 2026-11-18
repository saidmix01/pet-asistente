const path = require('path')
const { spawn } = require('child_process')
const { BACKEND_DIR, getBestPython } = require('./python-utils')

const py = getBestPython()
if (!py) {
  console.error('[ERROR] No se encontró Python 3. Ejecutá: npm run install:all')
  process.exit(1)
}

const mainPy = path.join(BACKEND_DIR, 'main.py')
console.log(`[Backend] Starting ${mainPy} with ${py}`)

const child = spawn(py, [mainPy], {
  cwd: BACKEND_DIR,
  stdio: 'inherit',
  env: { ...process.env, PYTHONUNBUFFERED: '1' },
})

child.on('exit', (code) => process.exit(code ?? 0))
process.on('SIGINT', () => child.kill('SIGINT'))
process.on('SIGTERM', () => child.kill('SIGTERM'))
