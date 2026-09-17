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

### Favoritos

No son un canal de Blender: son un filtro **transversal** que el usuario marca
con la estrella de cada tarjeta. Se guardan en `settings.favorites` como claves
de `model.build.favorite_key` (**rama|versión**, sin plataforma ni arquitectura
a propósito: `InstalledBuild` no las guarda, y así marcar 4.5.5 en la tienda
marca también la instalada). Se guarda la *serie* y no la build exacta para que
un favorito sobre una diaria no se pierda cuando Blender publica la siguiente.

El canal `"favorites"` lo resuelven las mismas funciones puras que el resto
(`api.filter_builds`, `installed.filter_installed`) con el argumento
`favorites`; ahí no se excluyen las experimentales, porque manda lo que el
usuario haya marcado. **No lo filtres en la UI.**

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

Todo lo gestiona `.github/workflows/build.yml` (y `promote.yml` para publicar).
**No hay que crear tags para tener binarios publicados.**

### Un push a main actualiza el único pre-release

Basta con empujar a `main`:

```bash
git push origin main
```

El workflow calcula la versión y actualiza **el mismo pre-release** (`v1.3.0`)
con los 3 binarios + `checksums.txt`: mueve el tag al commit nuevo y reemplaza
los assets (mismos nombres). **Nunca hay más de un pre-release**, y su tag es ya
el de la versión final a la que aspira ese ciclo.

Mientras iteres, la gente no recibe nada: el auto-update consulta
`.../releases/latest`, que **ignora los pre-releases**. Antes cada push
publicaba una release final y disparaba el auto-update de todos; se cambió
porque acababa en un montón de versiones y pre-releases sueltos.

Para probar algo sin que salga en Releases, lanza el workflow a mano
(`workflow_dispatch`) sobre una rama que no sea `main`: compila y deja los
binarios como artefactos del run, sin publicar.

### Promover a release final

Actions → **promote** → *Run workflow*. `promote.yml` busca el pre-release y le
quita la marca de pre-release (`gh release edit --prerelease=false --latest`).

**No reconstruye nada**: reutiliza los binarios ya compilados y probados, y por
eso la versión cocida dentro de ellos sigue coincidiendo con el tag. Es el
motivo de que todas las iteraciones de un ciclo compartan versión con la final
(`v1.3.0`): solo cambia la marca.

Tras promover, el siguiente push a main calcula la **minor siguiente**
(`v1.4.0`) y empieza un ciclo nuevo: la versión se saca de la última release
**final** (`/releases/latest`, que ignora pre-releases) + 1 en la minor.

### Publicar una release con un número concreto

Empujar un tag `vX.Y.Z` compila los 3 binarios con esa versión y publica una
release **final** directamente (sin pasar por el pre-release):

```bash
git tag -a v1.3.0 -m "Blender Manager v1.3.0"
git push origin main   # si aún no está empujado
git push origin v1.3.0
```

### Por qué no reetiquetar binarios ya subidos

La versión va *cocida dentro del binario* (`inject_version.py` reescribe
`src/version.py` antes de compilar). Si creas un tag `v1.2.0` apuntando a los
binarios de `v1.1.87`, la app instalada seguirá diciendo «1.1.87», verá que
`1.2.0` es más nueva, se actualizará... y volverá a decir «1.1.87»: **bucle
infinito de actualización**. Reetiqueta siempre recompilando — y por eso
promover no toca la versión, solo la marca de pre-release.

**Cuidado con la numeración**: si etiquetas a mano con un número más bajo que el
que ya tienen algunos usuarios, nunca les llegará. A mano, **sube siempre la
minor** (`v1.3.0`).

### Reglas que no hay que romper

- **Una etiqueta con texto que puede ser largo se hace con `ElidedLabel`**
  (`ui/widgets/labels.py`), nunca con un `QLabel` pelado. Un `QLabel` pide como
  ancho mínimo el texto **completo**, así que deforma el layout: el nombre de una
  carpeta instalada medía 483 px y arrastraba su tarjeta a 507 px en la rejilla
  mientras las de al lado se quedaban en 249 (columnas desiguales), y en lista el
  meta con la ruta la llevaba a 974 px en una ventana de 900. `ElidedLabel`
  recorta con `…` al pintar, deja el texto entero en `text()` y en el tooltip
  (solo cuando no cabe) y no pide ancho. Para nombres de fichero, `ElideMiddle`.
