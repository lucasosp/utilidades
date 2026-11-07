"""Texto a voz con Chatterbox (local, multilingüe y con clonación de voz)."""

import queue
import sys
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from .. import ui
from ..config import CARPETA_AUDIOS, CARPETA_VOCES, asegurar_carpeta
from ..voz import motor
from .base import Herramienta
from .qr_motor import nombre_seguro, ruta_libre

VOZ_BASE = "Predeterminada"
PREVIA = motor.VENV_VOZ / "ultimo.wav"
EXTENSIONES_AUDIO = ("*.wav", "*.mp3", "*.m4a", "*.ogg", "*.opus", "*.flac", "*.aac", "*.webm",
                     "*.mp4")


voces_guardadas = motor.voces_guardadas


class HerramientaVoz(Herramienta):
    id = "voz"
    nombre = "Texto a voz"
    descripcion = "Escribe un texto y conviértelo en audio con una voz natural. Puede clonar voces."
    icono = "voz"

    def __init__(self, master, app):
        super().__init__(master, app)
        self.motor: motor.MotorVoz | None = None
        self.instalador: motor.Instalador | None = None
        self._peticion = None        # id de la generación en curso
        self._destino = None         # archivo final de la generación en curso
        self._ultimo = None          # último archivo generado
        self._parar_audio = None     # after() que restaura el botón de reproducir

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.vista_instalar = self._crear_vista_instalar()
        self.vista_principal = None
        if motor.instalado():
            self._mostrar_principal()
        else:
            self.vista_instalar.grid(row=0, column=0, sticky="nsew")

    # ======================================================== instalación ==
    def _crear_vista_instalar(self):
        tarjeta = ui.Tarjeta(self)
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=28, pady=26)

        ui.Etiqueta(cuerpo, "Falta instalar el motor de voz", 17, "bold").pack(fill="x")
        gpu = motor.tiene_gpu_nvidia()
        texto = (
            "Para que la voz suene natural, la app usa Chatterbox, un modelo de voz libre "
            "(licencia MIT) que funciona entero en tu ordenador: el texto no sale de tu PC.\n\n"
            "La primera vez hay que descargar PyTorch y el modelo: unos "
            f"{'6' if gpu else '4'} GB en total. Se guarda todo dentro de la carpeta del "
            "proyecto (.venv-voz y .modelos), así que si algún día no lo quieres basta con "
            "borrar esas dos carpetas."
        )
        ui.Etiqueta(cuerpo, texto, 13, suave=True, wraplength=640).pack(fill="x", pady=(10, 14))
        aviso = ("✓  Tarjeta NVIDIA detectada: generará la voz rápido." if gpu else
                 "•  No se ha detectado tarjeta NVIDIA: funcionará con el procesador, pero "
                 "bastante más lento.")
        ui.Etiqueta(cuerpo, aviso, 12, "bold", text_color=ui.EXITO if gpu else ui.AVISO
                    ).pack(fill="x")

        self.boton_instalar = ui.Boton(cuerpo, "Instalar motor de voz", self._instalar,
                                       "descargar", "primario", alto=44, tamano=14)
        self.boton_instalar.pack(anchor="w", pady=(22, 16))
        self.boton_instalar.boton.configure(width=240)

        self.paso = ui.Etiqueta(cuerpo, "", 13, "bold")
        self.paso.pack(fill="x")
        self.barra_instalar = ctk.CTkProgressBar(cuerpo, height=8, corner_radius=4,
                                                 progress_color=ui.ACENTO,
                                                 fg_color=ui.SECUNDARIO, mode="indeterminate")
        self.registro_instalar = ctk.CTkTextbox(
            cuerpo, corner_radius=10, border_width=0, fg_color=ui.CAMPO,
            text_color=ui.TEXTO_SUAVE, font=ctk.CTkFont(family="Consolas", size=11),
            wrap="none", height=60,
        )
        return tarjeta

    def _instalar(self):
        if self.instalador:
            return
        self.boton_instalar.configurar(texto="Instalando…", estado="disabled")
        self.barra_instalar.pack(fill="x", pady=(8, 12))
        self.barra_instalar.start()
        self.registro_instalar.pack(fill="both", expand=True)
        self.instalador = motor.Instalador()
        self.instalador.start()
        self.after(150, self._leer_instalador)

    def _leer_instalador(self):
        try:
            while True:
                tipo, datos = self.instalador.eventos.get_nowait()
                if tipo == "paso":
                    self.paso.configure(text=datos, text_color=ui.TEXTO)
                elif tipo == "linea":
                    self.registro_instalar.insert("end", datos + "\n")
                    self.registro_instalar.see("end")
                elif tipo == "fin":
                    self.instalador = None
                    self.barra_instalar.stop()
                    if datos:
                        self.vista_instalar.grid_remove()
                        self._mostrar_principal()
                        self.al_mostrar()
                    else:
                        self.paso.configure(text="La instalación no se ha completado. Revisa "
                                                 "tu conexión y vuelve a intentarlo.",
                                            text_color=ui.ERROR)
                        self.boton_instalar.configurar(texto="Reintentar", estado="normal")
                    return
        except queue.Empty:
            pass
        self.after(150, self._leer_instalador)

    # ========================================================== principal ==
    def _mostrar_principal(self):
        if self.vista_principal is None:
            self.vista_principal = self._crear_vista_principal()
        self.vista_principal.grid(row=0, column=0, sticky="nsew")

    def _crear_vista_principal(self):
        vista = ctk.CTkFrame(self, fg_color="transparent")
        vista.grid_columnconfigure(0, weight=1)
        vista.grid_rowconfigure(0, weight=1)

        # --- Texto ---------------------------------------------------------
        tarjeta = ui.Tarjeta(vista)
        tarjeta.grid(row=0, column=0, sticky="nsew", pady=(0, 16))
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=22, pady=(18, 18))
        cabecera = ctk.CTkFrame(cuerpo, fg_color="transparent")
        cabecera.pack(fill="x")
        ui.Etiqueta(cabecera, "Texto", 13, "bold").pack(side="left")
        self.contador = ui.Etiqueta(cabecera, "", 12, suave=True)
        self.contador.pack(side="right")
        self.texto = ctk.CTkTextbox(
            cuerpo, corner_radius=10, border_width=1, border_color=ui.BORDE, fg_color=ui.CAMPO,
            text_color=ui.TEXTO, font=ui.fuente(14), wrap="word",
        )
        self.texto.pack(fill="both", expand=True, pady=(8, 0))
        self.texto.bind("<KeyRelease>", lambda _e: self._contar())
        self.texto.bind("<<Paste>>", lambda _e: self.after(10, self._contar))
        self.texto.bind("<Control-Return>", lambda _e: (self.generar(), "break")[1])
        self.texto.bind("<FocusIn>", lambda _e: self.texto.configure(border_color=ui.ACENTO))
        self.texto.bind("<FocusOut>", lambda _e: self.texto.configure(border_color=ui.BORDE))

        # --- Opciones y acciones ------------------------------------------
        tarjeta = ui.Tarjeta(vista)
        tarjeta.grid(row=1, column=0, sticky="ew")
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cuerpo.pack(fill="x", padx=22, pady=18)

        opciones = ctk.CTkFrame(cuerpo, fg_color="transparent")
        opciones.pack(fill="x")
        for col, texto in enumerate(("Voz", "", "Idioma", "Expresividad", "Formato")):
            if texto:
                ui.Etiqueta(opciones, texto, 13, "bold").grid(
                    row=0, column=col, sticky="w", padx=(0 if col == 0 else 14, 0))

        self.voz = ui.Desplegable(opciones, [VOZ_BASE], width=170, comando=self._elegir_voz)
        self.voz.grid(row=1, column=0, sticky="w", pady=(8, 0))
        botones_voz = ctk.CTkFrame(opciones, fg_color="transparent")
        botones_voz.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(8, 0))
        for glifo, texto, cmd in ((ui.icono("anadir") or "+", "Añadir voz", self._anadir_voz),
                                  (ui.icono("carpeta") or "…", "Carpeta de voces",
                                   lambda: ui.abrir_en_explorador(asegurar_carpeta(CARPETA_VOCES)))):
            b = ctk.CTkButton(botones_voz, text=glifo, width=36, height=36, corner_radius=10,
                              font=ui.fuente_icono(14), fg_color=ui.SECUNDARIO,
                              hover_color=ui.SECUNDARIO_HOVER, text_color=ui.TEXTO, command=cmd)
            b.pack(side="left", padx=(0, 6))
            ui.Consejo(b, texto)

        self.idioma = ui.Desplegable(opciones, list(motor.IDIOMAS), width=120,
                                     comando=lambda v: self.ajustes.__setitem__("voz_idioma", v))
        self.idioma.set(self.ajustes["voz_idioma"] if self.ajustes["voz_idioma"] in motor.IDIOMAS
                        else "Español")
        self.idioma.grid(row=1, column=2, sticky="w", padx=(14, 0), pady=(8, 0))

        fila_exp = ctk.CTkFrame(opciones, fg_color="transparent")
        fila_exp.grid(row=1, column=3, sticky="w", padx=(14, 0), pady=(8, 0))
        self.expresividad = ctk.CTkSlider(
            fila_exp, from_=0.25, to=1.0, number_of_steps=15, width=110,
            progress_color=ui.ACENTO, button_color=ui.ACENTO, button_hover_color=ui.ACENTO_HOVER,
            fg_color=ui.SECUNDARIO, command=self._cambiar_expresividad,
        )
        self.expresividad.set(float(self.ajustes["voz_expresividad"]))
        self.expresividad.pack(side="left")
        self.valor_exp = ui.Etiqueta(fila_exp, "", 12, suave=True, width=50)
        self.valor_exp.pack(side="left", padx=(8, 0))
        self._cambiar_expresividad(self.expresividad.get(), guardar=False)

        self.formato = ui.Selector(opciones, ["MP3", "WAV"], width=100,
                                   comando=lambda v: self.ajustes.__setitem__("voz_formato", v))
        self.formato.set(self.ajustes["voz_formato"])
        self.formato.grid(row=1, column=4, sticky="w", padx=(14, 0), pady=(8, 0))

        # Progreso + botón principal
        accion = ctk.CTkFrame(cuerpo, fg_color="transparent")
        accion.pack(fill="x", pady=(18, 0))
        accion.grid_columnconfigure(0, weight=1)
        self.estado = ui.Etiqueta(accion, "", 12, suave=True)
        self.estado.grid(row=0, column=0, sticky="ew", padx=(0, 16))
        self.barra = ctk.CTkProgressBar(accion, height=8, corner_radius=4,
                                        progress_color=ui.ACENTO, fg_color=ui.SECUNDARIO)
        self.barra.set(0)
        self.barra.grid(row=1, column=0, sticky="ew", padx=(0, 16), pady=(6, 0))
        self.boton = ui.Boton(accion, "Generar audio", self.generar, "voz", "primario", alto=44,
                              tamano=14)
        self.boton.grid(row=0, column=1, rowspan=2, sticky="e")
        self.boton.boton.configure(width=200)

        # Resultado
        self.fila_resultado = ctk.CTkFrame(cuerpo, fg_color=ui.CAMPO, corner_radius=10)
        self.resultado = ui.Etiqueta(self.fila_resultado, "", 12, "bold", text_color=ui.EXITO)
        self.resultado.pack(side="left", padx=14, pady=10)
        ui.Boton(self.fila_resultado, "Abrir carpeta", self._abrir_resultado, "carpeta",
                 alto=34, tamano=12).pack(side="right", padx=(0, 8), pady=6)
        self.boton_play = ui.Boton(self.fila_resultado, "Escuchar", self._reproducir, "play",
                                   alto=34, tamano=12)
        self.boton_play.pack(side="right", padx=(0, 8), pady=6)

        self._cargar_voces(self.ajustes["voz_voz"])
        self._contar()
        return vista

    # ------------------------------------------------------------ opciones --
    def _contar(self):
        n = len(self._contenido())
        self.contador.configure(text=f"{n} caracteres" if n else "Ctrl+Enter para generar")

    def _contenido(self) -> str:
        return self.texto.get("1.0", "end").strip()

    def _cambiar_expresividad(self, valor, guardar=True):
        valor = round(float(valor), 2)
        etiqueta = "Neutra" if valor < 0.4 else "Normal" if valor < 0.65 else "Intensa"
        self.valor_exp.configure(text=etiqueta)
        if guardar:
            self.ajustes["voz_expresividad"] = valor

    def _cargar_voces(self, seleccion=None):
        nombres = [VOZ_BASE] + list(voces_guardadas())
        self.voz.configure(values=nombres)
        self.voz.set(seleccion if seleccion in nombres else VOZ_BASE)

    def _elegir_voz(self, nombre):
        self.ajustes["voz_voz"] = nombre

    def _anadir_voz(self):
        ruta = filedialog.askopenfilename(
            parent=self.winfo_toplevel(), title="Elige un audio con la voz (10-20 segundos)",
            filetypes=[("Audio", " ".join(EXTENSIONES_AUDIO)), ("Todos", "*.*")],
        )
        if not ruta:
            return
        dialogo = ctk.CTkInputDialog(
            title="Nueva voz",
            text="¿Cómo quieres llamar a esta voz?\n\nUsa solo tu voz o la de alguien que te "
                 "haya dado permiso.",
            font=ui.fuente(13), button_fg_color=ui.ACENTO, button_hover_color=ui.ACENTO_HOVER,
        )
        nombre = nombre_seguro(dialogo.get_input() or "", 40).replace("_", " ").strip()
        if not nombre:
            return
        self._estado(f"Preparando la voz «{nombre}»…")

        def convertir():
            try:
                motor.anadir_voz(Path(ruta), nombre)
                ok, error = True, ""
            except (OSError, RuntimeError) as e:
                ok, error = False, str(e)
            self.after(0, lambda: terminado(ok, error))

        def terminado(ok, error):
            if ok:
                self._cargar_voces(nombre)
                self._elegir_voz(nombre)
                self._estado(f"✓  Voz «{nombre}» añadida. Ya puedes usarla.", ui.EXITO)
            else:
                self._estado(f"No se pudo leer ese audio: {error[:120]}", ui.ERROR)

        threading.Thread(target=convertir, daemon=True).start()

    # ------------------------------------------------------------ generar --
    def al_mostrar(self):
        if self.vista_principal is None:
            return
        self._arrancar_motor()
        self.texto.focus_set()

    def _arrancar_motor(self):
        if self.motor and self.motor.vivo:
            return
        self.motor = motor.MotorVoz()
        self._estado("Cargando el modelo de voz…")
        self.after(100, self._leer_motor)

    def generar(self):
        if self._peticion is not None:
            self.motor.cancelar()
            self.boton.configurar(texto="Cancelando…", estado="disabled")
            return
        texto = self._contenido()
        if not texto:
            self._estado("Escribe primero el texto que quieres oír.", ui.AVISO)
            self.texto.focus_set()
            return
        self._arrancar_motor()
        self._parar_reproduccion()

        base = "voz_" + (nombre_seguro(texto, 40) or "audio")
        self._destino = ruta_libre(asegurar_carpeta(CARPETA_AUDIOS), base,
                                   self.formato.get().lower())

        voz = voces_guardadas().get(self.voz.get())
        self._peticion = self.motor.generar(
            texto, motor.IDIOMAS.get(self.idioma.get(), "es"), voz,
            round(self.expresividad.get(), 2), PREVIA,
        )
        self.fila_resultado.pack_forget()
        self.barra.set(0)
        self.boton.configurar(texto="Cancelar", tipo="peligro", icono_nombre="cancelar")
        if not self._listo:
            self._estado("Cargando el modelo de voz… (empezará en cuanto esté listo)")

    _listo = False

    def _leer_motor(self):
        m = self.motor
        if m is None:
            return
        try:
            while True:
                ev = m.eventos.get_nowait()
                getattr(self, f"_ev_{ev['ev']}", lambda _e: None)(ev)
                if ev["ev"] == "cerrado":
                    return
        except queue.Empty:
            pass
        self.after(100, self._leer_motor)

    def _ev_estado(self, ev):
        if self._peticion is None or not self._listo:
            self._estado(ev["texto"])
            self.barra.configure(mode="indeterminate")
            self.barra.start()

    def _ev_listo(self, ev):
        self._listo = True
        self._parar_indeterminado()
        quien = {"cuda": "la tarjeta gráfica", "mps": "la GPU", "cpu": "el procesador"}
        if self._peticion is None:
            self._estado(f"Modelo listo (usando {quien.get(ev['dispositivo'], ev['dispositivo'])}).")
        else:
            self._estado("Generando…")

    def _ev_progreso(self, ev):
        if ev.get("id") != self._peticion:
            return
        self._parar_indeterminado()
        hecho, total = ev["hecho"], ev["total"]
        self.barra.set(hecho / total if total else 0)
        frases = "fragmento" if total == 1 else "fragmentos"
        self._estado(f"Generando…  {hecho} de {total} {frases}")

    def _ev_terminado(self, ev):
        if ev.get("id") != self._peticion:
            return
        self._estado("Guardando…")
        destino, segundos = self._destino, ev["segundos"]

        def guardar():
            try:
                motor.exportar(PREVIA, destino)
                error = None
            except (OSError, RuntimeError) as e:
                error = str(e)
            self.after(0, lambda: self._guardado(destino, segundos, error))

        threading.Thread(target=guardar, daemon=True).start()

    def _guardado(self, destino: Path, segundos, error):
        self._fin_peticion()
        if error:
            self._estado(f"No se pudo guardar el audio: {error[:150]}", ui.ERROR)
            return
        self._ultimo = destino
        self.barra.set(1)
        self._estado("")
        self.resultado.configure(text=f"✓  {destino.name}  ·  {segundos:.0f} s")
        self.fila_resultado.pack(fill="x", pady=(14, 0))

    def _ev_cancelado(self, ev):
        if ev.get("id") == self._peticion:
            self._fin_peticion()
            self.barra.set(0)
            self._estado("Cancelado.")

    def _ev_error(self, ev):
        if ev.get("id") in (self._peticion, None):
            self._fin_peticion()
            self._parar_indeterminado()
            self._estado(ev["texto"][:200], ui.ERROR)

    def _ev_cerrado(self, ev):
        self._listo = False
        if self._peticion is not None or ev.get("codigo"):
            self._fin_peticion()
            self._parar_indeterminado()
            self._estado(f"El motor de voz se ha cerrado inesperadamente. Detalles en "
                         f"{motor.REGISTRO.relative_to(motor.VENV_VOZ.parent)}", ui.ERROR)
        self.motor = None

    def _fin_peticion(self):
        self._peticion = None
        self.boton.configurar(texto="Generar audio", tipo="primario", icono_nombre="voz",
                              estado="normal")

    # -------------------------------------------------------- reproducir --
    def _reproducir(self):
        if self._parar_audio:
            return self._parar_reproduccion()
        if sys.platform != "win32" or not PREVIA.exists():
            if self._ultimo:
                ui.abrir_archivo(self._ultimo)
            return
        import wave
        import winsound
        with wave.open(str(PREVIA)) as w:
            duracion = w.getnframes() / w.getframerate()
        winsound.PlaySound(str(PREVIA), winsound.SND_FILENAME | winsound.SND_ASYNC)
        self.boton_play.configurar(texto="Detener", icono_nombre="parar")
        self._parar_audio = self.after(int(duracion * 1000) + 200, self._parar_reproduccion)

    def _parar_reproduccion(self):
        if self._parar_audio:
            self.after_cancel(self._parar_audio)
            self._parar_audio = None
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(None, 0)
            self.boton_play.configurar(texto="Escuchar", icono_nombre="play")

    def _abrir_resultado(self):
        if self._ultimo:
            ui.abrir_en_explorador(self._ultimo, seleccionar=True)
        else:
            ui.abrir_en_explorador(asegurar_carpeta(CARPETA_AUDIOS))

    # -------------------------------------------------------- utilidades --
    def _estado(self, texto, color=ui.TEXTO_SUAVE):
        self.estado.configure(text=texto, text_color=color)

    def _parar_indeterminado(self):
        if self.barra.cget("mode") == "indeterminate":
            self.barra.stop()
            self.barra.configure(mode="determinate")
            self.barra.set(0)

    # ------------------------------------------------------------ cierre --
    def puede_cerrar(self) -> bool:
        return self._peticion is None and self.instalador is None

    def al_cerrar(self):
        self._parar_reproduccion()
        if self.instalador:
            self.instalador.cancelar()
        if self.motor:
            self.motor.cerrar()
