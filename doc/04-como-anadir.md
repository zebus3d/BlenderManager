# 04 - Cómo se añadió el canal "Experimental" (ejemplo completo)

Este capítulo cuenta, paso a paso, cómo se añadió una función real: poder ver y
descargar las **ramas experimentales** de Blender. Sirve de plantilla para
cuando quieras añadir algo tú.

> Regla general: primero el **servicio** (la lógica), luego el **modelo** si hace
> falta, después el **controlador** y por último la **vista**. Y al final, una
> **prueba**.

## Contexto: dónde están las ramas experimentales

Blender publica compilaciones en dos listados separados:

- Diarias y estables: `https://builder.blender.org/download/daily/?format=json&v=2`
  (el que ya usaba la app).
- Ramas experimentales: `https://builder.blender.org/download/experimental/?format=json&v=2`
  (solo tiene contenido cuando el equipo abre ramas de funciones nuevas).

Los dos devuelven la misma estructura JSON, así que se pueden tratar igual.

## Paso 1 — El modelo (`model/build.py`)

Añadimos un campo para saber si una build es experimental. Con un valor por
defecto, el resto del código no se entera del cambio:

```python
@dataclass
class Build:
    ...
    experimental: bool = False
```

## Paso 2 — El servicio (`services/api.py`)

1. Un segundo endpoint:

```python
EXPERIMENTAL_URL = "https://builder.blender.org/download/experimental/?format=json&v=2"
```

2. `_to_build` acepta si es experimental y lo marca.
3. `fetch_builds` descarga **los dos** listados. El experimental va en su propio
   `try`: muchas veces está vacío o falla, y eso no debe romper el listado
   normal.
4. Se extrae la lógica de filtrado a una función pura y fácil de probar:

```python
def filter_builds(builds, channel, search=""):
    if channel == "experimental":
        selected = [b for b in builds if b.experimental]
    else:
        selected = [b for b in builds if not b.experimental]
        ...
```

**Decisión de diseño**: las experimentales **solo** se ven en su canal. En los
demás canales se excluyen, para no confundir a quien solo quiere una versión
normal de Blender.

## Paso 3 — El controlador (`ui/widgets/main_window.py`)

Como el filtrado ya está en `api.py`, aquí solo hay que llamarlo:

```python
def _filtered(self):
    builds = api.available_for(self.builds, self.platform, self.arch)
    return api.filter_builds(builds, self.channel, self.search)
```

Y en la tarjeta (`ui/widgets/cards.py`), si es experimental mostramos el
**nombre de la rama** como etiqueta en vez de "Alfa"/"Diaria":

```python
if build.experimental:
    self.channel_text = build.branch
```

> **Cuidado aquí**: no reimplementes el filtro dentro de la ventana. La primera
> versión del port lo repetía a mano y los canales dejaban de filtrar (pasó dos
> veces: en la tienda y en Instaladas). Si `services/` ya tiene una función para
> eso, se usa.

## Paso 4 — La vista (`ui/widgets/main_window.py` + `ui/qss.py`)

En Qt no hay `.kv`: la pastilla se crea en `_build_filters`, dentro del bucle de
canales:

```python
for key, label in (("all", "All"), ("lts", "LTS"), ("stable", "Stable"),
                   ("daily", "Daily"), ("experimental", "Experimental")):
    btn = Pill(tr(label), tr(f"Filter: {label.lower()}"))
    self.channel_group.addButton(btn)
    btn.clicked.connect(lambda _=False, k=key: self.set_channel(k))
```

El aspecto de `Pill` (y de su estado activo) ya está en `ui/qss.py`, así que una
pastilla nueva no necesita nada más.

Además, cuando el canal está vacío, mostramos un mensaje propio en vez del
genérico "No se encontraron compilaciones" (`main_window.py`, `_rebuild_store`).

## Paso 5 — Los textos (`i18n.py`)

Toda cadena visible se escribe en inglés como clave y se traduce aparte:

```python
"Experimental": "Experimentales",
"Filter: experimental branches": "Filtro: solo ramas experimentales ...",
"No experimental builds right now": "Ahora mismo no hay ramas experimentales ...",
```

