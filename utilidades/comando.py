"""Instala el comando `utilidades` para poder usarlo desde cualquier terminal.

Crea dos lanzadores diminutos en ~/.local/bin (uno .cmd para CMD/PowerShell y
otro sin extensión para Git Bash / WSL / macOS / Linux) que llaman al Python del
entorno de la app. Si esa carpeta no está en el PATH, la añade al PATH del
usuario.
"""

import os
import sys
from pathlib import Path

from .config import RAIZ

CARPETA_BIN = Path.home() / ".local" / "bin"
ENTRADA = RAIZ / "cli.py"


def _python() -> Path:
    """Python del entorno de la app (no pythonw: la consola necesita su salida)."""
    actual = Path(sys.executable)
    if actual.name.lower() == "pythonw.exe":
        actual = actual.with_name("python.exe")
    return actual


def _en_path(carpeta: Path) -> bool:
    partes = os.environ.get("PATH", "").split(os.pathsep)
    return any(Path(p).resolve() == carpeta.resolve() for p in partes if p)


def _anadir_al_path_usuario(carpeta: Path) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as clave:
        try:
            actual, tipo = winreg.QueryValueEx(clave, "Path")
        except FileNotFoundError:
            actual, tipo = "", winreg.REG_EXPAND_SZ
        partes = [p for p in actual.split(";") if p]
        if any(Path(os.path.expandvars(p)).resolve() == carpeta.resolve() for p in partes):
            return False
        winreg.SetValueEx(clave, "Path", 0, tipo, ";".join(partes + [str(carpeta)]))
    # Avisar a Windows para que las terminales nuevas vean el cambio.
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 2, 5000, None)
    return True


def instalar_comando() -> list[Path]:
    CARPETA_BIN.mkdir(parents=True, exist_ok=True)
    python = _python()
    creados = []

    if sys.platform == "win32":
        cmd = CARPETA_BIN / "utilidades.cmd"
        cmd.write_text(f'@echo off\r\n"{python}" "{ENTRADA}" %*\r\n', encoding="utf-8")
        creados.append(cmd)

    sh = CARPETA_BIN / "utilidades"
    py_sh, entrada_sh = python.as_posix(), ENTRADA.as_posix()
    sh.write_text(f'#!/bin/sh\nexec "{py_sh}" "{entrada_sh}" "$@"\n', encoding="utf-8",
                  newline="\n")
    try:
        sh.chmod(0o755)
    except OSError:
        pass
    creados.append(sh)

    if not _en_path(CARPETA_BIN) and _anadir_al_path_usuario(CARPETA_BIN):
        print(f"Añadido {CARPETA_BIN} al PATH del usuario.", file=sys.stderr)
    return creados


def instalar_skill() -> Path:
    """Copia la skill de Claude Code a ~/.claude/skills/utilidades (válida en todos los proyectos)."""
    import shutil

    origen = RAIZ / "skill" / "SKILL.md"
    destino = Path.home() / ".claude" / "skills" / "utilidades" / "SKILL.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino)
    return destino
