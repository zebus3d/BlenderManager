# AGENTS.md

Guía para trabajar en **BlenderManager** (app PySide6 de descarga/gestión de
versiones de Blender; nació en Kivy y se portó a Qt, ver más abajo). El código
y los comentarios están en español; las claves de i18n son cadenas en inglés y
los textos viven en `src/locale/<idioma>.json`.

## Estructura

```
src/
  main.py            # entrada, QApplication, --smoke / --screenshot / --apply-update
  version.py         # __version__ (el CI la reescribe desde el tag)
  paths.py           # APP_DIR / RESOURCE_DIR
  i18n.py            # el mecanismo (detectar idioma, cargar, tr())
  locale/es.json     # los textos en español (la clave es el inglés)
  model/build.py     # modelo de compilación
  services/          # api, channels, downloader, extractor, installed,
                     # organizer, launcher, recent, addons, detector,
                     # settings, autostart, elevate, opener, sources, tls,
                     # macos_dmg, updater y la familia blender_*:
                     #   blender_config    dónde vive la config de cada versión
                     #   blender_addons    migrar addons y ficheros de prefs
                     #   blender_snapshots guardados de "valores de fábrica"
                     #   blender_prefs     preferencias clave a clave
                     #   blender_runner    arrancar Blender en --background
                     #   blender_style     tema y keymap como presets
  ui/
    theme.py         # tokens de color (+ contraste WCAG medido)
    qss.py           # stylesheet global (el "look" de toda la app)
    icons.py         # glifos de Font Awesome
    fonts.py         # carga de la fuente de iconos / glyph_icon()
    widgets/
      main_window.py   # la cáscara: cabecera, lateral, pie, navegación, bandeja
      build_lists.py   # Nube y Local: filtros, rejilla, zoom y refiltrado
      settings_view.py # la pantalla de Ajustes
      folder_library.py# la biblioteca de carpetas
      downloads.py     # descargar, instalar, lanzar y borrar versiones
      updates.py       # actualizar BlenderManager
      shell.py         # tablas y widgets que comparten la ventana y sus partes
      migrate/         # la migración: view + addons_tab/prefs_tab/factory_tab
      addons.py        # gestor de addons
      recent.py        # ficheros recientes
      buttons.py       # Pill, SideButton, CardButton, IconLinkButton, SwitchPill...
      cards.py         # tarjetas (lista y rejilla) y settings_card / GripCard
      dialogs.py       # AppDialog, confirm(), show_error(), update_available()
      labels.py        # ElidedLabel y compañía
      layouts.py       # clear_layout, list_scroll, muted_note, FittedList
      menus.py         # card_menu (menús con el aspecto de la app)
      folders.py       # la fila de una carpeta de la biblioteca
      tray.py          # el icono de la bandeja
doc/                 # guía de arquitectura en español (para principiantes)
packaging/           # spec de PyInstaller, scripts de build, inject_version.py
tests/               # unittest (la UI corre con QT_QPA_PLATFORM=offscreen)
run.sh               # lanzador de desarrollo (crea el venv si falta)
```

**Ningún módulo de `src/` pasa de 1000 líneas**, y lo vigila
`tests/test_layout.py` con una lista de excepciones vacía. `main_window.py`
llegó a tener 3314 y `migrate.py` 2492: a partir de ahí nadie lee el fichero
entero, y lo que no se lee es donde se esconde el código repetido. Cuando uno
se acerca al tope se parte **por responsabilidad**, no por número de líneas.
Las partes de la ventana y de la migración son **mixins** de su clase, no
objetos independientes: todos trabajan sobre el estado del mismo widget y
meterlos en otro objeto solo movería el acoplo de sitio; lo que de verdad no
depende de la interfaz ya está en `services/`. `shell.py` existe solo para
romper la circularidad (la ventana importa sus partes y las partes necesitan
sus tablas).

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

