"""Generador de códigos QR con vista previa en directo."""

import re
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

import customtkinter as ctk
import qrcode
from PIL import Image, ImageDraw

from .. import ui
from ..config import CARPETA_QR, asegurar_carpeta
from .base import Herramienta

COLORES = ["#111111", "#5B5BF0", "#2563EB", "#0F9D58", "#E11D48", "#EA580C", "#7C3AED"]


def nombre_seguro(texto: str, maximo: int = 40) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^\w\s-]", "", texto.lower())
    texto = re.sub(r"[\s_-]+", "_", texto).strip("_")
    return texto[:maximo].rstrip("_")


def nombre_desde_contenido(contenido: str) -> str:
    contenido = contenido.strip()
    url = urlparse(contenido if "://" in contenido else "")
    if url.netloc:
        dominio = url.netloc.removeprefix("www.").split(".")[0]
        ruta = next((p for p in url.path.split("/") if p), "")
        return nombre_seguro(f"{dominio} {ruta}") or "qr"
    return nombre_seguro(contenido) or "qr"


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
        self.color = self.ajustes["qr_color"]
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

        ui.Etiqueta(cuerpo, "Estilo", 13, "bold").pack(fill="x", pady=(18, 8))
        fila = ctk.CTkFrame(cuerpo, fg_color="transparent")
        fila.pack(fill="x")
        self._muestras = {}
        for color in COLORES:
            b = ctk.CTkButton(
                fila, text="", width=30, height=30, corner_radius=15, fg_color=color,
                hover_color=color, border_width=3, border_color=ui.TARJETA,
                command=lambda c=color: self._elegir_color(c),
            )
            b.pack(side="left", padx=(0, 8))
            self._muestras[color] = b
        self._marcar_color()

        self.transparente = ctk.CTkSwitch(
            fila, text="Fondo transparente", font=ui.fuente(12), text_color=ui.TEXTO,
            progress_color=ui.ACENTO, command=self._cambiar_transparencia,
        )
        if self.ajustes["qr_transparente"]:
            self.transparente.select()
        self.transparente.pack(side="right")

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
        self.info = ui.Etiqueta(cuerpo, "", 12, suave=True, anchor="center", justify="center")
        self.info.pack(fill="x")

    # -------------------------------------------------------------- lógica --
    def al_mostrar(self):
        self.texto.focus_set()

    def _contenido(self) -> str:
        return self.texto.get("1.0", "end").strip()

    def _elegir_color(self, color):
        self.color = color
        self.ajustes["qr_color"] = color
        self._marcar_color()
        self._actualizar_previa()

    def _marcar_color(self):
        for color, boton in self._muestras.items():
            boton.configure(border_color=ui.ACENTO if color == self.color else ui.TARJETA)

    def _cambiar_transparencia(self):
        self.ajustes["qr_transparente"] = bool(self.transparente.get())
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
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=20, border=4)
        qr.add_data(contenido)
        qr.make(fit=True)
        fondo = "transparent" if self.transparente.get() else "white"
        imagen = qr.make_image(fill_color=self.color, back_color=fondo).get_image()
        return imagen.convert("RGBA"), qr.version

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
        if self.transparente.get():
            fondo = fondo_cuadriculado(tam, celda=16)
            fondo.alpha_composite(muestra)
            muestra = fondo
        self._ctk_img = ctk.CTkImage(muestra, size=(self.tam_previa, self.tam_previa))
        self.previa.configure(image=self._ctk_img, text="")
        lado = self.imagen.size[0]
        self.info.configure(
            text=f"{lado}×{lado} px  ·  versión {version}  ·  {len(contenido)} caracteres",
            text_color=ui.TEXTO_SUAVE,
        )
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
        carpeta = asegurar_carpeta(CARPETA_QR)
        ruta = carpeta / f"{base}.png"
        if ruta.exists():
            ruta = carpeta / f"{base}_{datetime.now():%Y%m%d_%H%M%S}.png"
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
