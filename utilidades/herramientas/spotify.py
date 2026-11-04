"""Descargador de Spotify: canciones, álbumes y listas en MP3."""

import threading

import customtkinter as ctk

from .. import ui
from ..config import CARPETA_DESCARGAS, asegurar_carpeta
from .base import Herramienta
from .descarga_base import CALIDADES_MP3, ffmpeg_disponible
from .panel_descarga import PanelDescarga
from .spotify_motor import LIMITE_LISTA, Descargador, Peticion, analizar_enlace, obtener
from .youtube import leer_portapapeles

TIPOS = {"track": "Canción", "album": "Álbum", "playlist": "Lista"}


class HerramientaSpotify(Herramienta):
    id = "spotify"
    nombre = "Spotify"
    descripcion = "Pega una canción, álbum o lista de Spotify y descárgala en MP3."
    icono = "musica"

    def __init__(self, master, app):
        super().__init__(master, app)
        self._consulta = 0          # para descartar respuestas de enlaces antiguos
        self._pendiente = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._crear_formulario()
        self.panel = PanelDescarga(
            self, CARPETA_DESCARGAS,
            "Las canciones se buscan en YouTube y se guardan con la portada y los datos de "
            "Spotify.")
        self.panel.grid(row=1, column=0, sticky="nsew")
        self._al_cambiar_enlace()

    def _crear_formulario(self):
        tarjeta = ui.Tarjeta(self)
        tarjeta.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cuerpo.pack(fill="x", padx=22, pady=20)
        cuerpo.grid_columnconfigure(0, weight=1)

        ui.Etiqueta(cuerpo, "Enlace de Spotify", 13, "bold").grid(row=0, column=0, sticky="w")
        self.url = ui.Campo(cuerpo, placeholder="https://open.spotify.com/track/…")
        self.url.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.url.bind("<KeyRelease>", lambda _e: self._al_cambiar_enlace())
        self.url.bind("<<Paste>>", lambda _e: self.after(10, self._al_cambiar_enlace))
        self.url.bind("<Return>", lambda _e: self.descargar())
        ui.Boton(cuerpo, "Pegar", self._pegar, "pegar", alto=42).grid(
            row=1, column=1, sticky="e", padx=(10, 0), pady=(8, 0))

        self.pista = ui.Etiqueta(cuerpo, "", 12, suave=True)
        self.pista.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        opciones = ctk.CTkFrame(cuerpo, fg_color="transparent")
        opciones.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        opciones.grid_columnconfigure(1, weight=1)
        ui.Etiqueta(opciones, "Calidad del MP3", 13, "bold").grid(row=0, column=0, sticky="w")
        self.calidad = ui.Desplegable(opciones, list(CALIDADES_MP3), width=150,
                                      comando=lambda v: self.ajustes.__setitem__(
                                          "sp_calidad", v))
        guardada = self.ajustes["sp_calidad"]
        self.calidad.set(guardada if guardada in CALIDADES_MP3 else "320 kbps")
        self.calidad.grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.boton = ui.Boton(opciones, "Descargar", self.descargar, "descargar", "primario",
                              alto=44, tamano=14)
        self.boton.grid(row=1, column=1, sticky="e", pady=(8, 0))
        self.boton.boton.configure(width=200)

    # ------------------------------------------------------- interacción --
    def al_mostrar(self):
        if not self.url.get().strip() and not self.panel.ocupado:
            texto = leer_portapapeles(self)
            if "\n" not in texto and analizar_enlace(texto):
                self.url.insert(0, texto)
                self._al_cambiar_enlace()
        self.url.focus_set()

    def _pegar(self):
        self.url.delete(0, "end")
        self.url.insert(0, leer_portapapeles(self))
        self._al_cambiar_enlace()

    def _pista(self, texto, color=ui.TEXTO_SUAVE):
        self.pista.configure(text=texto, text_color=color)

    def _al_cambiar_enlace(self):
        texto = self.url.get().strip()
        self._consulta += 1
        if self._pendiente:
            self.after_cancel(self._pendiente)
            self._pendiente = None
        if not ffmpeg_disponible():
            self._pista("No se ha encontrado ffmpeg: instálalo para poder convertir a MP3.",
                        ui.AVISO)
        elif not texto:
            self._pista("Funciona con canciones, álbumes y listas públicas.")
        elif not analizar_enlace(texto):
            self._pista("Eso no parece un enlace de Spotify.", ui.AVISO)
        else:
            self._pista("Buscando en Spotify…")
            consulta = self._consulta
            self._pendiente = self.after(400, lambda: self._previsualizar(texto, consulta))

    def _previsualizar(self, texto, consulta):
        """Consulta Spotify en segundo plano para enseñar qué se va a descargar."""
        self._pendiente = None

        def tarea():
            try:
                c = obtener(texto)
                if c.tipo == "track":
                    msg, color = f"{ui.icono('musica')}  Canción  ·  {c.nombre}", ui.TEXTO_SUAVE
                else:
                    n = len(c.canciones)
                    msg = (f"{ui.icono('lista')}  {TIPOS[c.tipo]}  ·  {c.nombre}  ·  "
                           f"{n} {'canción' if n == 1 else 'canciones'}")
                    color = ui.TEXTO_SUAVE
                    if c.tipo == "playlist" and n >= LIMITE_LISTA:
                        msg += f" (máximo {LIMITE_LISTA} sin iniciar sesión)"
            except Exception as e:  # noqa: BLE001
                msg, color = f"No se ha podido leer el enlace: {e}", ui.AVISO
            self.after(0, lambda: consulta == self._consulta and self._pista(msg, color))

        threading.Thread(target=tarea, daemon=True).start()

    # ---------------------------------------------------------- descargas --
    def descargar(self):
        if self.panel.ocupado:
            self.panel.cancelar()
            self.boton.configurar(texto="Cancelando…", estado="disabled")
            return
        url = self.url.get().strip()
        if not analizar_enlace(url):
            self._pista("Pega primero un enlace de Spotify.", ui.AVISO)
            self.url.focus_set()
            return
        peticion = Peticion(url=url, calidad=self.calidad.get(),
                            carpeta=asegurar_carpeta(CARPETA_DESCARGAS))
        self.boton.configurar(texto="Cancelar", tipo="peligro", icono_nombre="cancelar")
        self.panel.iniciar(Descargador(peticion), self._al_terminar)

    def _al_terminar(self, _resultado):
        self.boton.configurar(texto="Descargar", tipo="primario", icono_nombre="descargar",
                              estado="normal")

    def puede_cerrar(self) -> bool:
        return not self.panel.ocupado

    def al_cerrar(self):
        self.panel.cancelar()
