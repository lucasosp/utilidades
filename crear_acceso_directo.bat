@echo off
rem Crea accesos directos "Utilidades" en el escritorio y en el menu Inicio.
rem Desde cualquiera de los dos se puede anclar la app a la barra de tareas.
cd /d "%~dp0"
call "%~dp0iniciar.bat" --acceso-directo
if errorlevel 1 (
    echo.
    echo   No se pudieron crear los accesos directos.
) else (
    echo.
    echo   Listo. Tambien puedes buscar "Utilidades" en el menu Inicio.
)
pause
