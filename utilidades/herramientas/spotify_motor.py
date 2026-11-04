"""Descarga de canciones, álbumes y listas de Spotify.

El audio de Spotify está cifrado (DRM), así que no se puede bajar directamente.
Lo que se hace es lo mismo que herramientas como spotDL:

1. Se leen los datos públicos (título, artistas, duración, portada) de la
   página «embed» de Spotify; no hace falta cuenta ni claves de API.
2. Se busca cada canción en YouTube y se elige el resultado cuya duración
   coincide con la de Spotify.
3. Se descarga en MP3 y se etiqueta con los datos y la portada de Spotify.
"""

import http.client
import json
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .descarga_base import CALIDADES_MP3, HiloDescarga

_AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
_PATRON = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[\w-]+/)?(?:embed/)?|spotify:)"
    r"(track|album|playlist)[/:]([A-Za-z0-9]{22})"
)
# Palabras que, si aparecen en YouTube pero no en Spotify, indican otra versión.
_VERSIONES = ("live", "en vivo", "directo", "cover", "karaoke", "instrumental", "remix",
              "8d", "slowed", "sped up", "nightcore", "reverb", "acoustic", "acústico",
              "1 hour", "1 hora", "tutorial", "reaction")


@dataclass
class Cancion:
    titulo: str
    artistas: list[str]
    duracion: float | None = None     # segundos
    id: str | None = None
    album: str | None = None
    portada: str | None = None        # URL
    numero: int | None = None
    anio: str | None = None

    @property
    def nombre(self) -> str:
        return f"{', '.join(self.artistas)} - {self.titulo}" if self.artistas else self.titulo


@dataclass
class Coleccion:
    tipo: str                          # track | album | playlist
    nombre: str
    canciones: list[Cancion] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Lectura de Spotify
# --------------------------------------------------------------------------- #
def analizar_enlace(texto: str) -> tuple[str, str] | None:
    m = _PATRON.search(texto.strip())
    return (m.group(1), m.group(2)) if m else None


LIMITE_LISTA = 100  # la página pública de Spotify no enseña más canciones que estas


def _descargar(url: str, timeout=20, intentos=3) -> bytes:
    peticion = urllib.request.Request(url, headers={"User-Agent": _AGENTE})
    for intento in range(intentos):
        try:
            with urllib.request.urlopen(peticion, timeout=timeout) as r:
                return r.read()
        except (OSError, http.client.HTTPException):
            if intento == intentos - 1:
                raise
            time.sleep(1 + intento)


def _entidad(tipo: str, id_: str) -> dict:
    html = _descargar(f"https://open.spotify.com/embed/{tipo}/{id_}").decode("utf-8")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("Spotify no ha devuelto los datos esperados.")
    try:
        return json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (KeyError, TypeError):
        raise RuntimeError("No se ha encontrado nada en ese enlace (¿es privado?).") from None


def _mejor_imagen(entidad: dict) -> str | None:
    imagenes = ((entidad.get("visualIdentity") or {}).get("image") or []) + \
               ((entidad.get("coverArt") or {}).get("sources") or [])
    if not imagenes:
        return None
    return max(imagenes, key=lambda i: i.get("maxWidth") or i.get("width") or 0)["url"]


def _anio(entidad: dict) -> str | None:
    fecha = entidad.get("releaseDate")
    if isinstance(fecha, dict):
        fecha = fecha.get("isoString")
    return str(fecha)[:4] if fecha else None


def _artistas(texto: str) -> list[str]:
    return [a.strip() for a in texto.replace("\xa0", " ").split(",") if a.strip()]


def obtener(url: str) -> Coleccion:
    tipo_id = analizar_enlace(url)
    if not tipo_id:
        raise ValueError("No es un enlace de Spotify válido.")
    tipo, id_ = tipo_id
    e = _entidad(tipo, id_)
    nombre = e.get("name") or e.get("title") or "Spotify"

    if tipo == "track":
        cancion = Cancion(
            titulo=nombre, artistas=[a["name"] for a in e.get("artists") or []],
            duracion=(e.get("duration") or 0) / 1000 or None, id=id_,
            portada=_mejor_imagen(e), anio=_anio(e),
        )
        return Coleccion(tipo, cancion.nombre, [cancion])

    es_album = tipo == "album"
    portada = _mejor_imagen(e) if es_album else None
    canciones = []
    for i, t in enumerate(e.get("trackList") or [], start=1):
        canciones.append(Cancion(
            titulo=t.get("title") or "", artistas=_artistas(t.get("subtitle") or ""),
            duracion=(t.get("duration") or 0) / 1000 or None,
            id=(t.get("uri") or "").rsplit(":", 1)[-1] or None,
            album=nombre if es_album else None, portada=portada, numero=i,
            anio=_anio(e) if es_album else None,
        ))
    return Coleccion(tipo, nombre, canciones)


def completar_datos(cancion: Cancion):
    """En las listas, la portada y el año de cada canción se piden aparte."""
    if cancion.portada or not cancion.id:
        return
    try:
        e = _entidad("track", cancion.id)
        cancion.portada = _mejor_imagen(e)
        cancion.anio = cancion.anio or _anio(e)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Búsqueda en YouTube
# --------------------------------------------------------------------------- #
def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", texto.lower())).strip()


