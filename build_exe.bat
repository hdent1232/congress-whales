@echo off
rem Rebuild the shareable CongressWhales.exe after code changes. Requires Python on PATH.
cd /d "%~dp0"
python -m PyInstaller ^
  --onefile --windowed --name CongressWhales --icon appicon.ico ^
  --add-data "dashboard.html;." --add-data "appicon.ico;." ^
  --collect-all webview --noconfirm desktop_app.py
echo.
echo Built dist\CongressWhales.exe
pause
