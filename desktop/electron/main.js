const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, screen, globalShortcut, clipboard, session } = require('electron')
const path = require('path')
const fs = require('fs')
const os = require('os')
const { spawn, execSync } = require('child_process')
const http = require('http')

// ── Linux graphics & transparency compatibility ─────────────
if (process.platform === 'linux') {
  // If we have an X11 display (native X11 or XWayland) and ozone-platform was not passed,
  // re-spawn with --ozone-platform=x11 and --enable-transparent-visuals.
  // This guarantees true ARGB transparency with zero window borders, boxes, shadows, or compositor blur.
  const hasOzone = process.argv.some((a) => a.startsWith('--ozone-platform'))
  if (!hasOzone && process.env.DISPLAY) {
    const child = spawn(
      process.execPath,
      ['--ozone-platform=x11', '--enable-transparent-visuals', ...process.argv.slice(1)],
      {
        detached: true,
        stdio: 'inherit',
        env: process.env,
      }
    )
    child.unref()
    process.exit(0)
  }

  app.commandLine.appendSwitch('enable-transparent-visuals')
  if (process.env.PET_DISABLE_GPU === '1') {
    app.disableHardwareAcceleration()
  }
}

let mainWindow = null
let chatWindow = null
let configWindow = null
let backendProcess = null
let tray = null
let linuxMouseInterval = null
let linuxIgnoringMouse = false
let isDraggingPet = false
let petHitbox = { x: 118, y: 292, width: 64, height: 64 }
let lastShapeRects = []

const isLinuxWayland =
  process.platform === 'linux' &&
  (process.env.PET_OZONE_PLATFORM === 'wayland' ||
    (!process.env.DISPLAY && !!process.env.WAYLAND_DISPLAY))

// ── Paths ──────────────────────────────────────────────────
const isDev = !!process.env.VITE_DEV_SERVER_URL || !app.isPackaged

function getAppIconPath() {
  const iconPng = path.join(__dirname, '..', 'assets', 'icon.png')
  if (fs.existsSync(iconPng)) return iconPng
  const gridPng = path.join(__dirname, '..', 'assets', 'pugasset-grid.png')
  if (fs.existsSync(gridPng)) return gridPng
  return null
}

