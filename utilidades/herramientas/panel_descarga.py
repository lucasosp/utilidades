"""Tarjeta de progreso compartida por todas las herramientas de descarga."""

import queue
import threading
from pathlib import Path

import customtkinter as ctk

from .. import ui
from ..config import asegurar_carpeta
from .descarga_base import HiloDescarga, actualizar_yt_dlp


def _bytes_seg(v) -> str:
    if not v:
        return ""
    for unidad in ("B/s", "KB/s", "MB/s", "GB/s"):
        if v < 1024:
            return f"{v:.0f} {unidad}" if unidad == "B/s" else f"{v:.1f} {unidad}"
        v /= 1024
    return f"{v:.1f} TB/s"


def _tiempo(seg) -> str:
    seg = int(seg)
    if seg >= 3600:
        return f"{seg // 3600}:{seg % 3600 // 60:02d}:{seg % 60:02d}"
    return f"{seg // 60}:{seg % 60:02d}"


class PanelDescarga(ui.Tarjeta):
    """Muestra el progreso de un ``HiloDescarga`` y el registro de archivos."""

    def __init__(self, master, carpeta: Path, texto_inicial: str):
        super().__init__(master)
        self.carpeta = carpeta
        self.descargador: HiloDescarga | None = None
        self._al_terminar = None
        self._carpeta_ultima = None
        self._ultimo_estado = None

        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=22, pady=20)

        self._titulo = ui.Etiqueta(cuerpo, "Listo para descargar", 14, "bold", wraplength=700)
        self._titulo.pack(fill="x")
        self._detalle = ui.Etiqueta(cuerpo, texto_inicial, 12, suave=True)
        self._detalle.pack(fill="x", pady=(2, 10))
        self.barra = ctk.CTkProgressBar(cuerpo, height=8, corner_radius=4,
                                        progress_color=ui.ACENTO, fg_color=ui.SECUNDARIO)
        self.barra.set(0)
        self.barra.pack(fill="x")

        self.registro = ctk.CTkTextbox(
            cuerpo, corner_radius=10, border_width=0, fg_color=ui.CAMPO, text_color=ui.TEXTO,
            font=ui.fuente(12), wrap="word", height=60,
        )
        self.registro.configure(state="disabled")

        # El pie se coloca antes que el registro para que, si falta espacio,
        # encoja el registro y los botones sigan visibles.
        pie = ctk.CTkFrame(cuerpo, fg_color="transparent")
        pie.pack(side="bottom", fill="x")
        self.registro.pack(fill="both", expand=True, pady=(16, 12))
        ui.Boton(pie, "Abrir carpeta", self._abrir_carpeta, "carpeta", alto=38).pack(side="left")
        self.boton_actualizar = ui.Boton(pie, "Actualizar yt-dlp", self._actualizar_yt_dlp,
                                         "actualizar", alto=38)
        self.boton_actualizar.pack(side="right")

    # ----------------------------------------------------------- público --
    @property
    def ocupado(self) -> bool:
        return self.descargador is not None

    def iniciar(self, descargador: HiloDescarga, al_terminar=None):
        self.descargador = descargador
        self._al_terminar = al_terminar
        self._carpeta_ultima = None
        self._ultimo_estado = None
        self._limpiar_registro()
        self.barra.set(0)
        self.titulo("Preparando…")
        self.detalle("")
        descargador.start()
        self.after(100, self._leer_eventos)

    def cancelar(self):
        if self.descargador:
            self.descargador.cancelar()

    def titulo(self, texto):
        self._titulo.configure(text=texto)

    def detalle(self, texto):
        self._detalle.configure(text=texto)

    def escribir(self, linea, tipo=None):
        colores = {"ok": ui.EXITO, "error": ui.ERROR, "aviso": ui.TEXTO_SUAVE}
        self.registro.configure(state="normal")
        if tipo:
            oscuro = ctk.get_appearance_mode() == "Dark"
            self.registro.tag_config(tipo, foreground=colores[tipo][int(oscuro)])
        self.registro.insert("end", linea + "\n", tipo)
        self.registro.see("end")
        self.registro.configure(state="disabled")

    # ------------------------------------------------------------ eventos --
    def _leer_eventos(self):
        d = self.descargador
        if d is None:
            return
        try:
            while True:
                tipo, datos = d.eventos.get_nowait()
                getattr(self, f"_ev_{tipo}")(datos)
                if tipo == "fin":
                    return
        except queue.Empty:
            pass
        self.after(100, self._leer_eventos)

    @staticmethod
    def _prefijo(posicion) -> str:
        indice, total = posicion or (None, None)
        if indice and total:
            return f"{indice} de {total}"
        return f"N.º {indice}" if indice else ""

    def _ev_estado(self, texto):
        if texto == self._ultimo_estado:
            return
        self._ultimo_estado = texto
        self.detalle(texto)
        if texto.startswith(("Obteniendo", "Leyendo")):
            self.barra.configure(mode="indeterminate")
            self.barra.start()

    def _ev_progreso(self, p):
        self._parar_indeterminado()
        self._ultimo_estado = None
        self.titulo(p["titulo"])
        partes = [self._prefijo(p["posicion"])]
        if p["fraccion"] is not None:
            partes.append(f"{p['fraccion'] * 100:.0f} %")
        if p["pista"]:
            partes.append("pista de audio")
        partes.append(_bytes_seg(p["velocidad"]))
        if p["eta"]:
            partes.append(f"quedan {_tiempo(p['eta'])}")
        self.detalle("  ·  ".join(x for x in partes if x))
        if p["fraccion"] is not None:
            self.barra.set(p["fraccion"])

    def _ev_procesando(self, p):
        self.titulo(p["titulo"])
        self.barra.set(1)

    def _ev_completado(self, ruta: Path):
        self._carpeta_ultima = ruta.parent
        self.escribir(f"✓  {ruta.name}", "ok")

    def _ev_aviso(self, texto):
        self.escribir(f"•  {texto}", "aviso")

    def _ev_error(self, mensaje):
        self.escribir(f"✕  {mensaje}", "error")

    def _ev_fin(self, r):
        self._parar_indeterminado()
        self.descargador = None
        hechos, errores = r["completados"], r["errores"]
        archivos = "archivo" if hechos == 1 else "archivos"
        if r["cancelado"]:
            self.titulo("Descarga cancelada")
            self.detalle(f"Se completaron {hechos} {archivos} antes de cancelar.")
        elif hechos and not errores:
            self.titulo("¡Listo!" if hechos == 1 else f"¡Listo! {hechos} {archivos} descargados")
            self.detalle("Pulsa «Abrir carpeta» para verlos.")
            self.barra.set(1)
        elif hechos:
            self.titulo(f"{hechos} {archivos} descargados, {errores} con errores")
            self.detalle("Algunos elementos pueden ser privados o no estar disponibles.")
        else:
            self.titulo("No se pudo descargar")
            self.detalle("Revisa el enlace. Si el problema sigue, prueba «Actualizar yt-dlp».")
            self.barra.set(0)
        if self._al_terminar:
            self._al_terminar(r)

    # -------------------------------------------------------- utilidades --
    def _parar_indeterminado(self):
        if self.barra.cget("mode") == "indeterminate":
            self.barra.stop()
            self.barra.configure(mode="determinate")
            self.barra.set(0)

    def _limpiar_registro(self):
        self.registro.configure(state="normal")
        self.registro.delete("1.0", "end")
        self.registro.configure(state="disabled")

    def _abrir_carpeta(self):
        ui.abrir_en_explorador(asegurar_carpeta(self._carpeta_ultima or self.carpeta))

    def _actualizar_yt_dlp(self):
        self.boton_actualizar.configurar(texto="Actualizando…", estado="disabled")

        def tarea():
            ok, msg = actualizar_yt_dlp()
            self.after(0, lambda: terminado(ok, msg))

        def terminado(ok, msg):
            self.boton_actualizar.configurar(texto="Actualizar yt-dlp", estado="normal")
            if ok:
                self.escribir("✓  yt-dlp actualizado. Reinicia la app para usar la nueva "
                              "versión.", "ok")
            else:
                self.escribir(f"✕  No se pudo actualizar yt-dlp: {msg}", "error")

        threading.Thread(target=tarea, daemon=True).start()
