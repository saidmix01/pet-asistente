const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const fs = require('fs')

let mainWindow = null
let chatWindow = null

// ── Config file ──────────────────────────────────────────────
function getConfigPath() {
  return path.join(app.getPath('userData'), 'pet-config.json')
}

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

// ── Default config ───────────────────────────────────────────
function getDefaultConfig() {
  return {
    assistantName: 'Pet',
    aiMode: 'local',
    deepseekToken: '',
    firstLaunch: true,
  }
}

function getRendererUrl() {
  if (process.env.VITE_DEV_SERVER_URL) return process.env.VITE_DEV_SERVER_URL
  return null
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 150,
    height: 180,
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

// ── Config IPC handlers ──────────────────────────────────────
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
  const interactive = Boolean(payload && payload.interactive)
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
  const nextX = Math.round(x + dx)
  const nextY = Math.round(y + dy)
  mainWindow.setPosition(nextX, nextY, false)
  return [nextX, nextY]
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

app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