function getPythonCommand() {
  // 1. Explicit override via environment variable
  if (process.env.PET_PYTHON && fs.existsSync(process.env.PET_PYTHON)) {
    return process.env.PET_PYTHON
  }

  // 2. Local virtualenv inside backend/ (.venv or venv) — preferred on Linux & Windows
  const backendDir = path.join(__dirname, '..', '..', 'backend')
  const venvCandidates = process.platform === 'win32'
    ? [
        path.join(backendDir, '.venv', 'Scripts', 'python.exe'),
        path.join(backendDir, 'venv', 'Scripts', 'python.exe'),
      ]
    : [
        path.join(backendDir, '.venv', 'bin', 'python'),
        path.join(backendDir, '.venv', 'bin', 'python3'),
        path.join(backendDir, 'venv', 'bin', 'python'),
        path.join(backendDir, 'venv', 'bin', 'python3'),
      ]

  for (const candidate of venvCandidates) {
    if (fs.existsSync(candidate)) return candidate
  }

  // 3. System Python fallback
  if (process.platform === 'win32') {
    const localAppData = process.env.LOCALAPPDATA || ''
    const candidates = [
      path.join(localAppData, 'Programs', 'Python', 'Python314', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python313', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python312', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python311', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python310', 'python.exe'),
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
    aiMode: 'antigravity',
    deepseekToken: '',
    clickupToken: '',
    soundMuted: false,
    simulateActivity: false,
    aiAutonomy: true,
    firstLaunch: true,
    autoStart: false,
  }
}

function getEffectiveConfig() {
  const loaded = loadConfig() || {}
  return {
    ...getDefaultConfig(),
    ...loaded,
    autoStart: isAutoStartEnabled(),
  }
}

function broadcastConfig(config) {
  const effective = { ...getDefaultConfig(), ...(config || {}) }
  for (const win of [mainWindow, chatWindow, configWindow]) {
    if (win && !win.isDestroyed()) {
      try { win.webContents.send('pet:config-updated', effective) } catch {}
    }
  }
  refreshTrayMenu()
}

// ── Autostart (Windows & Linux) ─────────────────────────────
function getLinuxAutostartPath() {
  const configDir = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config')
  return path.join(configDir, 'autostart', 'pet-asistente.desktop')
}

function isAutoStartEnabled() {
  if (process.platform === 'win32') {
    try {
      const settings = app.getLoginItemSettings()
      return Boolean(settings.openAtLogin)
    } catch {
      const cfg = loadConfig()
      return Boolean(cfg?.autoStart)
    }
  } else if (process.platform === 'linux') {
    try {
      const desktopFile = getLinuxAutostartPath()
      return fs.existsSync(desktopFile)
    } catch {
      const cfg = loadConfig()
      return Boolean(cfg?.autoStart)
    }
  } else if (process.platform === 'darwin') {
    try {
      return Boolean(app.getLoginItemSettings().openAtLogin)
    } catch {
      const cfg = loadConfig()
      return Boolean(cfg?.autoStart)
    }
  }
  const cfg = loadConfig()
  return Boolean(cfg?.autoStart)
}

function setAutoStart(enable) {
  const shouldEnable = Boolean(enable)
  console.log(`[Pet] Setting autostart: ${shouldEnable} (platform: ${process.platform})`)

  if (process.platform === 'win32') {
    try {
      app.setLoginItemSettings({
        openAtLogin: shouldEnable,
        path: process.execPath,
        args: ['--autostart'],
      })
    } catch (err) {
      console.error('[Pet] Error updating Windows login items:', err.message)
    }
  } else if (process.platform === 'linux') {
    try {
      const autostartFile = getLinuxAutostartPath()
      if (shouldEnable) {
        const autostartDir = path.dirname(autostartFile)
        if (!fs.existsSync(autostartDir)) {
          fs.mkdirSync(autostartDir, { recursive: true })
        }
        const execTarget = process.env.APPIMAGE || process.execPath
        const iconTarget = getAppIconPath() || 'pet-asistente'
        const desktopContent = [
          '[Desktop Entry]',
          'Type=Application',
          'Version=1.0',
          'Name=Pet Asistente',
          'Comment=Desktop pet assistant',
          `Exec="${execTarget}" --autostart`,
          `Icon=${iconTarget}`,
          'Terminal=false',
          'Categories=Utility;',
          'X-GNOME-Autostart-enabled=true',
          '',
        ].join('\n')
        fs.writeFileSync(autostartFile, desktopContent, 'utf-8')
        try { fs.chmodSync(autostartFile, 0o755) } catch {}
      } else {
        if (fs.existsSync(autostartFile)) {
          fs.unlinkSync(autostartFile)
        }
      }
    } catch (err) {
      console.error('[Pet] Error updating Linux autostart file:', err.message)
    }
  } else if (process.platform === 'darwin') {
    try {
      app.setLoginItemSettings({ openAtLogin: shouldEnable })
    } catch (err) {
      console.error('[Pet] Error updating macOS login items:', err.message)
    }
  }

  const cfg = loadConfig() || getDefaultConfig()
  cfg.autoStart = shouldEnable
  saveConfig(cfg)
  broadcastConfig(cfg)
  refreshTrayMenu()
  return isAutoStartEnabled()
}

// ── Backend lifecycle ──────────────────────────────────────
function isBackendAlive() {
  return new Promise((resolve) => {
    const req = http.get('http://127.0.0.1:8000/', (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(1000, () => { req.destroy(); resolve(false) })
    req.end()
  })
}

function startBackend() {
  return new Promise(async (resolve, reject) => {
    // If backend is already running (e.g. started in another terminal), reuse it
    if (await isBackendAlive()) {
      console.log('[Pet] Backend already running on port 8000')
      resolve()
      return
    }

    const backendPath = getBackendPath()
    let cmd, args, cwd

    if (backendPath && fs.existsSync(backendPath)) {
      // Production: compiled binary
      cmd = backendPath
      args = []
      cwd = path.dirname(backendPath)
      console.log(`[Pet] Starting backend binary: ${cmd}`)
    } else {
      // Dev: python main.py
      const backendDir = path.join(__dirname, '..', '..', 'backend')
      const mainPy = path.join(backendDir, 'main.py')
      if (!fs.existsSync(mainPy)) {
        console.error('[Pet] Backend not found:', mainPy)
        reject(new Error('Backend main.py not found'))
        return
      }
      const pyCmd = getPythonCommand()
      cmd = pyCmd
      args = [mainPy]
      cwd = backendDir
      console.log(`[Pet] Starting backend via ${pyCmd}: ${mainPy}`)
    }

    let settled = false
    const finishResolve = () => { if (!settled) { settled = true; resolve() } }
    const finishReject = (err) => { if (!settled) { settled = true; reject(err) } }

    backendProcess = spawn(cmd, args, {
      cwd,
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
      finishReject(err)
    })

    backendProcess.on('exit', (code) => {
      console.log(`[Pet] Backend exited with code ${code}`)
      backendProcess = null
      if (!settled) {
        finishReject(new Error(`Backend exited early with code ${code}`))
      }
    })

    // Wait for backend to be ready (poll port 8000)
    const maxRetries = 30
    let retries = 0
    const poll = () => {
      if (settled) return
      retries++
      const req = http.get('http://127.0.0.1:8000/', (res) => {
        res.resume()
        if (res.statusCode === 200) {
          console.log('[Pet] Backend ready!')
          finishResolve()
        } else if (retries < maxRetries) {
          setTimeout(poll, 1000)
        } else {
          finishReject(new Error('Backend did not respond with 200'))
        }
      })
      req.on('error', () => {
        if (settled) return
        if (retries < maxRetries) {
          setTimeout(poll, 1000)
        } else {
          finishReject(new Error('Backend did not start within 30s'))
        }
      })
      req.end()
    }
    setTimeout(poll, 1000) // first check after 1s
  })
}

function stopBackend() {
  if (!backendProcess) return
  const proc = backendProcess
  backendProcess = null
  console.log('[Pet] Stopping backend...')
  if (process.platform === 'win32') {
    // Windows: use taskkill to properly terminate the process tree
    try {
      execSync(`taskkill /pid ${proc.pid} /f /t`, { stdio: 'ignore' })
    } catch {
      try { proc.kill() } catch {}
    }
  } else {
    try { proc.kill('SIGTERM') } catch {}
    // Force kill after 3s if still alive
    setTimeout(() => {
      try {
        process.kill(proc.pid, 0)
        proc.kill('SIGKILL')
      } catch {}
    }, 3000)
  }
}

// ── Window creation ─────────────────────────────────────────
function getRendererUrl() {
  if (process.env.VITE_DEV_SERVER_URL) return process.env.VITE_DEV_SERVER_URL
  return null
}

function startLinuxMouseTracker() {
  stopLinuxMouseTracker()
  if (process.platform !== 'linux') return

  linuxMouseInterval = setInterval(() => {
    if (!mainWindow || mainWindow.isDestroyed()) return
    if (isDraggingPet) {
      if (linuxIgnoringMouse) {
        linuxIgnoringMouse = false
        mainWindow.setIgnoreMouseEvents(false)
      }
      return
    }
    try {
      const cursor = screen.getCursorScreenPoint()
      const winBounds = mainWindow.getBounds()
      const pad = 8
      const left = winBounds.x + petHitbox.x - pad
      const top = winBounds.y + petHitbox.y - pad
      const right = winBounds.x + petHitbox.x + petHitbox.width + pad
      const bottom = winBounds.y + petHitbox.y + petHitbox.height + pad
      const overPet =
        cursor.x >= left && cursor.x <= right &&
        cursor.y >= top && cursor.y <= bottom

      const shouldIgnore = !overPet
      if (shouldIgnore !== linuxIgnoringMouse) {
        linuxIgnoringMouse = shouldIgnore
        mainWindow.setIgnoreMouseEvents(shouldIgnore)
      }
    } catch {}
  }, 50)
}

function stopLinuxMouseTracker() {
  if (linuxMouseInterval) {
    clearInterval(linuxMouseInterval)
    linuxMouseInterval = null
  }
}

const PET_WIN_WIDTH = 320
const PET_WIN_HEIGHT = 260
const WAYLAND_WIN_WIDTH = 280
const WAYLAND_WIN_HEIGHT = 200
let waylandClickThrough = false

function enableLinuxX11Overlay(win) {
  if (process.platform !== 'linux' || isLinuxWayland) return
  if (!win || win.isDestroyed()) return
  try {
    const buf = win.getNativeWindowHandle()
    if (!buf || buf.length < 4) return
    const wid = buf.readUInt32LE(0)
    if (!wid) return

    const inlinePy = `
import ctypes, sys
try:
    wid = int(sys.argv[1], 0)
    class XSetWindowAttributes(ctypes.Structure):
        _fields_ = [
            ('background_pixmap', ctypes.c_ulong), ('background_pixel', ctypes.c_ulong),
            ('border_pixmap', ctypes.c_ulong), ('border_pixel', ctypes.c_ulong),
            ('bit_gravity', ctypes.c_int), ('win_gravity', ctypes.c_int),
            ('backing_store', ctypes.c_int), ('backing_planes', ctypes.c_ulong),
            ('backing_pixel', ctypes.c_ulong), ('save_under', ctypes.c_int),
            ('event_mask', ctypes.c_long), ('do_not_propagate_mask', ctypes.c_long),
            ('override_redirect', ctypes.c_int), ('colormap', ctypes.c_ulong),
            ('cursor', ctypes.c_ulong)
        ]
    xlib = ctypes.cdll.LoadLibrary('libX11.so.6')
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    dpy = xlib.XOpenDisplay(None)
    if dpy:
        attrs = XSetWindowAttributes()
        attrs.override_redirect = 1
        xlib.XUnmapWindow(dpy, wid)
        xlib.XSync(dpy, 0)
        xlib.XChangeWindowAttributes(dpy, wid, 1 << 9, ctypes.byref(attrs))
        xlib.XMapRaised(dpy, wid)
        xlib.XSync(dpy, 0)
        xlib.XCloseDisplay(dpy)
        sys.exit(0)
except Exception:
    sys.exit(1)
`
    const { spawnSync } = require('child_process')
    const pyCmd = getPythonCommand()
    let res = spawnSync(pyCmd, ['-c', inlinePy, String(wid)], { stdio: 'ignore', timeout: 2000 })
    if (res.status !== 0) {
      res = spawnSync('python3', ['-c', inlinePy, String(wid)], { stdio: 'ignore', timeout: 2000 })
    }
    if (res.status === 0) {
      console.log(`[Pet] Linux X11 override_redirect overlay enabled (wid=0x${wid.toString(16)})`)
    }
  } catch (err) {
    console.log('[Pet] X11 overlay helper skipped:', err.message)
  }
}

function applyWindowShape(rects) {
  if (!mainWindow || mainWindow.isDestroyed()) return
  if (typeof mainWindow.setShape !== 'function') return
  if (isLinuxWayland) return
  if (isDraggingPet) {
    try { mainWindow.setShape([]) } catch {}
    return
  }
  const clean = (Array.isArray(rects) ? rects : [])
    .filter((r) => r && Number.isFinite(r.x) && Number.isFinite(r.y) && r.width > 0 && r.height > 0)
    .map((r) => ({
      x: Math.max(0, Math.floor(r.x)),
      y: Math.max(0, Math.floor(r.y)),
      width: Math.ceil(r.width),
      height: Math.ceil(r.height),
    }))
  if (clean.length > 0) {
    lastShapeRects = clean
    try { mainWindow.setShape(clean) } catch {}
  }
}

function createWindow() {
  const iconPath = getAppIconPath()
  const workArea = screen.getPrimaryDisplay().workArea
  const savedCfg = getEffectiveConfig()

  const winW = isLinuxWayland ? WAYLAND_WIN_WIDTH : PET_WIN_WIDTH
  const winH = isLinuxWayland ? WAYLAND_WIN_HEIGHT : PET_WIN_HEIGHT
  const defaultX = Math.max(workArea.x, workArea.x + workArea.width - winW - 40)
  const defaultY = Math.max(workArea.y, workArea.y + workArea.height - winH - 20)
  const minX = workArea.x
  const maxX = Math.max(minX, workArea.x + workArea.width - winW)
  const minY = workArea.y
  const maxY = Math.max(minY, workArea.y + workArea.height - winH)
  const winX = Number.isFinite(savedCfg.lastX) ? Math.min(maxX, Math.max(minX, savedCfg.lastX)) : defaultX
  const winY = Number.isFinite(savedCfg.lastY) ? Math.min(maxY, Math.max(minY, savedCfg.lastY)) : defaultY

  mainWindow = new BrowserWindow({
    width: winW,
    height: winH,
    x: winX,
    y: winY,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    roundedCorners: false,
    thickFrame: false,
    focusable: true,
    ...(process.platform === 'linux' && !isLinuxWayland ? { type: 'dock' } : {}),
    backgroundColor: '#00000000',
    ...(iconPath ? { icon: iconPath } : {}),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
      autoplayPolicy: 'no-user-gesture-required',
    },
  })

  mainWindow.setMenuBarVisibility(false)
  mainWindow.setAlwaysOnTop(true, 'screen-saver')
  try {
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  } catch {}

  if (process.platform === 'linux') {
    if (isLinuxWayland) {
      mainWindow.setIgnoreMouseEvents(waylandClickThrough)
    } else {
      // X11 / XWayland: use override_redirect (no compositor shadow/frame,
      // permanently always-on-top) + setShape() for exact click-through!
      mainWindow.setIgnoreMouseEvents(false)
      mainWindow.once('ready-to-show', () => {
        enableLinuxX11Overlay(mainWindow)
        // Re-apply intended position after override_redirect remapping
        // (Cutefish WM centers managed windows before override_redirect takes over)
        mainWindow.setBounds({ x: winX, y: winY, width: winW, height: winH }, false)
        // Re-apply initial shape after override_redirect remapping
        applyWindowShape([{
          x: Math.round((PET_WIN_WIDTH - 84) / 2),
          y: PET_WIN_HEIGHT - 90,
          width: 84,
          height: 90,
        }])
      })
    }
  } else {
    // Windows / macOS: forward:true lets clicks pass through transparent area
    // while forwarding mousemove to detect hover over the pet.
    mainWindow.setIgnoreMouseEvents(true, { forward: true })
  }

  const rendererUrl = getRendererUrl()

  if (rendererUrl) {
    mainWindow.loadURL(rendererUrl)
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'dist', 'index.html'))
  }

  mainWindow.on('closed', () => {
    stopMainDragLoop()
    stopLinuxMouseTracker()
    mainWindow = null
  })
}