- **Tienda e instaladas comparten medidas de tarjeta.** `GridBuildCard` y
  `GridInstalledCard` usan el mismo `_grid_height(zoom)` y el mismo logo
  (`60·zoom`); `BuildCard` e `InstalledCard`, 68 px de alto y logo de 44. Si una
  crece y la otra no, al cambiar de pestaña las tarjetas bailan de tamaño y el
  logo cambia. La fila de la etiqueta (insignia "LTS"/"Instalada" en la tienda,
  aviso de actualización en instaladas) se reserva siempre, aunque vaya vacía.
  Lo vigila `test_las_instaladas_miden_como_las_de_la_tienda`. Son deliberadamente
  **compactas** (unos 6 px de holgura sobre el contenido): para verlas grandes
  está el zoom, no conviene engordarlas.
- **El "look" va en `ui/qss.py`, no en el código.** Un widget nuevo se estiliza
  dándole un `objectName` (o una propiedad dinámica, p. ej. `variant` en
  `CardButton`) y añadiendo la regla al QSS. Ojo con la especificidad: en QSS
  `#Card[installed="true"]` y `#Card:hover` empatan, y gana la última; por eso
  los `:hover` van al final del bloque.
- **Nada de importar Qt en `services/`, `model/`, `i18n.py` ni `paths.py`.**
  Esa capa es independiente de la UI (es lo que permitió el port); si necesita
  avisar de algo, expone funciones puras o callbacks.
- **El código se lee como material de aprendizaje.** El README lo vende como un
  proyecto de fin de curso y hay que sostenerlo: docstrings en lo público (que
  expliquen el *por qué*, no repetir el nombre de la función), comentarios en
  español contando la decisión, y nada de trucos sin explicar. Si algo necesita
  un comentario para entenderse, **se escribe el comentario**; si no, se
  simplifica el código. Las claves de i18n van en inglés, pero los comentarios y
  los docstrings van en español, con acentos (el resto del proyecto los lleva).
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

### El otro gotcha: el OpenSSL del binario no encuentra las CAs

El OpenSSL que va dentro del binario viene de Ubuntu 22.04 y busca las
autoridades en las rutas de Debian (`/usr/lib/ssl/cert.pem`, `/usr/lib/ssl/certs`).
En **Arch, Fedora y otras distros esas rutas no existen**, así que *todas* las
peticiones HTTPS fallaban con:

```
CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate
```

Y el fallo quedaba medio tapado, que es lo peor: el listado de compilaciones caía
al caché de disco (parecía que había red) y el aviso de actualización decía "ya
tienes la última versión" en lugar de avisar de que no había podido preguntar.
Se descubrió en Arch (EndeavourOS) al no ofrecer la actualización a la 1.4.0.

Por eso **todas** las llamadas pasan un contexto explícito:
`services/tls.ssl_context()`, que localiza un almacén de CAs que exista de verdad
(`/etc/ssl/certs/ca-certificates.crt` y compañía). Si añades una petición HTTP
nueva, pásale el contexto; no uses `urlopen` a pelo. En el CI (Ubuntu) el fallo
no se reproduce, así que los tests solo cubren la función, no el síntoma.

### Y el tercero: `LD_LIBRARY_PATH` rompe los programas externos

El bootloader de PyInstaller mete la carpeta `_internal` en `LD_LIBRARY_PATH`
(deja el valor previo en `LD_LIBRARY_PATH_ORIG`) y **el entorno se hereda a
cualquier hijo**. En el AppImage, `xdg-open` y, detrás, el navegador o Blender
cargaban las `libstdc++`, `libssl`, `libglib`... del bundle en vez de las del
sistema y no arrancaban — casi siempre en silencio, porque el lanzamiento sí se
produce (el aviso de "no se pudo abrir el navegador" no saltaba). En modo fuente
no hay contaminación, así que solo se veía en el binario. Comprobado leyendo
`/proc/<pid>/environ` de un binario empaquetado:

```
LD_LIBRARY_PATH=/ruta/dist/BlenderManager/_internal
```

Por eso **nada externo se lanza a pelo**: `services/opener` (`clean_env`,
`open_url`, `open_path`, `reveal`) es el único camino para abrir URLs, carpetas
o lanzar Blender (`launcher.launch` le pasa `env=clean_env()`). Si añades una
llamada a `xdg-open`/`webbrowser`/`Popen` de un programa de fuera, pásale ese
entorno o el fallo vuelve.

### El spec (`packaging/blendermanager.spec`)

