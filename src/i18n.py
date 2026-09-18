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
        "Installing...": "Instalando...",
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
        "Check for updates on startup": "Buscar actualizaciones al iniciar",
        "Check for updates periodically": "Buscar actualizaciones periódicamente",
        "Look for new versions of BlenderManager every so often,\n"
        "even if the startup check is off.":
            "Busca versiones nuevas de BlenderManager cada cierto tiempo,\n"
            "aunque esté desactivado el chequeo al iniciar.",
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
        "Check for new BlenderManager versions when the app starts.\n"
        "It only downloads one when you accept; checking is cheap.":
            "Busca versiones nuevas de BlenderManager al abrir la "
            "aplicación.\nSolo descarga una cuando la aceptas; comprobar es "
            "barato.",
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

        # --- Migración de addons entre versiones de Blender ---
        "Migrate": "Migrar",
        "Copy add-ons, extensions and preferences from one Blender version to "
        "another.":
            "Copia addons, extensiones y preferencias de una versión de Blender "
            "a otra.",
        "Migrate add-ons, extensions and preferences":
            "Migrar addons, extensiones y preferencias",
        "Copy the add-ons (and extensions) of one installed version to "
        "another, checking first whether they are compatible.":
            "Copia los addons (y extensiones) de una versión instalada a otra, "
            "comprobando antes si son compatibles.",
        "From": "Desde",
        "To": "Hacia",
        "Source": "Origen",
        "Destination": "Destino",
        "(not copied)": "(no se copia)",
        "Source and destination must be different.":
            "El origen y el destino tienen que ser distintos.",
        "You need at least two installed Blender versions.":
            "Necesitas al menos dos versiones de Blender instaladas.",
        "No add-ons found in this version":
            "No se encontraron addons en esta versión",
        "Install some add-ons in the source version first.":
            "Instala addons en la versión de origen primero.",
        "Add-ons": "Addons",
        "Extension": "Extensión",
        "Legacy add-on": "Addon clásico",
        "Compatible": "Compatible",
        "Review": "Revisar",
        "Not compatible": "No compatible",
        "It needs Blender {version} or newer.":
            "Necesita Blender {version} o posterior.",
        "It does not support Blender {version} yet.":
            "Todavía no soporta Blender {version}.",
        "It is not published for this system.":
            "No está publicado para este sistema.",
        "Its dependencies are built for another Python version.":
            "Sus dependencias están compiladas para otra versión de Python.",
        "It does not state a minimum version.":
            "No indica una versión mínima.",
        # Cómo revisar un addon marcado "Review" (el motivo solo no basta).
        "Copy it and enable it in the destination version. If it fails to "
        "load, it needs a build of the add-on made for that Blender "
        "(its compiled dependencies do not match).":
            "Cópialo y actívalo en la versión de destino. Si no carga, "
            "necesitas una compilación del addon hecha para ese Blender (sus "
            "dependencias compiladas no coinciden).",
        "The add-on does not say which Blender it works with. Copy it and "
        "test its panel or operators in the destination version; if they "
        "fail, leave it disabled.":
            "El addon no indica con qué Blender funciona. Cópialo y prueba su "
            "panel u operadores en la versión de destino; si fallan, déjalo "
            "desactivado.",
        "Copy it and test it in the destination version before relying on it.":
            "Cópialo y pruébalo en la versión de destino antes de confiar en él.",
        "{total} add-ons · {ok} compatible · {warn} to review · {blocked} "
        "not compatible":
            "{total} addons · {ok} compatibles · {warn} por revisar · "
            "{blocked} no compatibles",
        "Select all": "Seleccionar todo",
        "Select none": "No seleccionar ninguno",
        "Add-ons keep the state they had in the source: the ones that were "
        "enabled there are enabled here too.":
            "Los addons conservan el estado que tenían en el origen: los que "
            "estaban activados allí también lo estarán aquí.",
        "Copy selected": "Copiar seleccionados",
        "Copy the selected add-ons to the destination.":
            "Copia los addons marcados a la versión de destino.",
        "Nothing selected": "No has seleccionado nada",
        "Copied {count} add-ons.": "Se copiaron {count} addons.",
        "Nothing was copied.": "No se copió nada.",
        "Migration complete": "Migración completada",
        "Some add-ons could not be copied:":
            "Algunos addons no se pudieron copiar:",
        "What was replaced was kept next to it as a backup.":
            "Lo que se reemplazó se guardó al lado como copia de seguridad.",
        "Enabling the add-ons in Blender...":
            "Activando los addons en Blender...",
        "Enabled {count} add-ons in Blender {version}.":
            "Se activaron {count} addons en Blender {version}.",
        "The add-ons were copied but not enabled. You can enable them in "
        "Blender's preferences.":
            "Los addons se copiaron pero no se activaron. Puedes activarlos en "
            "las preferencias de Blender.",
        "Could not enable some add-ons:":
            "No se pudieron activar algunos addons:",
        "Close Blender {version} before migrating: it would overwrite the "
        "changes when it quits.":
            "Cierra Blender {version} antes de migrar: si no, sobrescribirá "
            "los cambios al salir.",
        "Blender {version} is running": "Blender {version} está abierto",
        "No add-ons to migrate": "No hay addons que migrar",

        # --- Migración de preferencias (ficheros de config/) ---
        "Preferences": "Preferencias",
        "Preferences file": "Fichero de preferencias",
        "Copy the preferences file of the source version. It replaces the "
        "current one (a backup is kept).":
            "Copia el fichero de preferencias de la versión de origen. "
            "Reemplaza el actual (se guarda una copia de seguridad).",
        "Copy preferences": "Copiar preferencias",
        "Copy the selected preference files.":
            "Copia los ficheros de preferencias marcados.",
        "(replaces the current one)": "(reemplaza el actual)",
        "The startup file replaces your default scene and interface. "
        "Leave it off unless you know what it does.":
            "El fichero de arranque reemplaza tu escena e interfaz por defecto. "
            "Déjalo desactivado salvo que sepas lo que hace.",
        "No preferences found in the source version.":
            "No se encontraron preferencias en la versión de origen.",
        "Copied {count} preference files.":
            "Se copiaron {count} ficheros de preferencias.",
        "Some files could not be copied:":
            "Algunos ficheros no se pudieron copiar:",
        "Undo last migration": "Deshacer última migración",
        "Put back what the last migration replaced and remove what it copied.":
            "Devuelve lo que reemplazó la última migración y quita lo que copió.",
        "This puts back what the last migration replaced and removes what it "
        "copied from Blender {version}.\n\nAdd-ons you have changed since then "
        "will be lost.":
            "Esto devuelve lo que reemplazó la última migración y quita lo que "
            "copió de Blender {version}.\n\nLos addons que hayas cambiado desde "
            "entonces se perderán.",
        "Undo": "Deshacer",
        "Migration undone": "Migración deshecha",
        "Restored {count} items to their previous state.":
            "Se restauraron {count} elementos a su estado anterior.",
        "Removed {count} items that were copied.":
            "Se quitaron {count} elementos que se habían copiado.",
        "There was nothing to undo.": "No había nada que deshacer.",
        "Some items could not be restored:":
            "Algunos elementos no se pudieron restaurar:",

        # --- Preferencias selectivas (comparadas con las de fábrica) ---
        "Preferences in detail": "Preferencias en detalle",
        "Pick individual settings changed from Blender's defaults. They are "
        "read automatically from the source version (it starts once, it may "
        "take a moment).":
            "Elige ajustes concretos que hayan cambiado respecto a los valores "
            "por defecto de Blender. Se leen automáticamente de la versión de "
            "origen (arranca una vez, puede tardar un momento).",
        "Read again": "Leer de nuevo",
        "Read the settings from the source version again.":
            "Vuelve a leer los ajustes de la versión de origen.",
        "{changed} settings changed from Blender's defaults · {active} "
        "add-ons enabled in the source.":
            "{changed} ajustes cambiados respecto a los valores por defecto de "
            "Blender · {active} addons activados en el origen.",
        "Apply to destination": "Aplicar al destino",
        "Write the selected settings in the destination version.":
            "Escribe los ajustes marcados en la versión de destino.",
        "Reading settings...": "Leyendo ajustes...",
        "Could not read the settings.": "No se pudieron leer los ajustes.",
        "You have no settings changed from Blender's defaults.":
            "No tienes ajustes cambiados respecto a los valores por defecto de "
            "Blender.",
        "{count} settings changed from Blender's defaults.":
            "{count} ajustes cambiados respecto a los valores por defecto de "
            "Blender.",
        "This depends on your computer, not on your settings. Leave it off "
        "unless it is the same machine.":
            "Esto depende de tu equipo, no de tus ajustes. Déjalo desactivado "
            "salvo que sea el mismo ordenador.",
        "The source version has no executable to read.":
            "La versión de origen no tiene ejecutable que leer.",
        "The destination version has no executable to write.":
            "La versión de destino no tiene ejecutable en el que escribir.",
        "Applying settings...": "Aplicando ajustes...",
        "Settings applied": "Ajustes aplicados",
        "Applied {count} settings to Blender {version}.":
            "Se aplicaron {count} ajustes a Blender {version}.",
        "No settings were applied.": "No se aplicó ningún ajuste.",
        "These settings no longer exist in this version:":
            "Estos ajustes ya no existen en esta versión:",

        # --- Tooltips de la vista de migración ---
        "Pick a source and a destination version above, then use the tabs to "
        "copy add-ons, individual settings or the whole preferences file.":
            "Elige arriba una versión de origen y otra de destino y usa las "
            "pestañas para copiar addons, ajustes concretos o el fichero de "
            "preferencias entero.",
        "Version you are copying the add-ons and settings from.":
            "Versión de la que copias los addons y los ajustes.",
        "Version you are copying the add-ons and settings to.":
            "Versión a la que copias los addons y los ajustes.",
        "Folder with the settings and add-ons of the source version. It is "
        "only read, never written.":
            "Carpeta con los ajustes y addons de la versión de origen. Solo se "
            "lee, nunca se escribe.",
        "Folder with the settings and add-ons of the destination version. This "
        "is where the copy writes; what exists there is kept as a backup.":
            "Carpeta con los ajustes y addons de la versión de destino. Aquí "
            "escribe la copia; lo que ya exista se guarda como copia de "
            "seguridad.",
        "The add-ons and settings selected on the left are copied to the "
        "version on the right.":
            "Los addons y ajustes marcados a la izquierda se copian a la "
            "versión de la derecha.",
        "The ticked add-ons are copied from left to right. Nothing is moved: "
        "the source version stays as it is.":
            "Los addons marcados se copian de izquierda a derecha. No se mueve "
            "nada: la versión de origen se queda como está.",
        "Add-ons installed in the version you are copying from. Tick the ones "
        "you want in the destination version.":
            "Addons instalados en la versión de origen. Marca los que quieras "
            "tener en la de destino.",
        "Where each add-on lands in the destination version. Add-ons that were "
        "enabled in the source are enabled here too.":
            "Dónde queda cada addon en la versión de destino. Los que estaban "
            "activados en el origen también se activan aquí.",
        "How many add-ons were found, how many are compatible, how many you "
        "should review and how many cannot be copied.":
            "Cuántos addons se encontraron, cuántos son compatibles, cuántos "
            "conviene revisar y cuántos no se pueden copiar.",
        "Tick every add-on that can be copied. The ones marked \"Not "
        "compatible\" cannot be ticked.":
            "Marca todos los addons que se puedan copiar. Los de «No "
            "compatible» no se pueden marcar.",
        "Untick them all, to copy nothing.":
            "Desmárcalos todos, para no copiar nada.",
        "Tick every setting listed below.":
            "Marca todos los ajustes de la lista.",
        "Untick them all, to migrate no setting.":
            "Desmárcalos todos, para no migrar ningún ajuste.",
        "Copy the ticked add-ons to the destination version and enable the "
        "ones that were enabled in the source.":
            "Copia los addons marcados a la versión de destino y activa los "
            "que estaban activados en el origen.",
        "Tick to include this add-on in the copy.":
            "Marca para incluir este addon en la copia.",
        "It works with the destination version; it will be copied and kept as "
        "it is.":
            "Funciona con la versión de destino; se copiará y se dejará tal "
            "cual.",
        "This add-on is not copied, so nothing changes here.":
            "Este addon no se copia, así que aquí no cambia nada.",
        "Where it lands on the destination side: {path}":
            "Dónde queda en la versión de destino: {path}",
        "{name} of the source version:\n{path}":
            "{name} de la versión de origen:\n{path}",
        "Settings saved aside by a previous reset, ready to be put back.":
            "Ajustes guardados aparte por un restablecimiento anterior, listos "
            "para recuperarlos.",

        # --- Reset a valores de fábrica (con instantánea recuperable) ---
        "Factory settings": "Valores de fábrica",
        "Put Blender {version} back to a clean state. Its current settings are "
        "saved aside and can be restored, unless you delete them.":
            "Devuelve Blender {version} a un estado limpio. Sus ajustes "
            "actuales se guardan aparte y se pueden recuperar, salvo que los "
            "borres.",
        "Reset to factory settings": "Restablecer a valores de fábrica",
        "Save the current settings aside and start clean.":
            "Guarda aparte los ajustes actuales y empieza de cero.",
        "Restore last settings": "Recuperar últimos ajustes",
        "Put the saved settings back.": "Devuelve los ajustes guardados.",
        "Delete saved settings": "Borrar ajustes guardados",
        "Delete the saved settings for good.":
            "Borra los ajustes guardados para siempre.",
        "Saved settings: {count}. The newest is from {date}.":
            "Ajustes guardados: {count}. El más reciente es del {date}.",
        "No saved settings. Resetting will keep nothing to go back to.":
            "No hay ajustes guardados. Si restableces, no habrá nada a lo que "
            "volver.",
        "This version has no settings yet.":
            "Esta versión todavía no tiene ajustes.",
        "Settings saved aside and reset.":
            "Ajustes guardados aparte y restablecidos.",
        "Your settings were saved. Blender {version} will start clean the next "
        "time you open it.":
            "Tus ajustes se guardaron. Blender {version} arrancará limpio la "
            "próxima vez que lo abras.",
        "Blender {version} will start clean on next launch.\n\nYour settings "
        "are saved aside, so you can put them back from this same screen.":
            "Blender {version} arrancará limpio la próxima vez.\n\nTus ajustes "
            "se guardan aparte, así que podrás devolverlos desde esta misma "
            "pantalla.",
        "Reset": "Restablecer",
        "Put back the saved settings of Blender {version}?\n\nThe clean "
        "settings you have now are saved aside, so this can be undone too.":
            "¿Devolver los ajustes guardados de Blender {version}?\n\nLos "
            "ajustes limpios que tienes ahora se guardan aparte, así que esto "
            "también se puede deshacer.",
        "Restore": "Recuperar",
        "Settings restored.": "Ajustes recuperados.",
        "Delete the saved settings for good? You will not be able to restore "
        "them.":
            "¿Borrar los ajustes guardados para siempre? No podrás "
            "recuperarlos.",
        "Saved settings deleted.": "Ajustes guardados borrados.",
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