// ── IPC handlers ────────────────────────────────────────────
ipcMain.handle('pet:ping', async () => 'pong')

ipcMain.handle('pet:get-config', async () => {
  return getEffectiveConfig()
})

ipcMain.handle('pet:save-config', async (event, config) => {
  if (config && typeof config.autoStart === 'boolean') {
    setAutoStart(config.autoStart)
  }
  const merged = { ...getEffectiveConfig(), ...(config || {}) }
  saveConfig(merged)
  broadcastConfig(merged)
  return true
})

ipcMain.handle('pet:get-autostart', async () => isAutoStartEnabled())
ipcMain.handle('pet:set-autostart', async (event, enabled) => setAutoStart(Boolean(enabled)))

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

ipcMain.handle('pet:focus-window', async () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.focus()
    return true
  }
  return false
})

ipcMain.handle('pet:get-position', async () => {
  if (!mainWindow) return { x: 0, y: 0 }
  const [x, y] = mainWindow.getPosition()
  return { x, y }
})

ipcMain.handle('pet:get-screen-size', async () => {
  const display = screen.getPrimaryDisplay()
  const wa = display.workArea
  const winH = isLinuxWayland ? WAYLAND_WIN_HEIGHT : PET_WIN_HEIGHT
  const maxY = Math.max(wa.y, wa.y + wa.height - winH)
  return {
    width: wa.width,
    height: wa.height,
    x: wa.x,
    y: wa.y,
    maxY,
  }
})

