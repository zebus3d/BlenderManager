# 00 - Empieza aquí

## ¿Qué es Blender Manager?

Una aplicación de escritorio hecha con **Python** y **PySide6 (Qt Widgets)** que
sirve para buscar, descargar, organizar y lanzar versiones de
[Blender](https://www.blender.org/): LTS, estables y de desarrollo (diarias y
ramas experimentales). Funciona en Linux, Windows y macOS, y está pensada para
ser **portable**: una vez empaquetada no hace falta instalar nada.

## Cómo se ejecuta en modo desarrollo

```bash
# Crea el .venv con PySide6 la primera vez y arranca la app
./run.sh

# Equivalente a mano
.venv/bin/python src/main.py

# Con registro detallado
.venv/bin/python src/main.py --debug

# Sin ventana: lista las compilaciones disponibles por consola
.venv/bin/python src/main.py --smoke

# Arranca, guarda una captura y sale
.venv/bin/python src/main.py --screenshot /tmp/x.png
```

> Para ver un cambio visual basta con cerrar y volver a arrancar: la app tarda
> menos de un segundo en abrir. El aspecto vive en `src/ui/qss.py`, así que los
> retoques de color o de borde no tocan código de comportamiento.

## ¿Cuál es el archivo principal?

**`src/main.py`**. Es el punto de entrada. Sus tareas, en orden, son:

1. Poner `src/` en el `sys.path` para poder importar `services`, `ui`, `model`.
2. Leer los argumentos (`--smoke`, `--debug`, `--screenshot`, `--apply-update`).
3. Definir el modo `--smoke` (lista por consola, **sin** crear `QApplication`).
4. Cargar los ajustes y el idioma.
5. Crear `QApplication`, cargar la fuente de iconos y aplicar el QSS.
6. Crear `MainWindow`, dimensionarla y mostrarla.

## Mapa rápido del proyecto

```
src/
  main.py            # punto de entrada (empieza a leer por aquí)
  version.py         # número de versión (el CI lo reescribe en los releases)
  paths.py           # rutas: en código fuente vs. empaquetado
  i18n.py            # traducciones (inglés/español)

  model/
    build.py         # los "objetos" de datos: Build y InstalledBuild

  services/          # la lógica de verdad (no saben nada de Qt)
    api.py           # consulta el listado de Blender, lo filtra y lo cachea
    detector.py      # detecta el sistema operativo y la arquitectura
    settings.py      # ajustes persistentes y modo portable
    downloader.py    # descarga en segundo plano con progreso y SHA-256
    extractor.py     # extrae .tar.xz / .zip de forma segura
    installed.py     # escanea las versiones ya descargadas
    launcher.py      # lanza Blender como proceso aparte
    updater.py       # comprueba e instala actualizaciones

  ui/                # la interfaz (lo único que conoce Qt)
    qss.py           # el aspecto de TODA la app (una hoja de estilos)
    theme.py         # los colores, en constantes
    icons.py         # los glifos de la fuente de iconos
    fonts.py         # carga de la fuente de iconos
    widgets/
      buttons.py     # botones, pastillas, interruptores e iconos
      cards.py       # tarjetas de compilaciones (tienda e instaladas)
      dialogs.py     # diálogos con el aspecto de la app
      main_window.py # MainWindow: el controlador de la pantalla principal

  assets/            # logo de Blender, icono de la app y fuente de iconos

tests/               # pruebas automáticas (unittest)
packaging/           # cómo se empaquetan los binarios (PyInstaller, AppImage)
doc/                 # esto que estás leyendo
```

## Cómo se prueban los cambios

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -t . -s tests
```

Las de la interfaz corren con el plugin **offscreen** de Qt, así que no hace
falta pantalla ni servidor gráfico. Cubren el modelo, los servicios (API,
extracción, ajustes, actualizaciones) y la lógica de la ventana que se puede
comprobar sin verla: filtros, columnas de la rejilla, zoom y diálogos.

## Vocabulario que se repite

- **Build**: una compilación concreta publicada por Blender (por ejemplo
  `5.2.1` para Linux x86_64).
- **InstalledBuild**: una build que ya has descargado y extraído en tu carpeta.
- **Vista / View**: cada pantalla (Tienda, Instaladas, Ajustes).
- **Widget**: cualquier "cacharro" de la interfaz (un botón, una etiqueta...).
- **Layout**: la caja que coloca los widgets (fila, columna, rejilla).
- **QSS**: la hoja de estilos de Qt; aquí vive todo el aspecto.
- **`objectName`**: el nombre que le das a un widget para que el QSS lo pinte.
- **Señal**: el evento que emite un widget; se conecta a un método con
  `.connect()`.
