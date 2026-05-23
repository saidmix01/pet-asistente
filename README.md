# 🐾 Pet Asistente

Desktop pet assistant — una mascota virtual en tu escritorio que reacciona a tu actividad.

## Estructura

```
pet-asistente/
├── desktop/         ← Electron + React (el pet visual)
├── backend/         ← Python FastAPI (el cerebro)
├── package.json     ← Scripts del monorepo
└── electron-builder.yml ← Config de empaquetado
```

## Dev

```bash
# Iniciar ambos
npm run dev

# O por separado
npm run dev:backend   # Python FastAPI :8000
npm run dev:desktop   # Electron + Vite
```

## Build

```bash
npm run build
npm run pack
```
