# 02 - Kivy: los conceptos que usa el proyecto

Esta es la parte que más cuesta al empezar. Aquí tienes cada concepto de Kivy
que aparece en el proyecto, con **dónde verlo** en el código. No hace falta
memorizarlo: vuelve aquí cuando te pierdas.

## 1. Python y `.kv`: quién hace qué

En Kivy, una misma cosa se reparte entre dos sitios:

- El archivo **`.kv`** describe **cómo se ve** (tamaños, colores, qué hijos
  tiene un widget).
- La clase de **Python** describe **qué hace** (métodos, propiedades).

En este proyecto:
- Clase Python: `Pill` en `src/ui/widgets/basic.py`.
- Su aspecto: la regla `<Pill>:` en `src/views/widgets.kv`.

Kivy une las dos por el **nombre de la clase**. Por eso en el `.kv` las reglas
se escriben entre `< >`: `<Pill>:` significa "esto es el aspecto de la clase
`Pill`".

## 2. La `Factory`: registrar las clases propias

Cuando el `.kv` dice `Pill:` (sin `<>`), Kivy tiene que saber **cómo construir**
un `Pill`. Para eso se registran las clases antes de cargar los `.kv`
(`src/main.py`):

```python
for widget in widgets:
    Factory.register(widget.__name__, cls=widget)
```

Regla práctica: **si creas una clase de widget nueva y la usas en un `.kv`,
añádela a la lista `widgets` de `main.py`**.

## 3. Propiedades y *binding*: la magia de Kivy

Las propiedades de Kivy (`StringProperty`, `NumericProperty`, `BooleanProperty`...)
avisan cuando cambian. Si en el `.kv` escribes:

```kv
Label:
    text: root.status_text
```

el texto se **actualiza solo** cuando cambia `root.status_text`. No hay que
llamar a nada. A eso se le llama *binding*.

Dónde verlo:
- Propiedades: `RootWidget` en `src/ui/widgets/root.py`.
- Uso en la vista: `src/views/main.kv` (por ejemplo `text: root.status_text`).

También puedes reaccionar desde Python con `self.bind(...)`:

```python
self.bind(channel=lambda *_: self._on_filter_changed())
```

## 4. `AliasProperty`: propiedades calculadas

A veces una propiedad no se guarda, sino que se **calcula** a partir de otras.
Ese es `AliasProperty`. Ejemplo (`root.py`):

```python
def _get_show_filters(self):
    return self.view != "settings"

show_filters = AliasProperty(_get_show_filters, bind=("view",))
```

`show_filters` vale `True` o `False` según `view`. El `bind=("view",)` es
importante: le dice a Kivy de qué depende para recalcularla.

## 5. `canvas.before`, `canvas` y `canvas.after`: el orden de dibujo

Kivy dibuja en este orden:

1. `canvas.before` — **detrás** de los hijos.
2. los **hijos**.
3. `canvas` — **encima** de los hijos.
4. `canvas.after` — lo último, por encima de todo.

**Truco que se repite mucho**: el fondo de un widget (botones, tarjetas) va
siempre en `canvas.before`. Si lo pones en `canvas`, taparía a sus hijos.
Míralo en `<CardButton>:` de `src/views/widgets.kv`.

## 6. El patrón de tres capas de los botones

Todos los botones del tema se dibujan con tres rectángulos redondeados
superpuestos (`<CardButton>` en `widgets.kv`):

1. Color de relleno (cambia según `hovered` / `state`).
2. Un degradado blanco con transparencia (`theme.GRADIENT_TOP`) que da volumen.
3. Un borde fino negro con `Line` y `rounded_rectangle`.

Copiar ese patrón mantiene la interfaz coherente.

## 7. `HoverBehavior`: resaltar y mostrar tooltips

`src/ui/tooltip.py` define `HoverBehavior`, un *mixin* que añades a tus widgets:

```python
class MiBoton(HoverBehavior, Button):
    pass
```

Te da dos cosas gratis:
- La propiedad `hovered`, que usas en el `.kv` para resaltar el widget.
- El `tooltip_text`, que muestra un texto de ayuda al pasar el ratón.

Se enlaza y desenlaza del ratón en `on_parent` para no dejar referencias
colgando cuando los widgets se reconstruyen.

## 8. Hilos y `Clock`: no congelar la ventana

Lo que tarda (red, disco) va en un hilo aparte y, al terminar, vuelve al hilo
de Kivy con `Clock.schedule_once`:

```python
def worker():
    builds = api.get_builds(force=True)
    Clock.schedule_once(lambda dt: self._on_builds_loaded(builds), 0)

threading.Thread(target=worker, daemon=True).start()
```

Está por todo `root.py` (descargas, comprobación de actualizaciones, abrir el
navegador...). **Nunca toques un widget desde otro hilo.**

## 9. `ScreenManager`: cambiar de pantalla

Las tres vistas (Tienda, Instaladas, Ajustes) están en un `ScreenManager` del
`.kv` (`main.kv`). Desde Python se cambia con `manager.current = "settings"`, y
la transición se elige con `SlideTransition` o `NoTransition` (`set_view` en
`root.py`).

## 10. El patrón "colapsar" en vez de ocultar

Para esconder algo sin destruirlo, se juntan **tres** cosas:

```kv
width: dp(130) if root.show_zoom else 0
opacity: 1 if root.show_zoom else 0
disabled: not root.show_zoom
```

- `width: 0` lo encoge (deja de ocupar sitio).
- `opacity: 0` lo hace invisible.
- `disabled: True` evita que capture clics.

Las tres son necesarias. Míralo en `header_tools` y `zoom_box` de `main.kv`.

## 11. `modal` y popups propios

No usamos los `Popup` por defecto de Kivy (se ven claros y desentonan).
Heredamos de ellos (`AppPopup`, `AppModalView` en `dialogs.py`) y les cambiamos
el color de fondo desde `dialogs.kv`.

## 12. Un par de trampas que ya están resueltas

- **El primer clic se lo comía el gestor de ventanas.** Se soluciona llamando a
  `Window.raise_window()` y `Window.focus = True` en `on_start` (`main.py`).
- **`KIVY_NO_ARGS`** debe fijarse **antes** de importar Kivy, o Kivy intenta
  leer los argumentos del programa y falla.
- **`text_size: self.size`** es necesario en una `Label` para que el texto se
  parta o se recorte con `shorten: True`. Sin eso, se sale.
- **Las reglas del `.kv` se ejecutan durante el `__init__`**, antes de tu código.
  Por eso las propiedades deben tener valores por defecto válidos.
