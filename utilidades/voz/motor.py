"""Lado de la app del motor de voz: instalación y comunicación con el trabajador.

El motor (PyTorch + Chatterbox) vive en su propio entorno `.venv-voz`, que se
crea solo la primera vez que se usa la pestaña. Así la app sigue siendo ligera
para quien no lo necesite.
"""

import json
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from ..config import RAIZ

VENV_VOZ = RAIZ / ".venv-voz"
MARCA = VENV_VOZ / "motor_instalado.txt"
REGISTRO = VENV_VOZ / "trabajador.log"
TRABAJADOR = Path(__file__).with_name("trabajador.py")
PAQUETES = ["chatterbox-tts==0.1.7"]
VERSION_MOTOR = "chatterbox-0.1.7"

IDIOMAS = {
    "Español": "es", "English": "en", "Français": "fr", "Italiano": "it",
    "Português": "pt", "Deutsch": "de", "Nederlands": "nl", "Polski": "pl",
    "Türkçe": "tr", "Русский": "ru", "日本語": "ja", "中文": "zh", "한국어": "ko",
    "العربية": "ar", "हिन्दी": "hi",
}

_SIN_VENTANA = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def python_voz() -> Path:
    if sys.platform == "win32":
        return VENV_VOZ / "Scripts" / "python.exe"
    return VENV_VOZ / "bin" / "python"


def instalado() -> bool:
    try:
        return python_voz().exists() and MARCA.read_text().strip() == VERSION_MOTOR
    except OSError:
        return False


def tiene_gpu_nvidia() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    try:
        r = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=10,
                           creationflags=_SIN_VENTANA)
        return r.returncode == 0 and "GPU" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


# --------------------------------------------------------------------------- #
# Instalación
# --------------------------------------------------------------------------- #
class Instalador(threading.Thread):
    """Crea `.venv-voz` e instala el motor. Emite ("linea", texto), ("paso", texto)
    y al final ("fin", ok)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.eventos: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._proceso = None
        self._cancelado = False

    def cancelar(self):
        self._cancelado = True
        if self._proceso and self._proceso.poll() is None:
            self._proceso.kill()

    def _ejecutar(self, args) -> bool:
        self._proceso = subprocess.Popen(
            [str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA,
        )
        for linea in self._proceso.stdout:
            if linea.strip():
                self.eventos.put(("linea", linea.rstrip()))
        return self._proceso.wait() == 0 and not self._cancelado

    def run(self):
        ok = False
        try:
            base = getattr(sys, "_base_executable", sys.executable)
            pip = [python_voz(), "-m", "pip", "install", "--disable-pip-version-check"]
            pasos = []
            if not python_voz().exists():
                pasos.append(("Creando el entorno del motor de voz…",
                              [base, "-m", "venv", VENV_VOZ]))
            pasos.append(("Actualizando pip…", pip + ["-U", "pip"]))
            if sys.platform == "win32" or sys.platform.startswith("linux"):
                indice = "cu126" if tiene_gpu_nvidia() else "cpu"
                texto = ("Descargando PyTorch con soporte para tu tarjeta NVIDIA (≈2,5 GB)…"
                         if indice != "cpu" else "Descargando PyTorch para CPU (≈300 MB)…")
                pasos.append((texto, pip + ["torch", "torchaudio", "--index-url",
                                            f"https://download.pytorch.org/whl/{indice}"]))
            pasos.append(("Instalando Chatterbox…", pip + PAQUETES))

            for texto, args in pasos:
                self.eventos.put(("paso", texto))
                if not self._ejecutar(args):
                    return
            MARCA.write_text(VERSION_MOTOR)
            ok = True
        except Exception as e:  # noqa: BLE001
            self.eventos.put(("linea", f"Error: {e}"))
        finally:
            self.eventos.put(("fin", ok))


# --------------------------------------------------------------------------- #
# Cliente del trabajador
# --------------------------------------------------------------------------- #
class MotorVoz:
    """Arranca el trabajador y le manda órdenes. Los eventos llegan a `eventos`."""

    def __init__(self):
        self.eventos: "queue.Queue[dict]" = queue.Queue()
        self._registro = open(REGISTRO, "a", encoding="utf-8", errors="replace")
        self._proceso = subprocess.Popen(
            [str(python_voz()), "-u", str(TRABAJADOR)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._registro,
            text=True, encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA,
            cwd=str(RAIZ),
        )
        self._siguiente_id = 0
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        for linea in self._proceso.stdout:
            try:
                self.eventos.put(json.loads(linea))
            except ValueError:
                pass
        codigo = self._proceso.wait()
        self.eventos.put({"ev": "cerrado", "codigo": codigo})

    def _mandar(self, **orden):
        if self._proceso.poll() is None:
            try:
                self._proceso.stdin.write(json.dumps(orden, ensure_ascii=False) + "\n")
                self._proceso.stdin.flush()
            except OSError:
                pass

    @property
    def vivo(self) -> bool:
        return self._proceso.poll() is None

    def generar(self, texto, idioma, voz, expresividad, salida: Path) -> int:
        self._siguiente_id += 1
        self._mandar(cmd="generar", id=self._siguiente_id, texto=texto, idioma=idioma,
                     voz=str(voz) if voz else None, expresividad=expresividad,
                     salida=str(salida))
        return self._siguiente_id

    def cancelar(self):
        self._mandar(cmd="cancelar")

    def cerrar(self):
        self._mandar(cmd="salir")
        try:
            self._proceso.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._proceso.kill()
        self._registro.close()


# --------------------------------------------------------------------------- #
# Voces y archivos (comunes a la app y a la consola)
# --------------------------------------------------------------------------- #
def _ffmpeg() -> str:
    from ..herramientas.descarga_base import ruta_ffmpeg
    return ruta_ffmpeg() or "ffmpeg"


def voces_guardadas() -> dict[str, Path]:
    from ..config import CARPETA_VOCES
    if not CARPETA_VOCES.exists():
        return {}
    return {p.stem: p for p in sorted(CARPETA_VOCES.glob("*.wav"))}


def anadir_voz(origen: Path, nombre: str, carpeta: Path | None = None) -> Path:
    """Convierte un audio cualquiera en una voz de referencia (24 kHz mono, ≤20 s)."""
    from ..config import CARPETA_VOCES
    carpeta = carpeta or CARPETA_VOCES
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{nombre}.wav"
    r = subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(origen), "-t", "20", "-ac", "1",
         "-ar", "24000", str(destino)],
        capture_output=True, text=True, creationflags=_SIN_VENTANA,
    )
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "ffmpeg no pudo leer el audio")
    return destino


def exportar(wav: Path, destino: Path):
    """Copia el WAV generado al destino, convirtiéndolo a MP3 si hace falta."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.suffix.lower() == ".wav":
        shutil.copyfile(wav, destino)
        return
    r = subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame",
         "-q:a", "2", str(destino)],
        capture_output=True, text=True, creationflags=_SIN_VENTANA,
    )
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "ffmpeg no pudo crear el MP3")
