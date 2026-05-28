@echo off
REM Post-install: pip-install the bundled meshforge wheel, then create Start Menu shortcut.
REM %PREFIX% is set by the NSIS installer to the chosen install directory.

set LOGFILE=%PREFIX%\meshforge_install.log
echo [post_install] PREFIX=%PREFIX% > "%LOGFILE%"

REM Install meshforge from the bundled wheel (offline, no internet required)
"%PREFIX%\python.exe" -m pip install --no-index --no-deps "%PREFIX%\share\meshforge\meshforge-0.2.0-py3-none-any.whl" >> "%LOGFILE%" 2>&1
echo [post_install] pip exit code: %ERRORLEVEL% >> "%LOGFILE%"

REM Create Start Menu shortcut (use full path to powershell.exe — PATH is minimal in NSIS context)
set PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
set SHORTCUT_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\MeshForge
set MESHFORGE_EXE=%PREFIX%\Scripts\meshforge.exe
set SHORTCUT=%SHORTCUT_DIR%\MeshForge.lnk

if not exist "%SHORTCUT_DIR%" mkdir "%SHORTCUT_DIR%"

"%PS%" -NoProfile -NonInteractive -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.TargetPath='%MESHFORGE_EXE%'; $s.WorkingDirectory='%PREFIX%'; $s.Description='MeshForge - STEP to FEA meshing'; $s.Save()" >> "%LOGFILE%" 2>&1
echo [post_install] shortcut exit code: %ERRORLEVEL% >> "%LOGFILE%"

echo [post_install] done >> "%LOGFILE%"
