const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage } = require('electron')
const path = require('path')
const fs = require('fs')
const { spawn } = require('child_process')
const http = require('http')

let mainWindow = null
let chatWindow = null
let configWindow = null
let backendProcess = null
let tray = null

// ── Paths ──────────────────────────────────────────────────
const isDev = !!process.env.VITE_DEV_SERVER_URL || !app.isPackaged

function getPythonCommand() {
  if (process.platform === 'win32') {
    // Try common Python install paths on Windows
    const fs = require('fs')
    const candidates = [
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python314', 'python.exe'),
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python313', 'python.exe'),
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python312', 'python.exe'),
      'python',
    ]
    for (const p of candidates) {
      if (p === 'python') return p
      if (fs.existsSync(p)) return p
    }
    return 'python'
  }
  return 'python3'
}

function getBackendPath() {
  if (isDev) {
    // Dev: use Python directly
    return null
  }
  // Prod: use compiled binary
  const resourcePath = process.resourcesPath
  const binName = process.platform === 'win32' ? 'asistente-core.exe' : 'asistente-core'
  const fullPath = path.join(resourcePath, 'backend', binName)
  console.log(`[Pet] Backend path: ${fullPath} (exists: ${fs.existsSync(fullPath)})`)
  return fullPath
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
      windowsHide: true,
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
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
      autoplayPolicy: 'no-user-gesture-required',
    },
  })

  mainWindow.setMenuBarVisibility(false)
  // Use forward:true so clicks pass through the transparent area to windows below,
  // but the renderer can still receive forwarded mousemove to detect hover over the pet.
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
  const interactive = !!(payload && payload.interactive)
  if (interactive) {
    mainWindow.setIgnoreMouseEvents(false)
  } else {
    mainWindow.setIgnoreMouseEvents(true, { forward: true })
  }
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

