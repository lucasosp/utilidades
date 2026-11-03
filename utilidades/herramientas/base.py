"""Clase base de la que heredan todas las herramientas."""

import customtkinter as ctk


class Herramienta(ctk.CTkFrame):
    """Una pantalla de la app.

    Para crear una herramienta nueva basta con heredar de esta clase, rellenar
    los atributos de clase y construir la interfaz en ``__init__``. Después se
    añade a la lista ``HERRAMIENTAS`` de ``herramientas/__init__.py``.
    """

    id: str = ""            # identificador corto, se guarda en ajustes
    nombre: str = ""        # texto del menú lateral
    descripcion: str = ""   # subtítulo de la cabecera
    icono: str = ""         # clave de ui.ICONOS

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

    @property
    def ajustes(self):
        return self.app.ajustes

    def al_mostrar(self):
        """Se llama cada vez que la herramienta pasa a primer plano."""

    def puede_cerrar(self) -> bool:
        """Devuelve False para pedir confirmación antes de cerrar la app."""
        return True

    def al_cerrar(self):
        """Limpieza antes de salir (hilos, temporales...)."""
