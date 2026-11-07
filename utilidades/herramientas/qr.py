"""Generador de códigos QR con vista previa en directo."""

import re
from tkinter import colorchooser

import customtkinter as ctk
from PIL import Image, ImageDraw

from .. import ui
from ..config import CARPETA_QR, asegurar_carpeta
from .base import Herramienta
from .qr_motor import (BLANCO, NEGRO, aviso_contraste, generar_qr, nombre_desde_contenido,
                       nombre_seguro, ruta_libre)

def fondo_cuadriculado(tam: int, celda: int = 10) -> Image.Image:
    img = Image.new("RGBA", (tam, tam), "#FFFFFF")
    d = ImageDraw.Draw(img)
    for y in range(0, tam, celda):
        for x in range(0, tam, celda):
            if (x // celda + y // celda) % 2:
                d.rectangle([x, y, x + celda - 1, y + celda - 1], fill="#E6E8EE")
    return img


class HerramientaQR(Herramienta):
    id = "qr"
    nombre = "Códigos QR"
    descripcion = "Escribe un enlace o un texto y guárdalo como imagen PNG."
    icono = "qr"

    def __init__(self, master, app):
        super().__init__(master, app)
        self.imagen = None            # PIL.Image a resolución completa
        self._pendiente = None        # id del after() para la vista previa
        self.tam_previa = 260

        self.grid_columnconfigure(0, weight=3, uniform="col")
        self.grid_columnconfigure(1, weight=2, uniform="col")
        self.grid_rowconfigure(0, weight=1)

        self._crear_formulario()
        self._crear_previa()
        self._actualizar_previa()

    # ------------------------------------------------------------------ UI --
    def _crear_formulario(self):
        tarjeta = ui.Tarjeta(self)
        tarjeta.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tarjeta.grid_columnconfigure(0, weight=1)
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=22, pady=20)

        ui.Etiqueta(cuerpo, "Contenido", 13, "bold").pack(fill="x")
        ui.Etiqueta(cuerpo, "Un enlace, un texto, un teléfono… lo que quieras.", 12,
                    suave=True).pack(fill="x", pady=(0, 8))
        self.texto = ctk.CTkTextbox(
            cuerpo, height=110, corner_radius=10, border_width=1, border_color=ui.BORDE,
            fg_color=ui.CAMPO, text_color=ui.TEXTO, font=ui.fuente(13), wrap="word",
        )
        self.texto.pack(fill="x")
        self.texto.bind("<KeyRelease>", lambda _e: self._programar_previa())
        self.texto.bind("<<Paste>>", lambda _e: self.after(10, self._programar_previa))
        self.texto.bind("<Control-Return>", lambda _e: (self.guardar(), "break")[1])
        self.texto.bind("<FocusIn>", lambda _e: self.texto.configure(border_color=ui.ACENTO))
        self.texto.bind("<FocusOut>", lambda _e: self.texto.configure(border_color=ui.BORDE))

        ui.Etiqueta(cuerpo, "Nombre del archivo", 13, "bold").pack(fill="x", pady=(18, 0))
        ui.Etiqueta(cuerpo, "Opcional. Si lo dejas vacío se genera uno a partir del contenido.",
                    12, suave=True).pack(fill="x", pady=(0, 8))
        self.nombre_archivo = ui.Campo(cuerpo, placeholder="p. ej. qr_instagram")
        self.nombre_archivo.pack(fill="x")
        self.nombre_archivo.bind("<Return>", lambda _e: self.guardar())

        # Colores: por defecto negro sobre blanco; las opciones solo salen si se piden.
        self.fila_personalizar = ctk.CTkFrame(cuerpo, fg_color="transparent")
        self.fila_personalizar.pack(fill="x", pady=(18, 0))
        self.personalizar = ctk.CTkSwitch(
            self.fila_personalizar, text="Personalizar colores", font=ui.fuente(13, "bold"),
            text_color=ui.TEXTO, progress_color=ui.ACENTO, command=self._cambiar_personalizar,
        )
        self.personalizar.pack(side="left")
        self.panel_colores = self._crear_panel_colores(cuerpo)
        if self.ajustes["qr_personalizar"]:
            self.personalizar.select()
            self.panel_colores.pack(fill="x", pady=(10, 0), after=self.fila_personalizar)

        ctk.CTkFrame(cuerpo, fg_color="transparent", height=1).pack(fill="both", expand=True)

        botones = ctk.CTkFrame(cuerpo, fg_color="transparent")
        botones.pack(fill="x", pady=(16, 0))
        botones.grid_columnconfigure(0, weight=3)
        botones.grid_columnconfigure(1, weight=2)
        self.boton_guardar = ui.Boton(botones, "Guardar PNG", self.guardar, "guardar", "primario",
                                      alto=44)
        self.boton_guardar.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ui.Boton(botones, "Abrir carpeta", lambda: ui.abrir_en_explorador(
            asegurar_carpeta(CARPETA_QR)), "carpeta", alto=44).grid(row=0, column=1, sticky="ew")

        self.estado = ui.Etiqueta(cuerpo, "", 12, suave=True)
        self.estado.pack(fill="x", pady=(10, 0))

    def _crear_panel_colores(self, master):
        panel = ctk.CTkFrame(master, fg_color=ui.CAMPO, corner_radius=12)
        panel.grid_columnconfigure(3, weight=1)
        self._filas_color = {}
        for fila, (clave, texto) in enumerate((("qr_color", "Código"), ("qr_fondo", "Fondo"))):
            ui.Etiqueta(panel, texto, 12, "bold", width=60).grid(
                row=fila, column=0, sticky="w", padx=(14, 8), pady=(12 if fila == 0 else 6, 6))
            muestra = ctk.CTkButton(
                panel, text="", width=34, height=30, corner_radius=8, border_width=1,
                border_color=ui.BORDE, command=lambda c=clave: self._abrir_selector(c),
            )
            muestra.grid(row=fila, column=1, padx=(0, 8))
            campo = ui.Campo(panel, height=30, width=100)
            campo.grid(row=fila, column=2, sticky="w")
            campo.bind("<Return>", lambda _e, c=clave: self._color_desde_campo(c))
            campo.bind("<FocusOut>", lambda _e, c=clave: self._color_desde_campo(c), add="+")
            self._filas_color[clave] = (muestra, campo)

        self.transparente = ctk.CTkSwitch(
            panel, text="Transparente", font=ui.fuente(12), text_color=ui.TEXTO,
            progress_color=ui.ACENTO, command=self._cambiar_transparencia,
        )
        if self.ajustes["qr_transparente"]:
            self.transparente.select()
        self.transparente.grid(row=1, column=3, sticky="w", padx=(14, 0))

        restablecer = ctk.CTkButton(
            panel, text="Restablecer", width=90, height=28, corner_radius=8,
            font=ui.fuente(12), fg_color="transparent", hover_color=ui.SECUNDARIO,
            text_color=ui.TEXTO_SUAVE, command=self._restablecer_colores,
        )
        restablecer.grid(row=0, column=3, sticky="e", padx=(0, 10), pady=(12, 6))
        ctk.CTkFrame(panel, fg_color="transparent", width=1, height=6).grid(row=2, column=0)
        self._pintar_colores()
        return panel

    def _crear_previa(self):
        tarjeta = ui.Tarjeta(self)
        tarjeta.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=22, pady=20)

        ui.Etiqueta(cuerpo, "Vista previa", 13, "bold").pack(fill="x")
        marco = ctk.CTkFrame(cuerpo, fg_color=ui.CAMPO, corner_radius=12)
        marco.pack(fill="both", expand=True, pady=(10, 10))
        marco.bind("<Configure>", self._al_redimensionar)
        self.previa = ctk.CTkLabel(marco, text="", font=ui.fuente(13), text_color=ui.TEXTO_SUAVE)
        self.previa.place(relx=0.5, rely=0.5, anchor="center")
        self.info = ui.Etiqueta(cuerpo, "", 12, suave=True, anchor="center", justify="center",
                                wraplength=280)
        self.info.pack(fill="x")

    # -------------------------------------------------------------- lógica --
    def al_mostrar(self):
        self.texto.focus_set()

    def _contenido(self) -> str:
        return self.texto.get("1.0", "end").strip()

    # Colores ---------------------------------------------------------------
    def _colores(self) -> tuple[str, str | None]:
        """(color del código, color del fondo o None si es transparente)."""
        if not self.personalizar.get():
            return NEGRO, BLANCO
        fondo = None if self.transparente.get() else self.ajustes["qr_fondo"]
        return self.ajustes["qr_color"], fondo

    def _pintar_colores(self):
        for clave, (muestra, campo) in self._filas_color.items():
            color = self.ajustes[clave]
            muestra.configure(fg_color=color, hover_color=color)
            campo.delete(0, "end")
            campo.insert(0, color.upper())
        transparente = bool(self.transparente.get())
        muestra, campo = self._filas_color["qr_fondo"]
        muestra.configure(state="disabled" if transparente else "normal")
        campo.configure(state="disabled" if transparente else "normal")

    def _poner_color(self, clave, color):
        self.ajustes[clave] = color.lower()
        self._pintar_colores()
        self._actualizar_previa()

    def _abrir_selector(self, clave):
        titulo = "Color del código" if clave == "qr_color" else "Color del fondo"
        _rgb, color = colorchooser.askcolor(self.ajustes[clave], title=titulo,
                                            parent=self.winfo_toplevel())
        if color:
            self._poner_color(clave, color)

    def _color_desde_campo(self, clave):
        _muestra, campo = self._filas_color[clave]
        texto = campo.get().strip().lstrip("#")
        if len(texto) == 3:
            texto = "".join(c * 2 for c in texto)
        if re.fullmatch(r"[0-9a-fA-F]{6}", texto):
            if f"#{texto.lower()}" != self.ajustes[clave]:
                self._poner_color(clave, f"#{texto}")
        else:
            self._pintar_colores()  # valor no válido: se vuelve al anterior

    def _restablecer_colores(self):
        self.ajustes["qr_color"], self.ajustes["qr_fondo"] = NEGRO, BLANCO
        self.transparente.deselect()
        self.ajustes["qr_transparente"] = False
        self._pintar_colores()
        self._actualizar_previa()

    def _cambiar_personalizar(self):
        activo = bool(self.personalizar.get())
        self.ajustes["qr_personalizar"] = activo
        if activo:
            self.panel_colores.pack(fill="x", pady=(10, 0), after=self.fila_personalizar)
        else:
            self.panel_colores.pack_forget()
        self._actualizar_previa()

    def _cambiar_transparencia(self):
        self.ajustes["qr_transparente"] = bool(self.transparente.get())
        self._pintar_colores()
        self._actualizar_previa()

    def _al_redimensionar(self, evento):
        # La vista previa ocupa el hueco disponible (dejando margen).
        escala = ctk.ScalingTracker.get_widget_scaling(self)
        lado = int(min(evento.width, evento.height) / escala) - 20
        lado = max(140, min(lado, 420))
        if abs(lado - self.tam_previa) > 4:
            self.tam_previa = lado
            self._programar_previa()

    def _programar_previa(self):
        if self._pendiente:
            self.after_cancel(self._pendiente)
        self._pendiente = self.after(180, self._actualizar_previa)

    def _generar(self, contenido: str) -> tuple[Image.Image, int]:
        return generar_qr(contenido, *self._colores())

    def _actualizar_previa(self):
        self._pendiente = None
        contenido = self._contenido()
        if not contenido:
            self.imagen = None
            self.previa.configure(image=None, text="Aquí aparecerá\ntu código QR")
            self.info.configure(text="")
            self.boton_guardar.configurar(estado="disabled")
            return
        try:
            self.imagen, version = self._generar(contenido)
        except Exception as e:  # texto demasiado largo, etc.
            self.imagen = None
            self.previa.configure(image=None, text="No se puede generar")
            self.info.configure(text=str(e), text_color=ui.ERROR)
            self.boton_guardar.configurar(estado="disabled")
            return

        tam = self.tam_previa * 2  # el doble para que se vea nítido en pantallas HiDPI
        muestra = self.imagen.resize((tam, tam), Image.Resampling.NEAREST)
        if self._colores()[1] is None:
            fondo = fondo_cuadriculado(tam, celda=16)
            fondo.alpha_composite(muestra)
            muestra = fondo
        self._ctk_img = ctk.CTkImage(muestra, size=(self.tam_previa, self.tam_previa))
        self.previa.configure(image=self._ctk_img, text="")
        lado = self.imagen.size[0]
        texto = f"{lado}×{lado} px  ·  versión {version}  ·  {len(contenido)} caracteres"
        color = ui.TEXTO_SUAVE
        if aviso := aviso_contraste(*self._colores()):
            texto, color = f"{texto}\n{aviso}", ui.AVISO
        self.info.configure(text=texto, text_color=color)
        self.boton_guardar.configurar(estado="normal")

    def guardar(self):
        if self._pendiente:
            self.after_cancel(self._pendiente)
            self._actualizar_previa()
        if self.imagen is None:
            self._mostrar_estado("Escribe algo primero.", ui.AVISO)
            return

        base = nombre_seguro(self.nombre_archivo.get(), 60) or nombre_desde_contenido(
            self._contenido())
        ruta = ruta_libre(asegurar_carpeta(CARPETA_QR), base, "png")
        try:
            self.imagen.save(ruta, format="PNG")
        except OSError as e:
            self._mostrar_estado(f"No se pudo guardar: {e}", ui.ERROR)
            return
        self._ultimo = ruta
        self._mostrar_estado(f"✓  Guardado como {ruta.name}  —  clic para verlo", ui.EXITO,
                             clicable=True)

    def _mostrar_estado(self, texto, color, clicable=False):
        self.estado.configure(text=texto, text_color=color,
                              cursor="hand2" if clicable else "")
        self.estado.unbind("<Button-1>")
        if clicable:
            self.estado.bind("<Button-1>",
                             lambda _e: ui.abrir_en_explorador(self._ultimo, seleccionar=True))
