# AGENTS.md

Guía para trabajar en **BlenderManager** (app Kivy de descarga/gestión de
versiones de Blender). El código y los comentarios están en español; las claves
de i18n son cadenas en inglés (ver `src/i18n.py`).

## Estructura

```
src/
  main.py            # entrada, QApplication, --smoke / --screenshot / --apply-update
  version.py         # __version__ (el CI la reescribe desde el tag)
  paths.py           # APP_DIR / RESOURCE_DIR
  i18n.py            # traducciones es/en
  model/build.py     # modelo de compilación
  services/          # api, downloader, extractor, installed, launcher,
                     # detector, settings, updater
  ui/
    theme.py         # tokens de color (+ contraste WCAG medido)
    qss.py           # stylesheet global (el "look" de toda la app)
    icons.py         # glifos de Font Awesome
    fonts.py         # carga de la fuente de iconos / glyph_icon()
    widgets/
      buttons.py     # Pill, SideButton, CardButton, IconLinkButton, SwitchPill...
      cards.py       # tarjetas de la tienda e instaladas (lista y rejilla)
      dialogs.py     # AppDialog, confirm(), show_error(), update_available()
      main_window.py # MainWindow: controlador de la pantalla principal
doc/                 # guía de arquitectura en español (para principiantes)
packaging/           # spec de PyInstaller, scripts de build, inject_version.py
tests/               # unittest (la UI corre con QT_QPA_PLATFORM=offscreen)
run.sh               # lanzador de desarrollo (crea el venv si falta)
```

La UI es **PySide6 (Qt Widgets)**. El aspecto vive en `ui/qss.py`; los widgets
llevan un `objectName` (o una propiedad dinámica) que el QSS usa como selector.
`ui/widgets/__init__.py` reexporta todo, así que `from ui.widgets import X`
sigue funcionando.

`services/`, `model/`, `i18n.py`, `paths.py` y `updater.py` son **independientes
de la UI** (no importan Qt): es lo que permitió portar la interfaz sin tocarlos
y lo que hay que preservar al refactorizar.

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
# App en desarrollo (crea el .venv si falta)
./run.sh

# Equivalente sin el script
.venv/bin/python src/main.py

# Tests (la UI corre sin pantalla, con QT_QPA_PLATFORM=offscreen)
.venv/bin/python -m unittest discover -t . -s tests -v

# Build local (one-folder; --appimage añade el AppImage en Linux)
python3 packaging/inject_version.py 1.2.3   # opcional: fija la versión local
packaging/build.sh
packaging/build.sh --appimage
```

En modo fuente la app **no** comprueba actualizaciones (solo si `sys.frozen`).
Para verificar la UI sin pantalla se usa el plugin *offscreen* de Qt (ver más
abajo).

## Releases (lo importante)

Todo lo gestiona `.github/workflows/build.yml`. **No hay que crear tags para
tener binarios publicados.**

### Un push a master = una release

Basta con empujar a `master`:

```bash
git push origin master
```

El workflow calcula la versión (`v1.1.<nº de build>`, usando el último tag como
base) y publica una **release final** (no pre-release) con los 3 binarios +
`checksums.txt`, marcada como `latest`. **No hay paso de promoción** ni canal
de pre-releases: cada commit es una release.

Consecuencia a tener en cuenta: como la release es `latest`, el auto-update de
la app (que consulta `.../releases/latest`) **salta en todos los usuarios** en
el siguiente arranque. Es intencionado. Si necesitas probar algo sin que llegue
a la gente, lanza el workflow a mano (`workflow_dispatch`) sobre una rama que
no sea `master`, o desmarca el auto-update temporalmente.

### Publicar una release con un número concreto

Empujar un tag `vX.Y.Z` compila los 3 binarios con esa versión:

```bash
git tag -a v1.2.0 -m "Blender Manager v1.2.0"
git push origin master   # si aún no está empujado
git push origin v1.2.0
```

### Por qué no reetiquetar binarios ya subidos

La versión va *cocida dentro del binario* (`inject_version.py` reescribe
`src/version.py` antes de compilar). Si creas un tag `v1.2.0` apuntando a los
binarios de `v1.1.87`, la app instalada seguirá diciendo «1.1.87», verá que
`1.2.0` es más nueva, se actualizará... y volverá a decir «1.1.87»: **bucle
infinito de actualización**. Reetiqueta siempre recompilando.

**Cuidado con la numeración**: el parche es el número de run de GitHub Actions,
que solo sube (`v1.1.87`, `v1.1.88`...). Si etiquetas a mano con un parche más
bajo (`v1.1.2`), será *más antigua* que la que ya tienen algunos usuarios y
nunca les llegará. Para etiquetar a mano, **sube siempre la minor** (`v1.2.0`).

### Reglas que no hay que romper

- **El "look" va en `ui/qss.py`, no en el código.** Un widget nuevo se estiliza
  dándole un `objectName` (o una propiedad dinámica, p. ej. `variant` en
  `CardButton`) y añadiendo la regla al QSS. Ojo con la especificidad: en QSS
  `#Card[installed="true"]` y `#Card:hover` empatan, y gana la última; por eso
  los `:hover` van al final del bloque.
