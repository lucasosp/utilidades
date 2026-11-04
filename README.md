<p align="center">
  <img src="assets/icono.png" width="96" alt="Utilidades">
</p>

<h1 align="center">Utilidades</h1>

<p align="center">
  Una caja de herramientas de escritorio para el día a día: rápida, bonita y fácil de ampliar.<br>
  Por ahora incluye un <b>generador de códigos QR</b> y descargadores de <b>YouTube</b> (MP3 / MP4) y <b>Spotify</b> (MP3).
</p>

<p align="center">
  <img src="assets/capturas/youtube.png" width="32%" alt="Descargador de YouTube">
  <img src="assets/capturas/spotify.png" width="32%" alt="Descargador de Spotify">
  <img src="assets/capturas/qr.png" width="32%" alt="Generador de QR">
</p>

---

## Qué hace

### Códigos QR
- Vista previa **en directo** mientras escribes.
- Por defecto, negro sobre blanco de toda la vida. Si activas **Personalizar colores** puedes elegir el color del código y del fondo (selector de color o código hex) o dejar el **fondo transparente**. Te avisa si el contraste es tan bajo que el móvil puede no leerlo.
- Se guardan como PNG de alta resolución en la carpeta `generados/`.
- El nombre del archivo se genera solo a partir del contenido (o pon el tuyo).

### YouTube
- Descarga en **MP3** (con portada y metadatos) o en **MP4** (H.264 + AAC, se reproduce en cualquier sitio).
- Eliges la calidad: 320/192/128 kbps o Máxima/1080p/720p/480p/360p.
- **Listas de reproducción**: si el enlace es un vídeo dentro de una lista, eliges si quieres *solo ese vídeo* o *la lista entera*. Las listas se guardan en su propia subcarpeta y numeradas.
- Progreso, velocidad y tiempo restante; puedes cancelar en cualquier momento (se limpian los archivos a medias).
- Si copias un enlace antes de abrir la pestaña, se pega solo.
- Los archivos se guardan en la carpeta `descargas/`.

### Spotify
- Pega el enlace de una **canción**, un **álbum** o una **lista** pública y se descarga en MP3.
- El MP3 lleva el título, los artistas, el álbum, el número de pista, el año y la **portada de Spotify**.
- No hace falta cuenta ni claves de API.
- Si una descarga se corta, vuelve a darle: las canciones que ya tienes se saltan.

> **¿Cómo funciona?** El audio de Spotify está protegido (DRM) y no se puede descargar tal cual. La app lee los datos públicos de Spotify, busca cada canción en YouTube (elige la versión cuya duración coincide con la de Spotify y descarta directos, covers, remixes…) y la etiqueta con la información de Spotify. Es el mismo método que usa [spotDL](https://github.com/spotDL/spotify-downloader).
>
> Sin iniciar sesión, Spotify solo enseña las **primeras 100 canciones** de una lista.

Además: modo claro/oscuro, recuerda tus últimas opciones y atajos <kbd>Ctrl</kbd>+<kbd>1</kbd>, <kbd>Ctrl</kbd>+<kbd>2</kbd>, <kbd>Ctrl</kbd>+<kbd>3</kbd>… para cambiar de herramienta.

## Instalación (Windows)

1. Instala **[Python 3.10 o superior](https://www.python.org/downloads/)** marcando la casilla *“Add python.exe to PATH”*.
2. Descarga este repositorio (botón verde *Code → Download ZIP*) o clónalo:
   ```bash
   git clone https://github.com/lucasosp/utilidades.git
   ```
3. Haz doble clic en **`iniciar.bat`**.

La primera vez tarda un minuto porque crea un entorno virtual (`.venv`) e instala las dependencias. A partir de ahí se abre al momento.

### Acceso directo y barra de tareas

Ejecuta **`crear_acceso_directo.bat`** una vez: crea un acceso directo *Utilidades* en el escritorio y en el menú Inicio (así también la encuentras escribiendo "Utilidades" en el buscador de Windows).

Para anclarla a la barra de tareas, abre la app, haz clic derecho en su icono de la barra y elige **Anclar a la barra de tareas**. Se guarda con su propio icono y se abre aunque reinicies el PC.

> Si la anclaste con una versión anterior y te sale el icono de Python o una terminal, desánclala y vuelve a anclarla así.

### ffmpeg
Para convertir a MP3 y unir audio y vídeo hace falta **ffmpeg**. Si ya lo tienes instalado se usa ese; si no, la app usa el que viene con el paquete `imageio-ffmpeg`, así que no tienes que hacer nada.

### Otros sistemas
También funciona en macOS y Linux (necesitas Python con Tkinter):
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python Utilidades.pyw
```

## Si YouTube deja de funcionar

YouTube cambia a menudo y [yt-dlp](https://github.com/yt-dlp/yt-dlp) se actualiza para seguirle el ritmo. Si una descarga falla, pulsa **“Actualizar yt-dlp”** en la pestaña de YouTube o Spotify y reinicia la app.

Para algunos formatos YouTube exige un intérprete de JavaScript. Si ves errores de formatos no disponibles, instala [Deno](https://deno.com/) (`winget install DenoLand.Deno`) o Node.js; la app los detecta solos.

## Estructura del proyecto

```
utilidades/
├── iniciar.bat                 # prepara el entorno (la 1.ª vez) y abre la app
├── Utilidades.pyw              # abre la app sin consola (lo usan los accesos directos)
├── crear_acceso_directo.bat    # accesos directos en el escritorio y en el menú Inicio
├── requirements.txt
├── assets/                     # icono y capturas
├── generados/                  # aquí se guardan los QR
├── descargas/                  # aquí se guardan los vídeos y audios
└── utilidades/                 # código fuente
    ├── app.py                  # ventana principal y menú lateral
    ├── config.py               # rutas y ajustes guardados
    ├── ui.py                   # colores, fuentes y widgets comunes
    ├── windows.py              # icono en la barra de tareas y accesos directos
    └── herramientas/
        ├── __init__.py         # lista de herramientas registradas
        ├── base.py             # clase base Herramienta
        ├── qr.py
        ├── descarga_base.py    # hilo de descarga común (cancelar, limpiar, ffmpeg)
        ├── panel_descarga.py   # tarjeta de progreso común
        ├── youtube.py          # interfaz de YouTube
        ├── youtube_motor.py    # lógica de YouTube (yt-dlp)
        ├── spotify.py          # interfaz de Spotify
        └── spotify_motor.py    # lectura de Spotify + búsqueda en YouTube + etiquetas
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

Hecho con [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [qrcode](https://github.com/lincolnloop/python-qrcode), [Pillow](https://python-pillow.org/) y [Mutagen](https://github.com/quodlibet/mutagen).
