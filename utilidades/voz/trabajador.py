"""Proceso que genera la voz. Se ejecuta con el Python de `.venv-voz`.

Va aparte de la app porque necesita PyTorch y Chatterbox, que pesan varios GB
y tienen sus propias versiones de dependencias. Mantiene el modelo cargado en
memoria y habla con la app por stdin/stdout con una línea JSON por mensaje:

Entrada:
    {"cmd": "generar", "id": 1, "texto": "...", "idioma": "es", "voz": "ruta.wav" | null,
     "expresividad": 0.5, "salida": "ruta.wav"}
    {"cmd": "cancelar"}
    {"cmd": "salir"}

Salida:
    {"ev": "estado", "texto": "..."}
    {"ev": "listo", "dispositivo": "cuda"}
    {"ev": "progreso", "id": 1, "hecho": 2, "total": 5}
    {"ev": "terminado", "id": 1, "ruta": "...", "segundos": 12.3}
    {"ev": "cancelado", "id": 1}
    {"ev": "error", "id": 1, "texto": "..."}
"""

import json
import os
import queue
import re
import sys
import threading
import traceback
import wave
from pathlib import Path

# Los modelos se guardan dentro del proyecto para que sea fácil borrarlos.
RAIZ = Path(__file__).resolve().parents[2]
os.environ.setdefault("HF_HOME", str(RAIZ / ".modelos"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MAX_TROZO = 260          # caracteres por trozo (el modelo genera ~40 s como mucho)
PAUSA_FRASE = 0.22       # segundos de silencio entre trozos
PAUSA_PARRAFO = 0.55

_salida = sys.stdout
_salida.reconfigure(encoding="utf-8")  # la app lee en UTF-8 (en Windows, la tubería no lo es)
sys.stdout = sys.stderr  # que ningún print de las librerías rompa el protocolo


def enviar(**mensaje):
    _salida.write(json.dumps(mensaje, ensure_ascii=False) + "\n")
    _salida.flush()


# --------------------------------------------------------------------------- #
# Texto → trozos
# --------------------------------------------------------------------------- #
def _partir_largo(frase: str) -> list[str]:
    """Parte una frase demasiado larga por comas y, si hace falta, por espacios."""
    trozos, actual = [], ""
    for parte in re.split(r"(?<=[,;:])\s+", frase):
        if len(parte) > MAX_TROZO:
            palabras, parte_actual = parte.split(), ""
            for p in palabras:
                if len(parte_actual) + len(p) + 1 > MAX_TROZO:
                    trozos.append(parte_actual)
                    parte_actual = p
                else:
                    parte_actual = f"{parte_actual} {p}".strip()
            parte = parte_actual
        if len(actual) + len(parte) + 1 > MAX_TROZO and actual:
            trozos.append(actual)
            actual = parte
        else:
            actual = f"{actual} {parte}".strip()
    if actual:
        trozos.append(actual)
    return trozos


def trocear(texto: str) -> list[tuple[str, float]]:
    """Devuelve [(trozo, pausa_despues)] respetando frases y párrafos."""
    resultado = []
    for parrafo in [p.strip() for p in re.split(r"\n\s*\n|\n", texto) if p.strip()]:
        frases = re.split(r"(?<=[.!?…])\s+", parrafo)
        actual = ""
        trozos = []
        for frase in frases:
            if len(frase) > MAX_TROZO:
                if actual:
                    trozos.append(actual)
                    actual = ""
                trozos.extend(_partir_largo(frase))
            elif len(actual) + len(frase) + 1 > MAX_TROZO:
                trozos.append(actual)
                actual = frase
            else:
                actual = f"{actual} {frase}".strip()
        if actual:
            trozos.append(actual)
        for i, t in enumerate(trozos):
            resultado.append((t, PAUSA_PARRAFO if i == len(trozos) - 1 else PAUSA_FRASE))
    return resultado


def guardar_wav(ruta: Path, muestras, frecuencia: int):
    import numpy as np

    datos = np.clip(muestras, -1.0, 1.0)
    datos = (datos * 32767).astype("<i2")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frecuencia)
        w.writeframes(datos.tobytes())


# --------------------------------------------------------------------------- #
# Bucle principal
# --------------------------------------------------------------------------- #
class Trabajador:
    def __init__(self):
        self.modelo = None
        self.cancelar = threading.Event()
        self.ordenes: "queue.Queue[dict]" = queue.Queue()
        self._voz_cargada = object()  # ninguna

    def leer_entrada(self):
        for linea in sys.stdin:
            try:
                orden = json.loads(linea)
            except ValueError:
                continue
            if orden.get("cmd") == "cancelar":
                self.cancelar.set()
            else:
                self.ordenes.put(orden)
        self.ordenes.put({"cmd": "salir"})

    def cargar(self):
        import torch

        if torch.cuda.is_available():
            dispositivo = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            dispositivo = "mps"
        else:
            dispositivo = "cpu"
        enviar(ev="estado", texto="Cargando el modelo de voz…")
        from huggingface_hub import try_to_load_from_cache
        if not isinstance(try_to_load_from_cache("ResembleAI/chatterbox",
                                                 "t3_mtl23ls_v2.safetensors"), str):
            enviar(ev="estado", texto="Descargando el modelo de voz (solo la primera vez, "
                                      "unos 3 GB)…")
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        self.modelo = ChatterboxMultilingualTTS.from_pretrained(device=dispositivo)
        self._conds_base = self.modelo.conds
        enviar(ev="listo", dispositivo=dispositivo)

    def generar(self, orden: dict):
        import numpy as np

        id_ = orden.get("id")
        trozos = trocear(orden.get("texto", ""))
        if not trozos:
            enviar(ev="error", id=id_, texto="No hay texto que leer.")
            return
        expresividad = float(orden.get("expresividad", 0.5))
        voz = orden.get("voz")

        # Preparar la voz solo si ha cambiado (es lo más lento después del modelo).
        if voz != self._voz_cargada:
            if voz:
                self.modelo.prepare_conditionals(voz, exaggeration=expresividad)
            else:
                self.modelo.conds = self._conds_base
            self._voz_cargada = voz

        sr = self.modelo.sr
        partes = []
        enviar(ev="progreso", id=id_, hecho=0, total=len(trozos))
        for i, (trozo, pausa) in enumerate(trozos, start=1):
            if self.cancelar.is_set():
                enviar(ev="cancelado", id=id_)
                return
            wav = self.modelo.generate(
                trozo, language_id=orden.get("idioma", "es"), exaggeration=expresividad,
                cfg_weight=float(orden.get("cfg", 0.5)),
            )
            partes.append(wav.squeeze(0).numpy())
            partes.append(np.zeros(int(sr * pausa), dtype=np.float32))
            enviar(ev="progreso", id=id_, hecho=i, total=len(trozos))

        audio = np.concatenate(partes[:-1]) if len(partes) > 1 else partes[0]
        salida = Path(orden["salida"])
        guardar_wav(salida, audio, sr)
        enviar(ev="terminado", id=id_, ruta=str(salida), segundos=round(len(audio) / sr, 1))

    def bucle(self):
        # En Windows, mientras un hilo espera en stdin (una tubería), cualquier otro
        # que consulte ese mismo stdin se queda bloqueado, y algunas librerías lo
        # hacen al importarse. Por eso se carga todo ANTES de empezar a leer órdenes;
        # las que lleguen mientras tanto esperan en la tubería.
        try:
            self.cargar()
        except Exception as e:  # noqa: BLE001
            enviar(ev="error", id=None, texto=f"No se pudo cargar el modelo: {e}",
                   detalle=traceback.format_exc())
            return
        threading.Thread(target=self.leer_entrada, daemon=True).start()
        while True:
            orden = self.ordenes.get()
            if orden.get("cmd") == "salir":
                return
            if orden.get("cmd") == "generar":
                self.cancelar.clear()
                try:
                    self.generar(orden)
                except Exception as e:  # noqa: BLE001
                    enviar(ev="error", id=orden.get("id"), texto=str(e),
                           detalle=traceback.format_exc())


if __name__ == "__main__":
    Trabajador().bucle()
