"""Paleta de colores, tipografías y widgets reutilizables.

Cada color es una tupla (modo claro, modo oscuro), que es lo que CustomTkinter
entiende para cambiar de tema en caliente.
"""

import os
import subprocess
import sys
import tkinter.font as tkfont
from pathlib import Path

import customtkinter as ctk

# --------------------------------------------------------------------------- #
# Colores
# --------------------------------------------------------------------------- #
ACENTO = ("#5B5BF0", "#7C7CFF")
ACENTO_HOVER = ("#4848D6", "#6666EE")
FONDO = ("#F3F4F7", "#0F1116")
LATERAL = ("#FFFFFF", "#15181F")
TARJETA = ("#FFFFFF", "#1A1E26")
CAMPO = ("#F5F6F9", "#12151B")
BORDE = ("#E2E5EB", "#272C36")
TEXTO = ("#161A22", "#E8EAF0")
TEXTO_SUAVE = ("#6B7280", "#8B93A7")
SECUNDARIO = ("#ECEEF3", "#232833")
SECUNDARIO_HOVER = ("#E0E3EA", "#2C3240")
NAV_ACTIVO = ("#EEEEFE", "#22243A")
EXITO = ("#16A34A", "#4ADE80")
ERROR = ("#DC2626", "#F87171")
AVISO = ("#D97706", "#FBBF24")

# --------------------------------------------------------------------------- #
# Iconos (glifos de las fuentes de iconos que trae Windows)
# --------------------------------------------------------------------------- #
ICONOS = {
    "qr": "",
    "video": "",
    "musica": "",
    "descargar": "",
    "carpeta": "",
    "pegar": "",
    "guardar": "",
    "cancelar": "",
    "tema": "",
    "actualizar": "",
    "enlace": "",
    "lista": "",
}

_familia_iconos = None
_fuentes = {}


def familia_texto() -> str:
    return "Segoe UI" if sys.platform == "win32" else "Helvetica"


def familia_iconos() -> str | None:
    """Devuelve la fuente de iconos disponible (Windows 11 → Windows 10 → nada)."""
    global _familia_iconos
    if _familia_iconos is None:
        disponibles = set(tkfont.families())
        _familia_iconos = next(
            (f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in disponibles), ""
        )
    return _familia_iconos or None


def fuente(tamano=13, peso="normal") -> ctk.CTkFont:
    clave = (tamano, peso)
    if clave not in _fuentes:
        _fuentes[clave] = ctk.CTkFont(family=familia_texto(), size=tamano, weight=peso)
    return _fuentes[clave]


def fuente_icono(tamano=16) -> ctk.CTkFont:
    clave = ("icono", tamano)
    if clave not in _fuentes:
        _fuentes[clave] = ctk.CTkFont(family=familia_iconos() or familia_texto(), size=tamano)
    return _fuentes[clave]


def icono(nombre: str) -> str:
    return ICONOS.get(nombre, "") if familia_iconos() else ""


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #
class Tarjeta(ctk.CTkFrame):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", TARJETA)
        kw.setdefault("corner_radius", 14)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", BORDE)
        super().__init__(master, **kw)


class Etiqueta(ctk.CTkLabel):
    def __init__(self, master, texto="", tamano=13, peso="normal", suave=False, **kw):
        kw.setdefault("text_color", TEXTO_SUAVE if suave else TEXTO)
        kw.setdefault("anchor", "w")
        kw.setdefault("justify", "left")
        super().__init__(master, text=texto, font=fuente(tamano, peso), **kw)