**NO añadir un canal "Patch"** (las builds de pull requests abiertos de
`builder.blender.org/download/patch/`, con su `patch: "PR161547"`). Se probó
(commit `6a9933e`) y **se quitó a propósito**: el 99% de los usuarios no lo va a
usar, no son versiones oficiales, cambian a diario y meten cientos de filas de
ruido en la tienda. Es de nicho para quien verifica un PR concreto, y no merece
el coste en la interfaz. Si alguna vez se replantea, que sea como algo oculto
tras las opciones experimentales, nunca como pestaña normal.

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

## Biblioteca de carpetas

Las versiones ya no viven en "una carpeta y dos satélites". `settings.folders` es
una lista de `Folder(path, types, writable)`, y **`services/channels.py` es la
única definición** de qué tipo es una compilación (`type_of_build` para la
tienda, `type_from_marker`/`type_of_installed` para las instaladas). Antes esa
respuesta estaba en cuatro sitios; ahora de ella depende **en qué carpeta se
escriben cientos de MB**, así que no puede volver a duplicarse.

Reglas que no hay que romper:

- **Cada tipo tiene un único dueño.** Marcar LTS en una carpeta se lo quita a la
  que lo tuviera. Eso es lo que hace que `resolve_destination` sea un solo
  escalón y que el destino nunca sea ambiguo. `clean_folders` lo impone también
  sobre un `settings.json` editado a mano (gana el primero).
- **`writable=False` implica `types=[]`.** No se descarga donde no se escribe;
  cerrar el candado apaga las casillas. Así las casillas dicen *qué se descarga
  aquí* y el candado *si se puede tocar algo aquí*, sin solaparse. **Al volver a
  abrirlo se le devuelven los tipos huérfanos** (la misma regla que al añadir una
  carpeta): sin eso, cerrar y abrir dejaba la carpeta sin recibir nada y, si era
  la única, la app sin sitio donde descargar.
- **Anidar carpetas se permite.** Tener `Blender 3D` de raíz y
  `Blender 3D/Experimentales` dentro es un reparto natural, y no duplica nada
  porque `_scan_root` solo mira los hijos **directos** de cada raíz. Lo único
  que se rechaza al añadir es la misma carpeta dos veces.
- **Se puede quitar la última carpeta.** Negarlo encerraba al usuario: no podía
  cambiarla ni quitarla. Una lista vacía a propósito (la clave `folders` existe
  pero está vacía) **no se repone** al arrancar; solo se pone la de fábrica
  cuando no hay `settings.json`.
- **Solo lectura significa que la app no escribe NADA ahí**: ni descarga, ni
  borra, ni renombra, ni limpia `.part`. Dejar borrar pero no instalar sería
  incoherente. Lanzar y migrar sí funcionan (la migración escribe en la config
  de Blender, `~/.config/blender/<serie>`, no en la carpeta de instalación).
- **`destination_for` puede devolver `""`**: nadie recibe ese tipo. Hay que
  decírselo al usuario (`_no_folder_for`), nunca caer en una carpeta cualquiera.
  Al extraer se usa `archive.parent`, no se vuelve a preguntar: `Path("")` es el
  directorio actual y extraeríamos dentro de la app.
- **`organizer.move_build`: el origen no se borra hasta que el destino está
  completo y en su sitio.** Nada de `shutil.move` a pelo entre discos (copia y
  borra; si falla a mitad deja el destino incompleto y el origen tocado). Lo
  demuestra `test_un_fallo_a_media_copia_no_toca_el_origen`.
- **La migración del esquema 1 no mueve un byte.** `folders_from_legacy` decide
  la carpeta de las LTS **antes** que la de siempre, porque la exclusión mutua es
  "el primero se lo queda". `_legacy_mirror` sigue escribiendo los campos viejos
  por si alguien instala una versión anterior.
- **Nada de modales en el arranque.** El aviso de bienvenida a las carpetas se
  enseña una vez (`folders_hint_shown`) y el fixture de los tests lo trae ya
  marcado: un modal durante `MainWindow()` cuelga la suite entera.