ipcMain.handle('pet:set-interactive', async (event, payload) => {
  if (!mainWindow || mainWindow.isDestroyed()) return false
  if (process.platform === 'linux') {
    // Linux X11 uses setShape() for exact click-through; Wayland uses compact window
    return true
  }
  const interactive = !!(payload && payload.interactive)
  if (interactive) {
    mainWindow.setIgnoreMouseEvents(false)
  } else {
    mainWindow.setIgnoreMouseEvents(true, { forward: true })
  }
  return true
})

let dragLoopInterval = null

function stopMainDragLoop() {
  if (dragLoopInterval) {
    clearInterval(dragLoopInterval)
    dragLoopInterval = null
  }
}

ipcMain.handle('pet:set-dragging', async (event, payload) => {
  const wasDragging = isDraggingPet
  isDraggingPet = !!(payload && payload.dragging)
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (isDraggingPet && !isLinuxWayland) {
      if (process.platform === 'linux') {
        // Keep shape locked to full window while dragging so fast pointer moves never exit shape
        try { mainWindow.setShape([]) } catch {}
      }
      // Track cursor in main process for 1:1 DPI-accurate dragging on Windows & Linux
      stopMainDragLoop()
      try {
        const startCursor = screen.getCursorScreenPoint()
        const [startWinX, startWinY] = mainWindow.getPosition()
        const offsetX = startCursor.x - startWinX
        const offsetY = startCursor.y - startWinY
        dragLoopInterval = setInterval(() => {
          if (!isDraggingPet || !mainWindow || mainWindow.isDestroyed()) {
            stopMainDragLoop()
            return
          }
          try {
            const cur = screen.getCursorScreenPoint()
            const wa = screen.getPrimaryDisplay().workArea
            const minX = wa.x
            const maxX = Math.max(minX, wa.x + wa.width - PET_WIN_WIDTH)
            const minY = wa.y
            const maxY = Math.max(minY, wa.y + wa.height - PET_WIN_HEIGHT)
            const nx = Math.min(maxX, Math.max(minX, Math.round(cur.x - offsetX)))
            const ny = Math.min(maxY, Math.max(minY, Math.round(cur.y - offsetY)))
            mainWindow.setBounds({ x: nx, y: ny, width: PET_WIN_WIDTH, height: PET_WIN_HEIGHT }, false)
          } catch {}
        }, 16)
      } catch {}
    } else {
      stopMainDragLoop()
      if (process.platform === 'linux' && !isLinuxWayland && lastShapeRects.length > 0) {
        applyWindowShape(lastShapeRects)
      }
    }
    // Persist last position after drag finishes
    if (wasDragging && !isDraggingPet && !isLinuxWayland) {
      try {
        const [x, y] = mainWindow.getPosition()
        const cfg = getEffectiveConfig()
        cfg.lastX = x
        cfg.lastY = y
        saveConfig(cfg)
      } catch {}
    }
  }
  return true
})

