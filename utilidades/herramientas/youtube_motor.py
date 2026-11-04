"""Lógica de descarga de YouTube (sin interfaz) basada en yt-dlp."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .descarga_base import CALIDADES_MP3, HiloDescarga

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
# Descarga
# --------------------------------------------------------------------------- #
@dataclass
class Peticion:
    url: str
    formato: str          # "MP3" | "MP4"
    calidad: str          # clave de CALIDADES_MP3 / CALIDADES_MP4
    lista_completa: bool  # si el enlace trae lista: bajarla entera o solo el vídeo
    carpeta: Path


class Descargador(HiloDescarga):
    def __init__(self, peticion: Peticion):
        super().__init__(peticion.carpeta)
        self.peticion = peticion

    def _gancho_progreso(self, d):
        info = d.get("info_dict") or {}
        posicion = (info.get("playlist_index"), info.get("n_entries") or info.get("playlist_count"))
        pista = "audio" if info.get("vcodec") == "none" and self.peticion.formato == "MP4" else None
        self.progreso_desde_ytdlp(d, info.get("title") or "", posicion, pista)

    def _gancho_postproceso(self, d):
        nombres = {"ExtractAudio": "Convirtiendo a MP3…", "Merger": "Uniendo audio y vídeo…",
                   "EmbedThumbnail": "Añadiendo portada…"}
        if d["status"] == "started" and d.get("postprocessor") in nombres:
            self.emitir("estado", nombres[d["postprocessor"]])

    def _gancho_final(self, ruta):
        self.completados += 1
        self.emitir("completado", Path(ruta))

    def _opciones(self) -> dict:
        p = self.peticion
        if p.lista_completa:
            plantilla = ("%(playlist_title|Lista)s/"
                         "%(playlist_index&{:03d} - |)s%(title)s.%(ext)s")
        else:
            plantilla = "%(title)s.%(ext)s"

        opciones = self.opciones_base()
        opciones.update({
            # pl_thumbnail vacío: no guardar la miniatura de la propia lista.
            "outtmpl": {"default": plantilla, "pl_thumbnail": ""},
            "noplaylist": not p.lista_completa,
            "progress_hooks": [self._gancho_progreso],
            "postprocessor_hooks": [self._gancho_postproceso],
            "post_hooks": [self._gancho_final],
        })

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

    def trabajar(self):
        import yt_dlp
        self.emitir("estado", "Obteniendo información…")
        with yt_dlp.YoutubeDL(self._opciones()) as ydl:
            ydl.download([self.peticion.url])
