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
        "No builds found": "No se encontraron builds",
        "Loading...": "Cargando...",
        "Ready": "Listo",
        "Destination folder": "Carpeta de destino",
        "Language": "Idioma",
        "Automatic": "Automatico",
        "English": "Ingles",
        "Spanish": "Espanol",
        "Delete archive after extraction": "Borrar el archivo tras extraer",
        "Launch arguments": "Argumentos de lanzamiento",
        "Installed versions": "Versiones instaladas",
        "Installed build": "Instalada",
        "No installed versions found": "No se encontraron versiones instaladas",
        "Download complete": "Descarga completada",
        "Download failed": "Fallo en la descarga",
        "Extraction complete": "Extraccion completada",
        "Extraction failed": "Fallo en la extraccion",
        "Cancelled": "Cancelado",
        "Checksum error": "Error en la suma de verificacion",
        "Downloading {name}": "Descargando {name}",
        "Extracting {name}": "Extrayendo {name}",
        "Launching {name}": "Lanzando {name}",
        "Deleted {name}": "Borrado {name}",
        "Delete {name}?": "¿Borrar {name}?",
        "This will remove the folder permanently.": "Esto eliminara la carpeta permanentemente.",
        "Error": "Error",
        "Info": "Informacion",
        "Select destination folder": "Selecciona la carpeta de destino",
        "Platform": "Plataforma",
        "Architecture": "Arquitectura",
        "Unknown": "Desconocido",
        "Added by BlenderManager": "Anadido por Gestor de Blender",
        "No executable found": "No se encontro el ejecutable",
        "Show the store": "Muestra la tienda de compilaciones",
        "Show installed versions": "Muestra las versiones instaladas",
        "Open settings": "Abre los ajustes",
        "Refresh the list of builds": "Actualiza la lista de compilaciones",
        "Search builds by version or branch": "Busca compilaciones por version o rama",
        "Filter: all channels": "Filtro: todos los canales",
        "Filter: LTS only": "Filtro: solo versiones LTS",
        "Filter: stable only": "Filtro: solo versiones estables",
        "Filter: daily and alpha": "Filtro: versiones diarias y alfa",
        "Grid view": "Vista en cuadricula de iconos",
        "List view": "Vista en filas",
        "Target operating system": "Sistema operativo de destino",
        "Target architecture": "Arquitectura de destino",
        "Download and install this version": "Descarga e instala esta version",
        "Launch this installed version": "Lanza esta version instalada",
        "Remove this installed version": "Elimina esta version instalada",
        "Choose destination folder": "Elige la carpeta donde se guardaran las versiones",
        "Save settings": "Guarda los ajustes",
        "Zoom the icon size": "Ajusta el tamano de los iconos",
    }
}

_current = DEFAULT


def detect_language() -> str:
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
    global _current
    if language in (None, "", "auto"):
        _current = detect_language()
    else:
        _current = language if language in SUPPORTED else DEFAULT


def get_language() -> str:
    return _current


def tr(text, **kwargs) -> str:
    translated = _TRANSLATIONS.get(_current, {}).get(text, text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError):
            return translated
    return translated
