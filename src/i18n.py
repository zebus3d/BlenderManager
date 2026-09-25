"""Traducciones de la interfaz.

Las **claves son las cadenas en inglés**: si falta una traducción se enseña el
texto original en vez de romperse. El idioma se detecta de las variables de
entorno del sistema (LANG, LC_ALL...) salvo que el usuario lo fije en Ajustes.

Los textos viven en ``src/locale/<idioma>.json``, no aquí: con dos idiomas el
diccionario en Python ya pasaba de mil líneas, y en JSON se puede mandar una
traducción sin tocar código. Se cargan una vez, al primer uso.
"""

import json
import locale
import os

from paths import RESOURCE_DIR

SUPPORTED = ("en", "es", "zh", "ru", "ja", "pt_BR")
DEFAULT = "en"

# Carpeta con los ``<idioma>.json``. Va por ``RESOURCE_DIR`` para que también
# la encuentre el binario empaquetado (PyInstaller la copia ahí).
LOCALE_DIR = RESOURCE_DIR / "locale"

# Caché por idioma: leer el JSON en cada ``tr()`` sería absurdo.
_TRANSLATIONS = {}


def _load(language: str) -> dict:
    """Diccionario de ese idioma, del disco y una sola vez.

    El inglés no tiene fichero: es la clave. Si el JSON falta o está roto se
    devuelve vacío y la interfaz sale en inglés, que es preferible a no
    arrancar.
    """
    if language in _TRANSLATIONS:
        return _TRANSLATIONS[language]
    table = {}
    if language != DEFAULT:
        try:
            table = json.loads((LOCALE_DIR / f"{language}.json")
                               .read_text(encoding="utf-8"))
        except (OSError, ValueError):
            table = {}
    _TRANSLATIONS[language] = table
    return table


# Idioma en uso. Arranca en inglés (las claves) hasta que ``set_language`` lo
# fije con lo que diga el sistema o los ajustes.
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
    """Fija el idioma de la interfaz: 'auto' o un código de ``SUPPORTED``."""
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
    translated = _load(_current).get(text, text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # Una traducción con una llave suelta ("Versión {") no puede tumbar
            # la construcción de la interfaz: devolvemos el texto sin sustituir.
            return translated
    return translated
