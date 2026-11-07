"""Rutas del proyecto y ajustes persistentes del usuario."""

import json
from pathlib import Path

NOMBRE_APP = "Utilidades"
VERSION = "1.0.0"

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_ASSETS = RAIZ / "assets"
CARPETA_QR = RAIZ / "generados"
CARPETA_DESCARGAS = RAIZ / "descargas"
CARPETA_AUDIOS = RAIZ / "generados" / "voz"
CARPETA_VOCES = RAIZ / "voces"
ARCHIVO_AJUSTES = RAIZ / "ajustes.json"

_POR_DEFECTO = {
    "tema": "dark",
    "herramienta": "qr",
    "qr_personalizar": False,
    "qr_color": "#000000",
    "qr_fondo": "#ffffff",
    "qr_transparente": False,
    "yt_formato": "MP3",
    "yt_calidad_mp3": "320 kbps",
    "yt_calidad_mp4": "Máxima",
    "sp_calidad": "320 kbps",
    "voz_voz": "Predeterminada",
    "voz_idioma": "Español",
    "voz_expresividad": 0.5,
    "voz_formato": "MP3",
}


class Ajustes:
    """Diccionario pequeño que se guarda solo en ajustes.json."""

    def __init__(self):
        self._datos = dict(_POR_DEFECTO)
        try:
            self._datos.update(json.loads(ARCHIVO_AJUSTES.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def __getitem__(self, clave):
        return self._datos.get(clave, _POR_DEFECTO.get(clave))

    def __setitem__(self, clave, valor):
        if self._datos.get(clave) == valor:
            return
        self._datos[clave] = valor
        try:
            ARCHIVO_AJUSTES.write_text(
                json.dumps(self._datos, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass


def asegurar_carpeta(carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta
