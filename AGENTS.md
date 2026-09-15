# AGENTS.md

Guía para trabajar en **BlenderManager** (app Kivy de descarga/gestión de
versiones de Blender). El código y los comentarios están en español; las claves
de i18n son cadenas en inglés (ver `src/i18n.py`).

## Estructura

```
src/
  main.py            # entrada, --smoke / --screenshot / --apply-update
  version.py         # __version__ (el CI la reescribe desde el tag)
  paths.py           # APP_DIR / RESOURCE_DIR
  i18n.py            # traducciones es/en
  model/build.py     # modelo de compilación
  services/          # api, downloader, extractor, installed, launcher,
                     # detector, settings, updater
  ui/                # theme, icons, tooltip
    widgets/         # widgets de Python, repartidos por temas:
                     #   basic, spinners, dialogs, cards, root (controlador)
  views/             # interfaz declarativa Kivy, un .kv por grupo:
                     #   widgets.kv, dialogs.kv, cards.kv, main.kv
doc/                 # guía de arquitectura en español (para principiantes)
packaging/           # spec de PyInstaller, scripts de build, inject_version.py
tests/               # unittest
```

`main.py` define `KV_FILES` (los `.kv` a cargar, en orden) y registra en la
`Factory` las clases de `ui/widgets/` antes de cargar las vistas. El paquete
`ui/widgets/__init__.py` reexporta todo, así que `from ui.widgets import X`
sigue funcionando como cuando era un solo archivo.

## Canales de compilaciones

Todo vive en `src/services/api.py`; el filtrado por canal es la función pura
`filter_builds` (testeada en `tests/test_services.py`). Blender publica **dos
listados** y se descargan los dos:

- **Daily** (`API_URL`): estables y LTS por rama, más las alfas de `main`.
- **Experimental** (`EXPERIMENTAL_URL`, sección "Branch"): ramas de funciones
  nuevas. **Casi siempre está vacío** (Blender dejó de publicarlas en 2021 y no
  se sabe si volverán); por eso el canal muestra un aviso propio. Blender
  Launcher usa este mismo endpoint.

El canal *Experimental* solo se ve en su propia pestaña: el resto de canales lo
excluye para no confundir. En `fetch_builds` va en su propio `try` (un fallo ahí
no debe tumbar el listado normal). `Build.experimental` se cachea con `asdict` y
los cachés viejos caen a su valor por defecto.

## Comandos

```bash
# Tests (rápidos, sin interfaz)
python3 -m unittest discover -t . -s tests -v

# App en desarrollo
python3 src/main.py

# Build local (one-folder; --appimage añade el AppImage en Linux)
python3 packaging/inject_version.py 1.2.3   # opcional: fija la versión local
packaging/build.sh
packaging/build.sh --appimage
```

En modo fuente la app **no** comprueba actualizaciones (solo si `sys.frozen`).
Para verificar la UI sin pantalla se puede arrancar Kivy con
`SDL_VIDEODRIVER=offscreen` (ver más abajo).

## Releases (lo importante)

Todo lo gestiona `.github/workflows/build.yml`. **No hay que crear tags para
tener binarios publicados.**

### Publicar una pre-release automática (build normal)

Basta con empujar a `master`:

```bash
git push origin master
```

El workflow calcula la versión (`v1.1.<nº de build>`, usando el último tag como
base) y publica una **pre-release** con los 3 binarios + `checksums.txt`. Las
pre-releases **no** disparan el auto-update de los usuarios.

### Publicar una release estable (la que sí actualiza a los usuarios)

**Forma recomendada: el botón de promoción.** En Actions → **promote** → *Run
workflow*. Sin argumentos coge la pre-release más reciente; opcionalmente se le
pasa un tag concreto. El workflow comprueba que la release trae los 3 binarios
y el `checksums.txt`, y entonces le quita la marca de pre-release y la deja
como `latest`.

No recompila nada: promociona **los mismos binarios** que ya generó el push a
master. El auto-update de la app consulta `.../releases/latest`, que **ignora
pre-releases y drafts**, así que en cuanto se promociona una, a los usuarios
con `auto_update` les salta el aviso en el siguiente arranque.

**Por qué no hay que reetiquetar a mano unos binarios ya subidos**: la versión
va *cocida dentro del binario* (`inject_version.py` reescribe `src/version.py`
antes de compilar). Si creas un tag `v1.2.0` apuntando a los binarios de la
pre-release `v1.1.87`, la app instalada seguirá diciendo «1.1.87», verá que
`1.2.0` es más nueva, se actualizará... y volverá a decir «1.1.87»: **bucle
infinito de actualización**.

**Forma alternativa (recompilando)**: empujar un tag `vX.Y.Z`.

```bash
git tag -a v1.2.0 -m "Blender Manager v1.2.0"
git push origin master   # si aún no está empujado
git push origin v1.2.0
```

Esto sí compila los 3 binarios con esa versión y publica la release como
`latest`, así que la versión del binario y la del tag coinciden.

**Cuidado con la numeración**: el parche de las pre-releases es el número de
run de GitHub Actions, que solo sube (`v1.1.87`, `v1.1.88`...). Si etiquetas a
mano una estable con un parche más bajo (`v1.1.2`), será *más antigua* que la
que ya tienen algunos usuarios y nunca les llegará. Para una estable a mano,
**sube siempre la minor** (`v1.2.0`).

### Reglas que no hay que romper

- **Nada de `dp()`/`sp()` al definir una clase o en código de nivel de módulo.**
  Se evalúa al *importar* el módulo y `dp()` necesita una ventana para calcular
  la densidad. PyInstaller importa los módulos durante el empaquetado (sin
  ventana) y en Windows eso abortaba el build con `SystemExit`. Defínelo con un
  valor plano y fija el `dp()` real en `__init__` (que ya corre con ventana).
- **Nombres de asset**: deben coincidir con `ASSET_NAMES` de
  `src/services/updater.py` (`BlenderManager-x86_64.AppImage`,
  `BlenderManager-windows-x86_64.zip`, `BlenderManager-macos.zip`). Si cambian
  en el CI, actualiza también el updater.
- **`checksums.txt`**: el job `release` lo genera y el updater lo usa para
  verificar el SHA-256 antes de instalar. No quitar ese paso.
- **`src/version.py`**: no editarlo a mano para los releases; el CI lo
  sobrescribe desde el tag con `packaging/inject_version.py` (que además genera
  el recurso de versión de Windows, `packaging/version_info.txt`, ignorado por
  git).
- Antes de etiquetar, los tests deben pasar (`release` depende de `test`).
- **Marcador de instalación**: al extraer una build se escribe
  `.blendermanager.json` dentro de su carpeta con el hash de la compilación
  (`src/services/installed.py`). Sin él no se pueden distinguir dos diarias de
  la misma versión, porque el nombre de la carpeta extraída no lleva el hash.

## Build Linux portable (glibc + SDL2)

El job `linux:` compila en **Ubuntu 22.04 sin contenedor**. Hay dos
restricciones que se pelean entre sí y esta es la única combinación que
las satisface a la vez:

### 1. glibc vieja para máxima compatibilidad

El binario embebe el intérprete de Python y las libs de C. Ese intérprete
exige una versión mínima de glibc del sistema anfitrión. Ubuntu 22.04 da
**glibc 2.35**, que cubre Ubuntu 22.04+, Debian 12+, **Linux Mint 21/22**,
Fedora 36+ y Arch.

**NO compilar en un contenedor Arch** (lo intentamos y lo revertimos): el
Python 3.14 de Arch exige **glibc 2.44**, y en Linux Mint 22 / Ubuntu
24.04 (glibc 2.39) el binario crashea al arrancar con:

```
ImportError: libm.so.6: version `GLIBC_2.44' not found
```

### 2. SDL2 2.32 (parcial) y el muro de Mesa 25/26

El Kivy 2.3.1 que instala pip trae en `Kivy.libs/` una SDL2 **2.30.0.7**
que en Mesa moderno + Wayland pide GLX y Xwayland devuelve 0 configs
→ `No matching FB config found`. Forzando Wayland: `Could not get EGL display`.

El CI compila **SDL2 2.32.10** en el mismo Ubuntu 22.04 y **sustituye** el
`libSDL2-2-*.so*` que dejó PyInstaller (`dist/BlenderManager/_internal/Kivy.libs/`).
SDL2 mantiene ABI dentro de la serie 2.x, así que el módulo Cython
`_window_sdl2` carga la 2.32 sin recompilar.

**OJO — el swap NO arregla Mesa 25/26.** Medido en esta máquina:

| Entorno | Mesa | pip Kivy 2.30 | pip Kivy 2.32 | Kivy fuente + sdl2-compat+SDL3 |
|---|---|---|---|---|
| Ubuntu 22.04 (Xvfb) | 23 | ✅ | ✅ | ✅ |
| Ubuntu 24.04 (Xvfb) | 25 | ❌ | ❌ | — |
| Arch + KDE/Wayland | 26 | ❌ | ❌ | ❌ `Could not get EGL display` |
| Arch con `python-kivy` de pacman | 26 | — | — | ✅ |

Conclusiones firmes (no volver a intentarlas):
- Cambiar SDL2 a 2.32 **no** habilita Mesa 25/26 con pip Kivy.
- Compilar SDL3 + `sdl2-compat` + Kivy desde fuente en Ubuntu 22.04
  **tampoco**: funciona en Ubuntu 22.04, pero el SDL3 compilado sobre el
  EGL/libwayland viejos no inicializa EGL contra el Mesa 26 de Arch.
- Lo único que abre en Arch+Mesa 26 es el **Kivy nativo de Arch**, porque su
  paquete `sdl2` es en realidad **`sdl2-compat`** (SDL3 por debajo).

Detalles de mantenimiento:
- La compilación de SDL2 se cachea con `actions/cache` (clave
  `sdl2-2.32.10-ubuntu2204`) para no recompilar en cada push.
- El swap usa `find dist/BlenderManager -name "libSDL2-2-*" -exec cp ...`.
  Ojo con el patrón: `libSDL2-2-*` solo pilla el core; `libSDL2_image-*`,
  `libSDL2_mixer-*` y `libSDL2_ttf-*` NO se tocan.
- Hay un **smoke test** (`./binario --smoke`) tras el build con
  `APPIMAGE_EXTRACT_AND_RUN=1` (el runner no tiene libfuse2). `--smoke` NO
  abre ventana: para eso, `xvfb-run ... --screenshot` y buscar
  `[GL] OpenGL version`.
- **NO volver a `pip install kivy` sin más**, ni meter el job en un
  contenedor con glibc más nueva: cualquiera de las dos cosas reintroduce
  un bug ya sufrido por usuarios reales.

### 3. El muro de Mesa 25/26 y la salida correcta: Flatpak

Una app OpenGL depende del **driver del sistema** (Mesa/NVIDIA), y un AppImage
NO lo empaqueta. Por eso la app usa el Mesa del anfitrión, y el Kivy/SDL2 que
compilamos aquí no se lleva bien con Mesa 25/26. Con el Kivy actual **no existe
un único AppImage que sirva para Mint/X11 y Arch/Mesa26 a la vez**; es un choque
de stack, no un bug del código.

Salida correcta para "que funcione en todas las distros": **Flatpak**, que
ejecuta la app sobre un runtime fijo (`org.freedesktop.Platform`) con Mesa +
SDL2/SDL3 de una sola era; el anfitrión solo aporta el driver del kernel
(`/dev/dri`). `shelly` también instala/listа Flatpaks. La otra salida es esperar
a **Kivy 3.0** (SDL3 nativo, milestone ~enero 2027), que elimina `sdl2-compat`
de la ecuación. Plan mientras tanto: AppImage (Ubuntu 22.04) para quien no
quiera flatpak + Flatpak para cobertura total.

### Verificación antes de tocar este job

```bash
# En un contenedor Ubuntu 22.04 (persistente, para no chocar con timeouts):
podman run -d --name bmtest docker.io/ubuntu:22.04 sleep infinity
podman exec -it bmtest bash
# dentro: apt-get install python3-pip python3-venv cmake build-essential \
#   libx11-dev libwayland-dev libegl1-mesa-dev ... ; pip install kivy pyinstaller
# compilar SDL2 2.32, hacer el swap, y comprobar:
#   - ventana real: xvfb-run ... --screenshot -> "OpenGL version <b'...'>"
#   - máxima glibc requerida por _internal/*.so*: <= 2.35
#     (objdump -T <lib> | grep -oE 'GLIBC_[0-9.]+' | sort -V | tail -1)
```

El binario resultante pesa ~50 MB (vs ~170 MB del intento en Arch, que
arrastraba más libs).

### Gotchas de GitHub Actions (aplican a cualquier job)

1. **Comentarios en comandos multilínea**: El runner puede usar
   `shell: sh -e {0}`, que pasa el bloque entero como UN SOLO string al
   shell. Los `# comentarios` en medio de un comando partido con `\` se
   concatenan como ARGUMENTOS. Los comentarios van en sus propias líneas,
   nunca dentro del comando.

