"""Registro de herramientas.

Para añadir una utilidad nueva: crea un módulo en esta carpeta con una clase que
herede de ``Herramienta`` y añádela a la lista. El menú lateral se genera solo.
"""

from .base import Herramienta
from .qr import HerramientaQR
from .youtube import HerramientaYouTube

HERRAMIENTAS: list[type[Herramienta]] = [
    HerramientaQR,
    HerramientaYouTube,
]
