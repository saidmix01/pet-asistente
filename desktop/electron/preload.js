const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('pet', {
  ping: () => ipcRenderer.invoke('pet:ping'),
  setInteractive: (interactive) =>
    ipcRenderer.invoke('pet:set-interactive', { interactive: Boolean(interactive) }),
  moveBy: (dx, dy) => ipcRenderer.invoke('pet:move-by', { dx, dy }),
  getPosition: () => ipcRenderer.invoke('pet:get-position'),
  getScreenSize: () => ipcRenderer.invoke('pet:get-screen-size'),
})