def _puntuar(cancion: Cancion, resultado: dict) -> float:
    """Menos es mejor. Combina diferencia de duración y pistas del título."""
    titulo_yt = _normalizar(resultado.get("title") or "")
    canal = (resultado.get("channel") or resultado.get("uploader") or "").lower()
    titulo_sp = _normalizar(cancion.titulo)

    duracion = resultado.get("duration")
    puntos = abs(duracion - cancion.duracion) if duracion and cancion.duracion else 20
    if puntos > 15:
        puntos += 60  # casi seguro que es otra versión
    palabras = [p for p in titulo_sp.split() if len(p) > 1]
    if palabras:
        faltan = sum(p not in titulo_yt for p in palabras) / len(palabras)
        puntos += 40 * faltan
    for v in _VERSIONES:
        if v in titulo_yt and v not in titulo_sp:
            puntos += 30
    if canal.endswith(" - topic"):
        puntos -= 8   # «Artista - Topic» = audio oficial subido por la discográfica
    if cancion.artistas and _normalizar(cancion.artistas[0]) in _normalizar(canal):
        puntos -= 4
    if "official audio" in titulo_yt or "audio oficial" in titulo_yt:
        puntos -= 3
    return puntos


def buscar_en_youtube(ydl, cancion: Cancion) -> str | None:
    consulta = f"{' '.join(cancion.artistas)} {cancion.titulo} audio"
    info = ydl.extract_info(f"ytsearch8:{consulta}", download=False)
    resultados = [r for r in (info or {}).get("entries") or [] if r and r.get("id")]
    if not resultados:
        return None
    mejor = min(resultados, key=lambda r: _puntuar(cancion, r))
    return f"https://www.youtube.com/watch?v={mejor['id']}"


# --------------------------------------------------------------------------- #
# Etiquetas ID3
# --------------------------------------------------------------------------- #
def etiquetar(ruta: Path, cancion: Cancion):
    from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TPE2, TRCK, ID3NoHeaderError

    try:  # quitamos las etiquetas que haya puesto ffmpeg y escribimos las de Spotify
        ID3(ruta).delete()
    except ID3NoHeaderError:
        pass
    tags = ID3()
    tags.add(TIT2(encoding=3, text=cancion.titulo))
    if cancion.artistas:
        tags.add(TPE1(encoding=3, text=cancion.artistas))
        tags.add(TPE2(encoding=3, text=cancion.artistas[0]))
    if cancion.album:
        tags.add(TALB(encoding=3, text=cancion.album))
    if cancion.numero and cancion.album:
        tags.add(TRCK(encoding=3, text=str(cancion.numero)))
    if cancion.anio:
        tags.add(TDRC(encoding=3, text=cancion.anio))
    if cancion.portada:
        try:
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover",
                          data=_descargar(cancion.portada)))
        except Exception:
            pass
    tags.save(ruta, v2_version=3)


# --------------------------------------------------------------------------- #
# Descarga
# --------------------------------------------------------------------------- #
def nombre_archivo(texto: str) -> str:
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto).strip().rstrip(".")
    return texto[:150] or "cancion"


@dataclass
class Peticion:
    url: str
    calidad: str
    carpeta: Path


class Descargador(HiloDescarga):
    def __init__(self, peticion: Peticion):
        super().__init__(peticion.carpeta)
        self.peticion = peticion

    def trabajar(self):
        import yt_dlp

        self.emitir("estado", "Leyendo Spotify…")
        coleccion = obtener(self.peticion.url)
        total = len(coleccion.canciones)
        if not total:
            raise RuntimeError("Esa lista está vacía o es privada.")
        if coleccion.tipo == "track":
            destino = self.carpeta
        else:
            destino = self.carpeta / nombre_archivo(coleccion.nombre)
            self.emitir("aviso", f"{coleccion.nombre}  ·  {total} canciones")
            if coleccion.tipo == "playlist" and total >= LIMITE_LISTA:
                self.emitir("aviso", f"Spotify solo deja ver las primeras {LIMITE_LISTA} "
                                     "canciones de una lista sin iniciar sesión.")
        destino.mkdir(parents=True, exist_ok=True)

        buscador = yt_dlp.YoutubeDL({**self.opciones_base(), "extract_flat": "in_playlist"})
        calidad = CALIDADES_MP3.get(self.peticion.calidad, "320")

        for i, cancion in enumerate(coleccion.canciones, start=1):
            self.comprobar()
            posicion = (i, total) if total > 1 else (None, None)
            base = nombre_archivo(cancion.nombre)
            if total > 1:
                base = f"{i:03d} - {base}"
            final = destino / f"{base}.mp3"
            if final.exists():
                self.completados += 1
                self.emitir("completado", final)
                continue

            self.emitir("progreso", {"titulo": cancion.nombre, "posicion": posicion,
                                     "fraccion": 0, "velocidad": None, "eta": None,
                                     "pista": None})
            self.emitir("estado", "Buscando en YouTube…")
            url = buscar_en_youtube(buscador, cancion)
            self.comprobar()
            if not url:
                self.emitir("error", f"{cancion.nombre}: no se ha encontrado en YouTube")
                continue

            opciones = self.opciones_base()
            opciones.update({
                "paths": {"home": str(destino)},
                "outtmpl": base.replace("%", "%%") + ".%(ext)s",
                "noplaylist": True,
                "format": "bestaudio/best",
                "progress_hooks": [
                    lambda d, c=cancion, p=posicion: self.progreso_desde_ytdlp(d, c.nombre, p)],
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                    "preferredquality": calidad}],
            })
            with yt_dlp.YoutubeDL(opciones) as ydl:
                codigo = ydl.download([url])
            self.comprobar()
            if codigo or not final.exists():
                self.emitir("error", f"{cancion.nombre}: falló la descarga")
                continue

            self.emitir("estado", "Añadiendo portada y datos…")
            completar_datos(cancion)
            try:
                etiquetar(final, cancion)
            except Exception as e:  # el MP3 vale igual aunque fallen las etiquetas
                self.emitir("aviso", f"{cancion.nombre}: sin etiquetas ({e})")
            self.completados += 1
            self.emitir("completado", final)
