# 01 - Arquitectura

El proyecto está dividido en **capas**. Cada capa solo habla con la de al lado.
Esto es lo que hace que puedas cambiar una parte sin romper las demás.

```
   ┌───────────────────────────────────────────────────────────┐
   │  interfaz (ui/ y views/)                                  │
   │  - views/*.kv   -> aspecto                                 │
   │  - ui/widgets/  -> widgets y controlador (root.py)         │
   └───────────────────────────┬───────────────────────────────┘
                               │  llama a funciones
   ┌───────────────────────────▼───────────────────────────────┐
   │  servicios (services/)                                     │
   │  api, detector, settings, downloader, extractor,           │
   │  installed, launcher, updater                              │
   └───────────────────────────┬───────────────────────────────┘
                               │  crea y usa
   ┌───────────────────────────▼───────────────────────────────┐
   │  modelo (model/build.py)                                   │
   │  Build, InstalledBuild                                     │
   └───────────────────────────────────────────────────────────┘
```

- El **modelo** son solo datos. No sabe nada de Kivy ni de red.
- Los **servicios** hacen el trabajo (descargar, extraer, consultar la API,
  guardar ajustes...). Tampoco saben nada de Kivy: se pueden probar sin abrir
  una ventana. Por eso los `tests/` los prueban directamente.
- La **interfaz** usa esos servicios y los pinta. Es la única capa que conoce
  Kivy.

## El modelo: `model/build.py`

Dos dataclasses sencillas:

- **`Build`**: una compilación publicada por Blender. Campos: `version`,
  `branch`, `risk`, `platform`, `arch`, `url`, `filename`... y un par de
  propiedades útiles como `is_lts` o `human_size` (`"359.8 MB"`).
- **`InstalledBuild`**: una versión ya descargada. Guarda `path`, `executable`,
  `version`, `build_hash` y `branch`.

Al ser dataclasses, crear una es directo: `Build(version="5.2.1", ...)`.

## Los servicios

| Archivo | Qué hace | Dato curioso |
|---|---|---|
| `api.py` | Descarga los listados JSON de Blender (diarias y ramas experimentales), los filtra y los cachea. | Usa `?format=json&v=2` y solo la librería estándar. |
| `detector.py` | Detecta SO y arquitectura con `platform`. | Traduce a los identificadores de Blender (`linux`, `amd64`...). |
| `settings.py` | Carga/guarda ajustes en JSON de forma atómica. | Soporta **modo portable** (archivo `portable` junto al binario). |
| `downloader.py` | Descargar un archivo en un hilo aparte, con progreso y verificación SHA-256. | Escribe a `.part` y renombra solo al terminar. |
| `extractor.py` | Extrae `.tar.xz` y `.zip`. | Comprueba rutas maliciosas ("zip slip") antes de extraer. |
| `installed.py` | Escanea la carpeta destino y encuentra las versiones y su ejecutable. | Deja un marcador `.blendermanager.json` para distinguir diarias. |
| `launcher.py` | Lanza Blender como proceso independiente. | Si cierras el gestor, Blender sigue abierto. |
| `updater.py` | Comprueba e instala actualizaciones desde GitHub Releases. | Cada plataforma se actualiza a su manera. |

## La interfaz

- **`ui/theme.py`**: colores (paleta oscura tipo Blender), fuente de iconos y
  un degradado que da volumen a los botones.
- **`ui/icons.py`**: los glifos de la fuente Font Awesome como constantes.
- **`ui/tooltip.py`**: los textos de ayuda al pasar el ratón.
- **`ui/widgets/`**: los widgets de Python, repartidos por temas:
  - `basic.py` — botones, pastillas, logo de la cabecera, zoom.
  - `spinners.py` — desplegables.
  - `dialogs.py` — diálogos, barra de progreso y contenedores de ajustes.
  - `cards.py` — las tarjetas de compilaciones.
  - `root.py` — `RootWidget`, el controlador que lo une todo.
  - `__init__.py` — vuelve a exportar todo, así `from ui.widgets import X`
    funciona como si siguiera siendo un solo archivo.
- **`views/`**: el aspecto, en Kivy Language:
  - `widgets.kv`, `dialogs.kv`, `cards.kv` — estilos de cada grupo de widgets.
  - `main.kv` — la pantalla principal (`RootWidget`).

## Cómo viaja la información (flujo de datos)

**Del servidor a la pantalla (la tienda):**

```
api.get_builds()            descarga el JSON y lo cachea
        │
RootWidget.builds = [...]    lo guarda como propiedad
        │  (Kivy avisa al cambiar la propiedad)
api.available_for(...)       filtra por plataforma y arquitectura
        │
api.filter_builds(...)       filtra por canal y búsqueda
        │
_rebuild_store()             crea una tarjeta por compilación
```

**De la descarga al disco:**

```
install_build(build)
        │
downloader.start(...)        descarga en un hilo (no bloquea la ventana)
        │  (al terminar, vuelve al hilo de Kivy con Clock.schedule_once)
extractor.extract(...)       extrae el archivo
        │
installed.write_marker(...)  anota el hash de la build
        │
refresh_installed()          vuelve a escanear y repinta
```

## Hilos: la regla que no se puede romper

La red y el disco pueden tardar. Si los ejecutas en el hilo de la interfaz, la
ventana se queda **congelada**. Por eso todo lo lento va en un hilo aparte
(`threading.Thread`) y, al terminar, vuelve al hilo de Kivy con:

```python
Clock.schedule_once(lambda dt: self.actualizar_interfaz(...), 0)
```

**Nunca** toques un widget desde otro hilo.

## Código fuente vs. empaquetado

`paths.py` resuelve la diferencia:

- **Modo fuente** (`python3 src/main.py`): las rutas salen de `src/`.
- **Empaquetado** (PyInstaller): los recursos se extraen a una carpeta temporal
  (`sys._MEIPASS`) y el ejecutable está en `APP_DIR`.

No tienes que preocuparte por esto: usa siempre `APP_DIR`, `RESOURCE_DIR`,
`ASSETS_DIR` y `VIEWS_DIR` de `paths.py`.

## El sistema de actualización

`updater.py` consulta `.../releases/latest` de GitHub (que ignora las
pre-releases). Si hay versión nueva:

- **AppImage (Linux)**: sustituye el propio archivo `$APPIMAGE` y se relanza.
- **Windows**: extrae la release a un directorio temporal y relanza el binario
  nuevo con `--apply-update`.
- **macOS**: solo avisa (reemplazar un `.app` sin firma es poco fiable).
- **Modo fuente**: hace `git pull --ff-only` sobre un checkout limpio.
