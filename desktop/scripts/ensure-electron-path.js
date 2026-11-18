const fs = require('fs')
const path = require('path')
const { spawnSync } = require('child_process')

const electronDir = path.join(__dirname, '..', 'node_modules', 'electron')
const pathFile = path.join(electronDir, 'path.txt')

if (!fs.existsSync(electronDir)) process.exit(0)

let platformPath = 'electron'
if (process.platform === 'darwin') {
  platformPath = 'Electron.app/Contents/MacOS/Electron'
} else if (process.platform === 'win32') {
  platformPath = 'electron.exe'
}

const binPath = path.join(electronDir, 'dist', platformPath)

if (!fs.existsSync(binPath)) {
  const installScript = path.join(electronDir, 'install.js')
  if (fs.existsSync(installScript)) {
    console.log('[Electron] Descargando binario de Electron para', process.platform, '...')
    const res = spawnSync(process.execPath, [installScript], {
      cwd: electronDir,
      stdio: 'inherit',
    })
    if (res.status !== 0) {
      console.error('[Electron] No se pudo descargar el binario de Electron.')
      process.exit(res.status || 1)
    }
  }
}

if (!fs.existsSync(pathFile)) {
  try {
    fs.writeFileSync(pathFile, platformPath)
  } catch {
    process.exit(0)
  }
}