- **Nada de importar Qt en `services/`, `model/`, `i18n.py` ni `paths.py`.**
  Esa capa es independiente de la UI (es lo que permitió el port); si necesita
  avisar de algo, expone funciones puras o callbacks.
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

## Build Linux portable (PySide6)

El job `linux:` compila en **Ubuntu 22.04 sin contenedor**. Con Qt Widgets la
portabilidad es sencilla: **no hay OpenGL de por medio** (Qt renderiza con el
motor *raster*, CPU), así que el binario no depende del Mesa del anfitrión.

### El bug que motivó dejar Kivy

Kivy exige OpenGL vía SDL2. El Kivy que trae pip embebe su propia SDL2, y en
**Mesa 25/26** (Linux Mint 22, Arch/CachyOS) la ventana no abría:

```
No matching FB config found
# o, forzando Wayland:
Could not get EGL display
```

Se probaron cuatro enfoques sin éxito (SDL2 2.30, SDL2 2.32, `sdl2-compat` +
SDL3, y Kivy compilado desde fuente con SDL3): todos funcionaban en Ubuntu
22.04 y fallaban contra el Mesa moderno. **No volver a intentarlo.** La salida
fue portar la UI a Qt (`ui/qss.py`, `ui/widgets/`), que no usa GL.

### glibc

El binario embebe el intérprete de Python, y ese intérprete fija la glibc
mínima del anfitrión. Ubuntu 22.04 da **glibc 2.35**, que cubre Ubuntu 22.04+,
Debian 12+, **Linux Mint 21/22**, Fedora 36+, openSUSE Leap 15.5+ y Arch.
`PySide6-Essentials` solo pide **glibc 2.34**, así que el techo lo pone el
Python, no Qt.

**NO compilar en una distro rolling** (Arch): el Python de Arch exige glibc
2.44 y crashea en Mint 22 / Ubuntu 24.04 (glibc 2.39) con
`libm.so.6: version GLIBC_2.44 not found`.

### El único gotcha: el plugin xcb de Qt

Qt necesita el plugin de plataforma `xcb` (aunque renderice en CPU). Sus
dependencias tienen que estar en el runner **para que PyInstaller las bundlee**;
si no, el AppImage no abre en el equipo del usuario:

```
qt.qpa.plugin: Could not load the Qt platform plugin "xcb"
```

Son estas (el job `linux:` las instala): `libxcb-icccm4`, `libxcb-image0`,
`libxcb-keysyms1`, `libxcb-randr0`, `libxcb-render-util0`, `libxcb-shape0`,
`libxcb-xinerama0`, `libxcb-xkb1`, `libxkbcommon-x11-0`, `libxcb-cursor0`
(esta última es requisito desde Qt 6.5). Comprobar con:

```bash
ldd dist/BlenderManager/_internal/PySide6/Qt/plugins/platforms/libqxcb.so | grep "not found"
```

### El spec (`packaging/blendermanager.spec`)

- `datas` solo lleva `src/assets` (ya no hay `views/`).
- `QT_EXCLUDES` deja fuera los módulos de Qt que no usamos (WebEngine, QML,
  Multimedia, 3D...) para no arrastrar ~100 MB de más.
- **No excluir `shiboken6` ni `shiboken6.Shiboken`**: PySide6 los necesita para
  arrancar. Sin ellos el binario falla con
  `ModuleNotFoundError: No module named 'shiboken6.Shiboken'` — y el smoke test
  no lo pilla, porque `--smoke` no importa Qt. **Probar siempre la GUI.**

