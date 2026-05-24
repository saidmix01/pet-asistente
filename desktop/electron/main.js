const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')
const http = require('http')

let mainWindow = null
let chatWindow = null
let configWindow = null
let backendProcess = null

// ── Paths ──────────────────────────────────────────────────
const isDev = !!process.env.VITE_DEV_SERVER_URL || !app.isPackaged

function getPythonCommand() {
  return process.platform === 'win32' ? 'python' : 'python3'
}

function getBackendPath() {
  if (isDev) {
    // Dev: use Python directly
    return null
  }
  // Prod: use compiled binary
  const resourcePath = process.resourcesPath
  const binName = process.platform === 'win32' ? 'asistente-core.exe' : 'asistente-core'
  return path.join(resourcePath, 'backend', binName)
}

function getConfigPath() {
  return path.join(app.getPath('userData'), 'pet-config.json')
}

// ── Config ──────────────────────────────────────────────────
function loadConfig() {
  try {
    const p = getConfigPath()
    if (fs.existsSync(p)) {
      return JSON.parse(fs.readFileSync(p, 'utf-8'))
    }
  } catch {}
  return null
}

function saveConfig(config) {
  const p = getConfigPath()
  fs.writeFileSync(p, JSON.stringify(config, null, 2), 'utf-8')
}

function getDefaultConfig() {
  return {
    assistantName: 'Pet',
    aiMode: 'local',
    deepseekToken: '',
    firstLaunch: true,
  }
}

// ── Backend lifecycle ──────────────────────────────────────
function startBackend() {
  return new Promise((resolve, reject) => {
    const backendPath = getBackendPath()
    let cmd, args

    if (backendPath && fs.existsSync(backendPath)) {
      // Production: compiled binary
      cmd = backendPath
      args = []
      console.log(`[Pet] Starting backend binary: ${cmd}`)
    } else {
      // Dev: python3 main.py
      const mainPy = path.join(__dirname, '..', '..', 'backend', 'main.py')
      if (!fs.existsSync(mainPy)) {
        console.error('[Pet] Backend not found:', mainPy)
        reject(new Error('Backend main.py not found'))
        return
      }
      const pyCmd = getPythonCommand()
      cmd = pyCmd
      args = [mainPy]
      console.log(`[Pet] Starting backend via ${pyCmd}: ${mainPy}`)
    }

    backendProcess = spawn(cmd, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    })

    backendProcess.stdout.on('data', (data) => {
      console.log(`[Backend] ${data.toString().trim()}`)
    })

    backendProcess.stderr.on('data', (data) => {
      console.log(`[Backend] ${data.toString().trim()}`)
    })

    backendProcess.on('error', (err) => {
      console.error('[Pet] Backend process error:', err.message)
      reject(err)
    })

    backendProcess.on('exit', (code) => {
      console.log(`[Pet] Backend exited with code ${code}`)
      backendProcess = null
    })

    // Wait for backend to be ready (poll port 8000)
    const maxRetries = 30
    let retries = 0
    const poll = () => {
      retries++
      const req = http.get('http://127.0.0.1:8000/', (res) => {
        if (res.statusCode === 200) {
          console.log('[Pet] Backend ready!')
          resolve()
        } else if (retries < maxRetries) {
          setTimeout(poll, 1000)
        } else {
          reject(new Error('Backend did not respond with 200'))
        }
      })
      req.on('error', () => {
        if (retries < maxRetries) {
          setTimeout(poll, 1000)
        } else {
          reject(new Error('Backend did not start within 30s'))
        }
      })
      req.end()
    }
    setTimeout(poll, 2000) // first check after 2s
  })
}

function stopBackend() {
  if (backendProcess) {
    console.log('[Pet] Stopping backend...')
    if (process.platform === 'win32') {
      // Windows: use taskkill to properly terminate the process tree
      try {
        require('child_process').execSync(`taskkill /pid ${backendProcess.pid} /f /t`, { stdio: 'ignore' })
      } catch {}
      if (backendProcess) {
        backendProcess.kill()
        setTimeout(() => {
          if (backendProcess) {
            backendProcess.kill()
            backendProcess = null
          }
        }, 5000)
      }
    } else {
      backendProcess.kill('SIGTERM')
      // Force kill after 5s
      setTimeout(() => {
        if (backendProcess) {
          backendProcess.kill('SIGKILL')
          backendProcess = null
        }
      }, 5000)
    }
  }
}