ipcMain.on('pet:update-shape', (event, rects) => {
  if (process.platform === 'linux') {
    applyWindowShape(rects)
  }
})

ipcMain.on('pet:update-hitbox', (event, rect) => {
  if (rect && Number.isFinite(rect.x) && Number.isFinite(rect.y) &&
      Number.isFinite(rect.width) && Number.isFinite(rect.height)) {
    petHitbox = {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    }
  }
})

ipcMain.handle('pet:move-by', async (event, payload) => {
  if (!mainWindow || mainWindow.isDestroyed()) return null
  const dx = Number(payload && payload.dx)
  const dy = Number(payload && payload.dy)
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return null

  const workArea = screen.getPrimaryDisplay().workArea
  const minX = workArea.x
  const maxX = Math.max(minX, workArea.x + workArea.width - PET_WIN_WIDTH)
  const minY = workArea.y
  const maxY = Math.max(minY, workArea.y + workArea.height - PET_WIN_HEIGHT)

  const [curX, curY] = mainWindow.getPosition()
  const rawX = Math.round(curX + dx)
  const rawY = Math.round(curY + dy)
  const nextX = Math.min(maxX, Math.max(minX, rawX))
  const nextY = Math.min(maxY, Math.max(minY, rawY))

  mainWindow.setBounds({
    x: nextX,
    y: nextY,
    width: PET_WIN_WIDTH,
    height: PET_WIN_HEIGHT,
  }, false)

  return {
    x: nextX,
    y: nextY,
    hitLeft: rawX <= minX,
    hitRight: rawX >= maxX,
  }
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

function forwardBackendEvent(msg) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    try {
      mainWindow.webContents.send('pet:backend-event', msg)
    } catch {}
  }
}

// ── Config window (separada, no overlay) ─────────────────
function openConfigWindow() {
  if (configWindow && !configWindow.isDestroyed()) {
    configWindow.focus()
    return
  }
  const iconPath = getAppIconPath()
  configWindow = new BrowserWindow({
    width: 480,
    height: 720,
    resizable: false,
    alwaysOnTop: true,
    title: 'Pet Asistente - Configuración',
    backgroundColor: '#0d101b',
    ...(iconPath ? { icon: iconPath } : {}),
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

// ── Companion Hub / Chat window ───────────────────────────
function openChatWindow(initialTab = 'chat') {
  const tab = typeof initialTab === 'string' && initialTab ? initialTab : 'chat'
  if (chatWindow && !chatWindow.isDestroyed()) {
    chatWindow.show()
    chatWindow.focus()
    chatWindow.webContents.send('pet:switch-tab', tab)
    return
  }
  const iconPath = getAppIconPath()
  chatWindow = new BrowserWindow({
    width: 460,
    height: 640,
    minWidth: 400,
    minHeight: 540,
    resizable: true,
    alwaysOnTop: true,
    title: 'Pet Asistente',
    backgroundColor: '#0d101b',
    ...(iconPath ? { icon: iconPath } : {}),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
    },
  })
  chatWindow.setMenuBarVisibility(false)
  chatWindow.loadFile(path.join(__dirname, '..', 'chat-renderer', 'index.html'))
  chatWindow.webContents.once('did-finish-load', () => {
    if (chatWindow && !chatWindow.isDestroyed() && tab !== 'chat') {
      chatWindow.webContents.send('pet:switch-tab', tab)
    }
  })
  chatWindow.on('closed', () => { chatWindow = null })
}

ipcMain.handle('pet:open-chat', async (event, tab) => {
  openChatWindow(tab || 'chat')
})

function toggleSoundMute() {
  const cfg = getEffectiveConfig()
  cfg.soundMuted = !cfg.soundMuted
  saveConfig(cfg)
  broadcastConfig(cfg)
  // Sync with backend SQLite (best effort)
  try {
    const postData = JSON.stringify(cfg)
    const req = http.request({
      hostname: '127.0.0.1',
      port: 8000,
      path: '/config',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) },
    })
    req.on('error', () => {})
    req.write(postData)
    req.end()
  } catch {}
}

function centerPetWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    const wa = screen.getPrimaryDisplay().workArea
    const w = isLinuxWayland ? WAYLAND_WIN_WIDTH : PET_WIN_WIDTH
    const h = isLinuxWayland ? WAYLAND_WIN_HEIGHT : PET_WIN_HEIGHT
    const cx = Math.round(wa.x + (wa.width - w) / 2)
    const cy = Math.round(wa.y + wa.height - h - 40)
    mainWindow.setBounds({ x: cx, y: cy, width: w, height: h }, false)
    mainWindow.show()
  }
}

