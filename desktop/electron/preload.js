const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('pet', {
  // ── System ────────────────────────────────────────────
  ping: () => ipcRenderer.invoke('pet:ping'),
  setInteractive: (interactive) =>
    ipcRenderer.invoke('pet:set-interactive', { interactive: Boolean(interactive) }),
  moveBy: (dx, dy) => ipcRenderer.invoke('pet:move-by', { dx, dy }),
  getPosition: () => ipcRenderer.invoke('pet:get-position'),
  getScreenSize: () => ipcRenderer.invoke('pet:get-screen-size'),
  openChat: () => ipcRenderer.invoke('pet:open-chat'),

  // ── Config (new) ───────────────────────────────────────
  getConfig: () => ipcRenderer.invoke('pet:get-config'),
  saveConfig: (config) => ipcRenderer.invoke('pet:save-config', config),
  isFirstLaunch: () => ipcRenderer.invoke('pet:is-first-launch'),
  markConfigured: () => ipcRenderer.invoke('pet:mark-configured'),
})
