"""Uso de Utilidades desde la consola (y desde Claude Code u otros scripts).

    utilidades qr "https://ejemplo.com" -o qr.png
    utilidades youtube URL --formato mp3
    utilidades spotify URL
    utilidades voz "Hola, ¿qué tal?" -o saludo.mp3
    utilidades info

Con --json, la última línea de la salida es un JSON con el resultado (rutas de
los archivos creados, etc.); el progreso va siempre por stderr.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from .config import (CARPETA_AUDIOS, CARPETA_DESCARGAS, CARPETA_QR, CARPETA_VOCES, NOMBRE_APP,
                     RAIZ, VERSION)

CALIDADES_MP3 = {"320": "320 kbps", "192": "192 kbps", "128": "128 kbps"}
CALIDADES_MP4 = {"max": "Máxima", "1080": "1080p", "720": "720p", "480": "480p", "360": "360p"}


class Error(Exception):
    """Error que se muestra al usuario sin traza."""


# --------------------------------------------------------------------------- #
# Salida
# --------------------------------------------------------------------------- #
class Salida:
    def __init__(self, como_json: bool, silencio: bool):
        self.json = como_json
        self.silencio = silencio
        self._ultimo_progreso = 0.0

    def info(self, texto):
        if not self.silencio:
            print(texto, file=sys.stderr, flush=True)

    def progreso(self, texto):
        """Líneas de progreso, como mucho una cada medio segundo."""
        ahora = time.monotonic()
        if not self.silencio and ahora - self._ultimo_progreso > 0.5:
            self._ultimo_progreso = ahora
            print(f"  {texto}", file=sys.stderr, flush=True)

    def resultado(self, datos: dict):
        if self.json:
            print(json.dumps(datos, ensure_ascii=False))
        else:
            for ruta in datos.get("archivos", []):
                print(ruta)


def _destino(salida: str | None, carpeta_defecto: Path, base: str, extension: str) -> Path:
    """-o puede ser un archivo (con extensión) o una carpeta."""
    from .herramientas.qr_motor import ruta_libre

    if salida:
        ruta = Path(salida).expanduser().resolve()
        if ruta.suffix:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            return ruta
        return ruta_libre(ruta, base, extension)
    return ruta_libre(carpeta_defecto, base, extension)


def _carpeta(salida: str | None, defecto: Path) -> Path:
    carpeta = Path(salida).expanduser().resolve() if salida else defecto
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _leer_texto(args) -> list[str]:
    textos = list(args.texto or [])
    if args.archivo:
        textos.append(Path(args.archivo).read_text(encoding="utf-8"))
    if textos == ["-"]:
        textos = [sys.stdin.read()]
    textos = [t.strip() for t in textos if t.strip()]
    if not textos:
        raise Error("No hay texto. Pásalo como argumento, con --archivo o por stdin (-).")
    return textos


# --------------------------------------------------------------------------- #
# Comandos
# --------------------------------------------------------------------------- #
def cmd_qr(args, out: Salida):
    from .herramientas.qr_motor import (BLANCO, NEGRO, aviso_contraste, generar_qr,
                                        nombre_desde_contenido, nombre_seguro,
                                        normalizar_color)

    contenido = " ".join(args.contenido).strip()
    if contenido == "-":
        contenido = sys.stdin.read().strip()
    if not contenido:
        raise Error("Falta el contenido del QR.")
    try:
        codigo = normalizar_color(args.color) if args.color else NEGRO
        if args.fondo and args.fondo.lower() in ("transparente", "transparent", "none"):
            fondo = None
        else:
            fondo = normalizar_color(args.fondo) if args.fondo else BLANCO
    except ValueError as e:
        raise Error(str(e)) from None

    imagen, version = generar_qr(contenido, codigo, fondo, tam_modulo=args.modulo,
                                 borde=args.borde)
    if args.tam:
        from PIL import Image
        imagen = imagen.resize((args.tam, args.tam), Image.Resampling.NEAREST)
    base = nombre_seguro(args.nombre or "", 60) or nombre_desde_contenido(contenido)
    ruta = _destino(args.salida, CARPETA_QR, base, "png")
    imagen.save(ruta, format="PNG")
    if aviso := aviso_contraste(codigo, fondo):
        out.info(f"Aviso: {aviso}")
    out.info(f"QR guardado: {ruta}")
    out.resultado({"ok": True, "archivos": [str(ruta)], "tam": imagen.size[0],
                   "version": version})


def _consumir_descarga(hilo, out: Salida) -> dict:
    """Ejecuta un HiloDescarga y traduce sus eventos a la consola."""
    hilo.start()
    archivos, errores, ultimo_estado = [], [], None
    try:
        while True:
            tipo, datos = hilo.eventos.get()
            if tipo == "estado":
                if datos != ultimo_estado:
                    out.info(f"  {datos}")
                ultimo_estado = datos
            elif tipo == "aviso":
                out.info(f"  • {datos}")
            elif tipo == "progreso":
                i, total = datos["posicion"] or (None, None)
                pos = f"[{i}/{total}] " if i and total else ""
                pct = f" {datos['fraccion'] * 100:.0f}%" if datos["fraccion"] is not None else ""
                out.progreso(f"{pos}{datos['titulo']}{pct}")
            elif tipo == "completado":
                archivos.append(str(datos))
                out.info(f"  ✓ {datos.name}")
            elif tipo == "error":
                errores.append(datos)
                out.info(f"  ✕ {datos}")
            elif tipo == "fin":
                return {"ok": bool(archivos) and not datos["cancelado"], "archivos": archivos,
                        "errores": errores}
    except KeyboardInterrupt:
        hilo.cancelar()
        out.info("Cancelando…")
        while hilo.eventos.get()[0] != "fin":
            pass
        return {"ok": False, "archivos": archivos, "errores": errores + ["Cancelado"]}


def cmd_youtube(args, out: Salida):
    from .herramientas.youtube_motor import Descargador, Peticion, analizar_enlace

    enlace = analizar_enlace(args.url)
    if not enlace.valido:
        raise Error("Eso no parece un enlace.")
    formato = args.formato.upper()
    calidades = CALIDADES_MP3 if formato == "MP3" else CALIDADES_MP4
    calidad = calidades.get(str(args.calidad).lower()) if args.calidad else next(iter(
        calidades.values()))
    if not calidad:
        raise Error(f"Calidad no válida para {formato}. Opciones: {', '.join(calidades)}")
    lista = bool(enlace.lista) and (args.lista or not enlace.video)
    if enlace.lista and enlace.video and not args.lista:
        out.info("El enlace es un vídeo dentro de una lista: se baja solo el vídeo "
                 "(usa --lista para bajar la lista entera).")
    peticion = Peticion(args.url, formato, calidad, lista,
                        _carpeta(args.salida, CARPETA_DESCARGAS))
    r = _consumir_descarga(Descargador(peticion), out)
    out.resultado(r)
    return 0 if r["ok"] else 1


def cmd_spotify(args, out: Salida):
    from .herramientas.spotify_motor import Descargador, Peticion, analizar_enlace

    if not analizar_enlace(args.url):
        raise Error("Eso no es un enlace de Spotify (canción, álbum o lista).")
    calidad = CALIDADES_MP3.get(str(args.calidad))
    if not calidad:
        raise Error(f"Calidad no válida. Opciones: {', '.join(CALIDADES_MP3)}")
    peticion = Peticion(args.url, calidad, _carpeta(args.salida, CARPETA_DESCARGAS))
    r = _consumir_descarga(Descargador(peticion), out)
    out.resultado(r)
    return 0 if r["ok"] else 1


def _resolver_voz(nombre: str | None) -> Path | None:
    from .voz import motor

    if not nombre or nombre.lower() in ("predeterminada", "defecto", "default"):
        return None
    ruta = Path(nombre).expanduser()
    if ruta.suffix and ruta.exists():
        if ruta.suffix.lower() == ".wav":
            return ruta.resolve()
        # Otros formatos: se convierten a una voz temporal.
        return motor.anadir_voz(ruta, "voz_temporal", carpeta=motor.VENV_VOZ)
    voces = motor.voces_guardadas()
    coincidencia = next((p for n, p in voces.items() if n.lower() == nombre.lower()), None)
    if not coincidencia:
        disponibles = ", ".join(voces) or "ninguna (añade una con: utilidades voces --anadir)"
        raise Error(f"No existe la voz «{nombre}». Voces guardadas: {disponibles}")
    return coincidencia


def cmd_voz(args, out: Salida):
    from .herramientas.qr_motor import nombre_seguro
    from .voz import motor

    if args.instalar:
        return _instalar_motor_voz(out)
    if not motor.instalado():
        raise Error("El motor de voz no está instalado. Ejecuta: utilidades voz --instalar "
                    "(descarga unos 6 GB la primera vez).")
    idioma = args.idioma.lower()
    codigos = set(motor.IDIOMAS.values())
    if idioma not in codigos:
        nombres = {k.lower(): v for k, v in motor.IDIOMAS.items()}
        idioma = nombres.get(idioma, "")
        if not idioma:
            raise Error(f"Idioma no válido. Usa uno de: {', '.join(sorted(codigos))}")
    textos = _leer_texto(args)
    if args.salida and Path(args.salida).suffix and len(textos) > 1:
        raise Error("Con varios textos, -o tiene que ser una carpeta.")
    voz = _resolver_voz(args.voz)
    extension = args.formato.lower()

    destinos = []
    for texto in textos:
        base = "voz_" + (nombre_seguro(texto, 40) or "audio")
        destinos.append(_destino(args.salida, CARPETA_AUDIOS, base, extension))

    out.info("Cargando el motor de voz…")
    m = motor.MotorVoz()
    temporal = motor.VENV_VOZ / "cli.wav"
    archivos, duraciones = [], []
    try:
        for n, (texto, destino) in enumerate(zip(textos, destinos), start=1):
            id_ = m.generar(texto, idioma, voz, args.expresividad, temporal)
            prefijo = f"[{n}/{len(textos)}] " if len(textos) > 1 else ""
            while True:
                ev = m.eventos.get()
                tipo = ev["ev"]
                if tipo == "estado":
                    out.info(f"  {ev['texto']}")
                elif tipo == "listo":
                    out.info(f"  Modelo listo ({ev['dispositivo']}).")
                elif tipo == "progreso" and ev.get("id") == id_ and ev["total"]:
                    out.info(f"  {prefijo}fragmento {ev['hecho']}/{ev['total']}")
                elif tipo == "terminado" and ev.get("id") == id_:
                    motor.exportar(temporal, destino)
                    archivos.append(str(destino))
                    duraciones.append(ev["segundos"])
                    out.info(f"  ✓ {destino} ({ev['segundos']} s)")
                    break
                elif tipo == "error" and ev.get("id") in (id_, None):
                    raise Error(ev["texto"])
                elif tipo == "cerrado":
                    raise Error(f"El motor de voz se cerró. Mira {motor.REGISTRO}")
    except KeyboardInterrupt:
        m.cancelar()
        raise Error("Cancelado.") from None
    finally:
        m.cerrar()
    out.resultado({"ok": True, "archivos": archivos, "segundos": duraciones})


def _instalar_motor_voz(out: Salida):
    from .voz import motor

    if motor.instalado():
        out.info("El motor de voz ya está instalado.")
        out.resultado({"ok": True, "archivos": []})
        return 0
    out.info("Instalando el motor de voz (puede tardar bastante la primera vez)…")
    inst = motor.Instalador()
    inst.start()
    while True:
        tipo, datos = inst.eventos.get()
        if tipo == "paso":
            out.info(f"  {datos}")
        elif tipo == "linea" and ("error" in datos.lower() or datos.startswith("Successfully")):
            out.info(f"    {datos[:200]}")
        elif tipo == "fin":
            out.resultado({"ok": bool(datos), "archivos": []})
            return 0 if datos else 1


def cmd_voces(args, out: Salida):
    from .herramientas.qr_motor import nombre_seguro
    from .voz import motor

    if args.anadir:
        origen = Path(args.anadir).expanduser()
        if not origen.exists():
            raise Error(f"No existe el archivo {origen}")
        nombre = nombre_seguro(args.nombre or origen.stem, 40).replace("_", " ").strip()
        if not nombre:
            raise Error("Pon un nombre a la voz con --nombre.")
        ruta = motor.anadir_voz(origen, nombre)
        out.info(f"Voz «{nombre}» añadida: {ruta}")
        out.resultado({"ok": True, "archivos": [str(ruta)], "nombre": nombre})
        return 0
    voces = {n: str(p) for n, p in motor.voces_guardadas().items()}
    if out.json:
        out.resultado({"ok": True, "voces": voces})
    else:
        print("Predeterminada")
        for n in voces:
            print(n)
    return 0


def cmd_info(args, out: Salida):
    from .herramientas.descarga_base import ffmpeg_disponible, ruta_ffmpeg
    from .voz import motor

    datos = {
        "app": NOMBRE_APP, "version": VERSION, "raiz": str(RAIZ),
        "carpetas": {"qr": str(CARPETA_QR), "descargas": str(CARPETA_DESCARGAS),
                     "voz": str(CARPETA_AUDIOS), "voces": str(CARPETA_VOCES)},
        "ffmpeg": (ruta_ffmpeg() or "ffmpeg (en el PATH)") if ffmpeg_disponible() else None,
        "voz_instalada": motor.instalado(),
        "voces": ["Predeterminada"] + list(motor.voces_guardadas()),
        "idiomas_voz": sorted(set(motor.IDIOMAS.values())),
    }
    if out.json:
        out.resultado(datos)
    else:
        for clave, valor in datos.items():
            print(f"{clave}: {valor}")
    return 0


def cmd_abrir(args, out: Salida):
    import subprocess
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    ejecutable = pythonw if pythonw.exists() else Path(sys.executable)
    subprocess.Popen([str(ejecutable), str(RAIZ / "Utilidades.pyw")], cwd=str(RAIZ))
    return 0


def cmd_instalar_comando(args, out: Salida):
    from .comando import instalar_comando
    for ruta in instalar_comando():
        out.info(f"Creado: {ruta}")
    out.info("Listo. Abre una terminal nueva y prueba: utilidades --help")
    return 0


def cmd_instalar_skill(args, out: Salida):
    from .comando import instalar_skill
    ruta = instalar_skill()
    out.info(f"Skill de Claude Code instalada: {ruta}")
    out.resultado({"ok": True, "archivos": [str(ruta)]})
    return 0


# --------------------------------------------------------------------------- #
# Argumentos
# --------------------------------------------------------------------------- #
def crear_parser() -> argparse.ArgumentParser:
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--json", action="store_true",
                       help="imprime el resultado como JSON en la última línea de stdout")
    comun.add_argument("-q", "--silencio", action="store_true", help="no muestra el progreso")

    p = argparse.ArgumentParser(
        prog="utilidades", parents=[comun],
        description=f"{NOMBRE_APP} {VERSION}: QR, YouTube, Spotify y texto a voz desde la "
                    "consola. Sin subcomando abre la app.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Ejemplos:\n"
               '  utilidades qr "https://ejemplo.com" -o qr.png\n'
               "  utilidades youtube URL --formato mp4 --calidad 1080\n"
               "  utilidades spotify URL -o musica\n"
               '  utilidades voz "Hola, bienvenidos" --voz MiVoz -o intro.mp3\n'
               "  utilidades info --json",
    )
    sub = p.add_subparsers(dest="comando", metavar="COMANDO")

    q = sub.add_parser("qr", parents=[comun], help="genera un código QR en PNG")
    q.add_argument("contenido", nargs="+", help="texto o enlace ('-' para leer de stdin)")
    q.add_argument("-o", "--salida", help="archivo .png o carpeta (por defecto generados/)")
    q.add_argument("-n", "--nombre", help="nombre del archivo, sin extensión")
    q.add_argument("--color", help="color del código, #RRGGBB (por defecto negro)")
    q.add_argument("--fondo", help="color del fondo, #RRGGBB o 'transparente' (por defecto blanco)")
    q.add_argument("--tam", type=int, help="lado final de la imagen en píxeles (p. ej. 512)")
    q.add_argument("--modulo", type=int, default=20, help="píxeles por cuadradito (20)")
    q.add_argument("--borde", type=int, default=4, help="margen en cuadraditos (4)")
    q.set_defaults(funcion=cmd_qr)

    y = sub.add_parser("youtube", parents=[comun], aliases=["yt"],
                       help="descarga de YouTube (y otras webs) en MP3 o MP4")
    y.add_argument("url")
    y.add_argument("-f", "--formato", choices=["mp3", "mp4"], default="mp3", type=str.lower)
    y.add_argument("-c", "--calidad",
                   help="mp3: 320/192/128 (320) · mp4: max/1080/720/480/360 (max)")
    y.add_argument("--lista", action="store_true",
                   help="si el vídeo está en una lista, bajar la lista entera")
    y.add_argument("-o", "--salida", help="carpeta de destino (por defecto descargas/)")
    y.set_defaults(funcion=cmd_youtube)

    s = sub.add_parser("spotify", parents=[comun], help="canción, álbum o lista de Spotify a MP3")
    s.add_argument("url")
    s.add_argument("-c", "--calidad", default="320", help="320/192/128 kbps (320)")
    s.add_argument("-o", "--salida", help="carpeta de destino (por defecto descargas/)")
    s.set_defaults(funcion=cmd_spotify)

    v = sub.add_parser("voz", parents=[comun], aliases=["tts"],
                       help="texto a voz (local, con voces clonadas)")
    v.add_argument("texto", nargs="*",
                   help="uno o varios textos (cada uno, un archivo); '-' para stdin")
    v.add_argument("-a", "--archivo", help="leer el texto de un archivo .txt")
    v.add_argument("-o", "--salida", help="archivo .mp3/.wav o carpeta (por defecto generados/voz/)")
    v.add_argument("--voz", help="nombre de una voz guardada o ruta a un audio de referencia")
    v.add_argument("-i", "--idioma", default="es", help="código o nombre: es, en, fr… (es)")
    v.add_argument("-e", "--expresividad", type=float, default=0.5,
                   help="0.25 (neutra) a 1.0 (intensa); 0.5 por defecto")
    v.add_argument("-f", "--formato", choices=["mp3", "wav"], default="mp3", type=str.lower,
                   help="formato si -o es una carpeta (mp3)")
    v.add_argument("--instalar", action="store_true", help="instala el motor de voz (~6 GB)")
    v.set_defaults(funcion=cmd_voz)

    vs = sub.add_parser("voces", parents=[comun], help="lista o añade voces para clonar")
    vs.add_argument("--anadir", metavar="AUDIO", help="audio de 10-20 s con la voz a clonar")
    vs.add_argument("--nombre", help="nombre de la voz nueva")
    vs.set_defaults(funcion=cmd_voces)

    i = sub.add_parser("info", parents=[comun], help="rutas, voces y estado de la instalación")
    i.set_defaults(funcion=cmd_info)

    a = sub.add_parser("abrir", parents=[comun], help="abre la aplicación de escritorio")
    a.set_defaults(funcion=cmd_abrir)

    ic = sub.add_parser("instalar-comando", parents=[comun],
                        help="hace que 'utilidades' funcione en cualquier terminal")
    ic.set_defaults(funcion=cmd_instalar_comando)

    isk = sub.add_parser("instalar-skill", parents=[comun],
                         help="instala la skill para que Claude Code sepa usar este comando")
    isk.set_defaults(funcion=cmd_instalar_skill)
    return p


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = crear_parser()
    args = parser.parse_args(argv)
    if not args.comando:
        return cmd_abrir(args, None)
    out = Salida(args.json, args.silencio)
    try:
        codigo = args.funcion(args, out)
        return codigo or 0
    except Error as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
