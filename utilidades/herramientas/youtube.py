"""Descargador de YouTube (MP3 / MP4) con soporte para listas de reproducción."""

import queue
import threading

import customtkinter as ctk

from .. import ui
from ..config import CARPETA_DESCARGAS, asegurar_carpeta
from .base import Herramienta
from .youtube_motor import (CALIDADES_MP3, CALIDADES_MP4, Descargador, Peticion,
                            actualizar_yt_dlp, analizar_enlace, ffmpeg_disponible)

SOLO_VIDEO = "Solo este vídeo"
LISTA_ENTERA = "Toda la lista"


def _bytes_seg(v) -> str:
    if not v:
        return ""
    for unidad in ("B/s", "KB/s", "MB/s", "GB/s"):
        if v < 1024:
            return f"{v:.1f} {unidad}" if unidad != "B/s" else f"{v:.0f} {unidad}"
        v /= 1024
    return f"{v:.1f} TB/s"


def _tiempo(seg) -> str:
    if seg is None:
        return ""
    seg = int(seg)
    return f"{seg // 3600}:{seg % 3600 // 60:02d}:{seg % 60:02d}" if seg >= 3600 \
        else f"{seg // 60}:{seg % 60:02d}"


class HerramientaYouTube(Herramienta):
    id = "youtube"
    nombre = "YouTube"
    descripcion = "Pega un enlace y descárgalo en MP3 o MP4. También listas de reproducción."
    icono = "video"

    def __init__(self, master, app):
        super().__init__(master, app)
        self.descargador: Descargador | None = None
        self._carpeta_ultima = None
        self._ultimo_estado = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._crear_formulario()
        self._crear_progreso()
        self._al_cambiar_enlace()

    # ------------------------------------------------------------------ UI --
    def _crear_formulario(self):
        tarjeta = ui.Tarjeta(self)
        tarjeta.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cuerpo.pack(fill="x", padx=22, pady=20)
        cuerpo.grid_columnconfigure(0, weight=1)

        ui.Etiqueta(cuerpo, "Enlace", 13, "bold").grid(row=0, column=0, columnspan=2, sticky="w")
        self.url = ui.Campo(cuerpo, placeholder="https://www.youtube.com/watch?v=…")
        self.url.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.url.bind("<KeyRelease>", lambda _e: self._al_cambiar_enlace())
        self.url.bind("<<Paste>>", lambda _e: self.after(10, self._al_cambiar_enlace))
        self.url.bind("<Return>", lambda _e: self.descargar())
        ui.Boton(cuerpo, "Pegar", self._pegar, "pegar", alto=42).grid(
            row=1, column=1, sticky="e", padx=(10, 0), pady=(8, 0))

        self.pista = ui.Etiqueta(cuerpo, "", 12, suave=True)
        self.pista.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # Selector que solo aparece si el enlace es un vídeo dentro de una lista.
        self.fila_lista = ctk.CTkFrame(cuerpo, fg_color=ui.NAV_ACTIVO, corner_radius=10)
        ui.Etiqueta(self.fila_lista, f"{ui.icono('lista')}  Este vídeo forma parte de una lista",
                    12, "bold").pack(side="left", padx=14, pady=10)
        self.modo_lista = ui.Selector(self.fila_lista, [SOLO_VIDEO, LISTA_ENTERA])
        self.modo_lista.set(SOLO_VIDEO)
        self.modo_lista.pack(side="right", padx=10, pady=8)

        # Opciones
        opciones = ctk.CTkFrame(cuerpo, fg_color="transparent")
        opciones.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        opciones.grid_columnconfigure(2, weight=1)

        ui.Etiqueta(opciones, "Formato", 13, "bold").grid(row=0, column=0, sticky="w")
        ui.Etiqueta(opciones, "Calidad", 13, "bold").grid(row=0, column=1, sticky="w",
                                                          padx=(20, 0))
        self.formato = ui.Selector(opciones, ["MP3", "MP4"], comando=self._al_cambiar_formato,
                                   width=200)
        self.formato.set(self.ajustes["yt_formato"])
        self.formato.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.calidad = ui.Desplegable(opciones, ["-"], comando=self._al_cambiar_calidad,
                                      width=150)
        self.calidad.grid(row=1, column=1, sticky="w", padx=(20, 0), pady=(8, 0))
        self._al_cambiar_formato(self.formato.get(), guardar=False)

        self.boton = ui.Boton(opciones, "Descargar", self.descargar, "descargar", "primario",
                              alto=44, tamano=14)
        self.boton.grid(row=1, column=2, sticky="e", pady=(8, 0))
        self.boton.boton.configure(width=200)

    def _crear_progreso(self):
        tarjeta = ui.Tarjeta(self)
        tarjeta.grid(row=1, column=0, sticky="nsew")
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=22, pady=20)

        self.titulo_actual = ui.Etiqueta(cuerpo, "Listo para descargar", 14, "bold",
                                         wraplength=700)
        self.titulo_actual.pack(fill="x")
        self.detalle = ui.Etiqueta(cuerpo, "Los archivos se guardan en la carpeta «descargas».",
                                   12, suave=True)
        self.detalle.pack(fill="x", pady=(2, 10))
        self.barra = ctk.CTkProgressBar(cuerpo, height=8, corner_radius=4,
                                        progress_color=ui.ACENTO, fg_color=ui.SECUNDARIO)
        self.barra.set(0)
        self.barra.pack(fill="x")

        self.registro = ctk.CTkTextbox(
            cuerpo, corner_radius=10, border_width=0, fg_color=ui.CAMPO, text_color=ui.TEXTO,
            font=ui.fuente(12), wrap="word", height=120,
        )
        self.registro.pack(fill="both", expand=True, pady=(16, 12))
        self.registro.configure(state="disabled")

        pie = ctk.CTkFrame(cuerpo, fg_color="transparent")
        pie.pack(fill="x")
        ui.Boton(pie, "Abrir carpeta", self._abrir_carpeta, "carpeta", alto=38).pack(side="left")
        self.boton_actualizar = ui.Boton(pie, "Actualizar yt-dlp", self._actualizar, "actualizar",
                                         alto=38)
        self.boton_actualizar.pack(side="right")

    # ------------------------------------------------------- interacción --
    def al_mostrar(self):
        if not self.url.get().strip() and not self.descargador:
            try:
                portapapeles = self.clipboard_get().strip()
            except Exception:
                portapapeles = ""
            if self._parece_youtube(portapapeles):
                self.url.insert(0, portapapeles)
                self._al_cambiar_enlace()
        self.url.focus_set()

    @staticmethod
    def _parece_youtube(texto: str) -> bool:
        return "\n" not in texto and any(d in texto for d in ("youtube.com/", "youtu.be/"))

    def _pegar(self):
        try:
            texto = self.clipboard_get().strip()
        except Exception:
            return
        self.url.delete(0, "end")
        self.url.insert(0, texto)
        self._al_cambiar_enlace()

    def _al_cambiar_enlace(self):
        enlace = analizar_enlace(self.url.get())
        mostrar_selector = enlace.valido and enlace.video and enlace.lista
        if mostrar_selector:
            self.fila_lista.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        else:
            self.fila_lista.grid_remove()

        if not ffmpeg_disponible():
            self._pista("No se ha encontrado ffmpeg: instálalo para poder convertir a MP3/MP4.",
                        ui.AVISO)
        elif not self.url.get().strip():
            self._pista("Consejo: si copias un enlace antes de abrir esta pestaña, se pega solo.")
        elif not enlace.valido:
            self._pista("Eso no parece un enlace.", ui.AVISO)
        elif enlace.lista and enlace.es_mix:
            self._pista("Es un «Mix» automático de YouTube: la lista puede ser muy larga.",
                        ui.AVISO)
        elif enlace.lista and enlace.video:
            self._pista(f"{ui.icono('enlace')}  Vídeo dentro de una lista: elige qué descargar.")
        elif enlace.lista:
            self._pista(f"{ui.icono('lista')}  Lista de reproducción: se descargará entera.")
        elif enlace.video:
            self._pista(f"{ui.icono('video')}  Vídeo individual.")
        else:
            self._pista("Enlace de otra web: se intentará descargar igualmente.")

    def _pista(self, texto, color=ui.TEXTO_SUAVE):
        self.pista.configure(text=texto, text_color=color)

    def _al_cambiar_formato(self, formato, guardar=True):
        if guardar:
            self.ajustes["yt_formato"] = formato
        valores = list(CALIDADES_MP3 if formato == "MP3" else CALIDADES_MP4)
        clave = "yt_calidad_mp3" if formato == "MP3" else "yt_calidad_mp4"
        self.calidad.configure(values=valores)
        actual = self.ajustes[clave]
        self.calidad.set(actual if actual in valores else valores[0])

    def _al_cambiar_calidad(self, valor):
        clave = "yt_calidad_mp3" if self.formato.get() == "MP3" else "yt_calidad_mp4"
        self.ajustes[clave] = valor

    def _abrir_carpeta(self):
        carpeta = self._carpeta_ultima or CARPETA_DESCARGAS
        ui.abrir_en_explorador(asegurar_carpeta(carpeta))

    # ---------------------------------------------------------- descargas --
    def descargar(self):
        if self.descargador:
            return self._cancelar()
        url = self.url.get().strip()
        enlace = analizar_enlace(url)
        if not enlace.valido:
            self._pista("Pega primero un enlace válido.", ui.AVISO)
            self.url.focus_set()
            return

        lista = bool(enlace.lista) and (not enlace.video or self.modo_lista.get() == LISTA_ENTERA)
        peticion = Peticion(url=url, formato=self.formato.get(), calidad=self.calidad.get(),
                            lista_completa=lista, carpeta=asegurar_carpeta(CARPETA_DESCARGAS))
        self.descargador = Descargador(peticion)
        self._carpeta_ultima = None
        self._ultimo_estado = None
        self._limpiar_registro()
        self.barra.set(0)
        self._titulo("Preparando…")
        self._detalle("")
        self.boton.configurar(texto="Cancelar", tipo="peligro", icono_nombre="cancelar")
        self.descargador.start()
        self.after(100, self._leer_eventos)

    def _cancelar(self):
        if self.descargador:
            self.descargador.cancelar()
            self.boton.configurar(texto="Cancelando…", estado="disabled")

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
            return f"{indice} de {total}  ·  "
        return f"N.º {indice}  ·  " if indice else ""

    def _ev_estado(self, texto):
        if texto != self._ultimo_estado:
            self._ultimo_estado = texto
            self._detalle(texto)
            if texto.startswith("Obteniendo"):
                self.barra.configure(mode="indeterminate")
                self.barra.start()

    def _ev_progreso(self, p):
        self._parar_indeterminado()
        self._ultimo_estado = None
        self._titulo(p["titulo"])
        partes = [self._prefijo(p["posicion"]).rstrip(" ·")]
        if p["fraccion"] is not None:
            partes.append(f"{p['fraccion'] * 100:.0f} %")
        if p["pista"]:
            partes.append("pista de audio")
        if v := _bytes_seg(p["velocidad"]):
            partes.append(v)
        if p["eta"]:
            partes.append(f"quedan {_tiempo(p['eta'])}")
        self._detalle("  ·  ".join(x for x in partes if x))
        if p["fraccion"] is not None:
            self.barra.set(p["fraccion"])

    def _ev_procesando(self, p):
        self._titulo(p["titulo"])
        self.barra.set(1)

    def _ev_completado(self, ruta):
        self._carpeta_ultima = ruta.parent
        self._escribir(f"✓  {ruta.name}", "ok")

    def _ev_error(self, mensaje):
        self._escribir(f"✕  {mensaje}", "error")

    def _ev_fin(self, r):
        self._parar_indeterminado()
        self.descargador = None
        self.boton.configurar(texto="Descargar", tipo="primario", icono_nombre="descargar",
                              estado="normal")
        hechos, errores = r["completados"], r["errores"]
        archivos = "archivo" if hechos == 1 else "archivos"
        if r["cancelado"]:
            self._titulo("Descarga cancelada")
            self._detalle(f"Se completaron {hechos} {archivos} antes de cancelar.")
        elif hechos and not errores:
            self._titulo("¡Listo!" if hechos == 1 else f"¡Listo! {hechos} {archivos} descargados")
            self._detalle("Pulsa «Abrir carpeta» para verlos.")
            self.barra.set(1)
        elif hechos:
            self._titulo(f"{hechos} {archivos} descargados, {errores} con errores")
            self._detalle("Algunos vídeos pueden ser privados o no estar disponibles.")
        else:
            self._titulo("No se pudo descargar")
            self._detalle("Revisa el enlace. Si YouTube ha cambiado algo, prueba «Actualizar yt-dlp».")
            self.barra.set(0)

    # -------------------------------------------------------- utilidades --
    def _parar_indeterminado(self):
        if self.barra.cget("mode") == "indeterminate":
            self.barra.stop()
            self.barra.configure(mode="determinate")
            self.barra.set(0)

    def _titulo(self, texto):
        self.titulo_actual.configure(text=texto)

    def _detalle(self, texto):
        self.detalle.configure(text=texto)

    def _limpiar_registro(self):
        self.registro.configure(state="normal")
        self.registro.delete("1.0", "end")
        self.registro.configure(state="disabled")

    def _escribir(self, linea, etiqueta=None):
        oscuro = ctk.get_appearance_mode() == "Dark"
        colores = {"ok": ui.EXITO, "error": ui.ERROR}
        self.registro.configure(state="normal")
        if etiqueta:
            self.registro.tag_config(etiqueta, foreground=colores[etiqueta][int(oscuro)])
        self.registro.insert("end", linea + "\n", etiqueta)
        self.registro.see("end")
        self.registro.configure(state="disabled")

    def _actualizar(self):
        self.boton_actualizar.configurar(texto="Actualizando…", estado="disabled")

        def tarea():
            ok, msg = actualizar_yt_dlp()
            self.after(0, lambda: terminado(ok, msg))

        def terminado(ok, msg):
            self.boton_actualizar.configurar(texto="Actualizar yt-dlp", estado="normal")
            if ok:
                self._escribir("✓  yt-dlp actualizado. Reinicia la app para usar la nueva versión.",
                               "ok")
            else:
                self._escribir(f"✕  No se pudo actualizar yt-dlp: {msg}", "error")

        threading.Thread(target=tarea, daemon=True).start()

    # --------------------------------------------------------------- cierre --
    def puede_cerrar(self) -> bool:
        return self.descargador is None

    def al_cerrar(self):
        if self.descargador:
            self.descargador.cancelar()
