"""Lógica de los códigos QR, sin interfaz (la usan la app y la consola)."""

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import qrcode
from PIL import Image

NEGRO, BLANCO = "#000000", "#ffffff"


def nombre_seguro(texto: str, maximo: int = 40) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^\w\s-]", "", texto.lower())
    texto = re.sub(r"[\s_-]+", "_", texto).strip("_")
    return texto[:maximo].rstrip("_")


def nombre_desde_contenido(contenido: str) -> str:
    contenido = contenido.strip()
    url = urlparse(contenido if "://" in contenido else "")
    if url.netloc:
        dominio = url.netloc.removeprefix("www.").split(".")[0]
        ruta = next((p for p in url.path.split("/") if p), "")
        return nombre_seguro(f"{dominio} {ruta}") or "qr"
    return nombre_seguro(contenido) or "qr"


def _luminancia(color: str) -> float:
    canales = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lineal = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineal[0] + 0.7152 * lineal[1] + 0.0722 * lineal[2]


def aviso_contraste(codigo: str, fondo: str | None) -> str | None:
    """Los lectores de QR necesitan un código oscuro sobre fondo claro y buen contraste."""
    if fondo is None:
        if _luminancia(codigo) > 0.4:
            return "Fondo transparente: ponlo sobre algo claro para que se lea bien."
        return None
    l_cod, l_fon = _luminancia(codigo), _luminancia(fondo)
    if l_cod > l_fon:
        return "El código es más claro que el fondo: muchos móviles no lo leerán."
    if (l_fon + 0.05) / (l_cod + 0.05) < 3:
        return "Poco contraste entre colores: puede costar escanearlo."
    return None


def normalizar_color(texto: str) -> str:
    """'#abc', 'abc', '#aabbcc' → '#aabbcc'. Lanza ValueError si no es válido."""
    t = texto.strip().lstrip("#")
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", t):
        raise ValueError(f"Color no válido: {texto!r} (usa formato #RRGGBB)")
    return f"#{t.lower()}"


def generar_qr(contenido: str, codigo: str = NEGRO, fondo: str | None = BLANCO,
               tam_modulo: int = 20, borde: int = 4) -> tuple[Image.Image, int]:
    """Devuelve (imagen RGBA, versión del QR). fondo=None → transparente."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=tam_modulo, border=borde)
    qr.add_data(contenido)
    qr.make(fit=True)
    imagen = qr.make_image(fill_color=codigo, back_color=fondo or "transparent").get_image()
    return imagen.convert("RGBA"), qr.version


def ruta_libre(carpeta: Path, base: str, extension: str) -> Path:
    """carpeta/base.ext, o con marca de tiempo si ya existe."""
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{base}.{extension}"
    if ruta.exists():
        ruta = carpeta / f"{base}_{datetime.now():%Y%m%d_%H%M%S}.{extension}"
    return ruta