- **Windows se empaqueta `--onefile`, Linux/macOS one-folder.** El spec ramifica
  por `sys.platform`: en Windows la `EXE` se lleva `a.binaries`/`a.datas` y no hay
  `COLLECT`, así que el asset es un **único `BlenderManager.exe`** (sin
  `_internal`). Se hizo así porque el reparto Windows es un `.zip` manual y el
  error clásico del usuario era descomprimir solo el `.exe` (o borrar `_internal`)
  y encontrarse con `Failed to load Python DLL ... python312.dll`. El precio es un
  arranque más lento (descomprime ~100 MB en `%TEMP%` cada vez) y más ruido con
  antivirus heurísticos. Linux/macOS siguen one-folder (arranque instantáneo); el
  updater funciona en ambos layouts (`_apply_windows` busca el `.exe` y copia su
  carpeta, que en onefile es solo el ejecutable).
- `datas` solo lleva `src/assets` (ya no hay `views/`).
- **Iconos**: `packaging/icons/blendermanager.ico` (Windows) y `.icns` (macOS)
  los genera `packaging/make_icons.py` a partir de
  `src/assets/images/app_icon.png`, y se dejan en el repo para no depender de Qt
  antes de empaquetar. **Qt solo escribe un tamaño por fichero** (si encadenas
  `write()` se queda con el primero), así que los contenedores se montan a mano:
  el `.ico` uniendo los ICO de un tamaño que escribe Qt (pixeles en BMP/DIB, lo
  más compatible) y el `.icns` concatenando PNG con el código que toca a cada
  tamaño (`icp4`=16, `icp5`=32, `icp6`=64, `ic07`=128, `ic08`=256, `ic09`=512).
  Si cambias el PNG, vuelve a ejecutar el script.
- **El AppImage no usa esos ficheros**: `build_appimage.sh` copia el PNG como
  `blendermanager.png`, el `.desktop` con `Icon=blendermanager` y un `.DirIcon`
  (que es lo que enseña el gestor de ficheros). Si alguien dice que "el AppImage
  sale sin icono", **el icono va dentro**: comprobarlo con
  `./BlenderManager-x86_64.AppImage --appimage-extract` y mirar la raíz del
  AppDir. Lo que falta suele ser del sistema, no del paquete (comprobado con un
  usuario real):
  - **KDE/Dolphin**: `kio-extras` ya trae el plugin
    `thumbcreator/appimagethumbnail.so`, pero le falta la librería: `ldd` sobre
    ese .so dice `libappimage.so.1.0 => not found` hasta que se instala
    `libappimage` (paquete de `extra` en Arch). Después hay que **activar la
    vista previa** en Dolphin (Interfaz → Vistas previas) y borrar la caché de
    intentos fallidos (`~/.cache/thumbnails/*`).
  - **Cinnamon/Nemo** (Linux Mint): funciona de serie, porque Mint instala
    `xapp-thumbnailers`, que incluye un generador de miniaturas de AppImage que
    lee el `.DirIcon`.
  El CI verifica que el icono va dentro en cada build.
- **`QT_EXCLUDES`** deja fuera los módulos de Qt que no usamos (WebEngine, QML,
  Multimedia, 3D...) para no arrastrar ~100 MB de más.
- **No excluir `shiboken6` ni `shiboken6.Shiboken`**: PySide6 los necesita para
  arrancar. Sin ellos el binario falla con
  `ModuleNotFoundError: No module named 'shiboken6.Shiboken'` — y el smoke test
  no lo pilla, porque `--smoke` no importa Qt. Por eso el CI ahora lanza además
  la GUI empaquetada con el plugin *offscreen* en las tres plataformas.

### Avisos falsos de antivirus en Windows (y qué NO hacer)

Es un problema **conocido y esperado**, no un fallo del código: un `.exe` de
PyInstaller **sin firmar** cae a menudo en los heurísticos de Defender (típico
`Trojan:Win32/Wacatac.B!ml`, `PUA:Win32/...`). El bootloader se auto-extrae y eso
es justo el patrón que usan muchos malwares hechos con PyInstaller, así que el
detector dispara por parecido. `--onefile` es más propenso que one-folder, pero
lo elegimos a propósito para que no exista `_internal` que borrar (ver arriba).

**Lo que NO basta, o engaña:**

- **Certificado autofirmado** (`New-SelfSignedCertificate` + `Set-AuthenticodeSignature`,
  la técnica de `hurricane_solver`): **no quita SmartScreen** (no lo avala una CA)
  y cada build genera un certificado distinto, así que no da reputación. Puede
  suavizar heurísticos de algunos antivirus (el malware rara vez va firmado), pero
  no es una solución. Aun así lo hacemos **best-effort** en el job de Windows
  (`continue-on-error`, no rompe el release si el runner no deja firmar), porque
  es barato. Ojo con la comparación: que en `hurricane_solver` «no dé alertas» no
  demuestra que la firma funcione, porque aquel `.exe` es de **C++ (MSBuild)**, no
  un onefile de PyInstaller; los heurísticos de Defender disparan sobre todo por
  el bootloader que se auto-extrae.
