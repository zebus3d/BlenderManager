# 00 - Empieza aquí

## ¿Qué es Blender Manager?

Una aplicación de escritorio hecha con **Python** y **Kivy** que sirve para
buscar, descargar, organizar y lanzar versiones de [Blender](https://www.blender.org/):
LTS, estables y de desarrollo (diarias y ramas experimentales). Funciona en
Linux, Windows y macOS, y está pensada para ser **portable**: una vez empaquetada
no hace falta instalar nada.

## Cómo se ejecuta en modo desarrollo

```bash
# Solo necesita Kivy (todo lo demás es la librería estándar de Python)
python3 src/main.py

# Con registro detallado
python3 src/main.py --debug

# Sin ventana: lista las compilaciones disponibles por consola
python3 src/main.py --smoke

# Recarga .kv/tema al guardar (cómodo mientras diseñas la interfaz)
python3 src/main.py --watch
```

> El modo `--watch` es tu mejor amigo si vas a tocar los archivos `.kv`: guardas
> y la ventana se actualiza sola, sin cerrar y abrir la aplicación mil veces.

## ¿Cuál es el archivo principal?

**`src/main.py`**. Es el punto de entrada. Sus tareas, en orden, son:

1. Fijar `KIVY_NO_ARGS` **antes** de importar Kivy (si no, Kivy intenta
   interpretar los argumentos de la línea de comandos y se lía).
2. Poner `src/` en el `sys.path` para poder importar `services`, `ui`, `model`.
3. Definir el modo `--smoke` (lista por consola, sin ventana).
4. Registrar en la `Factory` de Kivy todas las clases propias de la interfaz
   (Kivy las necesita para construir los widgets que aparecen en los `.kv`).
5. Cargar los archivos de vista `src/views/*.kv`.
6. Crear la ventana y arrancar la aplicación (`MainApp`).

## Mapa rápido del proyecto

```
src/
  main.py            # punto de entrada (empieza a leer por aquí)
  version.py         # número de versión (el CI lo reescribe en los releases)
  paths.py           # rutas: en código fuente vs. empaquetado
  i18n.py            # traducciones (inglés/español)

  model/
    build.py         # los "objetos" de datos: Build y InstalledBuild

  services/          # la lógica de verdad (no sabe nada de la interfaz)
    api.py           # consulta el listado de Blender y lo cachea
    detector.py      # detecta el sistema operativo y la arquitectura
    settings.py      # ajustes persistentes y modo portable
    downloader.py    # descarga en segundo plano con progreso y SHA-256
    extractor.py     # extrae .tar.xz / .zip de forma segura
    installed.py     # escanea las versiones ya descargadas
    launcher.py      # lanza Blender como proceso aparte
    updater.py       # comprueba e instala actualizaciones

  ui/                # la interfaz
    theme.py         # colores y fuente de iconos
    icons.py         # los glifos de la fuente de iconos
    tooltip.py       # sistema de textos de ayuda al pasar el ratón
    widgets/         # los widgets de Python, repartidos por temas
      basic.py       # botones, pastillas y logo de la cabecera
      spinners.py    # desplegables (plataforma, arquitectura, idioma)
      dialogs.py     # diálogos, barra de progreso y tarjetas de ajustes
      cards.py       # tarjetas de compilaciones (tienda e instaladas)
      root.py        # RootWidget: el controlador de la pantalla principal

  views/             # el aspecto, en Kivy Language
    widgets.kv       # estilos de los widgets básicos
    dialogs.kv       # estilos de diálogos y ajustes
    cards.kv         # estilos de las tarjetas
    main.kv          # la pantalla principal completa

tests/               # pruebas automáticas (unittest)
packaging/           # cómo se empaquetan los binarios (PyInstaller, AppImage)
doc/                 # esto que estás leyendo
```

## Cómo se prueban los cambios

```bash
python3 -m unittest discover -t . -s tests -v
```

Son pruebas rápidas y **sin interfaz**: cubren el modelo de datos y los
servicios (API, extracción, ajustes, actualizaciones...). Si tocas esa lógica,
ejecútalas antes de dar algo por bueno.

## Vocabulario que se repite

- **Build**: una compilación concreta publicada por Blender (por ejemplo
  `5.2.1` para Linux x86_64).
- **InstalledBuild**: una build que ya has descargado y extraído en tu carpeta.
- **Vista / View**: cada pantalla (Tienda, Instaladas, Ajustes).
- **Widget**: cualquier "cacharro" de la interfaz (un botón, una etiqueta...).
- **KV**: el lenguaje declarativo de Kivy para describir el aspecto.
