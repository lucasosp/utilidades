"""Lógica de descarga (sin interfaz) basada en yt-dlp.

Se ejecuta en un hilo aparte y comunica lo que pasa a la interfaz mediante una
cola de eventos ``(tipo, datos)``.
"""

import gc
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CALIDADES_MP3 = {"320 kbps": "320", "192 kbps": "192", "128 kbps": "128"}
CALIDADES_MP4 = {"Máxima": None, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360}


# --------------------------------------------------------------------------- #
# Análisis del enlace
# --------------------------------------------------------------------------- #
@dataclass
class TipoEnlace:
    valido: bool = False
    video: str | None = None      # id del vídeo, si lo hay
    lista: str | None = None      # id de la lista, si la hay

    @property
    def es_mix(self) -> bool:
        """Los «Mix» de YouTube (RD…) son listas automáticas casi infinitas."""
        return bool(self.lista and self.lista.startswith("RD"))


def analizar_enlace(url: str) -> TipoEnlace:
    url = url.strip()
    if not url:
        return TipoEnlace()
    if "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    if not p.netloc or "." not in p.netloc:
        return TipoEnlace()
    q = parse_qs(p.query)
    video = (q.get("v") or [None])[0]
    host = p.netloc.lower()
    if host.endswith("youtu.be"):
        video = p.path.strip("/").split("/")[0] or None
    elif "/shorts/" in p.path or "/live/" in p.path:
        video = p.path.rstrip("/").split("/")[-1]
    lista = (q.get("list") or [None])[0]
    return TipoEnlace(True, video, lista)


# --------------------------------------------------------------------------- #
# Dependencias externas
# --------------------------------------------------------------------------- #
def ruta_ffmpeg() -> str | None:
    """ffmpeg del sistema si existe; si no, el que trae el paquete imageio-ffmpeg."""
    if shutil.which("ffmpeg"):
        return None  # yt-dlp lo encuentra solo
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


# --------------------------------------------------------------------------- #
# Descarga
# --------------------------------------------------------------------------- #
@dataclass
class Peticion:
    url: str
    formato: str          # "MP3" | "MP4"
    calidad: str          # clave de CALIDADES_MP3 / CALIDADES_MP4
    lista_completa: bool  # si el enlace trae lista: bajarla entera o solo el vídeo
    carpeta: Path


class Cancelado(Exception):
    pass


class _Registro:
    """Logger para yt-dlp: reenvía avisos y errores a la cola."""

    def __init__(self, emitir):
        self._emitir = emitir

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        msg = str(msg).removeprefix("ERROR: ")
        self._emitir("error", msg)


