@echo off
setlocal
echo ============================================
echo  Pet Asistente - Build Completo (Windows)
echo ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No se encontro Node.js en PATH.
    pause
    exit /b 1
)

echo [1/2] Compilando backend (Python -^> asistente-core.exe)...
node scripts\build-backend.js
if errorlevel 1 (
    echo [ERROR] Fallo la compilacion del backend.
    pause
    exit /b 1
)
echo.

echo [2/2] Compilando renderer y creando instalador de Windows...
set CSC_IDENTITY_AUTO_DISCOVERY=false
call npm run pack:win
if errorlevel 1 (
    echo [ERROR] Fallo electron-builder.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build completo!
echo  Instalador en: desktop\release\
echo ============================================
pause
