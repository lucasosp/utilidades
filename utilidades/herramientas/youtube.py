"""Descargador de YouTube (MP3 / MP4) con soporte para listas de reproducción."""

import customtkinter as ctk

from .. import ui
from ..config import CARPETA_DESCARGAS, asegurar_carpeta
from .base import Herramienta
from .descarga_base import CALIDADES_MP3, ffmpeg_disponible
from .panel_descarga import PanelDescarga
from .youtube_motor import CALIDADES_MP4, Descargador, Peticion, analizar_enlace

SOLO_VIDEO = "Solo este vídeo"
LISTA_ENTERA = "Toda la lista"


def leer_portapapeles(widget) -> str:
    try:
        return widget.clipboard_get().strip()
    except Exception:
        return ""


class HerramientaYouTube(Herramienta):
    id = "youtube"
    nombre = "YouTube"
    descripcion = "Pega un enlace y descárgalo en MP3 o MP4. También listas de reproducción."
    icono = "video"

    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._crear_formulario()
        self.panel = PanelDescarga(self, CARPETA_DESCARGAS,
                                   "Los archivos se guardan en la carpeta «descargas».")
        self.panel.grid(row=1, column=0, sticky="nsew")
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

    # ------------------------------------------------------- interacción --
    def al_mostrar(self):
        if not self.url.get().strip() and not self.panel.ocupado:
            texto = leer_portapapeles(self)
            if "\n" not in texto and any(d in texto for d in ("youtube.com/", "youtu.be/")):
                self.url.insert(0, texto)
                self._al_cambiar_enlace()
        self.url.focus_set()

    def _pegar(self):
        self.url.delete(0, "end")
        self.url.insert(0, leer_portapapeles(self))
        self._al_cambiar_enlace()

    def _al_cambiar_enlace(self):
        enlace = analizar_enlace(self.url.get())
        if enlace.valido and enlace.video and enlace.lista:
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

    # ---------------------------------------------------------- descargas --
    def descargar(self):
        if self.panel.ocupado:
            self.panel.cancelar()
            self.boton.configurar(texto="Cancelando…", estado="disabled")
            return
        url = self.url.get().strip()
        enlace = analizar_enlace(url)
        if not enlace.valido:
            self._pista("Pega primero un enlace válido.", ui.AVISO)
            self.url.focus_set()
            return

        lista = bool(enlace.lista) and (not enlace.video or self.modo_lista.get() == LISTA_ENTERA)
        peticion = Peticion(url=url, formato=self.formato.get(), calidad=self.calidad.get(),
                            lista_completa=lista, carpeta=asegurar_carpeta(CARPETA_DESCARGAS))
        self.boton.configurar(texto="Cancelar", tipo="peligro", icono_nombre="cancelar")
        self.panel.iniciar(Descargador(peticion), self._al_terminar)

    def _al_terminar(self, _resultado):
        self.boton.configurar(texto="Descargar", tipo="primario", icono_nombre="descargar",
                              estado="normal")

    # --------------------------------------------------------------- cierre --
    def puede_cerrar(self) -> bool:
        return not self.panel.ocupado

    def al_cerrar(self):
        self.panel.cancelar()
