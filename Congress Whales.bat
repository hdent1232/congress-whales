@echo off
rem Launch the Congress Whales dashboard in a native window (no console).
rem Requires Python on PATH. For a no-setup option, use dist\CongressWhales.exe instead.
start "" pythonw "%~dp0desktop_app.py"