// ── Backend proxy (IPC bridge for file:// CORS bypass) ───────
ipcMain.handle('pet:backend-fetch', async (event, urlPath) => {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:8000${urlPath}`, (res) => {
      let data = ''
      res.on('data', (chunk) => { data += chunk })
      res.on('end', () => {
        try { resolve(JSON.parse(data)) }
        catch { resolve(null) }
      })
    })
    req.on('error', () => resolve(null))
    req.setTimeout(5000, () => { req.destroy(); resolve(null) })
  })
})

ipcMain.handle('pet:backend-post', async (event, payload) => {
  const { path: urlPath, body } = payload || {}
  return new Promise((resolve) => {
    const postData = JSON.stringify(body || {})
    const req = http.request({
      hostname: '127.0.0.1',
      port: 8000,
      path: urlPath,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) },
    }, (res) => {
      let data = ''
      res.on('data', (chunk) => { data += chunk })
      res.on('end', () => {
        try { resolve(JSON.parse(data)) }
        catch { resolve(null) }
      })
    })
    req.on('error', () => resolve(null))
    req.setTimeout(10000, () => { req.destroy(); resolve(null) })
    req.write(postData)
    req.end()
  })
})

// ── WebSocket bridge (main process → renderer via IPC) ────────
let backendWs = null

function startWsBridge() {
  const WebSocket = require('ws')
  
  function connect() {
    try {
      backendWs = new WebSocket('ws://127.0.0.1:8000/ws/state')
    } catch { setTimeout(connect, 5000); return }

    backendWs.on('open', () => {
      console.log('[Pet] WS bridge connected')
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('pet:backend-event', { type: 'connected' })
      }
    })

    backendWs.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString())
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('pet:backend-event', msg)
        }
      } catch {}
    })

    backendWs.on('close', () => {
      backendWs = null
      setTimeout(connect, 5000)
    })

    backendWs.on('error', () => {
      if (backendWs) { try { backendWs.close() } catch {} }
    })
  }

  connect()
}

// ── Config window (separada, no overlay) ─────────────────
function openConfigWindow() {
  if (configWindow && !configWindow.isDestroyed()) {
    configWindow.focus()
    return
  }
  configWindow = new BrowserWindow({
    width: 460,
    height: 620,
    resizable: false,
    alwaysOnTop: true,
    title: 'Pet Asistente - Configuración',
    backgroundColor: '#1a1a2e',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
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
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
    },
  })
  chatWindow.setMenuBarVisibility(false)
  chatWindow.loadFile(path.join(__dirname, '..', 'chat-renderer', 'index.html'))
  chatWindow.on('closed', () => { chatWindow = null })
})

// ── System Tray ─────────────────────────────────────────────
function createTray() {
  // Create a small 16x16 icon programmatically (paw emoji fallback)
  const iconPath = path.join(__dirname, '..', 'assets', 'pugasset-grid.png')
  let trayIcon
  if (fs.existsSync(iconPath)) {
    trayIcon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 })
  } else {
    // Fallback: create a tiny colored square
    trayIcon = nativeImage.createEmpty()
  }

  tray = new Tray(trayIcon)
  tray.setToolTip('Pet Asistente')

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '💬 Chat',
      click: () => {
        if (ipcMain.listenerCount) {
          // Trigger open chat
          if (chatWindow && !chatWindow.isDestroyed()) {
            chatWindow.focus()
          } else {
            const { BrowserWindow } = require('electron')
            chatWindow = new BrowserWindow({
              width: 420,
              height: 560,
              resizable: false,
              alwaysOnTop: true,
              title: 'Pet Asistente - Chat',
              backgroundColor: '#1a1a2e',
              webPreferences: {
                preload: path.join(__dirname, 'preload.js'),
                contextIsolation: true,
                nodeIntegration: false,
                webSecurity: false,
              },
            })
            chatWindow.setMenuBarVisibility(false)
            chatWindow.loadFile(path.join(__dirname, '..', 'chat-renderer', 'index.html'))
            chatWindow.on('closed', () => { chatWindow = null })
          }
        }
      },
    },
    {
      label: '⚙️ Configuración',
      click: () => openConfigWindow(),
    },
    { type: 'separator' },
    {
      label: '👁️ Mostrar/Ocultar Pet',
      click: () => {
        if (mainWindow) {
          if (mainWindow.isVisible()) mainWindow.hide()
          else mainWindow.show()
        }
      },
    },
    { type: 'separator' },
    {
      label: '❌ Cerrar',
      click: () => {
        stopBackend()
        app.quit()
      },
    },
  ])

  tray.setContextMenu(contextMenu)

  tray.on('double-click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) mainWindow.focus()
      else mainWindow.show()
    }
  })
}

// ── App lifecycle ───────────────────────────────────────────
app.whenReady().then(async () => {
  try {
    console.log('[Pet] Starting backend...')
    await startBackend()
    console.log('[Pet] Backend is ready, creating window...')

    // Start WebSocket bridge (main process connects to backend, forwards to renderer)
    startWsBridge()

    // Auto-connect ClickUp if token is saved in config
    const cfg = loadConfig()
    if (cfg && cfg.clickupToken) {
      console.log('[Pet] Auto-connecting ClickUp...')
      try {
        const postData = JSON.stringify({ token: cfg.clickupToken })
        const req = http.request({
          hostname: '127.0.0.1',
          port: 8000,
          path: '/integrations/clickup/connect',
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) },
        }, (res) => {
          if (res.statusCode === 200) console.log('[Pet] ClickUp connected!')
          else console.log(`[Pet] ClickUp connect failed: ${res.statusCode}`)
        })
        req.on('error', () => {})
        req.write(postData)
        req.end()
      } catch {}
    }

    // Check first launch — open config window separately
    if (!cfg || cfg.firstLaunch !== false) {
      console.log('[Pet] First launch — opening config window...')
      openConfigWindow()
    }
  } catch (err) {
    console.error('[Pet] Failed to start backend:', err.message)
  }

  createWindow()
  createTray()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  // Keep running in tray on Windows/Linux
  if (process.platform === 'darwin') {
    // macOS: standard behavior
  }
  // Don't quit — app stays in system tray
})

app.on('before-quit', () => {
  stopBackend()
})
