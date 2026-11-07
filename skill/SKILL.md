---
name: utilidades
description: Use the local `utilidades` command to make QR codes, download YouTube video/audio (MP3/MP4, playlists), download Spotify songs/albums/playlists as tagged MP3, and generate natural local text-to-speech in 15 languages, including cloned voices. Use it whenever a task needs any of those files, alone or as ingredients of something bigger (a video with background music from YouTube, a QR on screen and a voice-over, a podcast intro, a narrated slideshow…). Triggers: "QR", "código QR", "descarga/baja este vídeo/canción", "YouTube", "Spotify", "MP3", "MP4", "texto a voz", "TTS", "voz en off", "locución", "narración", "lee este texto", "clona mi voz".
---

# Utilidades (QR · YouTube · Spotify · texto a voz)

`utilidades` is a CLI installed on this machine (desktop app + console). Every
command writes files and, with `--json`, prints **one JSON line on stdout** with
the result; progress goes to stderr. Always pass `--json` and read the paths from
`archivos` instead of guessing filenames.

Start with `utilidades info --json` when you need to know whether text-to-speech
is installed (`voz_instalada`), which cloned voices exist (`voces`) or where
default output folders are.

If the command is not found, tell the user to run `iniciar.bat` once in the app
folder and then `utilidades instalar-comando` (or call
`<app folder>/.venv/Scripts/python.exe <app folder>/cli.py …` directly).

## Commands

Use `-o` to write straight into the user's project. `-o` may be a file (with an
extension) or a folder; without `-o` files go to the app's own folders.

### QR
```bash
utilidades qr "https://ejemplo.com" -o assets/qr.png --json
utilidades qr "texto" --color "#1e3a8a" --fondo "#ffffff" --tam 1024 -o qr.png --json
utilidades qr "texto" --fondo transparente -o qr.png --json   # PNG with alpha
```
Default is black on white, ~740 px. `--tam N` resizes to N×N. Keep the code dark
on a light background or phones may not scan it (the command warns on low contrast).

### YouTube (also most other video sites supported by yt-dlp)
```bash
utilidades youtube URL --formato mp3 --calidad 320 -o musica --json
utilidades youtube URL --formato mp4 --calidad 1080 -o videos --json   # max|1080|720|480|360
utilidades youtube "URL?v=…&list=…" --lista -o musica --json         # whole playlist
```
A watch URL that also has `list=` downloads only that video unless `--lista`.
Pure playlist URLs download the whole list into a numbered subfolder.
MP3s get cover art and metadata; MP4s are H.264+AAC.

### Spotify
```bash
utilidades spotify "https://open.spotify.com/track|album|playlist/…" -o musica --json
```
Spotify audio is DRM-protected: each track is matched on YouTube by duration and
tagged with Spotify's title/artist/album/cover. No login; public playlists are
capped at 100 tracks. Re-running skips tracks that already exist.

### Text to speech (local, Chatterbox)
```bash
utilidades voz "Texto a leer." -o locucion.mp3 --json
utilidades voz "Frase uno." "Frase dos." "Frase tres." -o clips/ --json   # one file per text
utilidades voz --archivo guion.txt -i en -e 0.7 -o narracion.wav --json
utilidades voz "Hola" --voz "NombreGuardado" -o hola.mp3 --json
utilidades voz "Hola" --voz ruta/a/referencia.mp3 -o hola.mp3 --json   # clone from any audio
utilidades voces --anadir nota_de_voz.m4a --nombre "Ana" --json          # save a voice
```
- Languages: es en fr it pt de nl pl tr ru ja zh ko ar hi (`-i`, default `es`).
- `-e/--expresividad` 0.25 (flat) … 1.0 (very expressive), default 0.5.
- Long texts are split into sentences automatically, any length is fine.
- **Loading the model takes ~25-40 s per call; put all the texts for a task in
  ONE call** (several positional texts → one file each, in order of `archivos`).
  The JSON also gives each clip's duration in `segundos`, handy for timing a video.
- Runs on the NVIDIA GPU if present; on CPU it is much slower.
- If `voz_instalada` is false: `utilidades voz --instalar` downloads ~6 GB. Ask
  the user before doing it.
- Only clone the user's own voice or one they have permission for. Never use it
  to impersonate someone. Output carries an inaudible watermark.

## Composing bigger things (ffmpeg)

ffmpeg is available (`utilidades info --json` → `ffmpeg`). Get every ingredient
with the commands above first (one `voz` call for all narration), read durations
with `ffprobe`, then assemble. Example: 1280×720 video, solid background, QR in
the bottom-right corner from second 2, YouTube music at low volume that ducks
under the voice-over starting at second 1:

```bash
ffmpeg -y -f lavfi -i "color=c=#0f1116:s=1280x720:d=DUR:r=30" \
  -i qr.png -i musica.mp3 -i voz.mp3 \
  -filter_complex "\
[1:v]scale=360:-1[qr];\
[0:v][qr]overlay=W-w-60:H-h-60:enable='between(t,2,DUR)'[v];\
[2:a]volume=0.35,atrim=0:DUR,afade=t=out:st=DUR-1.5:d=1.5[m];\
[3:a]adelay=1000|1000,apad[vo];[vo]asplit=2[vo1][vo2];\
[m][vo1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];\
[md][vo2]amix=inputs=2:duration=first:normalize=0[a]" \
  -map "[v]" -map "[a]" -t DUR -c:v libx264 -pix_fmt yuv420p -c:a aac out.mp4
```
Replace `DUR` with the total length in seconds (and compute `DUR-1.5`). Use a
downloaded MP4 instead of the `color` source to put the QR over real footage. For
anything with designed scenes, text animation or captions, check whether a
video skill (e.g. HyperFrames) is available and use these files as its media.

## Troubleshooting
- YouTube/Spotify download errors → update yt-dlp: in the app press
  "Actualizar yt-dlp", or run `<app folder>/.venv/Scripts/python.exe -m pip install -U "yt-dlp[default]"`.
- Voice engine crashed → its log is `<app folder>/.venv-voz/trabajador.log`.
- Exit code 0 = ok, 1 = nothing downloaded, 2 = bad arguments/error (the JSON has `error`).
