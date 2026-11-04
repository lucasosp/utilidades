"""Integración con Windows: barra de tareas y accesos directos.

Al anclar una ventana a la barra de tareas, Windows guarda por defecto el
ejecutable que la creó (``pythonw.exe``), sin argumentos: por eso salía el
icono de Python y al pulsarlo no se abría nada. Para evitarlo se le dice a
Windows, mediante las propiedades «AppUserModel», qué identificador tiene la
app, con qué comando relanzarla y qué icono usar.
"""

import ctypes
import subprocess
import sys
import uuid
from ctypes import POINTER, byref, c_ubyte, c_ulong, c_ushort, c_void_p, c_wchar_p
from pathlib import Path

from .config import CARPETA_ASSETS, NOMBRE_APP, RAIZ

ID_APP = "Utilidades.CajaDeHerramientas"
LANZADOR = RAIZ / "Utilidades.pyw"
ICONO = CARPETA_ASSETS / "icono.ico"

_FMTID_APPUSERMODEL = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
_PID_RELAUNCH_COMMAND = 2
_PID_RELAUNCH_ICON = 3
_PID_RELAUNCH_NAME = 4
_PID_ID = 5
_IID_IPROPERTYSTORE = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"
_VT_LPWSTR = 31
_GPS_READWRITE = 2


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort),
                ("Data4", c_ubyte * 8)]

    @classmethod
    def de_texto(cls, texto):
        return cls.from_buffer_copy(uuid.UUID(texto).bytes_le)


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", c_ulong)]


class _PROPVARIANT(ctypes.Structure):
    # Solo usamos cadenas (VT_LPWSTR); el relleno da el tamaño real de PROPVARIANT.
    _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort),
                ("valor", c_wchar_p), ("relleno", c_void_p)]


def es_windows() -> bool:
    return sys.platform == "win32"


def _metodo(objeto, indice, *argtypes):
    """Devuelve el método `indice` de la vtable de un objeto COM."""
    vtable = ctypes.cast(objeto, POINTER(POINTER(c_void_p))).contents
    prototipo = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
    return lambda *args: prototipo(vtable[indice])(objeto, *args)


def _escribir_propiedades(almacen: c_void_p, valores: dict[int, str]):
    set_value = _metodo(almacen, 6, POINTER(_PROPERTYKEY), POINTER(_PROPVARIANT))
    commit = _metodo(almacen, 7)
    release = _metodo(almacen, 2)
    try:
        fmtid = _GUID.de_texto(_FMTID_APPUSERMODEL)
        for pid, texto in valores.items():
            clave = _PROPERTYKEY(fmtid, pid)
            valor = _PROPVARIANT(vt=_VT_LPWSTR, valor=texto)
            set_value(byref(clave), byref(valor))
        commit()
    finally:
        release()


def comando_relanzar() -> str:
    """pythonw.exe (del entorno virtual si existe) + Utilidades.pyw."""
    ejecutable = Path(sys.executable)
    pythonw = ejecutable.with_name("pythonw.exe")
    if pythonw.exists():
        ejecutable = pythonw
    return f'"{ejecutable}" "{LANZADOR}"'


def preparar_proceso():
    """Llamar antes de crear la ventana: agrupa la app bajo su propio icono."""
    if not es_windows():
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ID_APP)
    except Exception:
        pass


def preparar_ventana(hwnd: int):
    """Hace que al anclar la ventana se guarde el comando y el icono correctos."""
    if not es_windows():
        return
    try:
        almacen = c_void_p()
        iid = _GUID.de_texto(_IID_IPROPERTYSTORE)
        if ctypes.windll.shell32.SHGetPropertyStoreForWindow(hwnd, byref(iid), byref(almacen)):
            return
        _escribir_propiedades(almacen, {
            _PID_ID: ID_APP,
            _PID_RELAUNCH_COMMAND: comando_relanzar(),
            _PID_RELAUNCH_NAME: NOMBRE_APP,
            _PID_RELAUNCH_ICON: f"{ICONO},0",
        })
    except Exception:
        pass  # si falla, la app funciona igual; solo se pierde el anclado bonito


def _poner_id_en_acceso(ruta: Path):
    """Asigna el AppUserModelID a un .lnk para que agrupe con la ventana abierta."""
    ctypes.windll.ole32.CoInitialize(None)
    almacen = c_void_p()
    iid = _GUID.de_texto(_IID_IPROPERTYSTORE)
    hr = ctypes.windll.shell32.SHGetPropertyStoreFromParsingName(
        c_wchar_p(str(ruta)), None, _GPS_READWRITE, byref(iid), byref(almacen))
    if hr:
        raise OSError(f"No se pudo abrir {ruta.name} (0x{hr & 0xFFFFFFFF:08X})")
    _escribir_propiedades(almacen, {_PID_ID: ID_APP})


def crear_accesos_directos() -> list[Path]:
    """Crea accesos directos en el escritorio y en el menú Inicio."""
    import os

    destinos = [
        Path(os.environ["USERPROFILE"]) / "Desktop",
        Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    # El escritorio puede estar redirigido (OneDrive): se pregunta a Windows.
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if r.returncode == 0 and r.stdout.strip():
        destinos[0] = Path(r.stdout.strip())

    ejecutable, argumentos = comando_relanzar().split('" "', 1)
    creados = []
    for carpeta in destinos:
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"{NOMBRE_APP}.lnk"
        script = (
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:UT_LNK);"
            "$s.TargetPath = $env:UT_EXE; $s.Arguments = $env:UT_ARGS;"
            "$s.WorkingDirectory = $env:UT_DIR; $s.IconLocation = $env:UT_ICO;"
            "$s.Description = 'QR, YouTube, Spotify y más'; $s.Save()"
        )
        entorno = dict(os.environ, UT_LNK=str(ruta), UT_EXE=ejecutable.strip('"'),
                       UT_ARGS=f'"{argumentos.strip(chr(34))}"', UT_DIR=str(RAIZ),
                       UT_ICO=f"{ICONO},0")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], env=entorno,
                       check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        _poner_id_en_acceso(ruta)
        creados.append(ruta)
    return creados
