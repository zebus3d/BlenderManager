"""Traducciones de la interfaz (español e inglés).

El idioma se detecta automáticamente de las variables de entorno del sistema
(LANG, LC_ALL...) salvo que el usuario lo fije en los ajustes.

Usamos las cadenas en inglés como claves: si falta una traducción, se muestra
el texto original en inglés en lugar de romperse.
"""

import locale
import os

SUPPORTED = ("en", "es")
DEFAULT = "en"

_TRANSLATIONS = {
    "es": {
        "Blender Manager": "Gestor de Blender",
        "Blender Downloads Manager": "Gestor de descargas de Blender",
        "Store": "Tienda",
        "Installed": "Instaladas",
        "Settings": "Ajustes",
        "Refresh": "Actualizar",
        "Search...": "Buscar...",
        "All": "Todas",
        "Stable": "Estable",
        "Daily": "Diarias",
        "LTS": "LTS",
        "Alpha": "Alfa",
        "Beta": "Beta",
        "Download": "Descargar",
        "Downloading...": "Descargando...",
        "Choosing the fastest source...":
            "Buscando la fuente más rápida...",
        "Extracting...": "Extrayendo...",
        "Launch": "Lanzar",
        "Launching": "Lanzando",
        "Delete": "Borrar",
        "Uninstall": "Desinstalar",
        "Unexpected error": "Error inesperado",
        "Cancel": "Cancelar",
        "Close": "Cerrar",
        "Save": "Guardar",
        "Browse...": "Examinar...",
        "No builds found": "No se encontraron compilaciones",
        "Loading...": "Cargando...",
        "Ready": "Listo",
        "Destination folder": "Carpeta de destino",
        "Install LTS versions in a separate folder":
            "Instalar las versiones LTS en otra carpeta",
        "Keep LTS versions on another drive or folder (for example an SSD)":
            "Guarda las versiones LTS (soporte a largo plazo) en otro disco o carpeta "
            "(por ejemplo un SSD)",
        "Same as destination folder": "Igual que la carpeta de destino",
        "Choose the folder for LTS builds":
            "Elige la carpeta donde se guardarán las versiones LTS",
        "Could not write to the destination folder:":
            "No se pudo escribir en la carpeta de destino:",
        "Choose another folder": "Elegir otra carpeta",
        "Windows protects folders like Program Files. Pick a folder you can "
        "write to, such as Documents or another drive.":
            "Windows protege carpetas como Archivos de programa y solo deja "
            "escribir en ellas a un administrador. Elige una en la que puedas "
            "escribir, por ejemplo Documentos u otro disco.",
        "Grant permission (admin)": "Dar permiso (administrador)",
        "The permission request was cancelled.":
            "Se canceló la petición de permiso.",
        "The folder still could not be made writable.":
            "No se pudo dar permiso de escritura a esa carpeta.",
        "General": "General",
        "Downloads": "Descargas",
        "Language": "Idioma",
        "Automatic": "Automático",
        "English": "Inglés",
        "Spanish": "Español",
        "Delete archive after extraction": "Borrar el archivo tras extraer",
        "Yes": "Sí",
        "No": "No",
        "Launch options": "Opciones de lanzamiento",
        "Launch arguments": "Argumentos de lanzamiento",
        "Installed versions": "Versiones instaladas",
        "Installed build": "Instalada",
        "No installed versions found": "No se encontraron versiones instaladas",
        "Try clearing the search or another channel filter.":
            "Prueba a borrar la búsqueda o a cambiar el filtro de canal.",
        "Download one from the store to see it here.":
            "Descarga alguna desde la tienda y aparecerá aquí.",
        "Download complete": "Descarga completada",
        "Download failed": "Fallo en la descarga",
        "Extraction complete": "Extracción completada",
        "Extraction failed": "Fallo en la extracción",
        "Cancelled": "Cancelado",
        "Checksum error": "Error en la suma de verificación",
        "Downloading {name}": "Descargando {name}",
        "Extracting {name}": "Extrayendo {name}",
        "Launching {name}": "Lanzando {name}",
        "Deleted {name}": "Borrado {name}",
        "Delete {name}?": "¿Borrar {name}?",
        "This will remove the folder permanently.": "Esto eliminará la carpeta permanentemente.",
        "Error": "Error",
        "Info": "Información",
        "Select destination folder": "Selecciona la carpeta de destino",
        "Platform": "Plataforma",
        "Architecture": "Arquitectura",
        "Unknown": "Desconocido",
        "Added by BlenderManager": "Añadido por Gestor de Blender",
        "No executable found": "No se encontró el ejecutable",
        "Show the store": "Muestra la tienda de compilaciones",
        "Show installed versions": "Muestra las versiones instaladas",
        "Open settings": "Abre los ajustes",
        "Refresh the list of builds": "Actualiza la lista de compilaciones",
        "Search builds by version or branch": "Busca compilaciones por versión o rama",
        "Filter: all channels": "Filtro: todos los canales",
        "Filter: LTS only": "Filtro: solo versiones LTS",
        "Filter: stable only": "Filtro: solo estables (sin LTS)",
        "Filter: LTS and stable": "Filtro: versiones LTS y estables juntas",
        "Filter: daily and alpha": "Filtro: versiones diarias y alfa",
        "Experimental": "Experimentales",
        "Filter: experimental branches": "Filtro: solo ramas experimentales (funciones en desarrollo)",
        "No experimental builds right now": "Ahora mismo no hay ramas experimentales disponibles",
        "Favorites": "Favoritos",
        "Filter: favorites": "Filtro: solo las versiones marcadas como favoritas",
        "Mark as favorite": "Marcar como favorita",
        "Remove from favorites": "Quitar de favoritos",
        "No favorites yet": "Todavía no has marcado ninguna favorita",
        "Tap the star on a card to keep it here.":
            "Pulsa la estrella de una tarjeta para tenerla aquí.",
        "Feature branches with new features still in development.":
            "Ramas con funciones nuevas todavía en desarrollo. Pueden ser inestables.",
        "LTS + Stable": "LTS + Estable",
        "Grid view": "Vista en cuadrícula de iconos",
        "List view": "Vista en filas",
        "Target operating system": "Sistema operativo de destino",
        "Target architecture": "Arquitectura de destino",
        "Download and install this version": "Descarga e instala esta versión",
        "Launch this installed version": "Lanza esta versión instalada",
        "Read the release notes for this version": "Lee las notas de esta versión de Blender",
        "Opening the release notes...": "Abriendo las notas de versión...",
        "Could not open the browser": "No se pudo abrir el navegador",
        "Remove this installed version": "Elimina esta versión instalada",
        "Double-click to rename": "Doble clic para renombrar",
        "Rename folder": "Renombrar carpeta",
        "Renamed to {name}": "Renombrado a {name}",
        "The name cannot be empty.": "El nombre no puede estar vacío.",
        'The name cannot contain \\ / : * ? " < > |.':
            'El nombre no puede contener \\ / : * ? " < > |.',
        "That is already the name.": "Ese ya es el nombre.",
        "There is already a folder with that name.":
            "Ya existe una carpeta con ese nombre.",
        "The name is not valid.": "El nombre no es válido.",
        "Choose destination folder": "Elige la carpeta donde se guardarán las versiones",
        "Parent folder": "Carpeta superior",
        "Home folder": "Carpeta personal",
        "Use this folder": "Usar esta carpeta",
        "Save settings": "Guarda los ajustes",
        "Zoom the icon size (Ctrl +/- / Ctrl+0)":
            "Ajusta el tamaño de los iconos (Ctrl +/- / Ctrl+0)",
        "Reset zoom": "Zoom al restablecer",
        "Zoom the grid returns to (Ctrl+0 or Ctrl+click on the slider)":
            "Zoom al que vuelve la rejilla (Ctrl+0 o Ctrl+clic en el deslizador)",
        # Bandeja del sistema (system tray).
        "Close to the system tray": "Cerrar a la bandeja del sistema",
        "Keep BlenderManager running in the system tray when you close the "
        "window.\nClick the tray icon to open it again.":
            "Mantén BlenderManager en la bandeja del sistema al cerrar la "
            "ventana.\nHaz clic en el icono de la bandeja para volver a abrirlo.",
        "Minimize to the system tray": "Minimizar a la bandeja del sistema",
        "Hide the window in the system tray when you minimize it.\n"
        "Click the tray icon to bring it back.":
            "Oculta la ventana en la bandeja del sistema al minimizarla.\n"
            "Haz clic en el icono de la bandeja para recuperarla.",
        "The system tray is not available on this desktop.":
            "La bandeja del sistema no está disponible en este escritorio.",
        "On Wayland this needs X11 compatibility mode (XWayland); "
        "restart the app to apply it.":
            "En Wayland esto necesita el modo de compatibilidad X11 "
            "(XWayland); reinicia la aplicación para aplicarlo.",
        "Minimizing to the tray is not available on this desktop.":
            "Minimizar a la bandeja no está disponible en este escritorio.",
        "Restart BlenderManager to apply the change.":
            "Reinicia BlenderManager para aplicar el cambio.",
        # Autoarranque y arranque minimizado.
        "Start automatically at login": "Iniciar automáticamente al iniciar sesión",
        "Open BlenderManager automatically when you sign in to your computer.":
            "Abre BlenderManager automáticamente al iniciar sesión en el equipo.",
        "Start minimized in the system tray":
            "Iniciar minimizado en la bandeja del sistema",
        "Start hidden in the system tray.\n"
        "Recommended if it opens automatically at login.":
            "Empieza oculto en la bandeja del sistema.\n"
            "Recomendado si se abre automáticamente al iniciar sesión.",
        "Automatic startup is not available on this system.":
            "El arranque automático no está disponible en este sistema.",
        "Automatic startup": "Arranque automático",
        "Could not change the automatic startup.":
            "No se pudo cambiar el arranque automático.",
        "Show": "Mostrar",
        "Bring the BlenderManager window back.":
            "Vuelve a mostrar la ventana de BlenderManager.",
        "Quit": "Salir",
        "Close BlenderManager completely.": "Cierra BlenderManager por completo.",
        "Still running in the system tray":
            "Sigue ejecutándose en la bandeja del sistema",
        "BlenderManager keeps running in the tray. Click its icon to "
        "bring the window back.":
            "BlenderManager sigue ejecutándose en la bandeja. Haz clic en su "
            "icono para recuperar la ventana.",
        "Updates": "Actualizaciones",
        "Check for updates automatically": "Buscar actualizaciones automáticamente",
        "Check for updates periodically": "Buscar actualizaciones periódicamente",
        "Look for new versions of BlenderManager every so often":
            "Busca versiones nuevas de BlenderManager cada cierto tiempo",
        "Check for updates every": "Buscar actualizaciones cada",
        "Never": "Nunca",
        "Every minute": "Cada minuto",
        "{count} minutes": "{count} minutos",
        "Every hour": "Cada hora",
        "Every {count} hours": "Cada {count} horas",
        "Skip this version": "Saltar esta versión",
        "You will not be reminded about {version}.":
            "No se te volverá a avisar de {version}.",
        "You will not be reminded about Blender {series} updates.":
            "No se te volverá a avisar de actualizaciones de Blender {series}.",
        "Reactivate": "Reactivar",
        "Blender series you silenced with Never":
            "Series de Blender que silenciaste con «Nunca»",
        "Silenced: {series}": "Silenciadas: {series}",
        "Check for updates now": "Buscar actualizaciones ahora",
        "Check now": "Buscar ahora",
        "Version {version}": "Versión {version}",
        "Checking for updates...": "Buscando actualizaciones...",
        "Update check failed": "No se pudo comprobar la actualización",
        "You are up to date": "Estás en la última versión",
        "No update for this platform": "No hay actualización para esta plataforma",
        "A new version is available: {version}": "Hay una versión nueva disponible: {version}",
        "Download and install it now?": "¿Descargarla e instalarla ahora?",
        "Update available": "Actualización disponible",
        "You already have the latest version.": "Ya tienes la última versión.",
        "You already have the latest version ({version}).":
            "Ya tienes la última versión ({version}).",
        "Accept": "Aceptar",
        "Update": "Actualizar",
        "Later": "Más tarde",
        "Installing the update...": "Instalando la actualización...",
        "Restarting to install the update...": "Reiniciando para instalar la actualización...",
        "Update downloaded. Install it manually.": "Actualización descargada. Instálala manualmente.",
        "A download is already in progress": "Ya hay una descarga en curso",
        "Downloaded to {folder}": "Descargado en {folder}",
        "Open it to install Blender manually.": "Ábrelo para instalar Blender a mano.",
        "The language will change when you restart": "El idioma cambiará al reiniciar",
        "It will be installed and the app will restart automatically.":
            "Se instalará y la aplicación se reiniciará sola.",
        "It will be downloaded. You will have to install it manually.":
            "Se descargará. Tendrás que instalarla a mano.",
        "Running from source: the app will run git pull and restart.":
            "Estás ejecutando desde el código fuente: se hará git pull y se reiniciará.",
        "You have local changes. Commit or stash them and try again.":
            "Tienes cambios locales sin guardar. Confírmalos o guárdalos aparte e inténtalo de nuevo.",
        "Could not update. Run git pull manually.":
            "No se pudo actualizar. Ejecuta git pull a mano.",
        "Updating...": "Actualizando...",
        "Restarting...": "Reiniciando...",
        "Update downloaded. Restart the app.":
            "Actualización descargada. Reinicia la aplicación.",
        "Open it to install the new version.":
            "Ábrelo para instalar la versión nueva.",
        "Could not download the update automatically:":
            "No se pudo descargar la actualización automáticamente:",
        "You can download it from the releases page and install it manually.":
            "Puedes descargarla desde la página de releases e instalarla a mano.",
        "Open the releases page": "Abrir la página de releases",
        "Update to {version}": "Actualizar a {version}",
        "You have Blender {current} installed. Blender {new} is available.":
            "Tienes Blender {current} instalado. Hay una versión nueva: Blender {new}.",
        "Replace the installed version or download the new one as a copy?":
            "¿Reemplazas la versión instalada o descargas la nueva como copia?",
        "Replace": "Reemplazar",
        "Download as copy": "Descargar como copia",
        "{count} Blender updates available":
            "{count} actualizaciones de Blender disponibles",
        "Replaced {name}": "Reemplazado {name}",
        "This version is already installed": "Esta versión ya está instalada",

        # --- Tooltips descriptivos (pueden ser de varias líneas con \n) ---
        "Download the list of builds again.\nUse it if something looks out of "
        "date.":
            "Vuelve a descargar la lista de compilaciones.\n"
            "Úsalo si ves algo desactualizado.",
        "Filter by version, branch or file name as you type.":
            "Filtra por versión, rama o nombre de archivo mientras escribes.",
        "Show every build: stable, LTS, daily and alpha.":
            "Muestra todas las compilaciones: estables, LTS, diarias y alfa.",
        "LTS = Long Term Support.\nVersions maintained for years and the most "
        "stable.\nRecommended for everyday work.":
            "LTS = soporte a largo plazo (Long Term Support).\n"
            "Versiones mantenidas durante años y las más estables.\n"
            "Recomendadas para trabajar a diario.",
        "Stable versions that are not LTS.\nThey are the latest official "
        "releases, supported until the next one.":
            "Versiones estables que no son LTS.\n"
            "Son las últimas versiones oficiales, con soporte hasta la "
            "siguiente.",
        "Daily and alpha builds with the newest changes.\nThey can fail: for "
        "testing, not for work.":
            "Compilaciones diarias y alfa con los últimos cambios.\n"
            "Pueden fallar: son para probar, no para trabajar.",
        "Branches with new features still in development.\nThey are not ready "
        "for production and the list is usually empty.":
            "Ramas con funciones nuevas todavía en desarrollo.\n"
            "No están listas para producción y la lista suele estar vacía.",
        "Only the builds you marked with the star.":
            "Solo las compilaciones que marcaste con la estrella.",
        "Show the builds as a grid of icons.":
            "Muestra las compilaciones como una cuadrícula de iconos.",
        "Show the builds as a list of rows.":
            "Muestra las compilaciones como una lista de filas.",
        "System the build is for.\nChange it to download for another computer "
        "(for example, to copy it on a USB stick).":
            "Sistema para el que es la compilación.\n"
            "Cámbialo para descargar para otro equipo (por ejemplo, para "
            "copiarla en un USB).",
        "Processor type the build is for.\nx86_64 is the usual one on most "
        "PCs; arm64 is for Apple Silicon and ARM machines.":
            "Tipo de procesador para el que es la compilación.\n"
            "x86_64 es el habitual en la mayoría de PCs; arm64 es para Apple "
            "Silicon y equipos ARM.",
        "Show the versions you already have on this computer.":
            "Muestra las versiones que ya tienes en este equipo.",
        "Show the builds you can download from Blender.":
            "Muestra las compilaciones que puedes descargar de Blender.",
        "Settings.":
            "Ajustes.",
        "Folder where the Blender versions you download are stored.\nEach "
        "version goes in its own subfolder.":
            "Carpeta donde se guardan las versiones de Blender que "
            "descargas.\nCada versión va en su propia subcarpeta.",
        "Folder for the LTS versions only.\nLeave it empty to use the "
        "destination folder.":
            "Carpeta solo para las versiones LTS.\n"
            "Déjala vacía para usar la carpeta de destino.",
        "Delete the downloaded .zip/.tar.xz after extracting it.\nSaves disk "
        "space; you can download it again if you need it.":
            "Borra el .zip/.tar.xz descargado tras extraerlo.\n"
            "Ahorra espacio; puedes volver a descargarlo si lo necesitas.",
        "Language of the interface.\nIt changes when you restart the app.":
            "Idioma de la interfaz.\nCambia al reiniciar la aplicación.",
        "Size the grid returns to when you reset the zoom.":
            "Tamaño al que vuelve la rejilla cuando restableces el zoom.",
        "Window size": "Tamaño de la ventana",
        "Reset": "Restablecer",
        "Return the window to its default size and center it on the screen.":
            "Devuelve la ventana a su tamaño por defecto y la centra en la "
            "pantalla.",
        "Extra arguments Blender receives when you launch it.\nExample: "
        "--background to start without the interface.":
            "Argumentos extra que recibe Blender al lanzarlo.\n"
            "Ejemplo: --background para arrancar sin interfaz.",
        "Check for new BlenderManager versions when the app starts.\nTurn it "
        "off if you do not want to update.":
            "Busca versiones nuevas de BlenderManager al abrir la "
            "aplicación.\nApágalo si no quieres actualizar.",
        "How often BlenderManager looks for its own updates.\nIt only "
        "downloads one when you accept; checking is cheap.":
            "Cada cuánto busca BlenderManager sus propias actualizaciones.\n"
            "Solo descarga una cuando aceptas; comprobar apenas cuesta.",
        "Version of BlenderManager you are using right now.":
            "Versión de BlenderManager que estás usando ahora mismo.",
        "Download progress.": "Progreso de la descarga.",
        "Stop the download running now.":
            "Detén la descarga que está en marcha.",
        "Size of the cards in the grid.\nCtrl + and Ctrl - change it, Ctrl+0 "
        "resets it.":
            "Tamaño de las tarjetas en la cuadrícula.\n"
            "Ctrl + y Ctrl - lo cambian, Ctrl+0 lo restablece.",
        "Current zoom.": "Zoom actual.",
        "Ask me again another time.": "Pregúntame otra vez más tarde.",
        'Do not offer this exact version again.\n"Check now" still shows it.':
            'No vuelvas a ofrecer esta versión concreta.\n'
            '"Buscar ahora" sí la muestra.',
        "Download and install it now.\nThe app restarts by itself.":
            "Descárgala e instálala ahora.\nLa aplicación se reinicia sola.",
        "Keep the version you have and add the new one next to it.":
            "Conserva la versión que tienes y añade la nueva al lado.",
        "Delete the installed version and put the new one in its place.":
            "Borra la versión instalada y pon la nueva en su lugar.",
        "Never offer updates for this Blender series again.\nYou can undo it "
        "in Settings.":
            "No vuelvas a ofrecer actualizaciones de esta serie de Blender.\n"
            "Puedes deshacerlo en Ajustes.",
        "Run git pull and restart the app.":
            "Ejecuta git pull y reinicia la aplicación.",
        "Do nothing.": "No hace nada.",
        "This cannot be undone.": "Esto no se puede deshacer.",
        "Close this message.": "Cierra este aviso.",
    }
}

_current = DEFAULT


def detect_language() -> str:
    """Idioma según las variables de entorno (LANG, LC_ALL...)."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            code = value.split(":")[0].split(".")[0].split("_")[0].lower()
            if code in SUPPORTED:
                return code
    try:
        detected = locale.getlocale()[0]
    except (ValueError, TypeError):
        detected = None
    if detected:
        code = detected.split("_")[0].lower()
        if code in SUPPORTED:
            return code
    return DEFAULT


def set_language(language) -> None:
    """Fija el idioma de la interfaz: 'auto', 'en' o 'es'."""
    global _current
    if language in (None, "", "auto"):
        _current = detect_language()
    else:
        _current = language if language in SUPPORTED else DEFAULT


def get_language() -> str:
    """Idioma que se está usando ahora mismo."""
    return _current


def tr(text, **kwargs) -> str:
    """Traduce una cadena (las claves van en inglés).

    Si falta la traducción devuelve la clave tal cual, para que la
    interfaz no se rompa por un texto sin traducir.
    """
    translated = _TRANSLATIONS.get(_current, {}).get(text, text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # Una traducción con una llave suelta ("Versión {") no puede tumbar
            # la construcción de la interfaz: devolvemos el texto sin sustituir.
            return translated
    return translated
