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

## Paso 3 — El controlador (`ui/widgets/root.py`)

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

## Paso 4 — La vista (`views/main.kv`)

Añadimos una pastilla más a la barra de filtros:

```kv
Pill:
    text: tr("Experimental")
    tooltip_text: tr("Filter: experimental branches")
    state: "down" if root.channel == "experimental" else "normal"
    disabled: not root.show_filters
    group: "channel"
    on_release: root.set_channel("experimental")
```

Además, cuando el canal está vacío, mostramos un mensaje propio en vez del
genérico "No se encontraron compilaciones" (`root.py`, `_rebuild_store`).

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
    for channel in ("all", "lts", "stable", "lts_stable", "daily"):
        selected = api.filter_builds(builds, channel)
        self.assertNotIn("geometry-nodes", [b.branch for b in selected])
```

Ejecuta las pruebas:

```bash
python3 -m unittest discover -t . -s tests -v
```

## Lo que aprendimos de este ejemplo

- **Añadir un campo con valor por defecto** no rompe lo que ya existe.
- **Separar la lógica de la vista** (la función `filter_builds`) hace que se
  pueda probar. Esa es la razón de que los servicios no sepan de Kivy.
- **Un canal nuevo** toca 6 sitios: modelo, servicio, controlador, vista, i18n y
  pruebas. Teniéndolos localizados, es siempre igual.
- **Fíjate en las decisiones de diseño** (las experimentales no se mezclan con
  el resto). El código no basta; importa *cómo se comporta*.

## Y después se añadió el canal "Patch"

Las ramas experimentales de Blender casi nunca están disponibles (las que
recuerdas de "Sculpt Dev" o "Geometry Nodes" son de 2021). Para que ese hueco no
quedara siempre vacío se añadió un canal **Patch** con las builds de pull
request, siguiendo **exactamente los mismos 6 pasos**:

- `model/build.py`: campo `patch: str = ""` (el id de la PR; vacío si no lo es).
- `services/api.py`: `PATCH_URL`, se descarga junto a las demás, y
  `filter_builds` gana la rama `elif channel == "patch"`.
- `ui/widgets/cards.py`: la etiqueta de canal muestra el id de la PR.
- `views/main.kv`: la pastilla `Patch`.
- `i18n.py` y `tests/test_services.py`: textos y pruebas.

Ese es justo el valor de tener el filtrado en una función pura y los canales
bien separados: cada canal nuevo cuesta lo mismo y se prueba igual.