## Paso 6 — La prueba (`tests/test_services.py`)

Al haber sacado el filtrado a una función pura, se puede probar sin abrir la
ventana:

```python
def test_experimental_only_in_its_own_channel(self):
    builds = self._builds()   # incluye una experimental "geometry-nodes"
    experimental = api.filter_builds(builds, "experimental")
    self.assertEqual([b.branch for b in experimental], ["geometry-nodes"])
    for channel in ("all", "lts", "stable", "daily"):
        selected = api.filter_builds(builds, channel)
        self.assertNotIn("geometry-nodes", [b.branch for b in selected])
```

Ejecuta las pruebas:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -t . -s tests
```

## Lo que aprendimos de este ejemplo

- **Añadir un campo con valor por defecto** no rompe lo que ya existe.
- **Separar la lógica de la vista** (la función `filter_builds`) hace que se
  pueda probar. Esa es la razón de que los servicios no sepan de Qt.
- **Un canal nuevo** toca 6 sitios: modelo, servicio, controlador, vista, i18n y
  pruebas. Teniéndolos localizados, es siempre igual.
- **Fíjate en las decisiones de diseño** (las experimentales no se mezclan con
  el resto). El código no basta; importa *cómo se comporta*.

## Un aviso sobre las ramas experimentales

Blender publica builds de ramas de funciones nuevas en el listado
`/download/experimental/`. Antes eran habituales ("Sculpt Dev", "Geometry
Nodes", "Eevee Dof Refactor"...), pero desde ~2021 casi no se publican, así que
ese canal suele estar vacío. Aun así se deja implementado: el día que Blender
abra una rama, aparecerá sola. Es un buen ejemplo de por qué conviene separar
el filtrado en una función pura y probarlo: aunque hoy no haya datos, el código
está listo y verificado.

---

# Anexo - La migración de addons entre versiones

La vista **Migrar** copia los addons de una versión de Blender instalada a
otra, avisando antes de los que no son compatibles. Es una función nueva, no
una variación de las que ya había, así que toca más sitios; se deja aquí como
segundo ejemplo.

## Cómo está repartido

| Capa | Archivo | Qué hace |
| --- | --- | --- |
| Servicio (puro) | `services/blender_config.py` | Localiza la carpeta de configuración de cada versión. **Sin Qt.** |
| Servicio (puro) | `services/blender_addons.py` | Lee `bl_info`/`blender_manifest.toml`, decide compatibilidad y copia (con respaldo y deshacer). **Sin Qt.** |
| Servicio (puro) | `services/blender_snapshots.py` | Los guardados de "valores de fábrica". **Sin Qt.** |
| Servicio (proceso) | `services/blender_runner.py` | Arranca el Blender destino en `--background` para habilitar los addons copiados. **Sin Qt.** |
| Servicio (proceso) | `services/blender_prefs.py` | Le pregunta a Blender sus preferencias clave a clave y se las escribe. **Sin Qt.** |
| Vista | `ui/widgets/migrate/` | Un módulo por pestaña (`addons_tab`, `prefs_tab`, `factory_tab`) sobre una cáscara común (`view.py`). |
| Controlador | `ui/widgets/main_window.py` | Botón de la barra lateral, `set_view`, y refresco con las instaladas. |
| Aspecto | `ui/qss.py` | `#AddonRow`, `#SettingsCard`, `#MigrateTabs` y `#Danger` (la casilla la pinta `CheckPill`, ver abajo). |
| Textos | `i18n.py` | Claves en inglés, dentro del bloque "Migración". |
| Pruebas | `tests/test_blender_config.py`, `tests/test_blender_runner.py`, `tests/test_ui.py` | Núcleo, proceso (mockeado) y vista. |

## Las tres decisiones que hay que entender

1. **No se interpreta `userpref.blend`.** Es un `.blend` binario y su estructura
   no es API estable entre versiones. Lo que sea "estado habilitado" o
   "preferencias" se le pregunta al propio Blender, no se escribe a mano.
   Por eso la migración de **preferencias** no está en esta función:
   la parte de addons se puede hacer sin arrancar Blender (leyendo ficheros) y
   solo el *activar* necesita ejecutarlo.

