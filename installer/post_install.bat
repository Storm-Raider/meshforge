@echo off
REM Post-install: pip-install the bundled meshforge wheel, then create Start Menu shortcut

REM Install meshforge from the bundled wheel (no internet required)
"%PREFIX%\python.exe" -m pip install --no-index --no-deps "%PREFIX%\share\meshforge\meshforge-0.2.0-py3-none-any.whl"

REM Create Start Menu shortcut pointing to the console_scripts entry point
set SHORTCUT_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\MeshForge
if not exist "%SHORTCUT_DIR%" mkdir "%SHORTCUT_DIR%"

set SCRIPT=%TEMP%\make_shortcut.vbs
(
  echo Set oWS = WScript.CreateObject("WScript.Shell"^)
  echo sLinkFile = "%SHORTCUT_DIR%\MeshForge.lnk"
  echo Set oLink = oWS.CreateShortcut(sLinkFile^)
  echo oLink.TargetPath = "%PREFIX%\pythonw.exe"
  echo oLink.Arguments = "-m meshforge.main"
  echo oLink.WorkingDirectory = "%PREFIX%"
  echo oLink.IconLocation = "%PREFIX%\pythonw.exe,0"
  echo oLink.Description = "MeshForge - STEP to FEA meshing"
  echo oLink.Save
) > "%SCRIPT%"
cscript //nologo "%SCRIPT%"
del "%SCRIPT%"

echo MeshForge installed successfully.
