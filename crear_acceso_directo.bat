@echo off
rem Crea un acceso directo "Utilidades" en el escritorio con su icono.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d = [Environment]::GetFolderPath('Desktop');" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Utilidades.lnk'));" ^
  "$s.TargetPath = '%~dp0iniciar.bat';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = '%~dp0assets\icono.ico';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Utilidades: QR, YouTube y mas';" ^
  "$s.Save()"
if errorlevel 1 (
    echo No se pudo crear el acceso directo.
) else (
    echo Acceso directo creado en el escritorio.
)
pause
