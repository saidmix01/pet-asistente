@echo off
echo ============================================
echo  Pet Asistente - Build Completo
echo ============================================
echo.

set PYTHON_EXE=C:\Users\Developer\AppData\Local\Programs\Python\Python314\python.exe

:: 1. Install PyInstaller
echo [1/4] Instalando PyInstaller...
"%PYTHON_EXE%" -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] No se pudo instalar PyInstaller
    pause
    exit /b 1
)
echo [OK]
echo.

:: 2. Build backend exe
echo [2/4] Compilando backend (Python → exe)...
cd backend
"%PYTHON_EXE%" -m PyInstaller asistente-core.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERROR] Fallo la compilacion del backend
    pause
    exit /b 1
)
cd ..
echo [OK] backend\dist\asistente-core.exe
echo.

:: 3. Install electron-builder
echo [3/4] Instalando dependencias de build...
cd desktop
call npm install --save-dev electron-builder
if errorlevel 1 (
    echo [ERROR] Fallo npm install electron-builder
    pause
    exit /b 1
)
cd ..
echo [OK]
echo.

:: 4. Build installer
echo [4/4] Creando instalador de Windows...
cd desktop
set CSC_IDENTITY_AUTO_DISCOVERY=false
call npm run dist
if errorlevel 1 (
    echo [ERROR] Fallo electron-builder
    pause
    exit /b 1
)
cd ..
echo.

echo ============================================
echo  Build completo!
echo  Instalador en: desktop\release\
echo ============================================
pause