- Recomponer el bootloader de PyInstaller desde fuente: en la práctica da **más**
  falsos positivos, y añade un toolchain C al CI.

**Lo que sí funciona, gratis y sin cuenta (la vía de Blender Launcher V2):**

1. **Enviar la muestra a Microsoft** en el portal WDSI
   (<https://www.microsoft.com/en-us/wdsi/filesubmission>) marcándola como
   *Clean (false positive)*. No hace falta cuenta (el correo es opcional) y
   Microsoft saca el hash de las definiciones en uno o dos días. Ayuda
   `python packaging/report_false_positive.py <exe-o-zip>`, que calcula el
   SHA-256 y abre el portal.
   **¿Hay que hacerlo por cada build? No:**
   - Solo importan las releases **estables promovidas**. Los push a `main`
     actualizan un pre-release que el auto-update ignora y nadie descarga.
   - Los nombres con `!ml` son detecciones **genéricas** (machine learning): al
     confirmar el falso positivo, Microsoft suele ajustarlas y dejan de marcar
     builds parecidas. Se reenvía **solo cuando vuelve a saltar**, no en cada
     versión.
   - La **auto-actualización no pasa por SmartScreen**: la hace la app con
     `urllib`, que no pone Mark-of-the-Web (eso lo pone el navegador). El popup
     azul solo lo ve quien baja el `.zip` a mano.
   - Si aparece la marca, comparar en **VirusTotal** el `.exe` nuevo con el de la
     versión anterior: si el anterior no está marcado y el nuevo sí, es el
     heurístico del bootloader y toca enviarlo.
2. **Mantener PyInstaller al día**: cada release recompila el bootloader y suele
   tardar en estar en las listas negras. `requirements-build.txt` pide `>=6.6`.
3. **Documentar y verificar**: el README lleva el SHA-256 de cada asset
   (`checksums.txt`); quien quiera puede confirmar que el fichero es el nuestro.

Blender Launcher V2 (el proyecto hermano, 700+ estrellas) está **igual**: su zip
de Windows es un único `.exe` con `--onefile --windowed --noupx`, **sin firmar**,
y lo que hace con los falsos positivos es enviarlos a Microsoft (issue #87). No
hay poción mágica.

**El popup azul de SmartScreen** ("Windows protegió tu PC") solo lo quita un
certificado de una CA: es reputación de editor + hash, y el Mark-of-the-Web del
navegador lo dispara siempre. Para un usuario que baja el `.zip` de Releases,
**no hay forma de evitarlo** sin firmar; el usuario le da a "Más información" →
"Ejecutar de todas formas". La única alternativa es **SignPath** (gratis para
open source; registro + GitHub Action, la clave vive en su HSM, no en el repo).

Se evaluó **winget** para saltarse el popup (no hay descarga del navegador, así
que no hay Mark-of-the-Web) y se **descartó**: obliga al usuario inexperto a
aprender a usar un comando en una terminal, que es precisamente el público de
esta app. No merece la pena a cambio de quitar un aviso que se salta con dos
clics. Si algún día se retoma, la idea era `.github/workflows/winget.yml` con
`vedantmgoyal9/winget-releaser` y un PAT propio en `WINGET_ACC_TOKEN`.

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
    main limpio sale `1.2.0` y en una rama por delante,
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
- Firma de Windows: se firma **best-effort** con un autofirmado (no quita
  SmartScreen; ver "Avisos falsos de antivirus en Windows"). Para quitarlo de
  verdad, valorar SignPath (gratis para OSS), una CA real o Azure Trusted
  Signing, y enviar los falsos positivos a WDSI.

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

**Ojo al fijar el zoom en memoria** (lo hace `packaging/capture_docs.py` para que
las capturas salgan siempre iguales): `closeEvent` vuelca el zoom pendiente en
`settings.json`, así que un script que haga `window.zoom = 1.0` y no aísle la
config **deja el zoom cambiado al usuario**. En la app es lo correcto (si cierras
justo tras mover el slider, se guarda), pero en tests y scripts hay que
redirigir `settings.config_dir` a un directorio temporal (lo hace el mixin
`SettingsIsolated` de `tests/test_ui.py` y el `with tempfile` del script de
capturas).
