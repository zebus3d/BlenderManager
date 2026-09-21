"""Qué tipo de compilación es cada cosa, y a qué carpeta le toca ir.

Antes esta pregunta se respondía en cuatro sitios a la vez: las constantes de
``settings`` y de ``ui.widgets.main_window``, las ramas de ``api.filter_builds``
y unas heurísticas paralelas en ``installed`` (``is_experimental``,
``_is_stable_install``). Mientras solo servían para pintar una pestaña se podía
vivir con ello; desde que el usuario puede decir "las LTS a este disco y las
diarias a aquel", el tipo de una compilación es un **dato del que depende dónde
se escribe en disco**, y tener cuatro definiciones distintas de "esto es una
diaria" deja de ser un problema estético.

Este módulo es la única definición. No importa ``settings`` ni ``installed``
(ellos importan de aquí), así que no hay ciclos, y no toca disco ni Qt: todo son
funciones puras que se prueban con datos de mentira.
"""

import os
from pathlib import Path

from model.build import LTS_MINORS, minor_of

# Los tipos que puede recibir una carpeta. Son los canales de Blender menos los
# dos que no describen una compilación: "all" (no filtra) y "favorites" (es
# transversal, lo marca el usuario a mano).
TYPE_LTS = "lts"
TYPE_STABLE = "stable"
TYPE_DAILY = "daily"
TYPE_PATCH = "patch"
TYPE_EXPERIMENTAL = "experimental"
BUILD_TYPES = (TYPE_LTS, TYPE_STABLE, TYPE_DAILY, TYPE_PATCH, TYPE_EXPERIMENTAL)

# Canales de la barra de pestañas. Viven aquí para que no se dupliquen; las
# etiquetas traducidas son cosa de la interfaz.
CHANNELS = ("all", "lts", "stable", "daily", "patch", "experimental",
            "favorites")


def type_of_build(build) -> str:
    """Tipo de una compilación de la tienda.

    El orden de las preguntas importa y es el mismo que tenía
    ``api.filter_builds``: una compilación de un pull request (patch) es un
    patch aunque su versión coincida con la de una release; una rama
    experimental es experimental aunque su número de versión sea el de una LTS,
    y una alfa de una serie LTS es una diaria, no una LTS. Es decir, manda de
    dónde viene la compilación por encima de cómo se llama.
    """
    if getattr(build, "patch", ""):
        return TYPE_PATCH
    if getattr(build, "experimental", False):
        return TYPE_EXPERIMENTAL
    if getattr(build, "risk", "") != "stable":
        return TYPE_DAILY
    if getattr(build, "is_lts", False):
        return TYPE_LTS
    return TYPE_STABLE


def type_from_marker(branch: str, version: str, name: str = "",
                     risk: str = "") -> str:
    """Tipo de una instalación, a partir de lo que sepamos de ella.

    ``risk`` es el que anotamos en el marcador al instalarla, y cuando está es
    la respuesta buena: lo dio la propia API de Blender. Solo cuando falta
    —carpetas que no bajó la app, o instaladas antes de que existiera el
    marcador— hay que adivinar, y entonces se mira la rama y el nombre:

    * las ramas normales se llaman ``main`` (diarias) o ``v45``/``v52``
      (estables); cualquier otro nombre es una rama de funciones nuevas;
    * sin rama anotada nos queda el nombre de la carpeta, donde las diarias
      llevan ``alpha``, ``beta`` o ``daily``.

    Sin nada de eso se da por estable, que es lo que era antes de existir el
    marcador y lo menos sorprendente.
    """
    branch = (branch or "").strip()
    # Las compilaciones de pull requests se llaman ``main-PR161547``.
    if "-pr" in branch.lower():
        return TYPE_PATCH
    if branch and branch != "main" and not branch.startswith("v"):
        return TYPE_EXPERIMENTAL
    if risk and risk != "stable":
        return TYPE_DAILY
    if branch == "main":
        return TYPE_DAILY
    if any(token in (name or "").lower() for token in ("alpha", "beta", "daily")):
        return TYPE_DAILY
    if minor_of(version or "") in LTS_MINORS:
        return TYPE_LTS
    return TYPE_STABLE


def type_of_installed(entry) -> str:
    """Tipo de un ``InstalledBuild`` (envoltorio de ``type_from_marker``)."""
    return type_from_marker(
        getattr(entry, "branch", ""),
        getattr(entry, "version", ""),
        getattr(entry, "name", ""),
        getattr(entry, "risk", ""),
    )


def normalize_path(path) -> str:
    """Forma canónica de una ruta, para comparar dos carpetas.

    ``expanduser`` porque el usuario puede escribir ``~/Blender``, y
    ``normcase`` porque en Windows ``C:\\Blender`` y ``c:\\blender`` son la
    misma carpeta. **No** se usa ``resolve()`` aquí a propósito: resolver toca
    el disco y falla con enlaces rotos o unidades desconectadas, y esto tiene
    que funcionar sobre una configuración guardada aunque el disco no esté
    puesto. Para deduplicar lo que ya existe en disco está ``scan_folders``.
    """
    if not path:
        return ""
    return os.path.normcase(str(Path(str(path)).expanduser()))


def owner_of(folders, build_type: str):
    """Carpeta que se queda con ese tipo, o ``None`` si no lo tiene nadie.

    Cada tipo tiene **un único dueño**: la interfaz, al marcar una casilla, se
    la quita a la carpeta que la tuviera. Por eso aquí basta con devolver la
    primera que encaje, y por eso el destino de una descarga nunca es ambiguo.
    """
    for folder in folders or ():
        if folder.takes(build_type):
            return folder
    return None


def resolve_destination(folders, build_type: str) -> str:
    """Carpeta donde se instala ese tipo, o ``""`` si nadie lo recibe.

    Un solo escalón, y es deliberado. Con casillas, "quién recibe esto" es un
    dato que el usuario ha puesto a mano, no algo que haya que adivinar: si
    nadie ha marcado *Diarias*, lo correcto es decirlo y que lo arregle, no
    colar la diaria en la primera carpeta que pille. La cadena de reservas que
    haría falta con un desplegable (rol exacto → comodín → la primera que
    valga) es justo lo que esto se ahorra.
    """
    owner = owner_of(folders, build_type)
    return owner.path if owner is not None else ""


def orphan_types(folders) -> list:
    """Tipos que no recibe ninguna carpeta, en el orden de ``BUILD_TYPES``.

    La interfaz los avisa **antes** de que el usuario intente descargar uno:
    es la contrapartida de no tener cadena de reservas.
    """
    return [build_type for build_type in BUILD_TYPES
            if owner_of(folders, build_type) is None]
