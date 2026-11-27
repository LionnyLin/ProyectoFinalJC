@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================================
echo  Preparando ambiente - Simulador Ciudad Bicentenario
echo ========================================================

set "PY_CMD="
set "PY_VER="
set "PIP_OPTS=--default-timeout=120 --retries 5"

echo [1/4] Verificando instalacion previa de Python ^(3.11+^)...
call :find_python
if not "%PY_CMD%"=="" goto :python_ok

echo       No se detecto Python 3.11 o superior. Descargando e instalando Python 3.12...
call :install_python
if errorlevel 1 (
    echo [ERROR] No se pudo instalar Python automaticamente.
    echo         Instala Python 3.11+ manualmente desde https://www.python.org/downloads/
    exit /b 1
)

call :find_python
if "%PY_CMD%"=="" (
    echo [ERROR] Python se instalo pero no pudo ser localizado. Reinicia la terminal e intenta de nuevo.
    exit /b 1
)

:python_ok
echo       Python detectado: %PY_VER% ^(%PY_CMD%^)

echo [2/4] Verificando entorno virtual .venv...
if not exist ".venv\Scripts\python.exe" goto :create_venv

".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 (
    echo       Entorno virtual .venv existente detectado.
    goto :venv_ready
)

echo       Entorno virtual .venv previo incompatible o danado. Recreando...
rmdir /s /q ".venv" >nul 2>&1

:create_venv
echo       Creando entorno virtual en .venv...
%PY_CMD% -m venv .venv
if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual .venv.
    exit /b 1
)

:venv_ready
set "VENV_PY=.venv\Scripts\python.exe"

echo [3/4] Verificando e instalando dependencias ^(PySide6, matplotlib, etc.^)...
"%VENV_PY%" -c "import PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets, openpyxl, matplotlib, matplotlib.backends.backend_qtagg, docx, lxml, PIL" >nul 2>&1
if not errorlevel 1 (
    echo       Dependencias previas detectadas en .venv ^(PySide6, matplotlib, etc.^). Omitiendo descarga.
    goto :verify_modules
)

echo       Actualizando pip, setuptools y wheel...
"%VENV_PY%" -m pip install %PIP_OPTS% --upgrade pip setuptools wheel >nul 2>&1

echo       Instalando dependencias desde requirements.txt...
"%VENV_PY%" -m pip install %PIP_OPTS% -r requirements.txt
if errorlevel 1 (
    echo [AVISO] Fallo la instalacion estandar de requirements.txt. Intentando instalacion dedicada de PySide6...
    goto :fix_pyside6
)

"%VENV_PY%" -c "import PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets" >nul 2>&1
if not errorlevel 1 goto :verify_modules

echo [AVISO] PySide6 no quedo operativo tras requirements.txt. Reinstalando PySide6...

:fix_pyside6
"%VENV_PY%" -m pip install --no-cache-dir --force-reinstall %PIP_OPTS% pyside6
if errorlevel 1 (
    echo [ERROR] No se pudo descargar o instalar PySide6. Verifica tu conexion a internet.
    exit /b 1
)
"%VENV_PY%" -m pip install %PIP_OPTS% -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias restantes en requirements.txt.
    exit /b 1
)

:verify_modules
echo [4/4] Verificando modulos del entorno...
"%VENV_PY%" -c "import PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets, openpyxl, matplotlib, matplotlib.backends.backend_qtagg, docx, lxml, PIL; print('Dependencias verificadas correctamente.')"
if errorlevel 1 (
    echo [ERROR] Faltan modulos requeridos ^(verifica PySide6 o dependencias^).
    exit /b 1
)

if /I "%~1"=="--run" goto :run_app
if /I "%~1"=="--test" goto :run_tests

echo.
echo [OK] Ambiente listo para ejecutar el programa.
echo      - Ejecutar GUI:      .venv\Scripts\python.exe main.py
echo      - Todo en 1 paso:    setup.bat --run
echo      - Ejecutar pruebas:  setup.bat --test
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

:: --------------------------------------------------------
:: Subrutina: buscar Python >= 3.11 en PATH y rutas comunes
:: --------------------------------------------------------
:find_python
set "PY_CMD="
set "PY_VER="

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=py -3"
        for /f "delims=" %%V in ('py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"') do set "PY_VER=%%V"
        exit /b 0
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=python"
        for /f "delims=" %%V in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"') do set "PY_VER=%%V"
        exit /b 0
    )
)

for %%P in (
    "%LocalAppData%\Programs\Python\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python312\python.exe"
    "%LocalAppData%\Programs\Python\Python311\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
) do (
    if exist %%P (
        %%P -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 (
            set "PY_CMD=%%P"
            for /f "delims=" %%V in ('%%P -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"') do set "PY_VER=%%V"
            exit /b 0
        )
    )
)
exit /b 1

:: --------------------------------------------------------
:: Subrutina: descargar e instalar Python 3.12 en Windows
:: --------------------------------------------------------
:install_python
where winget >nul 2>&1
if not errorlevel 1 (
    echo       Instalando Python 3.12 mediante winget...
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --silent
    if not errorlevel 1 exit /b 0
    echo       winget no pudo completar la instalacion. Usando instalador oficial...
)

set "PY_INSTALLER=%TEMP%\python-3.12.8-amd64.exe"
set "PY_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
echo       Descargando %PY_URL%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%'"
if errorlevel 1 exit /b 1
if not exist "%PY_INSTALLER%" exit /b 1

echo       Ejecutando instalador silencioso de Python 3.12...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
set "INST_ERR=%ERRORLEVEL%"
del /q "%PY_INSTALLER%" >nul 2>&1
exit /b %INST_ERR%
