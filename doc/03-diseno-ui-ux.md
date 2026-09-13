# 03 - Diseño de la interfaz

La app imita el **tema oscuro por defecto de Blender**. Si respetas estas
reglas, cualquier cosa que añadas parecerá parte del programa.

## La idea de profundidad

Cuanto más oscuro, más "hundido"; cuanto más claro, más "elevado". Como en
Blender:

```
BG / FIELD   (más oscuro)  ->  fondo de la ventana y campos de texto
SURFACE/CHROME             ->  barras y tarjetas
BUTTON / SURFACE_ALT (más claro)  ->  botones y resaltados
```

Los colores están en `src/ui/theme.py` y se usan desde los `.kv` así:
`theme.ACCENT`. **No se ponen colores a mano en el `.kv`**: siempre desde
`theme`.

## Paleta (lo esencial)

| Constante | Color | Para qué |
|---|---|---|
| `BG` | `#1D1D1D` | Fondo de la ventana (lo más oscuro) |
| `FIELD` | `#171717` | Campos de texto (hundidos) |
| `FILTER` | `#1D1D1D` | Botón de filtro en reposo |
| `SURFACE` | `#303030` | Paneles, tarjetas, barra lateral |
| `CHROME` | `#303030` | Cabecera y pie |
| `SURFACE_ALT` | `#3D3D3D` | Resaltado al pasar el ratón |
| `BUTTON` | `#585858` | Botones neutros (gris de pestaña de Blender) |
| `TEXT` | `#E6E6E6` | Texto principal |
| `MUTED` | `#989898` | Texto secundario/apagado |
| `ACCENT` | `#5085B1` | Azul de selección/acción principal |
| `ACCENT_DARK` | `#3F6F96` | Azul pulsado/hover |
| `WARNING` | `#FFAF23` | Naranja (etiqueta LTS) |
| `DANGER` | `#B84A4A` | Rojo (desinstalar) |
| `SUCCESS_TEXT` | `#6FCF7A` | Verde claro para texto "Instalada" |
| `INFO_TEXT` | `#7AA7E0` | Azul claro para etiquetas de canal |

> Importante: las variantes `_TEXT` existen porque los colores "de fondo"
> (verde `SUCCESS`, azul `INFO`) son demasiado oscuros para leerlos como texto
> sobre una tarjeta.

## Cómo se comunica el estado

| Estado | Cómo se pinta |
|---|---|
| Normal | Color bajo (FILTER, BUTTON, CARD_DIM) |
| Hover | Un poco más claro (SURFACE_ALT, ACCENT_DARK) o +22 % de brillo |
| Activo/seleccionado | ACCENT a tope + texto blanco (`TEXT_SEL`) |
| Deshabilitado | Mismo color pero con `opacity` baja (0.32 / 0.6) |
| Destructivo | Rojo DANGER |

El resaltado al pasar el ratón lo da `self.hovered`, que viene de
`HoverBehavior`. Puedes verlo en cualquier regla de `views/*.kv`:
`rgba: theme.SURFACE_ALT if self.hovered else self.row_color`.

## Espaciado y tamaños

- **Márgenes exteriores**: `dp(14)` a `dp(16)`.
- **Márgenes interiores de tarjeta**: `dp(12)` a `dp(14)`.
- **Separación entre hermanos**: `dp(10)` en rejillas, `dp(6)` en grupos juntos.
- **Alto de la cabecera**: `dp(72)`. **Pie**: `dp(40)`. **Barra de filtros**: `dp(44)`.
- Todo se mide en `dp()` (píxeles independientes de densidad) y `sp()` (tamaño
  de fuente). **Nunca** pongas píxeles crudos.

## La pantalla, en tres zonas

```
+--------[ Cabecera: dp(72) ]--------+   logo, título, buscador, refrescar
+--------[ Filtros:  dp(44) ]--------+   canales, vista, plataforma, arquitectura
| barra |                             |
| late- |        contenido            |   tienda / instaladas / ajustes
| ral   |                             |
+--------[ Pie:      dp(40) ]--------+   estado, progreso, zoom
```

La cabecera y el pie tienen alto fijo (`size_hint_y: None` + `height`). El
cuerpo se queda con el espacio que sobra. La barra lateral mide `dp(74)`.

## Reglas de lectura

- Título de tarjeta: `sp(15)`–`sp(16)`, negrita, `TEXT`.
- Texto normal: `sp(13)`, `TEXT`.
- Texto secundario: `sp(11)`–`sp(12)`, `MUTED`.
- Para que un texto se parta o se recorte: `text_size: self.size` **y**
  `shorten: True` / `halign` / `valign`.

## Accesibilidad (lo que ya está cuidado)

- Zonas pulsables de al menos ~44 px (los botones redondos son `dp(50)`).
- El color **no** es el único indicador: las instaladas llevan también el
  rótulo "Instalada" y las no instaladas se atenúan con `opacity: 0.32`.
- Contraste bueno: texto claro sobre superficies oscuras.

## Si vas a cambiar algo visual

1. Toca primero `src/ui/theme.py` si es un color repetido.
2. El aspecto de cada widget está en `src/views/*.kv`. Busca la regla por el
   nombre de la clase: `<CardButton>:`, `<Pill>`...
3. Arranca con `python3 src/main.py --watch` y guarda: verás el cambio en vivo.