class Boton(ctk.CTkFrame):
    """Botón con icono + texto. `tipo` puede ser 'primario', 'secundario' o 'peligro'."""

    _ESTILOS = {
        "primario": (ACENTO, ACENTO_HOVER, ("#FFFFFF", "#FFFFFF")),
        "secundario": (SECUNDARIO, SECUNDARIO_HOVER, TEXTO),
        "peligro": (("#FDECEC", "#3A1D22"), ("#FBDADA", "#47222A"), ERROR),
    }

    def __init__(self, master, texto, comando=None, icono_nombre=None, tipo="secundario",
                 alto=40, tamano=13):
        super().__init__(master, fg_color="transparent")
        self._comando = comando
        self._icono_nombre = icono_nombre
        self._texto = texto
        self.boton = ctk.CTkButton(
            self, height=alto, corner_radius=10, font=fuente(tamano, "bold"),
            command=self._click, border_spacing=6,
        )
        self.boton.pack(fill="both", expand=True)
        self.configurar(texto=texto, tipo=tipo, icono_nombre=icono_nombre)

    def _click(self):
        if self._comando:
            self._comando()

    def configurar(self, texto=None, tipo=None, icono_nombre=None, comando=None, estado=None):
        if texto is not None:
            self._texto = texto
        if icono_nombre is not None:
            self._icono_nombre = icono_nombre
        if comando is not None:
            self._comando = comando
        glifo = icono(self._icono_nombre) if self._icono_nombre else ""
        # Los glifos de Segoe se mezclan bien con Segoe UI en la misma etiqueta.
        self.boton.configure(text=f"{glifo}   {self._texto}" if glifo else self._texto)
        if tipo is not None:
            fg, hover, color_texto = self._ESTILOS[tipo]
            self.boton.configure(fg_color=fg, hover_color=hover, text_color=color_texto,
                                 text_color_disabled=TEXTO_SUAVE)
        if estado is not None:
            self.boton.configure(state=estado)


class Campo(ctk.CTkEntry):
    def __init__(self, master, placeholder="", **kw):
        kw.setdefault("height", 42)
        kw.setdefault("corner_radius", 10)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", BORDE)
        kw.setdefault("fg_color", CAMPO)
        kw.setdefault("text_color", TEXTO)
        kw.setdefault("placeholder_text_color", TEXTO_SUAVE)
        super().__init__(master, placeholder_text=placeholder, font=fuente(13), **kw)
        self.bind("<FocusIn>", lambda _e: self.configure(border_color=ACENTO))
        self.bind("<FocusOut>", lambda _e: self.configure(border_color=BORDE))


class Selector(ctk.CTkSegmentedButton):
    def __init__(self, master, valores, comando=None, **kw):
        super().__init__(
            master, values=valores, command=comando, height=36, corner_radius=10,
            font=fuente(13, "bold"), fg_color=SECUNDARIO, unselected_color=SECUNDARIO,
            unselected_hover_color=SECUNDARIO_HOVER, selected_color=ACENTO,
            selected_hover_color=ACENTO_HOVER, text_color=TEXTO, **kw,
        )
        # El texto del segmento seleccionado debe ir en blanco en ambos temas.
        self._colorear()
        _cmd = self._command

        def envoltura(valor):
            self._colorear()
            if _cmd:
                _cmd(valor)

        self.configure(command=envoltura)

    def _colorear(self):
        actual = self.get()
        for valor, boton in self._buttons_dict.items():
            boton.configure(text_color=("#FFFFFF", "#FFFFFF") if valor == actual else TEXTO)

    def set(self, valor, *args, **kwargs):
        super().set(valor, *args, **kwargs)
        self._colorear()


class Desplegable(ctk.CTkOptionMenu):
    def __init__(self, master, valores, comando=None, **kw):
        super().__init__(
            master, values=valores, command=comando, height=36, corner_radius=10,
            font=fuente(13), dropdown_font=fuente(13), fg_color=SECUNDARIO,
            button_color=SECUNDARIO, button_hover_color=SECUNDARIO_HOVER, text_color=TEXTO,
            dropdown_fg_color=TARJETA, dropdown_hover_color=SECUNDARIO,
            dropdown_text_color=TEXTO, **kw,
        )


# --------------------------------------------------------------------------- #
# Utilidades varias
# --------------------------------------------------------------------------- #
def abrir_en_explorador(ruta: Path, seleccionar: bool = False):
    """Abre una carpeta (o muestra un archivo seleccionado) en el explorador."""
    ruta = Path(ruta)
    if sys.platform == "win32":
        if seleccionar and ruta.is_file():
            subprocess.Popen(["explorer", "/select,", str(ruta)])
        else:
            os.startfile(ruta if ruta.is_dir() else ruta.parent)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(ruta)] if seleccionar else ["open", str(ruta)])
    else:
        subprocess.Popen(["xdg-open", str(ruta if ruta.is_dir() else ruta.parent)])
