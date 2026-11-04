"""Piezas comunes a todos los descargadores (YouTube, Spotify…).

Cada descargador es un hilo que comunica lo que pasa a la interfaz mediante una
cola de eventos ``(tipo, datos)``:

- ``estado``      texto corto ("Convirtiendo a MP3…")
- ``progreso``    dict con titulo, posicion, fraccion, velocidad, eta, pista
- ``procesando``  dict con titulo, posicion (descarga terminada, toca convertir)
- ``completado``  Path del archivo final
- ``aviso``       texto informativo para el registro
- ``error``       texto del error
- ``fin``         dict con completados, errores, cancelado
"""

import gc
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

CALIDADES_MP3 = {"320 kbps": "320", "192 kbps": "192", "128 kbps": "128"}


# --------------------------------------------------------------------------- #
# Dependencias externas
# --------------------------------------------------------------------------- #
def ruta_ffmpeg() -> str | None:
    """None si ffmpeg está en el PATH; si no, el que trae el paquete imageio-ffmpeg."""
    if shutil.which("ffmpeg"):
        return None
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffmpeg_disponible() -> bool:
    return bool(shutil.which("ffmpeg") or ruta_ffmpeg())


def actualizar_yt_dlp() -> tuple[bool, str]:
    """Actualiza yt-dlp con pip (YouTube cambia a menudo y conviene tenerlo al día)."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", "--disable-pip-version-check",
         "yt-dlp[default]"],
        capture_output=True, text=True, creationflags=flags,
    )
    salida = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, (salida[-1] if salida else "")


class _Registro:
    """Logger para yt-dlp: reenvía los errores a la cola y calla lo demás."""

    def __init__(self, emitir):
        self._emitir = emitir

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self._emitir("error", str(msg).removeprefix("ERROR: "))


# --------------------------------------------------------------------------- #
# Hilo base
# --------------------------------------------------------------------------- #
class HiloDescarga(threading.Thread):
    """Gestiona cola de eventos, cancelación y limpieza. Las subclases implementan
    ``trabajar()`` y usan ``opciones_base()`` para configurar yt-dlp."""

    def __init__(self, carpeta: Path):
        super().__init__(daemon=True)
        self.carpeta = carpeta
        self.eventos: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._cancelar = threading.Event()
        self.completados = 0
        self.errores = 0

    # API pública ----------------------------------------------------------
    def cancelar(self):
        self._cancelar.set()

    @property
    def cancelado(self) -> bool:
        return self._cancelar.is_set()

    # Para las subclases ---------------------------------------------------
    def trabajar(self):
        raise NotImplementedError

    def emitir(self, tipo, datos=None):
        if tipo == "error":
            self.errores += 1
        self.eventos.put((tipo, datos))

    def comprobar(self, *_args, **_kw):
        """Lanza DownloadCancelled si el usuario ha cancelado. Sirve de match_filter."""
        if self._cancelar.is_set():
            import yt_dlp
            raise yt_dlp.utils.DownloadCancelled("Cancelado por el usuario")
        return None

    def opciones_base(self) -> dict:
        opciones = {
            "paths": {"home": str(self.carpeta)},
            "ignoreerrors": True,
            "windowsfilenames": True,
            "trim_file_name": 180,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": _Registro(self.emitir),
            "match_filter": self.comprobar,
            # YouTube necesita un intérprete de JavaScript para algunos formatos.
            "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
            "concurrent_fragment_downloads": 4,
        }
        if ffmpeg := ruta_ffmpeg():
            opciones["ffmpeg_location"] = ffmpeg
        return opciones

    def progreso_desde_ytdlp(self, d, titulo, posicion, pista=None):
        """Traduce un evento de progress_hooks de yt-dlp a nuestros eventos."""
        self.comprobar()
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            hecho = d.get("downloaded_bytes") or 0
            self.emitir("progreso", {
                "titulo": titulo, "posicion": posicion,
                "fraccion": (hecho / total) if total else None,
                "velocidad": d.get("speed"), "eta": d.get("eta"), "pista": pista,
            })
        elif d["status"] == "finished":
            self.emitir("procesando", {"titulo": titulo, "posicion": posicion})

    # Internos -------------------------------------------------------------
    def _limpiar_restos(self, desde: float):
        """Tras cancelar, borra los .part y miniaturas sueltas que hayan quedado."""
        finales = {".mp3", ".mp4", ".m4a", ".webm", ".mkv"}
        for ruta in self.carpeta.rglob("*"):
            try:
                if not ruta.is_file() or ruta.stat().st_mtime < desde:
                    continue
                if ruta.suffix in (".part", ".ytdl") or ".part-Frag" in ruta.name:
                    ruta.unlink()
                elif ruta.suffix in (".jpg", ".webp", ".png") and not any(
                        ruta.with_suffix(ext).exists() for ext in finales):
                    ruta.unlink()
                elif ".f" in ruta.stem and ruta.suffix in finales:  # pistas sin unir
                    partes = ruta.stem.rsplit(".f", 1)
                    if len(partes) == 2 and partes[1].isdigit():
                        ruta.unlink()
            except OSError:
                pass
        for carpeta in sorted(self.carpeta.rglob("*"), reverse=True):
            try:
                if carpeta.is_dir() and not any(carpeta.iterdir()):
                    carpeta.rmdir()
            except OSError:
                pass

    def run(self):
        inicio = time.time() - 1
        try:
            self.trabajar()
        except Exception as e:  # noqa: BLE001 - todo error se muestra en la interfaz
            if not (self.cancelado or type(e).__name__ == "DownloadCancelled"):
                self.emitir("error", str(e).removeprefix("ERROR: "))
        finally:
            if self.cancelado:
                # Los hilos de fragmentos pueden tardar un instante en soltar los archivos.
                for _ in range(3):
                    gc.collect()  # libera manejadores de archivo que yt-dlp deja abiertos
                    time.sleep(0.5)
                    self._limpiar_restos(inicio)
            self.emitir("fin", {"completados": self.completados, "errores": self.errores,
                                "cancelado": self.cancelado})
