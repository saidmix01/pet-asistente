const fs = require('fs')
const path = require('path')

const electronDir = path.join(__dirname, '..', 'node_modules', 'electron')
const pathFile = path.join(electronDir, 'path.txt')

if (!fs.existsSync(electronDir)) process.exit(0)
if (fs.existsSync(pathFile)) process.exit(0)

let platformPath = 'electron'

if (process.platform === 'darwin') {
  platformPath = 'Electron.app/Contents/MacOS/Electron'
} else if (process.platform === 'win32') {
  platformPath = 'electron.exe'
}

try {
  fs.writeFileSync(pathFile, platformPath)
} catch {
  process.exit(0)
}
