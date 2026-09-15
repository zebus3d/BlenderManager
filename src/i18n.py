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
        "Extracting...": "Extrayendo...",
        "Launch": "Lanzar",
        "Launching": "Lanzando",
        "Delete": "Borrar",
        "Uninstall": "Desinstalar",
        "Cancel": "Cancelar",
        "Close": "Cerrar",
        "Save": "Guardar",
        "Browse...": "Examinar...",
        "No builds found": "No se encontraron compilaciones",
        "Loading...": "Cargando...",
        "Ready": "Listo",
        "Destination folder": "Carpeta de destino",
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
        "Choose destination folder": "Elige la carpeta donde se guardarán las versiones",
        "Parent folder": "Carpeta superior",
        "Home folder": "Carpeta personal",
        "Use this folder": "Usar esta carpeta",
        "Save settings": "Guarda los ajustes",
        "Zoom the icon size (Ctrl +/- / Ctrl+0)":
            "Ajusta el tamaño de los iconos (Ctrl +/- / Ctrl+0)",
        "Updates": "Actualizaciones",
        "Check for updates automatically": "Buscar actualizaciones automáticamente",
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