class Descargador(threading.Thread):
    def __init__(self, peticion: Peticion):
        super().__init__(daemon=True)
        self.peticion = peticion
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

    # Internos -------------------------------------------------------------
    def _emitir(self, tipo, datos=None):
        if tipo == "error":
            self.errores += 1
        self.eventos.put((tipo, datos))

    def _comprobar(self, *_args, **_kw):
        if self._cancelar.is_set():
            import yt_dlp
            raise yt_dlp.utils.DownloadCancelled("Cancelado por el usuario")
        return None  # match_filter: None = aceptar

    def _gancho_progreso(self, d):
        self._comprobar()
        info = d.get("info_dict") or {}
        posicion = (info.get("playlist_index"), info.get("n_entries") or info.get("playlist_count"))
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            hecho = d.get("downloaded_bytes") or 0
            self._emitir("progreso", {
                "titulo": info.get("title") or "",
                "posicion": posicion,
                "fraccion": (hecho / total) if total else None,
                "velocidad": d.get("speed"),
                "eta": d.get("eta"),
                "pista": "audio" if info.get("vcodec") == "none" and
                         self.peticion.formato == "MP4" else None,
            })
        elif d["status"] == "finished":
            self._emitir("procesando", {"titulo": info.get("title") or "", "posicion": posicion})

    def _gancho_postproceso(self, d):
        if d["status"] == "started" and d.get("postprocessor") in (
                "ExtractAudio", "Merger", "EmbedThumbnail"):
            nombres = {"ExtractAudio": "Convirtiendo a MP3…", "Merger": "Uniendo audio y vídeo…",
                       "EmbedThumbnail": "Añadiendo portada…"}
            self._emitir("estado", nombres[d["postprocessor"]])

    def _gancho_final(self, ruta):
        self.completados += 1
        self._emitir("completado", Path(ruta))

    def _opciones(self) -> dict:
        p = self.peticion
        if p.lista_completa:
            plantilla = ("%(playlist_title|Lista)s/"
                         "%(playlist_index&{:03d} - |)s%(title)s.%(ext)s")
        else:
            plantilla = "%(title)s.%(ext)s"

        opciones = {
            "paths": {"home": str(p.carpeta)},
            # pl_thumbnail vacío: no guardar la miniatura de la propia lista.
            "outtmpl": {"default": plantilla, "pl_thumbnail": ""},
            "noplaylist": not p.lista_completa,
            "ignoreerrors": True,          # un vídeo roto no detiene la lista
            "windowsfilenames": True,
            "trim_file_name": 180,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": _Registro(self._emitir),
            "progress_hooks": [self._gancho_progreso],
            "postprocessor_hooks": [self._gancho_postproceso],
            "post_hooks": [self._gancho_final],
            "match_filter": self._comprobar,
            # YouTube necesita un intérprete de JavaScript para algunos formatos.
            "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
            "concurrent_fragment_downloads": 4,
        }
        if ffmpeg := ruta_ffmpeg():
            opciones["ffmpeg_location"] = ffmpeg

        if p.formato == "MP3":
            opciones.update({
                "format": "bestaudio/best",
                "writethumbnail": True,
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                     "preferredquality": CALIDADES_MP3.get(p.calidad, "320")},
                    {"key": "FFmpegMetadata", "add_metadata": True},
                    {"key": "FFmpegThumbnailsConvertor", "format": "jpg",
                     "when": "before_dl"},
                    {"key": "EmbedThumbnail"},
                ],
            })
        else:
            altura = CALIDADES_MP4.get(p.calidad)
            opciones.update({
                "format": "bestvideo*+bestaudio/best",
                # Preferimos H.264 + AAC en MP4: se reproduce en cualquier sitio.
                "format_sort": [f"res:{altura}" if altura else "res", "vcodec:h264",
                                "acodec:aac", "ext:mp4:m4a"],
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegMetadata", "add_metadata": True}],
            })
        return opciones

    def _limpiar_restos(self, desde: float):
        """Tras cancelar, borra los .part y miniaturas sueltas que hayan quedado."""
        finales = {".mp3", ".mp4", ".m4a", ".webm", ".mkv"}
        for ruta in self.peticion.carpeta.rglob("*"):
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
        for carpeta in sorted(self.peticion.carpeta.rglob("*"), reverse=True):
            if carpeta.is_dir() and not any(carpeta.iterdir()):
                carpeta.rmdir()

    def run(self):
        inicio = time.time() - 1
        try:
            import yt_dlp
            self._emitir("estado", "Obteniendo información…")
            with yt_dlp.YoutubeDL(self._opciones()) as ydl:
                ydl.download([self.peticion.url])
        except Exception as e:  # noqa: BLE001 - todo error se muestra en la interfaz
            nombre = type(e).__name__
            if not (self.cancelado or nombre == "DownloadCancelled"):
                self._emitir("error", str(e).removeprefix("ERROR: "))
        finally:
            if self.cancelado:
                # Los hilos de fragmentos pueden tardar un instante en soltar los archivos.
                for _ in range(3):
                    gc.collect()  # libera manejadores de archivo que yt-dlp deja abiertos
                    time.sleep(0.5)
                    self._limpiar_restos(inicio)
            self._emitir("fin", {"completados": self.completados, "errores": self.errores,
                                 "cancelado": self.cancelado})
