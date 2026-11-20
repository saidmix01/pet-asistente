const { contextBridge, ipcRenderer } = require('electron')

const isLinuxWayland =
  process.platform === 'linux' &&
  (process.env.PET_OZONE_PLATFORM === 'wayland' ||
    (!process.env.DISPLAY && !!process.env.WAYLAND_DISPLAY))

contextBridge.exposeInMainWorld('pet', {
  // ── System ────────────────────────────────────────────
  platform: process.platform,
  useCanvasMove: isLinuxWayland,
  ping: () => ipcRenderer.invoke('pet:ping'),
  setInteractive: (interactive) =>
    ipcRenderer.invoke('pet:set-interactive', { interactive: Boolean(interactive) }),
  setDragging: (dragging) =>
    ipcRenderer.invoke('pet:set-dragging', { dragging: Boolean(dragging) }),
  updateHitbox: (rect) =>
    ipcRenderer.send('pet:update-hitbox', rect),
  updateShape: (rects) =>
    ipcRenderer.send('pet:update-shape', rects),
  moveBy: (dx, dy) => ipcRenderer.invoke('pet:move-by', { dx, dy }),
  getPosition: () => ipcRenderer.invoke('pet:get-position'),
  getScreenSize: () => ipcRenderer.invoke('pet:get-screen-size'),
  openChat: (tab) => ipcRenderer.invoke('pet:open-chat', tab || 'chat'),
  openConfig: () => ipcRenderer.invoke('pet:open-config'),
  openExternal: (url) => ipcRenderer.invoke('pet:open-external', url),
  showContextMenu: () => ipcRenderer.invoke('pet:show-context-menu'),
  getLastError: () => ipcRenderer.invoke('pet:get-last-error'),
  launchBall: () => ipcRenderer.invoke('pet:launch-ball'),
  pickupBall: () => ipcRenderer.invoke('pet:pickup-ball'),
  focusWindow: () => ipcRenderer.invoke('pet:focus-window'),
  playSound: (name) => ipcRenderer.invoke('pet:play-sound', name),
  onPlaySound: (callback) => {
    const handler = (_event, name) => callback(name)
    ipcRenderer.on('pet:play-sound', handler)
    return () => ipcRenderer.removeListener('pet:play-sound', handler)
  },

  // ── Config ────────────────────────────────────────────
  getConfig: () => ipcRenderer.invoke('pet:get-config'),
  saveConfig: (config) => ipcRenderer.invoke('pet:save-config', config),
  getAutoStart: () => ipcRenderer.invoke('pet:get-autostart'),
  setAutoStart: (enabled) => ipcRenderer.invoke('pet:set-autostart', enabled),
  isFirstLaunch: () => ipcRenderer.invoke('pet:is-first-launch'),
  markConfigured: () => ipcRenderer.invoke('pet:mark-configured'),
  onConfigUpdated: (callback) => {
    const handler = (_event, cfg) => callback(cfg)
    ipcRenderer.on('pet:config-updated', handler)
    return () => ipcRenderer.removeListener('pet:config-updated', handler)
  },
  onSwitchTab: (callback) => {
    const handler = (_event, tab) => callback(tab)
    ipcRenderer.on('pet:switch-tab', handler)
    return () => ipcRenderer.removeListener('pet:switch-tab', handler)
  },

  // ── Backend proxy (avoids file:// CORS issues) ─────────
  backendFetch: (path) => ipcRenderer.invoke('pet:backend-fetch', path),
  backendPost: (path, body) => ipcRenderer.invoke('pet:backend-post', { path, body }),
  onBackendEvent: (callback) => {
    const handler = (_event, data) => callback(data)
    ipcRenderer.on('pet:backend-event', handler)
    return () => ipcRenderer.removeListener('pet:backend-event', handler)
  },
})
