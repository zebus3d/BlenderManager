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
  ui/                # theme, icons, tooltip, widgets (lógica de la pantalla)
  views/gui.kv       # interfaz declarativa Kivy
packaging/           # spec de PyInstaller, scripts de build, inject_version.py
tests/               # unittest
```

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

Cuando quieras que las apps instaladas se actualicen solas, empuja un tag
`vX.Y.Z`:

```bash
git tag -a v1.2.0 -m "Blender Manager v1.2.0"
git push origin master   # si aún no está empujado
git push origin v1.2.0
```

Esto compila los 3 binarios con esa versión y publica la release como `latest`.
El auto-update de la app consulta `.../releases/latest`, que **ignora
pre-releases y drafts**: solo salta con tags estables.

### Reglas que no hay que romper

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

## Auto-update

- Lógica en `src/services/updater.py`; UI en `src/ui/widgets.py`
  (`check_updates`, `_show_update_available`) y controles en el panel de
  ajustes de `src/views/gui.kv`.
- Preferencia `auto_update` en `src/services/settings.py` (por defecto activada).
- Aplicación por plataforma: Linux AppImage reemplaza `$APPIMAGE`; Windows
  extrae a staging y relanza el binario nuevo con `--apply-update`; macOS y no
  soportados solo avisan.
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
from ui.widgets import RootWidget, ZoomSlider  # + clases del .kv
theme.init(); Builder.load_file('views/gui.kv')
r = RootWidget()
print(r.current_version, r.show_filters)
"
```

Registrar en `Factory` las clases propias usadas en el `.kv` antes de
`Builder.load_file`, igual que hace `run_ui` en `src/main.py`.