2. **La compatibilidad es conservadora.** Un addon se bloquea si pide una
   versión más nueva (`blender_version_min`), si su `blender_version_max` ya se
   pasó, o si no está publicado para este sistema. Se marca para revisar si sus
   wheels son de otro Python o si no declara mínimo (no se puede saber). Los
   bloqueados **no se pueden marcar** en la interfaz: nunca se copian sin
   querer. La lógica vive en `compat_report`, una función pura con tests.

3. **Se imita el estado activado del origen.** No se activa todo por migrar: se
   pregunta al Blender origen qué addons tenía **habilitados** (una sola
   arrancada, `blender_runner.enabled_addons`) y solo esos se activan en
   destino. Los que allí estaban apagados se copian apagados, que es lo que el
   usuario espera de una copia. Por eso no hay interruptor de "activar tras
   copiar".

4. **Copiar nunca borra.** Si el addon ya existe en destino, se aparta con el
   sufijo `.blendermanager-bak` y se anota en `.blendermanager-migration.json`,
   que es lo que permite **deshacer** la última migración. Es el mismo espíritu
   que `_write_problem` o los backups atómicos de `settings.py`.

   Ojo con el detalle de los respaldos: **hay uno solo por destino, y se
   reutiliza**, porque los usuarios migran más de una vez (a veces en la
   dirección contraria) y con un sufijo por fecha se acumulaba un `.bak` por
   intento sin que nadie los viera. Lo que interesa conservar es el estado
   *inmediatamente anterior* al último cambio, no un histórico. El marcador se
   borra al deshacer, así que un segundo "deshacer" (doble clic típico) no
   restaura nada de más.

## Cómo está maquetada la pantalla

Para que no sea "todo a cholón", la vista tiene una jerarquía fija:

1. **Título** simple (la barra lateral solo trae iconos, hay que saber dónde
   estás).
2. **Tarjeta de versiones** (origen → destino) con la ruta real de cada config
   bajo su desplegable. Es **común a las pestañas** y siempre mide lo mismo, así
   que cambiar de pestaña no hace saltar la interfaz. Va en una tarjeta gris
   porque sobre el fondo oscuro de la ventana un desplegable (que también es
   oscuro) no se distinguiría.