function triggerBackendPost(urlPath, body = {}) {
  try {
    const postData = JSON.stringify(body)
    const req = http.request({
      hostname: '127.0.0.1',
      port: 8000,
      path: urlPath,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) },
    })
    req.on('error', () => {})
    req.write(postData)
    req.end()
  } catch {}
}

function buildAppMenuTemplate() {
  const cfg = getEffectiveConfig()
  return [
    { label: '💬 Chat', click: () => openChatWindow('chat') },
    { label: '🍅 Pomodoro', click: () => openChatWindow('pomodoro') },
    { label: '✅ Tareas', click: () => openChatWindow('tasks') },
    { label: '📋 Reporte del día', click: () => openChatWindow('report') },
    { label: '🧠 Memoria', click: () => openChatWindow('memory') },
    { type: 'separator' },
    { label: '✨ Acción IA ahora', click: () => triggerBackendPost('/ai/pet/think') },
    { label: '🐾 Hacer truco (IA)', click: () => triggerBackendPost('/ai/pet/command', { command: 'haz un truco divertido con coreografía en el escritorio' }) },
    {
      label: '🎙️ Escuchar orden por voz (Ctrl+Shift+V)',
      click: () => {
        forwardBackendEvent({
          type: 'event',
          data: {
            event: 'voice.start_listening',
            data: {},
          },
        })
      },
    },
    { type: 'separator' },
    {
      label: '🪜 Subir un escalón',
      click: () => {
        forwardBackendEvent({
          type: 'event',
          data: {
            event: 'pet.action',
            data: { action: 'step_up', speech: '¡Arriba! 🪜', sound: 'ladrido' },
          },
        })
      },
    },
    {
      label: '⬇️ Bajar de escalón',
      click: () => {
        forwardBackendEvent({
          type: 'event',
          data: {
            event: 'pet.action',
            data: { action: 'step_down', speech: '¡Bajando! 🐾' },
          },
        })
      },
    },
    {
      label: '🪟 Trepar a mi ventana activa',
      click: () => {
        forwardBackendEvent({
          type: 'event',
          data: {
            event: 'pet.action',
            data: { action: 'climb_window', speech: '¡A tu ventana! 🪟', sound: 'ladrido' },
          },
        })
      },
    },
    {
      label: '🎾 Lanzar pelotita (en pantalla)',
      click: () => {
        launchTennisBall()
      },
    },
    {
      label: '🍪 Dar snack / premio',
      click: () => {
        forwardBackendEvent({
          type: 'event',
          data: {
            event: 'pet.action',
            data: { action: 'feed_snack', speech: '¡Ñam ñam! 🍪', sound: 'ladrido' },
          },
        })
      },
    },
    {
      label: '🎯 Bajar al suelo (piso)',
      click: () => {
        forwardBackendEvent({
          type: 'event',
          data: {
            event: 'pet.action',
            data: { action: 'reset_step', speech: '¡Al suelo! 🐾' },
          },
        })
      },
    },
    { type: 'separator' },
    {
      label: '🔇 Silenciar sonidos',
      type: 'checkbox',
      checked: !!cfg.soundMuted,
      click: () => toggleSoundMute(),
    },
    {
      label: '🚀 Iniciar con el sistema',
      type: 'checkbox',
      checked: isAutoStartEnabled(),
      click: (menuItem) => setAutoStart(menuItem.checked),
    },
    { label: '⚙️ Configuración', click: () => openConfigWindow() },
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
    { label: '🎯 Centrar Pet en pantalla', click: () => centerPetWindow() },
    ...(isLinuxWayland ? [{
      label: '👻 Modo click-through (atravesar clics)',
      type: 'checkbox',
      checked: waylandClickThrough,
      click: (menuItem) => {
        waylandClickThrough = !!menuItem.checked
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.setIgnoreMouseEvents(waylandClickThrough)
        }
      },
    }] : []),
    { type: 'separator' },
    {
      label: '❌ Cerrar',
      click: () => {
        stopBackend()
        app.quit()
      },
    },
  ]
}

function refreshTrayMenu() {
  if (!tray) return
  try {
    tray.setContextMenu(Menu.buildFromTemplate(buildAppMenuTemplate()))
  } catch {}
}

ipcMain.handle('pet:show-context-menu', async () => {
  if (!mainWindow || mainWindow.isDestroyed()) return false
  const menu = Menu.buildFromTemplate(buildAppMenuTemplate())
  menu.popup({ window: mainWindow })
  return true
})

// ── System Tray ─────────────────────────────────────────────
function createTray() {
  const iconPath = getAppIconPath()
  let trayIcon
  if (iconPath && fs.existsSync(iconPath)) {
    const size = process.platform === 'linux' ? 22 : 16
    trayIcon = nativeImage.createFromPath(iconPath).resize({ width: size, height: size })
  } else {
    trayIcon = nativeImage.createEmpty()
  }

  tray = new Tray(trayIcon)
  tray.setToolTip('Pet Asistente')
  refreshTrayMenu()

  tray.on('double-click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) mainWindow.focus()
      else mainWindow.show()
    }
  })
}

// ── Screen Bouncing Tennis Ball Game ────────────────────────
let ballWindow = null
let ballPhysicsInterval = null

