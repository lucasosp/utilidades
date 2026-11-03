<p align="center">
  <img src="assets/icono.png" width="96" alt="Utilidades">
</p>

<h1 align="center">Utilidades</h1>

<p align="center">
  Una caja de herramientas de escritorio para el día a día: rápida, bonita y fácil de ampliar.<br>
  Por ahora incluye un <b>generador de códigos QR</b> y un <b>descargador de YouTube</b> (MP3 / MP4).
</p>

<p align="center">
  <img src="assets/capturas/youtube.png" width="49%" alt="Descargador de YouTube">
  <img src="assets/capturas/qr.png" width="49%" alt="Generador de QR">
</p>

---

## Qué hace

### Códigos QR
- Vista previa **en directo** mientras escribes.
- Colores a elegir y opción de **fondo transparente**.
- Se guardan como PNG de alta resolución en la carpeta `generados/`.
- El nombre del archivo se genera solo a partir del contenido (o pon el tuyo).

### YouTube
- Descarga en **MP3** (con portada y metadatos) o en **MP4** (H.264 + AAC, se reproduce en cualquier sitio).
- Eliges la calidad: 320/192/128 kbps o Máxima/1080p/720p/480p/360p.
- **Listas de reproducción**: si el enlace es un vídeo dentro de una lista, eliges si quieres *solo ese vídeo* o *la lista entera*. Las listas se guardan en su propia subcarpeta y numeradas.
- Progreso, velocidad y tiempo restante; puedes cancelar en cualquier momento (se limpian los archivos a medias).
- Si copias un enlace antes de abrir la pestaña, se pega solo.
- Los archivos se guardan en la carpeta `descargas/`.

Además: modo claro/oscuro, recuerda tus últimas opciones y atajos <kbd>Ctrl</kbd>+<kbd>1</kbd> / <kbd>Ctrl</kbd>+<kbd>2</kbd> para cambiar de herramienta.

## Instalación (Windows)

1. Instala **[Python 3.10 o superior](https://www.python.org/downloads/)** marcando la casilla *“Add python.exe to PATH”*.
2. Descarga este repositorio (botón verde *Code → Download ZIP*) o clónalo:
   ```bash
   git clone https://github.com/lucasosp/utilidades.git
   ```
3. Haz doble clic en **`iniciar.bat`**.

La primera vez tarda un minuto porque crea un entorno virtual (`.venv`) e instala las dependencias. A partir de ahí se abre al momento.

> 💡 Ejecuta **`crear_acceso_directo.bat`** una vez y tendrás un icono de *Utilidades* en el escritorio.

### ffmpeg
Para convertir a MP3 y unir audio y vídeo hace falta **ffmpeg**. Si ya lo tienes instalado se usa ese; si no, la app usa el que viene con el paquete `imageio-ffmpeg`, así que no tienes que hacer nada.

### Otros sistemas
También funciona en macOS y Linux (necesitas Python con Tkinter):
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m utilidades
```

## Si YouTube deja de funcionar

YouTube cambia a menudo y [yt-dlp](https://github.com/yt-dlp/yt-dlp) se actualiza para seguirle el ritmo. Si una descarga falla, pulsa **“Actualizar yt-dlp”** en la pestaña de YouTube y reinicia la app.

Para algunos formatos YouTube exige un intérprete de JavaScript. Si ves errores de formatos no disponibles, instala [Deno](https://deno.com/) (`winget install DenoLand.Deno`) o Node.js; la app los detecta solos.

## Estructura del proyecto

```
utilidades/
├── iniciar.bat                 # lanzador: prepara el entorno y abre la app
├── crear_acceso_directo.bat    # crea un acceso directo en el escritorio
├── requirements.txt
├── assets/                     # icono y capturas
├── generados/                  # aquí se guardan los QR
├── descargas/                  # aquí se guardan los vídeos y audios
└── utilidades/                 # código fuente
    ├── app.py                  # ventana principal y menú lateral
    ├── config.py               # rutas y ajustes guardados
    ├── ui.py                   # colores, fuentes y widgets comunes
    └── herramientas/
        ├── __init__.py         # lista de herramientas registradas
        ├── base.py             # clase base Herramienta
        ├── qr.py
        ├── youtube.py          # interfaz del descargador
        └── youtube_motor.py    # lógica de descarga (yt-dlp)
```

## Añadir una herramienta nueva

1. Crea `utilidades/herramientas/mi_herramienta.py`:
   ```python
   from .. import ui
   from .base import Herramienta

   class MiHerramienta(Herramienta):
       id = "mia"
       nombre = "Mi herramienta"
       descripcion = "Lo que hace, en una línea."
       icono = "enlace"  # cualquier clave de ui.ICONOS

       def __init__(self, master, app):
           super().__init__(master, app)
           tarjeta = ui.Tarjeta(self)
           tarjeta.pack(fill="both", expand=True)
           ui.Etiqueta(tarjeta, "¡Hola!", 16, "bold").pack(padx=22, pady=20)
   ```
2. Añádela a la lista `HERRAMIENTAS` en `utilidades/herramientas/__init__.py`.

Aparecerá sola en el menú lateral.

## Aviso

Descarga solo contenido que tengas derecho a descargar y respeta los términos de servicio de cada plataforma y los derechos de autor.

## Créditos

Hecho con [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [qrcode](https://github.com/lincolnloop/python-qrcode) y [Pillow](https://python-pillow.org/).