3. **Pestañas** (`#MigrateTabs`, estilizadas en `ui/qss.py` porque si no salen
   con el estilo claro del escritorio). Ojo con el fondo: las inactivas usan
   `SURFACE_ALT`, **no** `FILTER` (#1D1D1D, el mismo tono que la ventana), o no
   se leen.
   - **Add-ons**: tablero, y **debajo** el resumen de compatibilidad y la
     explicación. Van dentro de la pestaña, no en la tarjeta de versiones: al
     compartir tarjeta, ocultarlos al cambiar de pestaña movía toda la interfaz
     (el salto que se veía).
   - **Preferences**: primero el detalle fino (ajustes uno a uno, cada uno con
     el nombre y la descripción que les da Blender, que es lo recomendado),
     debajo el tema y el mapa de teclas como presets, y al final los ficheros
     completos (el atajo que lo pisa todo).
   - **Factory settings**: pestaña propia porque no migra nada, hace otra cosa
     (deja la versión destino limpia).

Se probó a anidar pestañas dentro de la de preferencias (detalle/ficheros vs
fábrica) y se descartó: pestañas dentro de pestañas se leen mal. Tres pestañas
planas dicen lo mismo sin confundir.

### El efecto de capas (gris unificado + tarjetas elevadas)

Toda la vista —cabecera (título + tarjeta de versiones) y canvas de las
pestañas— va del **mismo gris** (`SURFACE`, #303030), de modo que arriba y abajo
forman un solo bloque. Encima van las **tarjetas** un escalón por encima
(`SURFACE_HIGH`, #3D3D3D) con la misma sombra que las de la tienda
(`cards.card_shadow`, abajo a la derecha). Las **solapas** de las pestañas sí
son oscuras (`FILTER`, #1D1D1D), para que se lean como pestañas y no se fundan
con el gris; la activa se tiñe de acento.

Tres trampas que costaron un rato:

- **El pane del `QTabWidget` es la única parte que pinta fondo.** Las páginas
  son `QWidget` pelados, y con la regla global `QWidget { background-color }`
  tapaban el gris con el BG de la ventana. Además, `background: transparent` en
  un `QWidget` pelado no siempre deja pasar el fondo de debajo; se les da el
  gris **directo** (`QWidget#MigratePage { background-color: SURFACE }`), que es
  lo que de verdad se ve.
- **Ojo con la especificidad**: `QWidget#MigrateView QWidget` (id+tipo+tipo,
  0-2-1) gana a `QFrame#SettingsCard` (id+tipo, 0-1-1). Por eso las tarjetas se
  declaran con el mismo prefijo (`QWidget#MigrateView QFrame#SettingsCard`), o
  quedarían transparentes. Es exactamente el tipo de trampa que avisa
  `AGENTS.md` sobre el orden y la especificidad en QSS.
- **Un `QWidget` pelado (cabecera) no hereda el gris**: la regla global
  `QWidget { background-color: BG }` le pone el oscuro encima del gris de la
  vista. Hay que darle su propia regla (`QWidget#MigrateHeader`) para que la
  unificación funcione.
- **Una subclase de `QWidget` no pinta el fondo del QSS** salvo que active
  `setAttribute(Qt.WA_StyledBackground, True)`. `MigrateView` es subclase, así
  que sin eso su gris no se dibujaba: la zona de la fila de pestañas a la
  derecha de las solapas (que no pinta nadie) dejaba ver el oscuro de detrás.
  Se detectó pintando la regla de magenta como prueba: el QTabWidget tampoco la
  cogía, señal de que el hueco era del padre transparente.
- **La sombra se recorta si el padre mide exactamente lo mismo que la tarjeta.**
  `QGraphicsDropShadowEffect` no puede pintar fuera del padre, así que el
  tablero NO va dentro de un `QWidget` ajustado a su tamaño: su layout cuelga
  directamente de la página (que es grande) y así la sombra cae en el hueco.
  Medido: con el envoltorio, justo bajo el borde de la tarjeta el píxel saltaba
  de `#3D3D3D` a `#303030` sin sombra; sin él, aparece el degradado. De paso,
  las tarjetas ya no se estiran a lo alto: miden lo que miden sus filas.

### El tablero (por qué dos columnas)

El primer boceto era una lista con casillas. Se cambió a **origen a la
izquierda / destino a la derecha con una flecha de un solo sentido** porque
enseña de un vistazo *qué* se copia y *dónde* cae cada cosa. Detalle importante:
las dos columnas **comparten una única área de scroll**; así las filas quedan
alineadas sin sincronizar dos barras. Las filas miden `ROW_HEIGHT` (48 px) fijo
para que las dos mitades cuadren.

## El proceso: lo que costó

- `addon_utils.enable()` con `default_set=True` es lo que persiste el estado.
  Se probó de verdad contra Blender 5.2: el addon queda habilitado al reiniciar.
- **Los glifos de la fuente de iconos no valen como texto de botón** (salen como
  un recuadro): van dentro de un `QIcon` con `ui.fonts.glyph_icon`.
- **`deleteLater()` no es inmediato**: al recargar el tablero, las filas viejas
  seguían en el layout y salían duplicadas. Hay que hacer `setParent(None)` +
  `hide()` además de `deleteLater()`.
- El `BLENDER_USER_CONFIG` del entorno **no** reubica `scripts/`: los addons
  legacy cuelgan de `BLENDER_USER_SCRIPTS` o de la carpeta de la versión. Por
  eso `config_for` resuelve las tres rutas por separado.
- **La palomita del checkbox no se puede hacer por QSS.** Se intentó con un SVG
  en ``::indicator:checked { image: ... }`` (que aislado pinta perfecto) y en la
  app salía sin palomita: la regla global `QWidget { background-color }`
  **hereda** sobre el `::indicator` y Qt descarta el `image`. Da igual usar
  `background` o `background-color`, y tampoco ayuda un `border-radius` en la
  base. La salida es `CheckPill` (`ui/widgets/buttons.py`), que pinta el cuadro
  y el trazo con `QPainter`, igual que `SwitchPill`.

## Lo que aprendimos

- Una función nueva "grande" se apoya en lo que ya hay: `clean_env()` para
  lanzar Blender, `ElidedLabel` para los nombres, `SettingsCard`/`CardButton`
  para el aspecto, el patrón `threading.Thread` + señal de `Downloader` para el
  trabajo en segundo plano.
- **Probar el runner con Blender de verdad** merece la pena una vez: confirmó
  que 5.1 usa Python 3.13 (la tabla `_PYTHON_BY_SERIES` es heurística; la
  verdad la da `blender_runner.python_version` cuando la build está instalada).
- Lo que no se puede hacer sin riesgo, no se hace: el `startup.blend` y los
  keymaps no se tocan a mano; cuando se migran, delegan en Blender.

## Preferencias selectivas (comparar con los valores de fábrica)

`services/blender_prefs.py` resuelve la parte fina: en vez de copiar el
`userpref.blend` entero, le pregunta al Blender **origen** por sus preferencias
y por las de fábrica:

- `read_preferences(exe)` vuelca el árbol de preferencias recorriendo las
  propiedades RNA (`view.ui_scale`, `inputs.use_zoom_to_mouse`...). Se salta
  colecciones y lo de solo lectura; los punteros (`view`, `edit`) se recorren
  para bajar, no se copian.
- `read_preferences(exe, factory=True)` hace lo mismo con `--factory-startup`.
- `diff(user, factory)` deja **solo lo que el usuario cambió** (medido: 11 de
  280 claves en esta máquina) y `environment_preferences` aparta lo que depende
  del equipo (`system.gpu_backend`, rutas de temp...), que se ofrece sin marcar.
- `apply_preferences(exe, claves)` escribe **clave a clave** en la versión
  destino y devuelve las que fallaron. Ese informe es el "feedback de
  incompatibles": una preferencia que Blender renombró o hizo de solo lectura
  sale listada en vez de romper la migración entera.

Detalles que costó aprender:

- La ruta RNA **no es API estable**: por eso se aplica clave a clave y no se
  copia el fichero con las claves interpoladas.
- Los `set` de Blender (p. ej. `edit.key_insert_channels`) se imprimen como
  texto pero no se pueden volver a escribir por esta vía: se filtran con
  `is_settable`.
- Un test de verdad (Blender 5.2) enseñó que 10 de 11 claves aplican y una
  (`view.show_statusbar_vram`) es de solo lectura en esa versión: el informe la
  enseña en vez de fallar.
- **La lectura es automática** al elegir la versión de origen: `read_source`
  guarda para qué versión se hizo (`_source_read_for`) y no repite el arranque
  de Blender mientras no cambie el origen. El botón "Read again" solo fuerza un
  reintento.
- El **estado activado de los addons** y las **preferencias** se leen en una
  sola arrancada de Blender (`enabled_addons` + `read_preferences`), no dos:
  cambiar de versión no puede costar dos arranques.

## Reset a valores de fábrica (recuperable)

`snapshot_config` / `restore_snapshot` / `snapshots_for` / `delete_snapshot`
hacen lo que mucha gente hace a mano: **mover la carpeta `config`** para probar
una versión "de fábrica". La diferencia es que la apartan a una instantánea con
fecha (`.blendermanager-snapshots/config-<fecha>-<etiqueta>`) en vez de
renombrarla, así que:

- se puede **recuperar** los ajustes anteriores (y al recuperar, la config
  limpia se aparta también: el propio "restaurar" es reversible),
- se pueden tener **varias instantáneas** (resetear y reintentar es normal),
- y borrarlas para dejarlo limpio **para siempre**, que es la otra opción.

**Hallazgo importante:** `bpy.ops.wm.save_userpref()` **no crea** la carpeta
`config` si no existe (comprobado en Blender 5.2 en `--background`: falla en
silencio). Tras un reset esa carpeta puede faltar, así que `blender_runner`
la asegura antes de lanzar Blender; sin eso, activar addons después de un reset
no se guardaba.
