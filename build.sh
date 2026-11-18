#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo " Pet Asistente - Build Completo (Linux)"
echo "============================================"
echo

if ! command -v node >/dev/null 2>&1; then
  echo "[ERROR] No se encontró Node.js."
  exit 1
fi

echo "[1/2] Compilando backend (Python -> asistente-core)..."
node scripts/build-backend.js
echo

echo "[2/2] Compilando renderer y empaquetando app Linux (AppImage / deb)..."
CSC_IDENTITY_AUTO_DISCOVERY=false npm run pack:linux

echo
echo "============================================"
echo " Build completo!"
echo " Paquetes en: desktop/release/"
echo "============================================"