2. **`APPIMAGE_EXTRACT_AND_RUN=1`** para cualquier test que ejecute un
   AppImage en el runner (no tiene libfuse2). Lo mismo que hace
   `build_appimage.sh` con `appimagetool`.

3. **`inject_version.py` va ANTES de PyInstaller** y con la misma versión
   que el tag de la release (ver "Cuidado con la numeración" arriba);
   si no, el auto-update entra en bucle.

## Auto-update

- Lógica en `src/services/updater.py`; UI en `src/ui/widgets/root.py`
  (`check_updates`, `_show_update_available`, `_show_source_update`) y controles
  en el panel de ajustes de `src/views/main.kv`.
- Preferencia `auto_update` en `src/services/settings.py` (por defecto activada).
- Aplicación por plataforma: Linux AppImage reemplaza `$APPIMAGE`; Windows
  extrae a staging y relanza el binario nuevo con `--apply-update`; macOS y no
  soportados solo avisan.
- **Modo fuente**: al correr con `python3 src/main.py` no hay binario que
  reemplazar, así que la actualización es `git pull --ff-only` + reinicio
  (`updater.source_update` / `relaunch_source`). Solo aplica si hay `.git` en
  `APP_DIR`; sin él no se ofrece actualización automática. Compara contra el
  último tag del checkout (`source_tag`) para no ofrecer la misma versión en
  cada arranque. Si hay cambios locales sin confirmar no toca nada y lo avisa
  en el diálogo.
- Los diálogos usan `AppPopup`/`AppProgressBar` (reglas en `views/dialogs.kv`),
  no los widgets por defecto de Kivy.
- **Bit de ejecución**: `downloader.py` hace `chmod +x` al fichero descargado
  (`mode | 0o111`) tras renombrar el `.part`. Sin esto, si el self-replace falla,
  el fallback "Downloaded to … Open it to install" apunta a un `.AppImage` a
  `644` y el doble clic da "Permiso denegado" (bug visto en Linux Mint).
- **`_apply_appimage` valida `$APPIMAGE`**: si no está definido, `Path("").resolve()`
  es el directorio actual y el `os.replace` fallaba sin motivo aparente. Ahora
  comprueba que sea un fichero, loguea el motivo real y, ante cualquier fallo,
  deja la copia descargada ejecutable (`_make_executable`) para que el usuario
  pueda aplicarla a mano.
- **Cuidado al reemplazar el AppImage en ejecución**: el flujo es `copy2` a
  `target.new`, `chmod 0755`, `os.replace` y `Popen` del nuevo. Funciona en Linux
  (el inodo viejo sigue vivo), pero si `target` es un directorio o no está
  definido se cierra la app sin haber instalado nada — de ahí la validación.
- Firma de Windows: **descartada de momento** (un self-signed no reduce
  SmartScreen/AV). Si aparecen falsos positivos, valorar CA real o Azure
  Trusted Signing y resubmit a WDSI.

## Verificación de UI sin pantalla

Como en el CI, Kivy puede correr sin display:

```bash
cd src && SDL_VIDEODRIVER=offscreen KIVY_WINDOW=sdl2 KIVY_NO_ARGS=1 python3 -c "
from kivy.factory import Factory
from kivy.lang import Builder
from ui import theme
import ui.widgets as W
theme.init()
for name in dir(W):
    obj = getattr(W, name)
    if isinstance(obj, type):
        Factory.register(name, cls=obj)
for name in ('widgets.kv', 'dialogs.kv', 'cards.kv', 'main.kv'):
    Builder.load_file('views/' + name)
r = W.RootWidget()
print(r.current_version, r.show_filters)
"
```

Registrar en `Factory` las clases propias usadas en los `.kv` antes de
`Builder.load_file`, igual que hace `run_ui` en `src/main.py`. Los `.kv` a
cargar son los de `KV_FILES` en `main.py`.
