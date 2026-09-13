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

## Auto-update

- Lógica en `src/services/updater.py`; UI en `src/ui/widgets.py`
  (`check_updates`, `_show_update_available`, `_show_source_update`) y controles
  en el panel de ajustes de `src/views/gui.kv`.
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
- Los diálogos usan `AppPopup`/`AppProgressBar` (reglas en `gui.kv`), no los
  widgets por defecto de Kivy.
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
