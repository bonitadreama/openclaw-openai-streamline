@echo off
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo Failed to install build dependencies.
  exit /b 1
)

pyinstaller --noconsole --onefile --name OpenClawSetup app.py
if errorlevel 1 (
  echo PyInstaller build failed.
  exit /b 1
)

if not exist dist\OpenClawSetup mkdir dist\OpenClawSetup
copy /Y dist\OpenClawSetup.exe dist\OpenClawSetup\OpenClawSetup.exe >nul
if not exist dist\OpenClawSetup\scripts mkdir dist\OpenClawSetup\scripts
copy /Y scripts\install_openclaw.ps1 dist\OpenClawSetup\scripts\install_openclaw.ps1 >nul

echo.
echo Build complete.
echo EXE folder: %cd%\dist\OpenClawSetup
endlocal
