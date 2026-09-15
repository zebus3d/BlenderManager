# 01 - Arquitectura

El proyecto está dividido en **capas**. Cada capa solo habla con la de al lado.
Esto es lo que hace que puedas cambiar una parte sin romper las demás.

```
   ┌───────────────────────────────────────────────────────────┐
   │  interfaz (ui/)                                            │
   │  - qss.py      -> aspecto (hoja de estilos)                │
   │  - widgets/    -> widgets y controlador (main_window.py)   │
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

- El **modelo** son solo datos. No sabe nada de Qt ni de red.
- Los **servicios** hacen el trabajo (descargar, extraer, consultar la API,
  guardar ajustes...). Tampoco saben nada de Qt: se pueden probar sin abrir una
  ventana. Por eso los `tests/` los prueban directamente.
- La **interfaz** usa esos servicios y los pinta. Es la única capa que conoce
  Qt.

> Esa frontera no es decorativa: es lo que permitió portar la interfaz entera
> (de Kivy a Qt Widgets) sin tocar ni una línea de `services/`. Si te ves
> importando `PySide6` dentro de `services/`, algo se está torciendo.

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
| `api.py` | Descarga los listados JSON de Blender (diarias y ramas experimentales), los filtra y los cachea. | `filter_builds` es una **función pura**: la UI tiene que usarla, no reimplementarla. |
| `detector.py` | Detecta SO y arquitectura con `platform`. | Traduce a los identificadores de Blender (`linux`, `amd64`...). |
| `settings.py` | Carga/guarda ajustes en JSON de forma atómica. | Soporta **modo portable** (archivo `portable` junto al binario). |
| `downloader.py` | Descargar un archivo en un hilo aparte, con progreso y verificación SHA-256. | Escribe a `.part` y renombra solo al terminar. |
| `extractor.py` | Extrae `.tar.xz` y `.zip`. | Comprueba rutas maliciosas ("zip slip") antes de extraer. |
| `installed.py` | Escanea la carpeta destino y encuentra las versiones y su ejecutable. | Deja un marcador `.blendermanager.json` para distinguir diarias. |
| `launcher.py` | Lanza Blender como proceso independiente. | Si cierras el gestor, Blender sigue abierto. |
| `updater.py` | Comprueba e instala actualizaciones desde GitHub Releases. | En modo fuente no descarga nada: hace `git pull` y reinicia. |

## La interfaz

- **`ui/qss.py`**: el aspecto de toda la aplicación (una hoja de estilos Qt
  construida con los colores del tema). Sustituye a los antiguos `views/*.kv`.
- **`ui/theme.py`**: los colores (paleta oscura tipo Blender) como constantes.
- **`ui/icons.py`**: los glifos de la fuente Font Awesome como constantes.
- **`ui/fonts.py`**: carga la fuente de iconos y devuelve `QFont`/`QIcon`.
- **`ui/widgets/`**:
  - `buttons.py` — botones, pastillas, interruptores e iconos.
  - `cards.py` — las tarjetas de compilaciones (lista y rejilla).
  - `dialogs.py` — `AppDialog` y los atajos `confirm()`, `show_error()`...
  - `main_window.py` — `MainWindow`, el controlador que lo une todo.
  - `__init__.py` — vuelve a exportar todo, así `from ui.widgets import X`
    funciona sin saber en qué archivo vive cada cosa.

## Cómo viaja la información (flujo de datos)

**Del servidor a la pantalla (la tienda):**

```
api.get_builds()             descarga el JSON y lo cachea
        │
MainWindow.builds = [...]     lo guarda en el controlador
        │
api.available_for(...)        filtra por plataforma y arquitectura
        │
api.filter_builds(...)        filtra por canal y búsqueda
        │
_rebuild_store()              crea una tarjeta por compilación
```

**De la descarga al disco:**

```
install_build(build)
        │
downloader.start(...)         descarga en un hilo (no bloquea la ventana)
        │  (al terminar avisa emitiendo la señal _Bridge.done)
extractor.extract(...)        extrae el archivo
        │
installed.write_marker(...)   anota el hash de la build
        │
refresh_installed()           vuelve a escanear y repinta
```

## Hilos: la regla que no se puede romper

La red y el disco pueden tardar. Si los ejecutas en el hilo de la interfaz, la
ventana se queda **congelada**. Por eso todo lo lento va en un hilo aparte
(`threading.Thread`) y, al terminar, vuelve al hilo de la interfaz **emitiendo
una señal Qt** (que el receptor encola):

```python
def worker():
    builds = api.get_builds(force=True)
    self.builds_loaded.emit(builds)      # señal -> slot en el hilo de la UI

threading.Thread(target=worker, daemon=True).start()
```

Los callbacks de descarga se envuelven en `_Bridge` (`main_window.py`) por el
mismo motivo. **Nunca** toques un widget desde otro hilo (Qt revienta igual que
reventaba Kivy).

## Código fuente vs. empaquetado

`paths.py` resuelve la diferencia:

- **Modo fuente** (`./run.sh`): las rutas salen de `src/`.
- **Empaquetado** (PyInstaller): los recursos se extraen a una carpeta temporal
  (`sys._MEIPASS`) y el ejecutable está en `APP_DIR`.

No tienes que preocuparte por esto: usa siempre `APP_DIR`, `RESOURCE_DIR` y
`ASSETS_DIR` de `paths.py`.

## El sistema de actualización

`updater.py` consulta `.../releases/latest` de GitHub. Si hay versión nueva:

- **AppImage (Linux)**: sustituye el propio archivo `$APPIMAGE` y se relanza.
- **Windows**: extrae la release a un directorio temporal y relanza el binario
  nuevo con `--apply-update`.
- **macOS**: solo avisa (reemplazar un `.app` sin firma es poco fiable).
- **Modo fuente**: no hay binario que reemplazar. Al arrancar **no** avisa
  (comparar un checkout con la última release no dice nada: puede ir por
  delante), y el *check* manual hace `git pull --ff-only` y reinicia.

Cada push a `master` publica una **release final** marcada como *latest*, así
que el auto-update salta en el siguiente arranque. No hay canal de
pre-releases.
