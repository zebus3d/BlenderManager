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
