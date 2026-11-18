@echo off
echo ============================================
echo  Pet Asistente - Instalacion de dependencias
echo ============================================
echo.

:: Buscar Python
set PYTHON_EXE=C:\Users\Developer\AppData\Local\Programs\Python\Python314\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] No se encontro Python en %PYTHON_EXE%
    echo Instala Python desde https://python.org
    pause
    exit /b 1
)

echo [1/3] Instalando dependencias Python...
"%PYTHON_EXE%" -m pip install -r backend\requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias Python
    pause
    exit /b 1
)
echo [OK] Dependencias Python instaladas.
echo.

echo [2/3] Instalando dependencias del desktop (Electron)...
cd desktop
call npm install
if errorlevel 1 (
    echo [ERROR] Fallo npm install en desktop
    pause
    exit /b 1
)
echo [OK] Dependencias desktop instaladas.
echo.

echo [3/3] Instalando dependencias del renderer (React/Vite)...
cd renderer
call npm install
if errorlevel 1 (
    echo [ERROR] Fallo npm install en renderer
    pause
    exit /b 1
)
cd ..\..
echo [OK] Dependencias renderer instaladas.
echo.

echo ============================================
echo  Instalacion completa.
echo  Para iniciar: npm run dev
echo ============================================
pause
