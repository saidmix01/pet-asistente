const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')

let mainWindow = null

function getRendererUrl() {
  if (process.env.VITE_DEV_SERVER_URL) return process.env.VITE_DEV_SERVER_URL
  return null
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 120,
    height: 120,
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

ipcMain.handle('pet:ping', async () => {
  return 'pong'
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

app.whenReady().then(() => {
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
