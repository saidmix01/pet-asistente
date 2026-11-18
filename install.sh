#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo " Pet Asistente - Instalacion (Linux)"
echo "============================================"
echo

if ! command -v node >/dev/null 2>&1; then
  echo "[ERROR] No se encontró Node.js. Instálalo primero (v20+)."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] No se encontró python3. Instálalo primero (3.10+)."
  exit 1
fi

node scripts/install-all.js

echo
if ! command -v xdotool >/dev/null 2>&1 && ! command -v xprop >/dev/null 2>&1; then
  echo "[TIP] Para detección real de ventana activa en X11/XWayland, instalá xdotool o x11-utils (xprop):"
  echo "      sudo apt install xdotool x11-utils xprintidle"
fi
