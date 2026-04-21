@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

:: ── entry point ──────────────────────────────────────────────────────────────

if /i "%1"=="--setup" goto :setup
if /i "%1"=="/setup"  goto :setup
goto :launch

:: ── setup ────────────────────────────────────────────────────────────────────

:setup
echo.
echo ==========================================
echo   Pearl's File Tools -- First-Time Setup
echo ==========================================
echo.

:: Locate Python 3
set PYTHON=
for %%c in (python3 python) do (
    if "!PYTHON!"=="" (
        where %%c >nul 2>&1 && (
            for /f "delims=" %%v in ('%%c -c "import sys; print(sys.version_info.major)" 2^>nul') do (
                if "%%v"=="3" set PYTHON=%%c
            )
        )
    )
)

if "!PYTHON!"=="" (
    echo ERROR: Python 3 not found.
    echo.
    echo Download and install it from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('!PYTHON! --version 2^>^&1') do echo Using %%v
echo.

:: Create virtual environment
if exist ".venv\Scripts\python.exe" (
    echo Virtual environment already exists -- skipping creation.
) else (
    echo Creating virtual environment in .venv\ ...
    !PYTHON! -m venv .venv
    echo   Done.
)
echo.

:: Upgrade pip
.venv\Scripts\pip install --quiet --upgrade pip

:: Required dependency
echo Installing required dependency...
.venv\Scripts\pip install --quiet --upgrade "PyQt5>=5.15.0"
echo   [OK] PyQt5
echo.

:: Optional dependencies
echo Optional dependencies -- type Y and press Enter to install, or just press Enter to skip:
echo.

set /p ans="  RAR archive support (rarfile)? [y/N] "
if /i "!ans!"=="y" (
    .venv\Scripts\pip install --quiet rarfile && echo     [OK] rarfile || echo     [FAIL] rarfile
)

set /p ans="  7Z archive support (py7zr)? [y/N] "
if /i "!ans!"=="y" (
    .venv\Scripts\pip install --quiet py7zr && echo     [OK] py7zr || echo     [FAIL] py7zr
)

set /p ans="  Media metadata -- codec/fps/duration (pymediainfo)? [y/N] "
if /i "!ans!"=="y" (
    .venv\Scripts\pip install --quiet pymediainfo && echo     [OK] pymediainfo || echo     [FAIL] pymediainfo
)

set /p ans="  Watch folder automation (watchdog)? [y/N] "
if /i "!ans!"=="y" (
    .venv\Scripts\pip install --quiet watchdog && echo     [OK] watchdog || echo     [FAIL] watchdog
)

echo.

:: Check ffprobe
where ffprobe >nul 2>&1 && (
    echo   [OK] ffprobe detected -- video thumbnail and metadata features available.
) || (
    echo   [INFO] ffprobe not found ^(optional^).
    echo          Download ffmpeg from https://ffmpeg.org/download.html
    echo          and add its bin\ folder to your system PATH.
)

echo.
echo ==========================================
echo         Setup complete! Launching...
echo ==========================================
echo.

:: Fall through to launch

:: ── launch ───────────────────────────────────────────────────────────────────

:launch

:: Prefer venv Python
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    set PYTHON=
    for %%c in (python3 python) do (
        if "!PYTHON!"=="" (
            where %%c >nul 2>&1 && set PYTHON=%%c
        )
    )
)

if "!PYTHON!"=="" (
    echo ERROR: Python 3 not found.
    echo Run setup first:  run.bat --setup
    pause
    exit /b 1
)

!PYTHON! -c "import PyQt5" >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyQt5 is not installed.
    echo.
    echo Run setup to install everything automatically:
    echo   run.bat --setup
    echo.
    pause
    exit /b 1
)

!PYTHON! main.py
