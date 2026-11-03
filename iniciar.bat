@echo off
setlocal
cd /d "%~dp0"
title Utilidades

set "VENV=.venv"
set "PY=%VENV%\Scripts\python.exe"
set "PYW=%VENV%\Scripts\pythonw.exe"

rem --- 1. Entorno virtual (solo la primera vez) -------------------------------
if exist "%PY%" goto dependencias
echo.
echo   Primera ejecucion: preparando todo, tardara un minuto...
echo.
where py >nul 2>&1
if %errorlevel%==0 (py -3 -m venv "%VENV%") else (python -m venv "%VENV%")
if exist "%PY%" goto dependencias
echo   No se ha encontrado Python.
echo   Instalalo desde https://www.python.org/downloads/
echo   y marca la casilla "Add python.exe to PATH".
pause
exit /b 1

rem --- 2. Dependencias (solo si requirements.txt ha cambiado) -----------------
:dependencias
fc /b requirements.txt "%VENV%\requirements.txt" >nul 2>&1
if %errorlevel%==0 goto arrancar
echo   Instalando dependencias...
"%PY%" -m pip install --disable-pip-version-check -q --upgrade pip
"%PY%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo   No se pudieron instalar las dependencias. Revisa tu conexion.
    pause
    exit /b 1
)
copy /y requirements.txt "%VENV%\requirements.txt" >nul

rem --- 3. Arrancar sin ventana de consola -------------------------------------
:arrancar
start "" "%PYW%" -m utilidades