// ── Window creation ─────────────────────────────────────────
function getRendererUrl() {
  if (process.env.VITE_DEV_SERVER_URL) return process.env.VITE_DEV_SERVER_URL
  return null
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 300,
    height: 360,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    backgroundColor: '#00000000',
    webSecurity: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  mainWindow.setMenuBarVisibility(false)
  mainWindow.setIgnoreMouseEvents(true, { forward: true })

  const rendererUrl = getRendererUrl()

  if (rendererUrl) {
    mainWindow.loadURL(rendererUrl)
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'dist', 'index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ── IPC handlers ────────────────────────────────────────────
ipcMain.handle('pet:ping', async () => 'pong')

ipcMain.handle('pet:get-config', async () => {
  return loadConfig() || getDefaultConfig()
})

ipcMain.handle('pet:save-config', async (event, config) => {
  saveConfig(config)
  return true
})

ipcMain.handle('pet:is-first-launch', async () => {
  const cfg = loadConfig()
  return cfg ? cfg.firstLaunch !== false : true
})

ipcMain.handle('pet:mark-configured', async () => {
  const cfg = loadConfig() || getDefaultConfig()
  cfg.firstLaunch = false
  saveConfig(cfg)
  return true
})

ipcMain.handle('pet:get-position', async () => {
  if (!mainWindow) return { x: 0, y: 0 }
  const [x, y] = mainWindow.getPosition()
  return { x, y }
})

ipcMain.handle('pet:get-screen-size', async () => {
  const { screen } = require('electron')
  const bounds = screen.getPrimaryDisplay().workAreaSize
  return { width: bounds.width, height: bounds.height }
})

ipcMain.handle('pet:set-interactive', async (event, payload) => {
  if (!mainWindow) return false
  mainWindow.setIgnoreMouseEvents(!(payload && payload.interactive))
  return true
})

ipcMain.handle('pet:move-by', async (event, payload) => {
  if (!mainWindow) return null
  const dx = Number(payload && payload.dx)
  const dy = Number(payload && payload.dy)
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return null
  const [x, y] = mainWindow.getPosition()
  mainWindow.setPosition(Math.round(x + dx), Math.round(y + dy), false)
  return true
})

// ── Config window (separada, no overlay) ─────────────────
function openConfigWindow() {
  if (configWindow && !configWindow.isDestroyed()) {
    configWindow.focus()
    return
  }
  configWindow = new BrowserWindow({
    width: 440,
    height: 520,
    resizable: false,
    alwaysOnTop: true,
    title: 'Pet Asistente - Configuración',
    backgroundColor: '#1a1a2e',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  configWindow.setMenuBarVisibility(false)
  configWindow.loadFile(path.join(__dirname, '..', 'config-renderer', 'index.html'))
  configWindow.on('closed', () => { configWindow = null })
}

ipcMain.handle('pet:open-config', async () => {
  openConfigWindow()
})

// ── Chat window ────────────────────────────────────────────
ipcMain.handle('pet:open-chat', async () => {
  if (chatWindow && !chatWindow.isDestroyed()) {
    chatWindow.focus()
    return
  }
  chatWindow = new BrowserWindow({
    width: 420,
    height: 560,
    resizable: false,
    alwaysOnTop: true,
    title: 'Pet Asistente - Chat',
    backgroundColor: '#1a1a2e',
    webSecurity: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
  chatWindow.setMenuBarVisibility(false)
  chatWindow.loadFile(path.join(__dirname, '..', 'chat-renderer', 'index.html'))
  chatWindow.on('closed', () => { chatWindow = null })
})

// ── App lifecycle ───────────────────────────────────────────
app.whenReady().then(async () => {
  try {
    console.log('[Pet] Starting backend...')
    await startBackend()
    console.log('[Pet] Backend is ready, creating window...')

    // Check first launch — open config window separately
    const cfg = loadConfig()
    if (!cfg || cfg.firstLaunch !== false) {
      console.log('[Pet] First launch — opening config window...')
      openConfigWindow()
    }
  } catch (err) {
    console.error('[Pet] Failed to start backend:', err.message)
  }

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stopBackend()
})
