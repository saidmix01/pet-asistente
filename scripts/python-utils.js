const fs = require('fs')
const path = require('path')
const { spawnSync } = require('child_process')

const ROOT_DIR = path.resolve(__dirname, '..')
const BACKEND_DIR = path.join(ROOT_DIR, 'backend')
const VENV_DIR = path.join(BACKEND_DIR, '.venv')

function getVenvPython() {
  const candidates = process.platform === 'win32'
    ? [
        path.join(VENV_DIR, 'Scripts', 'python.exe'),
        path.join(BACKEND_DIR, 'venv', 'Scripts', 'python.exe'),
      ]
    : [
        path.join(VENV_DIR, 'bin', 'python'),
        path.join(VENV_DIR, 'bin', 'python3'),
        path.join(BACKEND_DIR, 'venv', 'bin', 'python'),
        path.join(BACKEND_DIR, 'venv', 'bin', 'python3'),
      ]

  for (const p of candidates) {
    if (fs.existsSync(p)) return p
  }
  return null
}

function probePython(cmd, args = []) {
  try {
    const res = spawnSync(cmd, [...args, '-c', 'import sys; print(sys.executable)'], {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    if (res.status === 0 && res.stdout && res.stdout.trim()) {
      return res.stdout.trim()
    }
  } catch {}
  return null
}

function findSystemPython() {
  if (process.env.PET_PYTHON) {
    const found = probePython(process.env.PET_PYTHON)
    if (found) return found
  }

  if (process.platform === 'win32') {
    const localAppData = process.env.LOCALAPPDATA || ''
    const explicitPaths = [
      path.join(localAppData, 'Programs', 'Python', 'Python314', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python313', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python312', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python311', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python310', 'python.exe'),
    ]
    const probes = [
      ['py', ['-3']],
      ['python', []],
      ['python3', []],
      ...explicitPaths.filter((p) => fs.existsSync(p)).map((p) => [p, []]),
    ]
    for (const [cmd, args] of probes) {
      const found = probePython(cmd, args)
      if (found) return found
    }
  } else {
    for (const cmd of ['python3', 'python']) {
      const found = probePython(cmd)
      if (found) return found
    }
  }

  return null
}

function ensureVenv() {
  const existing = getVenvPython()
  if (existing) {
    // Make sure pip is present inside an existing venv
    const pipCheck = spawnSync(existing, ['-m', 'pip', '--version'], { stdio: 'ignore' })
    if (pipCheck.status === 0) return existing
  }

  const sysPython = findSystemPython()
  if (!sysPython) {
    console.error('[ERROR] Python 3 no encontrado. Instalá Python 3.10+ primero.')
    process.exit(1)
  }

  if (!existing) {
    console.log(`[Setup] Creando entorno virtual en ${VENV_DIR} usando ${sysPython}...`)
    let res = spawnSync(sysPython, ['-m', 'venv', VENV_DIR], { stdio: 'inherit' })
    if (res.status !== 0) {
      // Fallback for Debian/Ubuntu without python3-venv (ensurepip missing)
      console.log('[Setup] ensurepip no disponible, reintentando con --without-pip...')
      try { fs.rmSync(VENV_DIR, { recursive: true, force: true }) } catch {}
      res = spawnSync(sysPython, ['-m', 'venv', '--without-pip', VENV_DIR], { stdio: 'inherit' })
      if (res.status !== 0) {
        console.error('[ERROR] No se pudo crear backend/.venv (en Debian/Ubuntu instalá: sudo apt install python3-venv)')
        process.exit(res.status || 1)
      }
    }
  }

  const venvPy = getVenvPython()
  if (!venvPy) {
    console.error('[ERROR] No se encontró el ejecutable de Python dentro de backend/.venv')
    process.exit(1)
  }

  // Bootstrap pip inside venv if created with --without-pip
  const pipCheck = spawnSync(venvPy, ['-m', 'pip', '--version'], { stdio: 'ignore' })
  if (pipCheck.status !== 0) {
    console.log('[Setup] Instalando pip dentro de backend/.venv...')
    const boot = spawnSync(sysPython, ['-m', 'pip', '--python', venvPy, 'install', 'pip'], {
      stdio: 'inherit',
    })
    if (boot.status !== 0) {
      console.error('[ERROR] No se pudo instalar pip dentro de backend/.venv. Instalá python3-venv o python3-pip.')
      process.exit(boot.status || 1)
    }
  }

  return venvPy
}

function getBestPython() {
  return getVenvPython() || findSystemPython()
}

module.exports = {
  ROOT_DIR,
  BACKEND_DIR,
  VENV_DIR,
  getVenvPython,
  findSystemPython,
  ensureVenv,
  getBestPython,
}