## Idiomas: cuáles valdría la pena añadir

Hoy hay **es/en** (522 claves en `src/locale/es.json`). Si algún día se amplía, esta es
la lista razonada, para no elegir por intuición.

El mejor dato **no** es el número de usuarios sino el esfuerzo demostrado: la
propia Blender lleva la cuenta de sus traducciones en `locale/languages` de su
repo (`ID:Etiqueta:ISO:PORCENTAJE`). Una comunidad que sostiene el 100% de la
interfaz de Blender año tras año es una que también traduciría esto.

- **Al 100% o casi**: español, chino simplificado, ruso, francés, catalán,
  eslovaco, georgiano; japonés 99%, vietnamita 95%, tamil 94%, urdu 87%,
  turco 79%, portugués (PT) 73%, suajili 73%.
- **Grandes pero flojas**: alemán 37%, portugués (BR) 44%, italiano 45%,
  coreano 50%, polaco 18%, **hindi 4%**.
- **Tráfico de blender.org**: la mitad viene de 8 países — EE. UU., India, Reino
  Unido, Alemania, Rusia, Brasil, Japón y China
  (<https://www.blender.org/news/blender-by-the-numbers-2020/>).

Cruzando las dos listas: **chino simplificado, ruso y japonés** son los únicos
que salen arriba en ambas (comunidad enorme *y* traducción mantenida). India es
top-8 en tráfico pero el hindi está al 4%: esos usuarios trabajan en inglés.
Alemania y Brasil son top-8 con traducciones a medias.

**Orden sugerido**: chino simplificado → ruso → japonés → portugués (BR).
Y solo si hay alguien que se comprometa a mantenerlo: cada cadena nueva hay que
traducirla a *todos* los idiomas activos, y un idioma a medias (frases sueltas
en inglés) se ve peor que no tenerlo.

Las traducciones ya están en `.json` por idioma (`src/locale/`), así que
añadir uno es copiar el fichero y traducirlo: no hace falta tocar Python.
Ojo: el `.spec` tiene que copiar `src/locale` al binario o el empaquetado sale
siempre en inglés.

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

- **El alto de una lista con asa va FIJO, no negociado con el layout**
  (`ui/widgets/layouts.py: FittedList`). Dejándoselo negociar, cuando la
  ventana se queda corta Qt reparte a la baja y encoge la lista hasta su
  mínimo, arrastrando a su tarjeta: quedaba media fila cortada justo encima de
  los botones y parecía que se metían dentro del listado. Con el alto fijo la
  tarjeta mide lo que tiene que medir y lo que no cabe lo resuelve el scroll de
  la página (por eso las páginas de Migración van dentro de un `QScrollArea`).
  El suelo son filas **enteras**, medidas sobre una fila de verdad.
- **El Python de local NO es el del CI** (aquí 3.14, el CI 3.12), y eso esconde
  una clase entera de fallos: desde 3.14 las anotaciones son **diferidas**
  (PEP 649), así que un `-> QMenu` sin importar no se evalúa nunca en local y
  en 3.12 revienta el import del módulo al definir la función. Pasó al repartir
  `main_window.py`: `build_lists.py` se quedó usando `QMenu`, `QApplication` y
  `opener` sin importarlos, la suite pasaba en verde aquí y el CI se caía
  entero (test + smoke de Linux + bundle de macOS). Lo vigila ahora
  `tests/test_layout.py::test_ningun_modulo_usa_un_nombre_que_no_importa`, que
  usa `symtable` (análisis de ámbitos de verdad) y por eso no depende de qué
  Python lo ejecute. **Al mover código entre módulos, los imports no se
  deducen leyendo: se comprueban.**
- **Toda clave de i18n tiene que usarse.** Lo comprueba
  `tests/test_i18n.py::test_no_quedan_claves_sin_usar`, que recoge con `ast`
  todas las cadenas literales de `src/` (así valen las de `tr("...")` y las que
  viven en una tabla y se traducen por variable). Había 74 claves muertas y 5
  repetidas —y una repetida pisa a la anterior en silencio— cuando se añadió.
- **Los textos visibles hablan de "versiones de Blender", no de
  "compilaciones"**: el código interno sigue con `Build`/`InstalledBuild`, que
  ahí sí es lo que son. "Compilación" se reserva para lo que de verdad lo es
  (la build de un wheel para una versión de Python).
- **Una etiqueta con texto que puede ser largo se hace con `ElidedLabel`**
  (`ui/widgets/labels.py`), nunca con un `QLabel` pelado. Un `QLabel` pide como
  ancho mínimo el texto **completo**, así que deforma el layout: el nombre de una
  carpeta instalada medía 483 px y arrastraba su tarjeta a 507 px en la rejilla
  mientras las de al lado se quedaban en 249 (columnas desiguales), y en lista el
  meta con la ruta la llevaba a 974 px en una ventana de 900. `ElidedLabel`
  recorta con `…` al pintar, deja el texto entero en `text()` y en el tooltip
  (solo cuando no cabe) y no pide ancho. Para nombres de fichero, `ElideMiddle`.
  **Cuidado con meterlo en un `QHBoxLayout` con un `addStretch`**: como no pide
  ancho, se queda a 0 px y el texto no se ve (pasó con el nombre de los addons).
  Hay que añadirlo con factor de estirado (`addWidget(label, 1)`) o en un
  `QVBoxLayout`, que sí le da el ancho.
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
- **La fila de filtros vive con las listas, no es global.** Tienda (Nube) e
  Instaladas (Local) comparten un contenedor (`build_lists.py: _build_lists_view`) con la fila de
  44 px encima y un sub-stack debajo; Migración y Ajustes son páginas del stack
  principal y no llevan filtros. Antes la fila era global y se reservaba ocultando
  su contenido para que la interfaz no diera un salto de 44 px al cambiar de
  vista; ahora desaparece con las listas. Lo vigila
  `test_los_filtros_viven_con_las_listas`.
- **Los canales (Todas, LTS, Estable, Diarias, Experimentales, Favoritos) son
  pestañas, no pastillas.** Son excluyentes, así que van en un `QTabBar`
  (`#ChannelTabs`); no tiene páginas: al cambiar de pestaña se refiltra la lista
  de debajo. La lista de canales está en la constante `CHANNELS`.
- **Con QSS, un fondo en una subclase de `QWidget` no se pinta** salvo
  `setAttribute(Qt.WA_StyledBackground, True)`. `MigrateView` lo necesita para
  su gris; sin ello, los huecos que no pinta nadie (p. ej. la fila de pestañas a
  la derecha de las solapas) dejaban ver el fondo oscuro de detrás. Un `QWidget`
  *directo* (no subclase) sí pinta el fondo del QSS sin ese atributo.
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
- **macOS: el `.dmg` se monta y se instala** (`src/services/macos_dmg.py`). La
  API solo publica `.dmg`, que no es un comprimido, así que `hdiutil attach
  -mountpoint` lo monta, se copian los `.app` a la carpeta destino con `ditto`
  (preserva firma/metadatos del bundle), se les quita la cuarentena con `xattr`
  (por si el `.dmg` venía marcado) y se desmonta con `detach -force`. Es el
  patrón de Homebrew Cask/kitty/Zed y el de Blender Launcher V2
  (`source/threads/extractor.py`). Así la Mac puede **lanzarse desde la app**
  como cualquier otra: antes solo se revelaba el fichero y no había forma de
  abrirla. Es un módulo de `services/` (sin Qt) y usa `clean_env()`; si el
  montaje falla, se cae al plan B (revelar y avisar). Los tests mockean
  `hdiutil`/`ditto`/`xattr`, así que **no se prueba en el CI** (Ubuntu).

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

#### Activar la firma con SignPath (gratis para OSS)

El job `windows` ya trae los pasos (`Subir el .exe sin firmar` + `Firmar con
SignPath`), **inertes hasta que exista el secreto** `SIGNPATH_API_TOKEN`. La
acción firma a partir de un **artifact de GitHub** (por eso se sube el `.exe`
con `archive: false` antes), no de un fichero local; el Artifact Configuration de
SignPath tiene que describir un único fichero PE. Puesta en marcha:

0. Cumplir sus condiciones (<https://signpath.org/terms>): licencia OSI (GPL-3.0),
   sin malware ni componentes propietarios, MFA en GitHub y una sección
   **"Code signing policy"** en la home y en las páginas de descarga (está en el
   README y `promote.yml` la añade al cuerpo de la release final). Ojo: exigen
   "cierta reputación verificable" para programas ejecutables y **aprobación
   manual por release** para firmar.
1. Pedir el certificado en <https://signpath.org/apply> (vincular el repo de
   GitHub; para OSS es gratis y la clave vive en su HSM, no en el repo).
2. En SignPath.io: Trusted Build System **GitHub.com** → proyecto → signing
   policy → **artifact configuration** (un fichero PE).
3. Crear un **API token** de un usuario con permiso *submitter*.
4. En GitHub (Settings → Secrets and variables → Actions):
   - **Secret** `SIGNPATH_API_TOKEN`.
   - **Variables** `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`,
     `SIGNPATH_SIGNING_POLICY_SLUG`, `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG`.
5. El siguiente push a `main` firma el `.exe`. Si el token no está, no cambia
   nada (queda el autofirmado best-effort de plan B).

Cuando esté firmado por una CA, el popup de SmartScreen desaparece **según se
gana reputación** (es un certificado OV, no EV: no es instantáneo). El SHA-256
del asset cambia al firmar, así que `checksums.txt` se recalcula solo (lo hace
el job `release` desde el artifact).

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

- Lógica en `src/services/updater.py`; UI en `src/ui/widgets/updates.py`
  (`check_updates`, `_show_update_available`, `_show_source_update`) y controles
  en `ui/widgets/settings_view.py` (`_settings_updates_card`).
- Preferencia `auto_update` en `src/services/settings.py` (por defecto activada).
- **Reintento de conexión** (`services/downloader.py`): el handshake TLS de
  `release-assets.githubusercontent.com` es **intermitente** (el log de un
  usuario de Mac lo enseña: el mismo asset se bajó bien en v1.29.0 y v1.31.0 y
  falló con `_ssl.c:993: The handshake operation timed out` en v1.33.0). Se
  reintenta la conexión hasta 3 veces (solo la conexión; no se reinicia una
  descarga a medias) y el `HTTPError` no se reintenta. El fallo es antes de
  descargar, así que reintentar no cuesta datos.
- Aplicación por plataforma: Linux AppImage reemplaza `$APPIMAGE`; Windows
  extrae a staging y relanza el binario nuevo con `--apply-update`; macOS extrae
  el zip y lanza un **helper** (estilo Sparkle) que espera a que la app se
  cierre, mueve el bundle viejo, copia el nuevo con `ditto`, quita la cuarentena
  y relanza. Si no se puede (sin permiso en el directorio del bundle, bundle no
  localizable), macOS revela la descarga y avisa, como antes. No soportados solo
  avisan.
  - **El `.zip` se extrae con `ditto -x -k`, NUNCA con `zipfile`**
    (`macos_dmg.extract_zip`). `zipfile` de Python pierde los bits de ejecución
    y los symlinks del bundle (y puede perder la firma), así que el `.app`
    extraído **no arranca** — el síntoma que reportó Manu: "reemplaza pero no
    abre". Es el mismo motivo por el que Blender Launcher V2 usa `ditto` en su
    `extractor.py`.
  - El helper comprueba `[ -x "$EXE" ]` antes de tocar nada y, si el nuevo
    bundle no abre, restaura el viejo desde `BUNDLE.old` (que no borra hasta que
    el nuevo arranca): así una actualización rota nunca deja al usuario sin app.
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
