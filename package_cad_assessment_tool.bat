@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ZIP=cad_assessment_tool.zip"

echo Packaging CAD Assessment Tool...
echo.

if exist "venv\Scripts\python.exe" (
    set "PY=venv\Scripts\python.exe"
) else (
    set "PY=python"
)

if not exist "main.spec" (
    echo ERROR: main.spec not found in %CD%
    exit /b 1
)

echo Building fresh main.exe with PyInstaller...
"%PY%" -m PyInstaller --noconfirm --clean main.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    echo Install PyInstaller in your environment: pip install pyinstaller
    exit /b 1
)

if not exist "main.exe" (
    echo ERROR: main.exe not found in project root after build.
    echo Your build.spec should output main.exe here, not only under dist\.
    exit /b 1
)
echo Built: %CD%\main.exe
echo.

call :require main.exe || exit /b 1
call :require kill.bat || exit /b 1
call :require purge_cache.ps1 || exit /b 1
call :require model_checks.xml || exit /b 1
call :require report_template.html.j2 || exit /b 1
call :require version || exit /b 1
call :require CHANGELOG.md || exit /b 1
call :require README.md || exit /b 1
call :require_dir config || exit /b 1
call :require_dir models || exit /b 1

if exist "%ZIP%" (
    echo Removing existing %ZIP%...
    del /f "%ZIP%"
    if exist "%ZIP%" (
        echo ERROR: Could not delete %ZIP%
        exit /b 1
    )
)

echo Creating %ZIP%...
tar -a -cf "%ZIP%" main.exe kill.bat purge_cache.ps1 model_checks.xml report_template.html.j2 version CHANGELOG.md README.md config models
if errorlevel 1 (
    echo ERROR: Failed to create zip.
    exit /b 1
)

echo.
echo Done: %CD%\%ZIP%
exit /b 0

:require
if not exist "%~1" (
    echo ERROR: Missing file: %~1
    exit /b 1
)
exit /b 0

:require_dir
if not exist "%~1\" (
    echo ERROR: Missing folder: %~1\
    exit /b 1
)
exit /b 0
