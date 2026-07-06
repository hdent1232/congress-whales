# Creates a "Congress Whales" shortcut on your Desktop with the whale icon.
# Requires Python on PATH (uses pythonw). No-setup alternative: dist\CongressWhales.exe.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py   = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $py) { Write-Host "pythonw not found on PATH. Install Python or use dist\CongressWhales.exe."; exit 1 }
$ws   = New-Object -ComObject WScript.Shell
$lnk  = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Congress Whales.lnk'))
$lnk.TargetPath       = $py
$lnk.Arguments        = '"' + (Join-Path $here 'desktop_app.py') + '"'
$lnk.WorkingDirectory = $here
$lnk.IconLocation     = (Join-Path $here 'appicon.ico')
$lnk.Description       = 'Congress Whales - live congressional trades + hedge-fund overlap'
$lnk.Save()
Write-Host "Created Desktop shortcut: Congress Whales"