### Verificación antes de tocar el job

```bash
# Ubuntu 22.04 (persistente, para no chocar con timeouts):
podman run -d --name bmtest docker.io/ubuntu:22.04 sleep infinity
podman exec -it bmtest bash
# dentro: apt-get install python3-pip python3-venv <libs xcb de arriba> ; \
#   pip install -r requirements-build.txt
# pyinstaller ... ; y comprobar:
#   - GUI:  QT_QPA_PLATFORM=offscreen ./dist/BlenderManager/BlenderManager --screenshot /tmp/x.png
#   - glibc máxima de _internal/*.so*: <= 2.35
#     (objdump -T <lib> | grep -oE 'GLIBC_[0-9.]+' | sort -V | tail -1)
```

El AppImage resultante pesa ~70 MB.

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

- Lógica en `src/services/updater.py`; UI en `src/ui/widgets/main_window.py`
  (`check_updates`, `_show_update_available`, `_show_source_update`) y controles
  en el panel de ajustes (dentro de `_build_settings_view`).
- Preferencia `auto_update` en `src/services/settings.py` (por defecto activada).
- Aplicación por plataforma: Linux AppImage reemplaza `$APPIMAGE`; Windows
  extrae a staging y relanza el binario nuevo con `--apply-update`; macOS y no
  soportados solo avisan.
- **Modo fuente**: al correr con `python3 src/main.py` no hay binario que
  reemplazar, así que la actualización es `git pull --ff-only` + reinicio
  (`updater.source_update` / `relaunch_source`, con `AppDialog` propio). Solo
  aplica si hay `.git` en `APP_DIR`.
  - **No se avisa al arrancar**: un checkout de desarrollo va por delante del
    último tag, así que compararlo con la última release publicada ofrecería
    "actualizar" a un binario que puede ser más viejo que el código que corre.
    La comprobación automática se salta y el `git pull` solo se ofrece cuando el
    usuario pulsa "Check for updates now".
  - La versión que se muestra (título y Ajustes) es el **describe** del
    checkout, no el tag: `app_version()` usa `source_describe()`, así que en
    master limpio sale `1.2.0` y en una rama por delante,
    `1.2.0-19-g24a0b43`. El tag a secas (`source_tag`) engañaba: decía "1.2.0"
    con 19 commits de cambios aplicados.
  - `source_update` distingue `"ok"`, `"up-to-date"` (el pull no movió HEAD),
    `"dirty"` (cambios locales sin confirmar: no toca nada y lo avisa) y
    `"failed"`.
  - El diálogo es **modal**, así que para reiniciar hay que cerrarlo
    (`dialog.accept()`) antes de cerrar la ventana; si no, `exec()` no devuelve
    y el bucle de eventos no termina.
- Los diálogos son propios (`AppDialog` en `ui/widgets/dialogs.py`), no
  `QMessageBox`: el estilo nativo claro desentona con el tema oscuro.
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

Qt tiene un plugin *offscreen*, así que la UI se puede montar sin servidor
gráfico (es lo que usa el CI y `tests/test_ui.py`):

```bash
cd src && QT_QPA_PLATFORM=offscreen ../.venv/bin/python -c "
from PySide6.QtWidgets import QApplication
app = QApplication([])
from ui import fonts, qss
fonts.load(); app.setStyleSheet(qss.build_qss())
from ui.widgets import MainWindow
w = MainWindow()
print(w.current_version, w.view)
"
```

Dos cosas a tener en cuenta:

- El plugin **tiene que fijarse ANTES de crear `QApplication`** (por eso va en
  el entorno del comando, no dentro del script). Si se crea antes, Qt elige el
  plugin por defecto y falla sin display.
- `MainWindow` lanza la carga de builds en un `QTimer` a los 100 ms, así que en
  un script de un tirón hay que dejar correr el bucle de eventos
  (`QTimer.singleShot(9000, app.quit); app.exec()`) para que lleguen datos.

Para una captura: `w.grab().save("/tmp/x.png")` (no depende de GL, a diferencia
del `Window.screenshot` de Kivy). Y `tests/test_ui.py` trae ejemplos de montar la
ventana e inyectar builds sin tocar la red.
