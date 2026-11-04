"""Ventana principal: menú lateral + área de la herramienta activa."""

import ctypes
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from . import ui, windows
from .config import CARPETA_ASSETS, NOMBRE_APP, VERSION, Ajustes
from .herramientas import HERRAMIENTAS


class App(ctk.CTk):
    def __init__(self):
        windows.preparar_proceso()  # antes de crear la ventana
        self.ajustes = Ajustes()
        ctk.set_appearance_mode(self.ajustes["tema"])
        super().__init__(fg_color=ui.FONDO)

        self.title(NOMBRE_APP)
        self.geometry(self._geometria_centrada(1080, 720))
        self.minsize(900, 640)
        self._poner_icono()

        self._clases = {h.id: h for h in HERRAMIENTAS}
        self._instancias = {}
        self._botones_nav = {}
        self.actual = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._crear_lateral()
        self._crear_contenido()

        inicial = self.ajustes["herramienta"]
        self.mostrar(inicial if inicial in self._clases else HERRAMIENTAS[0].id)

        for i, h in enumerate(HERRAMIENTAS[:9], start=1):
            self.bind(f"<Control-Key-{i}>", lambda _e, hid=h.id: self.mostrar(hid))
        self.protocol("WM_DELETE_WINDOW", self.cerrar)

    # ------------------------------------------------------------ ventana --
    def _geometria_centrada(self, ancho, alto):
        x = max((self.winfo_screenwidth() - ancho) // 2, 0)
        y = max((self.winfo_screenheight() - alto) // 2 - 30, 0)
        return f"{ancho}x{alto}+{x}+{y}"

    def _poner_icono(self):
        if not windows.es_windows():
            return
        ico = CARPETA_ASSETS / "icono.ico"
        if ico.exists():
            # CustomTkinter pone su propio icono a los ~200 ms; lo pisamos después.
            self.after(250, lambda: self.iconbitmap(str(ico)))
        # Icono y comando correctos al anclar a la barra de tareas.
        self.after(300, lambda: windows.preparar_ventana(
            ctypes.windll.user32.GetParent(self.winfo_id())))

    # ------------------------------------------------------------- lateral --
    def _crear_lateral(self):
        lateral = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=ui.LATERAL,
                               border_width=0)
        lateral.grid(row=0, column=0, sticky="nsw")
        lateral.grid_propagate(False)
        lateral.grid_columnconfigure(0, weight=1)
        lateral.grid_rowconfigure(2, weight=1)

        # Separador vertical sutil
        ctk.CTkFrame(self, width=1, corner_radius=0, fg_color=ui.BORDE).grid(
            row=0, column=0, sticky="nse")

        marca = ctk.CTkFrame(lateral, fg_color="transparent")
        marca.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 26))
        png = CARPETA_ASSETS / "icono.png"
        if png.exists():
            logo = ctk.CTkImage(Image.open(png), size=(34, 34))
            ctk.CTkLabel(marca, image=logo, text="").pack(side="left", padx=(0, 10))
        textos = ctk.CTkFrame(marca, fg_color="transparent")
        textos.pack(side="left")
        ui.Etiqueta(textos, NOMBRE_APP, 17, "bold").pack(anchor="w")
        ui.Etiqueta(textos, "tu caja de herramientas", 11, suave=True).pack(anchor="w")

        nav = ctk.CTkFrame(lateral, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=12)
        ui.Etiqueta(nav, "HERRAMIENTAS", 10, "bold", suave=True).pack(fill="x", padx=10,
                                                                     pady=(0, 6))
        for i, h in enumerate(HERRAMIENTAS, start=1):
            glifo = ui.icono(h.icono)
            b = ctk.CTkButton(
                nav, text=f"{glifo}    {h.nombre}" if glifo else h.nombre, anchor="w",
                height=42, corner_radius=10, font=ui.fuente(13, "bold"),
                fg_color="transparent", hover_color=ui.SECUNDARIO, text_color=ui.TEXTO,
                command=lambda hid=h.id: self.mostrar(hid),
            )
            b.pack(fill="x", pady=2)
            self._botones_nav[h.id] = b

        pie = ctk.CTkFrame(lateral, fg_color="transparent")
        pie.grid(row=3, column=0, sticky="ew", padx=22, pady=20)
        self.interruptor_tema = ctk.CTkSwitch(
            pie, text="Modo oscuro", font=ui.fuente(12), text_color=ui.TEXTO,
            progress_color=ui.ACENTO, command=self._cambiar_tema,
        )
        if ctk.get_appearance_mode() == "Dark":
            self.interruptor_tema.select()
        self.interruptor_tema.pack(anchor="w")
        ui.Etiqueta(pie, f"v{VERSION}", 11, suave=True).pack(anchor="w", pady=(10, 0))

    def _cambiar_tema(self):
        tema = "dark" if self.interruptor_tema.get() else "light"
        ctk.set_appearance_mode(tema)
        self.ajustes["tema"] = tema

    # ----------------------------------------------------------- contenido --
    def _crear_contenido(self):
        zona = ctk.CTkFrame(self, fg_color="transparent")
        zona.grid(row=0, column=1, sticky="nsew", padx=32, pady=(26, 28))
        zona.grid_columnconfigure(0, weight=1)
        zona.grid_rowconfigure(1, weight=1)

        cabecera = ctk.CTkFrame(zona, fg_color="transparent")
        cabecera.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.titulo = ui.Etiqueta(cabecera, "", 24, "bold")
        self.titulo.pack(fill="x")
        self.subtitulo = ui.Etiqueta(cabecera, "", 13, suave=True)
        self.subtitulo.pack(fill="x", pady=(2, 0))

        self.contenedor = ctk.CTkFrame(zona, fg_color="transparent")
        self.contenedor.grid(row=1, column=0, sticky="nsew")
        self.contenedor.grid_columnconfigure(0, weight=1)
        self.contenedor.grid_rowconfigure(0, weight=1)

    def mostrar(self, hid: str):
        if hid == self.actual:
            return
        if self.actual:
            self._instancias[self.actual].grid_remove()
        if hid not in self._instancias:  # las herramientas se crean al abrirlas
            self._instancias[hid] = self._clases[hid](self.contenedor, self)
        herramienta = self._instancias[hid]
        herramienta.grid(row=0, column=0, sticky="nsew")
        self.actual = hid
        self.ajustes["herramienta"] = hid

        self.titulo.configure(text=herramienta.nombre)
        self.subtitulo.configure(text=herramienta.descripcion)
        for bid, boton in self._botones_nav.items():
            activo = bid == hid
            boton.configure(fg_color=ui.NAV_ACTIVO if activo else "transparent",
                            text_color=ui.ACENTO if activo else ui.TEXTO)
        self.after(50, herramienta.al_mostrar)

    # -------------------------------------------------------------- cierre --
    def cerrar(self):
        ocupadas = [h for h in self._instancias.values() if not h.puede_cerrar()]
        if ocupadas and not messagebox.askyesno(
                "¿Salir?", "Hay una descarga en curso. Si sales ahora se cancelará.\n\n¿Salir igualmente?",
                parent=self):
            return
        for h in self._instancias.values():
            h.al_cerrar()
        self.destroy()


def main():
    try:
        App().mainloop()
    except Exception:
        # Con pythonw no hay consola: dejamos el error en un archivo y avisamos.
        import traceback
        from .config import RAIZ
        (RAIZ / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        messagebox.showerror(NOMBRE_APP, "Ha ocurrido un error inesperado.\n"
                             "Los detalles están en error.log.")
        raise


if __name__ == "__main__":
    main()