function launchTennisBall() {
  if (!mainWindow || mainWindow.isDestroyed()) return
  if (ballWindow && !ballWindow.isDestroyed()) {
    try { ballWindow.close() } catch {}
    ballWindow = null
  }
  if (ballPhysicsInterval) {
    clearInterval(ballPhysicsInterval)
    ballPhysicsInterval = null
  }

  const display = screen.getPrimaryDisplay()
  const wa = display.workArea
  const [petX, petY] = mainWindow.getPosition()

  // Ball spawn position (above pet)
  let ballX = Math.round(petX + 130)
  let ballY = Math.round(Math.max(wa.y + 40, petY - 40))

  // Initial velocity & spin
  const throwLeft = petX > wa.x + wa.width / 2
  let vx = (Math.random() * 6 + 13) * (throwLeft ? -1 : 1)
  let vy = -(Math.random() * 6 + 12)
  const gravity = 0.72
  const restitution = 0.75
  const floorY = wa.y + wa.height - 36
  const minX = wa.x + 6
  const maxX = wa.x + wa.width - 36
  let rot = 0
  let spin = vx * 2.8

  ballWindow = new BrowserWindow({
    width: 30,
    height: 30,
    x: ballX,
    y: ballY,
    transparent: true,
    frame: false,
    hasShadow: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false,
    type: process.platform === 'linux' ? 'toolbar' : undefined,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  })

  ballWindow.setIgnoreMouseEvents(true)
  enableLinuxX11Overlay(ballWindow)

  const ballHtml = `
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      html, body {
        margin: 0; padding: 0; width: 30px; height: 30px;
        background: transparent !important; overflow: hidden;
        user-select: none; display: flex; align-items: center; justify-content: center;
      }
      .ball-rotor {
        width: 24px; height: 24px;
        display: flex; align-items: center; justify-content: center;
        transform-origin: center center;
        will-change: transform;
        filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.45));
      }
      svg { width: 24px; height: 24px; display: block; }
    </style>
    </head>
    <body>
      <div class="ball-rotor" id="b">
        <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <radialGradient id="feltGrad" cx="35%" cy="30%" r="65%">
              <stop offset="0%" stop-color="#e2fca8"/>
              <stop offset="35%" stop-color="#bef264"/>
              <stop offset="70%" stop-color="#84cc16"/>
              <stop offset="100%" stop-color="#3f6212"/>
            </radialGradient>
          </defs>
          <!-- Spherical felt base -->
          <circle cx="50" cy="50" r="46" fill="url(#feltGrad)"/>
          <!-- Curved seam depth grooves -->
          <path d="M 20,24 C 38,36 38,64 20,76" fill="none" stroke="#365314" stroke-width="7" stroke-linecap="round" opacity="0.65"/>
          <path d="M 80,24 C 62,36 62,64 80,76" fill="none" stroke="#365314" stroke-width="7" stroke-linecap="round" opacity="0.65"/>
          <!-- Pure white tennis seams -->
          <path d="M 20,24 C 38,36 38,64 20,76" fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round"/>
          <path d="M 80,24 C 62,36 62,64 80,76" fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round"/>
        </svg>
      </div>
      <script>
        const el = document.getElementById('b');
        try {
          const { ipcRenderer } = require('electron');
          ipcRenderer.on('rot', (_, deg) => {
            el.style.transform = 'rotate(' + deg + 'deg)';
          });
        } catch (e) {}
      </script>
    </body>
    </html>
  `
  ballWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(ballHtml))

  forwardBackendEvent({
    type: 'event',
    data: {
      event: 'pet.action',
      data: { action: 'jump', speech: '¡Allá va la pelota! 🎾👀', sound: 'ladrido' },
    },
  })

  let bounces = 0
  let settled = false

  ballPhysicsInterval = setInterval(() => {
    if (!ballWindow || ballWindow.isDestroyed()) {
      clearInterval(ballPhysicsInterval)
      ballPhysicsInterval = null
      return
    }

    vy += gravity
    ballX += vx
    ballY += vy

    // Wall bounce X with spin friction
    if (ballX <= minX) {
      ballX = minX
      vx = -vx * restitution
      spin = -spin * 0.7
    } else if (ballX >= maxX) {
      ballX = maxX
      vx = -vx * restitution
      spin = -spin * 0.7
    }

    // Floor bounce & rolling friction
    if (ballY >= floorY) {
      ballY = floorY
      vy = -vy * restitution
      vx *= 0.93
      bounces++

      // Realistic rolling physics: surface friction spins the ball based on linear speed
      spin = (vx / 12) * (180 / Math.PI)

      if (Math.abs(vy) < 1.6 && Math.abs(vx) < 1.0 && bounces >= 3) {
        settled = true
      }
    } else {
      // In-flight air resistance dampens spin slightly
      spin *= 0.995
    }

    rot += spin

    // Ceiling bounce Y
    if (ballY <= wa.y) {
      ballY = wa.y
      vy = -vy * restitution
    }

    try {
      ballWindow.setBounds({
        x: Math.round(ballX),
        y: Math.round(ballY),
        width: 30,
        height: 30,
      }, false)
      ballWindow.webContents.send('rot', Math.round(rot))
    } catch {}

    if (settled) {
      clearInterval(ballPhysicsInterval)
      ballPhysicsInterval = null

      const targetPetX = Math.round(Math.max(minX, Math.min(maxX - 240, ballX - 110)))
      const targetPetY = Math.round(Math.max(wa.y, Math.min(wa.y + wa.height - PET_WIN_HEIGHT, ballY - 140)))

      forwardBackendEvent({
        type: 'event',
        data: {
          event: 'ball.settled',
          data: {
            x: targetPetX,
            y: targetPetY,
            ballX: Math.round(ballX),
            ballY: Math.round(ballY),
            originX: petX,
            originY: petY,
          },
        },
      })
    }
  }, 16)

  // Safety cleanup after 15 seconds
  setTimeout(() => {
    if (ballWindow && !ballWindow.isDestroyed()) {
      try { ballWindow.close() } catch {}
      ballWindow = null
    }
  }, 15000)
}

