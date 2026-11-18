# 🐾 Pet Asistente

Desktop pet assistant — una mascota virtual en tu escritorio que reacciona a tu actividad, chatea con IA (**Antigravity CLI `agy`**, Ollama local o DeepSeek remoto) e integra ClickUp, Pomodoro, Git y reportes diarios.

Compatible con **Windows** y **Linux**.

## Estructura

```
pet-asistente/
├── desktop/               ← Electron + React/Vite (mascota flotante, chat, ajustes, tray)
├── backend/               ← Python FastAPI + SQLite + WebSocket (cerebro y monitoreo)
├── scripts/               ← Scripts multiplataforma (Windows / Linux)
├── install.bat / .sh      ← Instalación de dependencias (Python venv + Node)
├── build.bat / .sh        ← Build de producción (PyInstaller + Electron Builder)
└── package.json           ← Scripts del monorepo
```

## Requisitos

- **Node.js** 20+ y **npm**
- **Python** 3.10+ (en Debian/Ubuntu: `sudo apt install python3-venv`)
- **Linux (opcional, recomendado)** para detección real de ventana activa e inactividad en X11/XWayland:
  ```bash
  sudo apt install xdotool x11-utils xprintidle
  ```
  (En Wayland también soporta `hyprctl`, `swaymsg`, `kdotool` y `gdbus`; si no hay herramientas disponibles, usa modo simulado automáticamente.)

## Instalación

En **Windows** o **Linux**:

```bash
npm run install:all
```

O usando los scripts directos:
- **Linux**: `./install.sh`
- **Windows**: `install.bat`

Esto crea automáticamente `backend/.venv`, instala `backend/requirements.txt` y las dependencias de `desktop/` y `desktop/renderer/`.

## Desarrollo

```bash
# Iniciar desktop (arranca Vite, Electron y el backend Python automáticamente)
npm run dev

# O por separado:
npm run dev:backend   # Python FastAPI en http://127.0.0.1:8000
npm run dev:desktop   # Electron + Vite
```

> **Nota sobre Wayland/X11 en Linux**: En Linux con `DISPLAY` disponible (X11 o XWayland), Electron usa `ozone-platform=x11` junto con `override_redirect` ([`desktop/scripts/set-x11-overlay.py`](desktop/scripts/set-x11-overlay.py)) y recorte de región `setShape()` para mantenerse siempre visible sobre las apps sin sombra/marco del compositor y con click-through real. Puedes forzar Wayland puro con `PET_OZONE_PLATFORM=wayland npm run start`.

## Build de producción

- **Linux** (`AppImage` y `.deb` en `desktop/release/`):
  ```bash
  ./build.sh
  # o: npm run release
  ```
- **Windows** (`.exe` NSIS y portable en `desktop/release/`):
  ```cmd
  build.bat
  rem o: npm run build && npm run pack:win
  ```
