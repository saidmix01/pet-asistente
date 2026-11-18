@echo off
setlocal
echo ============================================
echo  Pet Asistente - Instalacion (Windows)
echo ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No se encontro Node.js en PATH.
    echo Instala Node.js desde https://nodejs.org
    pause
    exit /b 1
)

node scripts\install-all.js
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion.
    pause
    exit /b 1
)

pause