ipcMain.handle('pet:launch-ball', async () => {
  launchTennisBall()
  return true
})

ipcMain.handle('pet:pickup-ball', async () => {
  if (ballWindow && !ballWindow.isDestroyed()) {
    try { ballWindow.close() } catch {}
    ballWindow = null
  }
  return true
})

// ── Clipboard Error Watcher ─────────────────────────────────
let lastClipboardSnippet = ''
let lastDetectedErrorText = ''
let clipboardWatcherInterval = null

function isCodeError(text) {
  if (!text || text.length < 20 || text.length > 50000) return false
  const errorIndicators = [
    /Traceback \(most recent call last\):/i,
    /Error:\s+[^\n]+/i,
    /Exception:\s+[^\n]+/i,
    /SyntaxError:/i,
    /TypeError:/i,
    /ReferenceError:/i,
    /NullPointerException/i,
    /panic:\s+[^\n]+/i,
    /fatal error:/i,
    /\bat\s+[^\n]+\s+\([^)]+:\d+:\d+\)/i,
    /undefined is not a function/i,
    /Cannot read propert(y|ies) of undefined/i,
  ]
  return errorIndicators.some((rx) => rx.test(text))
}

function startClipboardErrorWatcher() {
  if (clipboardWatcherInterval) return
  clipboardWatcherInterval = setInterval(() => {
    try {
      const text = clipboard.readText().trim()
      if (!text || text === lastClipboardSnippet) return
      lastClipboardSnippet = text

      if (isCodeError(text)) {
        lastDetectedErrorText = text
        forwardBackendEvent({
          type: 'event',
          data: {
            event: 'clipboard.error',
            data: {
              snippet: text.slice(0, 300),
              full_text: text.slice(0, 4000),
            },
          },
        })
      }
    } catch {}
  }, 1500)
}

function stopClipboardErrorWatcher() {
  if (clipboardWatcherInterval) {
    clearInterval(clipboardWatcherInterval)
    clipboardWatcherInterval = null
  }
}

ipcMain.handle('pet:get-last-error', async () => {
  return lastDetectedErrorText || null
})

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

    // Sync autostart on startup if configured
    if (cfg?.autoStart && !isAutoStartEnabled()) {
      setAutoStart(true)
    }

    // Check first launch — open config window separately (unless started automatically with --autostart)
    const isAutoStarted = process.argv.includes('--autostart')
    if (!isAutoStarted && (!cfg || cfg.firstLaunch !== false)) {
      console.log('[Pet] First launch — opening config window...')
      openConfigWindow()
    }
  } catch (err) {
    console.error('[Pet] Failed to start backend:', err.message)
  }

  createWindow()
  createTray()

  // Auto-grant audio/media permissions for speech recognition
  try {
    session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
      if (permission === 'media' || permission === 'audio-capture' || permission === 'microphone') {
        return callback(true)
      }
      callback(true)
    })
  } catch {}

  // ── Global Shortcuts ────────────────────────────────────
  const registerSafe = (key, handler) => {
    try {
      const ok = globalShortcut.register(key, handler)
      if (ok) console.log(`[Pet] Registered global shortcut: ${key}`)
    } catch {}
  }

  // Quick Summon & Chat: Ctrl+Shift+Space / Alt+Shift+Space
  const handleSummon = () => {
    if (!chatWindow || chatWindow.isDestroyed()) {
      openChatWindow('chat')
    } else if (chatWindow.isVisible()) {
      chatWindow.hide()
    } else {
      chatWindow.show()
      chatWindow.focus()
    }
    forwardBackendEvent({
      type: 'event',
      data: {
        event: 'pet.action',
        data: { action: 'jump', speech: '¡Aquí estoy! 🐾', sound: 'ladrido' },
      },
    })
  }
  registerSafe('CommandOrControl+Shift+Space', handleSummon)
  registerSafe('Alt+Shift+Space', handleSummon)
  registerSafe('CommandOrControl+Alt+Space', handleSummon)

  // Voice Command: Ctrl+Shift+V / Alt+Shift+V / Ctrl+Alt+V
  const handleVoice = () => {
    forwardBackendEvent({
      type: 'event',
      data: {
        event: 'voice.start_listening',
        data: {},
      },
    })
  }
  registerSafe('CommandOrControl+Shift+V', handleVoice)
  registerSafe('Alt+Shift+V', handleVoice)
  registerSafe('CommandOrControl+Alt+V', handleVoice)

  // Tennis Ball: Alt+Shift+P / Ctrl+Shift+P
  const handleBall = () => {
    forwardBackendEvent({
      type: 'event',
      data: {
        event: 'pet.action',
        data: { action: 'fetch_ball', speech: '¡A por la pelota! 🎾', sound: 'ladrido', mood: 'playful' },
      },
    })
  }
  registerSafe('Alt+Shift+P', handleBall)
  registerSafe('CommandOrControl+Shift+P', handleBall)

  // Snack: Alt+Shift+G / Ctrl+Shift+G
  const handleSnack = () => {
    forwardBackendEvent({
      type: 'event',
      data: {
        event: 'pet.action',
        data: { action: 'feed_snack', speech: '¡Ñam ñam! 🍪', sound: 'ladrido', mood: 'happy' },
      },
    })
  }
  registerSafe('Alt+Shift+G', handleSnack)
  registerSafe('CommandOrControl+Shift+G', handleSnack)

  startClipboardErrorWatcher()

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
  try { globalShortcut.unregisterAll() } catch {}
  stopClipboardErrorWatcher()
  stopLinuxMouseTracker()
  stopBackend()
})

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    stopLinuxMouseTracker()
    stopBackend()
    app.quit()
  })
}
