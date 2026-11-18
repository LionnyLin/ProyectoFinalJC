@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================================
echo  Preparando ambiente - Simulador Ciudad Bicentenario
echo ========================================================

set "PY_CMD="
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if %ERRORLEVEL% EQU 0 set "PY_CMD=py -3"
)
if "%PY_CMD%"=="" (
    where python >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if %ERRORLEVEL% EQU 0 set "PY_CMD=python"
    )
)
if "%PY_CMD%"=="" (
    echo [ERROR] Se requiere Python 3.11 o superior instalado y en el PATH.
    exit /b 1
)

if exist ".venv\Scripts\python.exe" goto :venv_ok
echo [1/3] Creando entorno virtual en .venv...
%PY_CMD% -m venv .venv
if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual .venv.
    exit /b 1
)
goto :install_deps

:venv_ok
echo [1/3] Entorno virtual .venv detectado.

:install_deps
set "VENV_PY=.venv\Scripts\python.exe"

echo [2/3] Instalando dependencias desde requirements.txt...
"%VENV_PY%" -m pip install --upgrade pip >nul
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    exit /b 1
)

echo [3/3] Verificando modulos del entorno...
"%VENV_PY%" -c "import tkinter, openpyxl, matplotlib, docx, lxml, PIL; print('Dependencias verificadas correctamente.')"
if errorlevel 1 (
    echo [ERROR] Faltan modulos requeridos ^(verifica tkinter o dependencias^).
    exit /b 1
)

if /I "%~1"=="--run" goto :run_app
if /I "%~1"=="--test" goto :run_tests

echo.
echo [OK] Ambiente listo para ejecutar el programa.
echo      - Ejecutar GUI:      .venv\Scripts\python.exe main.py
echo      - Todo en 1 paso:    setup.bat --run
exit /b 0

:run_app
echo.
echo Iniciando aplicacion...
"%VENV_PY%" main.py
exit /b %ERRORLEVEL%

:run_tests
echo.
echo Ejecutando pruebas unitarias...
"%VENV_PY%" -m unittest discover -s tests -v
exit /b %ERRORLEVEL%
