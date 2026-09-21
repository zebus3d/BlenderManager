"""Vista de migración de addons entre versiones de Blender.

El núcleo (``services/blender_config``) hace el trabajo: localiza las carpetas,
lee la versión mínima de cada addon y decide si es compatible. Aquí solo se
enseña el informe, se dejan marcar los que se quieren copiar y se lanza la
copia. La parte de habilitarlos en la versión destino la ejecuta Blender en
segundo plano (``services/blender_runner``), porque el estado *habilitado*
vive dentro de ``userpref.blend``.

La pantalla sigue la misma guía que Ajustes: pestañas arriba (a la altura de
las de canal), contenido debajo sobre el fondo oscuro y tarjetas un escalón por
encima. La tarjeta "desde → hacia" es común a las tres pestañas y se mueve a la
que esté abierta.

Dentro de Add-ons, la disposición es la de un tablero de transferencia: el **origen** a la
izquierda (con casilla, versión y veredicto), el **destino** a la derecha (con
la carpeta donde caerá cada addon) y una flecha de un solo sentido en medio.
Las dos columnas viven en la **misma área de scroll**, así que las filas quedan
siempre alineadas sin sincronizar nada.

No es una pestaña de compilaciones, así que la barra de filtros y el buscador
se ocultan (lo decide ``MainWindow._set_view``).
"""

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pathlib import Path

from i18n import tr
from model.build import version_tuple
from services import blender_config as bc
from services import blender_prefs as bprefs
from services import blender_runner
from ui import icons
from ui import theme as t
from ui.fonts import glyph_icon, icon_font
from ui.widgets.buttons import CardButton, CheckPill
from ui.widgets.cards import card_shadow
from ui.widgets.dialogs import AppDialog, confirm, show_info
from ui.widgets.labels import ElidedLabel

# Alto fijo de una fila: las dos columnas tienen que cuadrar una con otra.
ROW_HEIGHT = 48

# Alto máximo del área con las claves cambiadas. Un Blender puede tener cientos
# de ajustes distintos de fábrica: sin tope, la tarjeta crece sin fin, empuja
# los botones fuera de la pantalla y no se puede leer nada. Con esto caben unas
# ocho filas y el resto se ve con la barra de scroll, con los botones siempre a
# la vista.
DETAIL_SCROLL_HEIGHT = 260

# Alto máximo de la lista de guardados (mismo motivo: caben unos cuatro y a
# partir de ahí se baja con la barra).
SNAPSHOT_SCROLL_HEIGHT = 280

# Estos paneles se estiran desde su esquina inferior derecha
# (``_ResizableScroll``): el alto inicial es el de su contenido, y el usuario lo
# sube si quiere ver más filas sin tocar la ventana. Por debajo de estos mínimos
# no se puede encoger.
DETAIL_MIN_HEIGHT = 60
SNAPSHOT_MIN_HEIGHT = 60

# Color del glifo dentro de un botón (sobre el relleno de acento).
_ICON_ON_ACCENT = "#FFFFFF"

# objectName del QSS y texto del estado de compatibilidad.
_STATUS = {
    bc.OK: ("Success", "Compatible"),
    bc.WARN: ("Warning", "Review"),
    bc.BLOCKED: ("Danger", "Not compatible"),
}


def _reason_text(plan) -> str:
    """Frase que explica el motivo del estado (vacía si todo está bien)."""
    addon = plan.addon
    if plan.reason == bc.REASON_REQUIRES_NEWER:
        return tr("It needs Blender {version} or newer.",
                  version=addon.min_version)
    if plan.reason == bc.REASON_TOO_NEW:
        return tr("It does not support Blender {version} yet.",
                  version=addon.max_version)
    if plan.reason == bc.REASON_PLATFORM:
        return tr("It is not published for this system.")
    if plan.reason == bc.REASON_WHEEL_ABI:
        # Se nombra el paquete culpable y el Python del destino: el texto
        # genérico de antes ("sus dependencias son de otro Python") se leía
        # como si comparásemos las dos versiones de Blender entre sí.
        if not plan.detail:
            # Sin el nombre del paquete (un plan armado a mano) se dice lo
            # mismo en genérico, pero sin fingir que sabemos cuál falla.
            return tr("One of its dependencies has no build for the Python of "
                      "the destination version.")
        if plan.target_python:
            return tr("{package} has no build for Python {python}, which the "
                      "destination version uses.",
                      package=plan.detail, python=plan.target_python)
        return tr("{package} has no build for the Python of the destination "
                  "version.", package=plan.detail)
    if plan.reason == bc.REASON_UNKNOWN_VERSION:
        return tr("It does not state a minimum version.")
    return ""


# Qué hacer con un addon marcado "Review" (el motivo solo no basta: el usuario
# necesita saber cómo comprobarlo). Se elige la recomendación según la causa.
def _review_advice(plan) -> str:
    """Pasos concretos para revisar un addon que no se puede dar por seguro."""
    if plan.reason == bc.REASON_WHEEL_ABI:
        return tr(
            "Copy it and enable it in the destination version. If it fails to "
            "load, ask its author for a build that includes that dependency "
            "for this Python.")
    if plan.reason == bc.REASON_UNKNOWN_VERSION:
        return tr(
            "The add-on does not say which Blender it works with. Copy it and "
            "test its panel or operators in the destination version; if they "
            "fail, leave it disabled.")
    # Aviso sin causa concreta (no debería pasar, pero mejor dar algo que nada).
    return tr("Copy it and test it in the destination version before relying "
              "on it.")


def _status_tooltip(plan) -> str:
    """Tooltip del estado de una fila: motivo y, si toca, qué hacer.

    Sirve para las tres insignias: la verde dice que no hay nada que mirar, la
    amarilla por qué hay que revisarlo y cómo, y la roja por qué no se copia.
    """
    if plan.status == bc.OK:
        return tr("It works with the destination version; it will be copied and "
                  "kept as it is.")
    reason = _reason_text(plan)
    if plan.status == bc.WARN:
        advice = _review_advice(plan)
        return f"{reason}\n\n{advice}" if reason else advice
    # BLOCKED: el motivo de por qué no se puede copiar (ya viene en el texto).
    return reason


def _meta_text(addon) -> str:
    """Línea secundaria de una fila (versión, mínimo declarado y tipo)."""
    parts = []
    if addon.version:
        parts.append(f"v{addon.version}")
    if addon.min_version:
        parts.append(f"min {addon.min_version}")
    parts.append(tr("Extension") if addon.kind == "extension"
                 else tr("Legacy add-on"))
    return "  ·  ".join(parts)


def _destination_text(plan) -> str:
    """Carpeta relativa donde quedará el addon en la versión destino."""
    if plan.blocked:
        return tr("(not copied)")
    addon = plan.addon
    if addon.kind == "extension":
        addon_id = addon.module.rsplit(".", 1)[-1]
        return f"user_default/{addon_id}"
    return f"addons/{addon.path.name}"


def _clear_layout(layout) -> None:
    """Vacía un layout de widgets de verdad.

    Se **quita del layout y se oculta** además de ``deleteLater()``: el borrado
    diferido no es inmediato, así que sin el ``setParent(None)`` el widget viejo
    seguía ocupando su hueco (y salía duplicado) hasta que el bucle de eventos
    lo recogía.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.hide()
            widget.deleteLater()


def _accent_button(text: str, tooltip: str, on_click) -> CardButton:
    """Botón primario con la flecha de la migración como icono.

    El glifo va como ``QIcon``: el texto del botón usa la fuente general, así
    que pegar el carácter de la flecha ahí salía como un recuadro.
    """
    button = CardButton(text, variant="accent", tooltip=tooltip)
    button.setIcon(glyph_icon(icons.ARROW_RIGHT, 13, _ICON_ON_ACCENT))
    button.clicked.connect(on_click)
    return button


def _settings_card(title: str = "") -> tuple:
    """Tarjeta con el aspecto de los ajustes y su layout vertical.

    Es el mismo ``QFrame#SettingsCard`` que usa la pantalla de ajustes (título
    apagado, bordes redondeados, mismos márgenes); tenerlo en un solo sitio
    evita que las tarjetas de esta vista se vayan separando con el tiempo.
    Devuelve ``(tarjeta, layout)`` y, si hay ``title``, ya lo añade.
    """
    card = QFrame()
    card.setObjectName("SettingsCard")
    # Sombra abajo a la derecha (la misma que las tarjetas de la tienda): las
    # tarjetas van sobre el fondo oscuro de la pestaña y así se despegan de él.
    card_shadow(card)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    if title:
        label = QLabel(tr(title))
        label.setObjectName("Muted")
        lay.addWidget(label)
    return card, lay


def _entry_info(entry) -> tuple:
    """``(executable, version)`` de una instalada, aguantando ``None``.

    Las instaladas de verdad (``InstalledBuild``) siempre traen los dos campos,
    pero esto se llama también con entradas de tests y con el destino vacío, y
    un ``AttributeError`` aquí tumbaría la interfaz entera.
    """
    if entry is None:
        return None, ""
    return getattr(entry, "executable", None), getattr(entry, "version", "")


def _version_label(entry) -> str:
    """Texto de una opción del selector de fábrica: solo la versión.

    Allí el nombre de la carpeta no aporta nada y repetía el número
    («Blender 5.2.2 · blender-5.2.2-linux-x64»); la ruta ya está debajo.
    """
    return getattr(entry, "version", "") or getattr(entry, "name", "")


def _report_lines(summary: str, backed_up: bool, failed, failure_title: str,
                  failure_label) -> list:
    """Monta las líneas del diálogo de resultado de una copia.

    ``failed`` es una lista de ``(elemento, mensaje)`` y ``failure_label``
    extrae de cada elemento su nombre legible. Se listan como mucho diez para
    que un fallo masivo no convierta el diálogo en un muro de texto.
    """
    if not summary:
        return [tr("Nothing was copied.")]
    lines = [summary]
    if backed_up:
        lines.append(tr("What was replaced was kept next to it as a backup."))
    if failed:
        lines.append("")
        lines.append(failure_title)
        for item, message in failed[:10]:
            lines.append(f"· {failure_label(item)}: {message}")
    return lines


def _size_text(size: int) -> str:
    """Tamaño legible (``180 KB``, ``1.2 MB``). Unidades, no palabras.

    No pasa por ``tr``: un número con su unidad (KB/MB) se lee igual en los dos
    idiomas y así no hay una clave de traducción por cada medida.
    """
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _section_names(paths) -> list:
    """Nombres legibles de las secciones a las que pertenecen esas rutas RNA."""
    labels = dict(bprefs.SECTIONS)
    order = {key: index for index, (key, _) in enumerate(bprefs.SECTIONS)}
    positions = {}
    for path in paths:
        key = (path or "").split(".", 1)[0]
        positions.setdefault(key, order.get(key, 99))
    ordered = sorted(positions, key=lambda key: (positions[key], key))
    return [tr(labels.get(key, key)) for key in ordered]


def _snapshot_origin(snapshot) -> str:
    """Qué es ese guardado, en una frase (según la etiqueta del nombre).

    ``factory`` es la config limpia que se aparcó al restaurar; ``vX.Y.Z`` son
    los ajustes del usuario que se apartaron al restablecer esa versión. Sin la
    frase, dos carpetas con fechas distintas no dicen cuál es cuál.
    """
    label = bc.snapshot_label(snapshot)
    if label == "factory":
        return tr("Clean settings replaced by a restore")
    if label.startswith("v"):
        return tr("Your settings saved when resetting Blender {version}",
                  version=label[1:])
    return tr("Saved settings")


def _snapshot_files_text(details) -> str:
    """Qué trae el guardado, además de su userpref (barato, sin arrancar nada)."""
    parts = []
    if details.get("has_userpref"):
        parts.append(tr("preferences"))
    if details.get("has_startup"):
        parts.append(tr("startup"))
    if details.get("bookmarks"):
        parts.append(tr("bookmarks ({count})", count=details["bookmarks"]))
    if details.get("recent"):
        parts.append(tr("recent files ({count})", count=details["recent"]))
    if details.get("total"):
        parts.append(_size_text(int(details["total"])))
    return "  ·  ".join(parts) or tr("Empty")


class _SnapshotRow(QFrame):
    """Fila del gestor de guardados: qué es, qué trae y qué hacer con él.

    Cada acción va en su botón (ver, restaurar, borrar), así que no hay que
    seleccionar una y luego buscar el botón: es un gestor, no una lista de
    opciones.
    """

    def __init__(self, snapshot, details, on_restore, on_delete, on_details,
                 parent=None):
        super().__init__(parent)
        self.snapshot = Path(snapshot)
        # Preferencias leídas de este guardado (o None mientras se analiza).
        self.analysis = None
        self.setObjectName("SnapshotRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        date = bc.snapshot_date(self.snapshot) or self.snapshot.name
        origin = _snapshot_origin(self.snapshot)
        title = QLabel(f"{date}  ·  {origin}")
        title.setToolTip(tr("Saved on {date}. {origin}", date=date,
                            origin=origin))
        title_row.addWidget(title)
        self.badge = QLabel("")
        self.badge.setObjectName("Info")
        title_row.addWidget(self.badge)
        title_row.addStretch()
        info.addLayout(title_row)

        files = QLabel(_snapshot_files_text(details))
        files.setObjectName("Muted")
        files.setWordWrap(True)
        info.addWidget(files)

        self.analysis_label = QLabel("")
        self.analysis_label.setObjectName("Muted")
        self.analysis_label.setWordWrap(True)
        info.addWidget(self.analysis_label)
        lay.addLayout(info, 1)

        self.details_btn = CardButton(
            tr("View settings"),
            tooltip=tr("See the settings this saved copy changes from "
                       "Blender's defaults."))
        self.details_btn.clicked.connect(lambda: on_details(self.snapshot))
        self.details_btn.setEnabled(False)
        lay.addWidget(self.details_btn)

        self.restore_btn = CardButton(
            tr("Restore"), variant="accent",
            tooltip=tr("Put these settings back in Blender."))
        self.restore_btn.clicked.connect(lambda: on_restore(self.snapshot))
        self.restore_btn.setEnabled(bool(details.get("has_userpref")))
        lay.addWidget(self.restore_btn)

        delete = CardButton(tr("Delete"), variant="danger",
                            tooltip=tr("Delete this saved copy for good."))
        delete.clicked.connect(lambda: on_delete(self.snapshot))
        lay.addWidget(delete)

    def add_badge(self, text: str) -> None:
        """Añade una insignia ("más reciente", "más completo") a la fila."""
        current = self.badge.text()
        self.badge.setText(f"{current} · {text}" if current else text)

    def set_unreadable(self) -> None:
        """No se pudo leer ese guardado (Blender falló o no está)."""
        self.analysis = None
        self.analysis_label.setText(
            tr("Could not read this copy's settings."))

    def set_analysis(self, preferences) -> None:
        """Pinta el resumen del análisis (o "Analizando…" si es ``None``)."""
        self.analysis = preferences
        if preferences is None:
            self.analysis_label.setText(tr("Analyzing its settings..."))
            return
        self.details_btn.setEnabled(True)
        if not preferences:
            self.analysis_label.setText(
                tr("No settings changed from Blender's defaults"))
            return
        text = tr("{count} settings changed from Blender's defaults",
                  count=len(preferences))
        sections = _section_names([pref.path for pref in preferences])
        if sections:
            text += "  ·  " + " · ".join(sections)
        self.analysis_label.setText(text)


def _show_snapshot_details(parent, snapshot, preferences) -> None:
    """Diálogo con los ajustes que cambia ese guardado, uno por línea.

    En un scroll: un guardado puede traer decenas de claves y el diálogo no
    puede crecer hasta salirse de la pantalla.
    """
    date = bc.snapshot_date(snapshot) or Path(snapshot).name
    dialog = AppDialog(parent, tr("Saved settings of {date}", date=date),
                       tr("These are the settings this copy changes from "
                          "Blender's defaults."))
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setMaximumHeight(360)
    body = QWidget()
    body.setObjectName("SnapshotDetailsBody")
    body_lay = QVBoxLayout(body)
    body_lay.setContentsMargins(0, 0, 0, 0)
    body_lay.setSpacing(4)
    if not preferences:
        empty = QLabel(tr("No settings changed from Blender's defaults"))
        empty.setObjectName("Muted")
        body_lay.addWidget(empty)
    else:
        for section, items in bprefs.group_by_section(preferences):
            head = QLabel(tr(dict(bprefs.SECTIONS).get(section, section)))
            head.setObjectName("Muted")
            body_lay.addWidget(head)
            for pref in items:
                # La ruta RNA completa con su valor: es lo que permite
                # comprobarlo en Blender sin adivinar.
                line = QLabel(f"{pref.path}  =  {pref.value}")
                line.setWordWrap(True)
                body_lay.addWidget(line)
    body_lay.addStretch()
    scroll.setWidget(body)
    layout = dialog.layout()
    layout.insertWidget(layout.count() - 1, scroll)
    dialog.add_button(tr("Close"), variant="accent", on_click=dialog.accept,
                      tooltip=tr("Close this message."))
    dialog.exec()


class _CornerGrip(QWidget):
    """Esquinita para estirar el panel, abajo a la derecha.

    Sustituye a la barra horizontal que había antes: se agarra desde la esquina
    (donde todo el mundo busca el redimensionado) y no ocupa ninguna fila. Solo
    manda el desplazamiento vertical; el ancho lo fija el layout.
    """

    SIZE = 14

    def __init__(self, on_resize, tooltip: str = "", parent=None):
        super().__init__(parent)
        self._on_resize = on_resize
        self._last = None
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.SizeFDiagCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def paintEvent(self, event) -> None:
        # Tres rayitas diagonales, como el grip clásico; se encienden al pasar
        # el ratón para que se vea que se puede arrastrar.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(t.ACCENT if self.underMouse() else t.MUTED)
        painter.setPen(QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap))
        edge = self.SIZE - 1
        for offset in (4, 7, 10):
            painter.drawLine(edge - offset, edge, edge, edge - offset)
        painter.end()

    def mousePressEvent(self, event) -> None:
        self._last = event.globalPosition().y()

    def mouseMoveEvent(self, event) -> None:
        if self._last is None:
            return
        # Posición **global**: la esquinita se mueve con el panel al crecer, así
        # que la local daría un salto en cada fotograma.
        current = event.globalPosition().y()
        self._on_resize(int(current - self._last))
        self._last = current

    def mouseReleaseEvent(self, event) -> None:
        self._last = None


class _ResizableScroll(QScrollArea):
    """``QScrollArea`` con una esquinita para estirarlo desde abajo a la derecha.

    Qt no deja redimensionar un scroll arrastrando su borde y con el alto fijo
    el usuario se queda con las filas que quepan. La esquinita va **dentro** del
    scroll, pegada a su esquina inferior derecha, y avisa del desplazamiento;
    quien la usa decide el alto (``setFixedHeight``).
    """

    def __init__(self, on_resize, tooltip: str = "", parent=None):
        super().__init__(parent)
        self._grip = _CornerGrip(on_resize, tooltip, self)
        self._grip.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._grip.move(self.width() - self._grip.width(),
                        self.height() - self._grip.height())
        self._grip.raise_()


class _BoardRow(QFrame):
    """Base de las filas del tablero.

    Las dos columnas tienen que cuadrar una con otra (misma altura, mismo rayado
    cebra), así que ese preámbulo está aquí una sola vez: si una fila creciera
    sin la otra, al cambiar de versión el tablero quedaría desalineado.
    """

    def __init__(self, plan, zebra: bool, parent=None):
        super().__init__(parent)
        self.plan = plan
        self.setObjectName("AddonRow")
        self.setProperty("zebra", "true" if zebra else "false")
        self.setFixedHeight(ROW_HEIGHT)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(8)
        self.row_layout = lay


class _SourceRow(_BoardRow):
    """Fila del origen: casilla, nombre, versión y veredicto."""

    changed = Signal()

    def __init__(self, plan, zebra: bool, parent=None):
        super().__init__(plan, zebra, parent)
        lay = self.row_layout

        self.check = CheckPill()
        self.check.setChecked(plan.selected)
        # Lo que no es compatible no se puede marcar: nunca se copia sin querer.
        self.check.setEnabled(not plan.blocked)
        self.check.setToolTip(
            _status_tooltip(plan) if plan.blocked
            else tr("Tick to include this add-on in the copy."))
        self.check.toggled.connect(self._on_toggled)
        lay.addWidget(self.check)

        text = QVBoxLayout()
        text.setSpacing(1)
        name = ElidedLabel(plan.addon.name, Qt.ElideRight)
        name.setObjectName("Title")
        text.addWidget(name)
        meta = ElidedLabel(_meta_text(plan.addon), Qt.ElideRight)
        meta.setObjectName("Muted")
        text.addWidget(meta)
        lay.addLayout(text, 1)

        obj, label = _STATUS.get(plan.status, ("Muted", "Review"))
        status = QLabel(tr(label))
        status.setObjectName(obj)
        # El tooltip va en el distintivo (donde pone "Review") y en la fila: al
        # pasar el ratón por el texto amarillo se explica qué hay que revisar y
        # cómo. Es lo que pide cualquiera que vea "Review" y no sepa qué hacer.
        tooltip = _status_tooltip(plan)
        if tooltip:
            status.setToolTip(tooltip)
            self.setToolTip(tooltip)
        lay.addWidget(status)

    def _on_toggled(self, checked: bool) -> None:
        self.plan.selected = checked
        self.changed.emit()

    def set_checked(self, checked: bool) -> None:
        """Marca o desmarca respetando las bloqueadas."""
        self.check.setChecked(bool(checked) and not self.plan.blocked)


class _DestRow(_BoardRow):
    """Fila del destino: dónde caerá ese addon."""

    def __init__(self, plan, zebra: bool, parent=None):
        super().__init__(plan, zebra, parent)
        label = ElidedLabel(_destination_text(plan), Qt.ElideMiddle)
        label.setObjectName("Muted" if plan.blocked else "Info")
        if plan.blocked:
            tip = tr("This add-on is not copied, so nothing changes here.")
        else:
            tip = tr("Where it lands on the destination side: {path}",
                     path=plan.destination)
        label.setToolTip(tip)
        self.setToolTip(tip)
        self.row_layout.addWidget(label, 1)


class MigrateView(QWidget):
    """Pantalla para copiar addons de una versión instalada a otra."""

    status_message = Signal(str)
    activation_done = Signal(object)
    prefs_loaded = Signal(object)      # {"user", "factory", "error"}
    prefs_applied = Signal(object)     # {"result", "version"}
    source_read = Signal(object)       # {"version", "enabled", "error"}
    snapshots_analyzed = Signal(object)  # {"version", "results", "live"}
    snapshot_keep_changed = Signal(int)  # cuántas copias guardadas conservar

    def __init__(self, parent=None):
        super().__init__(parent)
        # objectName para el QSS (fondo gris unificado y tarjetas por encima).
        self.setObjectName("MigrateView")
        # Una SUBCLASE de QWidget no pinta el fondo que le pone el QSS salvo que
        # se active esto. Sin ello, el gris de la vista no se dibujaba y la zona
        # de la fila de pestañas a la derecha de las solapas quedaba con el
        # oscuro de detrás.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.platform = ""
        self.arch = ""
        self.installed = []
        self._choices = []
        self.source_cfg = None
        self.target_cfg = None
        self.source_entry = None
        self.target_entry = None
        self.plans = []
        self.pref_items = []
        self._rows = []
        # True solo mientras hay una activación pedida por el usuario. La señal
        # ``activation_done`` es pública y un evento diferido podría emitirla sin
        # que nadie esté esperando; sin esta guarda se abriría un diálogo modal
        # de la nada (le pasó al suite: un ``QTest.qWait`` procesaba el evento y
        # el modal bloqueaba las pruebas).
        self._activating = False
        self._prefs_loading = False
        # True solo mientras hay una lectura/aplicación pedida por el usuario.
        # Las señales ``prefs_loaded``/``prefs_applied`` son públicas y un evento
        # diferido podría emitirlas sin que nadie espere: sin esta guarda se
        # abriría un diálogo modal de la nada (le pasó al suite con QTest.qWait).
        self._prefs_waiting = False
        # Lectura automática del origen: guarda para qué versión se hizo, para
        # no repetir el arranque de Blender mientras no cambie el origen.
        self._source_read_for = ""
        self._source_reading = False
        self.source_enabled = set()
        self.detail_prefs = []
        self.detail_checks = []
        # Alto elegido a mano con el asa (None = el del contenido, con tope).
        self._detail_height = None
        self._snapshot_height = None
        # Gestor de guardados: filas por instantánea, análisis cacheado y
        # bandera de "ya se está analizando" (un arranque de Blender por fila).
        self._snapshot_widgets = {}
        self._analysis = {}
        self._analyzed_for = ""
        self._snapshots_waiting = False
        self._factory_live_count = None
        # Cuántas copias guardadas se conservan (lo fija MainWindow desde los
        # ajustes; aquí se usa al crear o restaurar una).
        self.snapshot_keep = 5
        self._build_ui()
        self.activation_done.connect(self._on_activation_done)
        self.prefs_loaded.connect(self._on_prefs_loaded)
        self.prefs_applied.connect(self._on_prefs_applied)
        self.source_read.connect(self._on_source_read)
        self.snapshots_analyzed.connect(self._on_snapshots_analyzed)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        """Estructura de la pantalla, calcada de Ajustes.

        Las **pestañas van arriba del todo** (a la misma altura que las de
        canal de Tienda/Instaladas) y el contenido debajo, sobre el mismo fondo
        oscuro que las listas; las tarjetas quedan un escalón por encima. Antes
        había una cabecera propia y toda la vista iba del gris de panel: era la
        única pantalla con el fondo claro.

        La tarjeta **origen → destino** es común a Add-ons y Preferences, así que
        hay una sola y se mueve a la pestaña visible (``_show_header``). La
        pestaña de fábrica **no migra nada**, así que lleva su propia tarjeta
        con un solo desplegable: allí un "Desde" y un "Hacia" hacían creer que
        la operación usaba los dos, cuando solo actúa sobre uno.

        * **Add-ons**: el tablero y el botón de copiar lo seleccionado.
        * **Preferences**: primero lo fino (ajustes uno a uno) y luego los
          ficheros completos.
        * **Factory settings**: una versión, que se restablece o se recupera.
        """
        root = QVBoxLayout(self)
        # Sin margen: las pestañas van **a sangre** (el canvas llega hasta la
        # barra lateral, el borde derecho y la barra de estado). El padding va
        # dentro de cada pestaña, no aquí.
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = self._build_header()
        self.factory_header = self._build_factory_header()

        self.tabs = QTabWidget()
        self.tabs.setObjectName("MigrateTabs")
        self.tabs.addTab(self._build_addons_tab(), tr("Add-ons"))
        self.tabs.addTab(self._build_preferences_tab(), tr("User prefs"))
        self.factory_page = self._build_factory_tab()
        self.tabs.addTab(self.factory_page, tr("Factory settings"))
        # Misma alineación que Ajustes: el QTabWidget dibuja su barra arriba del
        # todo, así que la vista baja lo que la fila mida de menos que la de
        # filtros y las dos terminan a la misma altura al cambiar de pantalla.
        # ``ensurePolished`` mide con el QSS ya aplicado (sin él la fila sale
        # un par de píxeles más alta).
        self.tabs.tabBar().ensurePolished()
        bar_height = self.tabs.tabBar().sizeHint().height()
        root.setContentsMargins(0, max(0, t.FILTERS_HEIGHT - bar_height), 0, 0)
        root.addWidget(self.tabs, 1)

        self.tabs.currentChanged.connect(self._show_header)
        self._show_header(self.tabs.currentIndex())

        self._set_controls_enabled(False)

    def _build_header(self) -> QWidget:
        """Bloque común a las tres pestañas: versiones y aviso de Blender abierto.

        Es **un solo widget** que se reparenta a la pestaña visible: con una
        copia por pestaña habría tres pares de desplegables que mantener en
        sincronía, y el origen/destino es uno para toda la pantalla.
        """
        header = QWidget()
        header.setObjectName("MigrateHeader")
        lay = QVBoxLayout(header)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(self._build_version_bar())

        self.warning = QLabel("")
        self.warning.setObjectName("Danger")
        self.warning.setWordWrap(True)
        self.warning.setVisible(False)
        lay.addWidget(self.warning)
        return header

    def _build_factory_header(self) -> QWidget:
        """Cabecera de la pestaña de fábrica: una sola versión.

        No es la barra origen → destino: en fábrica no hay copia, solo una
        versión que se restablece (o cuyos ajustes guardados se recuperan). Con
        dos desplegables parecía que la operación usaba el "Hacia" y el "Desde"
        a la vez, y el usuario no sabía cuál mandaba.
        """
        header = QWidget()
        header.setObjectName("MigrateHeader")
        lay = QVBoxLayout(header)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        card, card_lay = _settings_card()
        card.setToolTip(tr(
            "Pick the version whose settings you want to reset or put back."))
        column = QVBoxLayout()
        column.setSpacing(4)
        label = QLabel(tr("Version"))
        label.setToolTip(tr("The version whose settings are reset or restored."))
        column.addWidget(label)
        self.factory_combo = QComboBox()
        self.factory_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.factory_combo.setMinimumWidth(150)
        self.factory_combo.setToolTip(tr(
            "The version whose settings are reset or restored."))
        self.factory_combo.currentIndexChanged.connect(
            lambda _: self._on_factory_version())
        column.addWidget(self.factory_combo)
        self.factory_path_label = QLabel("")
        self.factory_path_label.setWordWrap(True)
        self.factory_path_label.setToolTip(tr(
            "Folder with the settings of this version. This is the one that "
            "gets reset or put back."))
        column.addWidget(self.factory_path_label)
        card_lay.addLayout(column)
        lay.addWidget(card)

        self.factory_warning = QLabel("")
        self.factory_warning.setObjectName("Danger")
        self.factory_warning.setWordWrap(True)
        self.factory_warning.setVisible(False)
        lay.addWidget(self.factory_warning)
        return header

    def _on_factory_version(self) -> None:
        """Cambió la versión de la pestaña de fábrica: refresca su estado.

        Se tira el análisis y el resumen porque son de otra versión: los
        guardados que se enseñan ahora son otros.
        """
        self._analysis = {}
        self._analyzed_for = ""
        self._factory_live_count = None
        self._refresh_factory()
        self._check_running(self._factory_entry(), self.factory_warning)

    def _show_header(self, index: int) -> None:
        """Mueve a la pestaña visible la tarjeta de versiones que le toca.

        Add-ons y Preferences comparten la barra origen → destino; fábrica usa su
        propio selector de una versión (``_build_factory_header``). La que no se
        usa se desparenta y se oculta, para que no quede por debajo.
        """
        page = self.tabs.widget(index)
        is_factory = page is self.factory_page
        header = self.factory_header if is_factory else self.header
        other = self.header if is_factory else self.factory_header
        # Sacar la que no toca (``removeWidget`` no la desparenta, así que hay
        # que insertarla de nuevo al volver: no basta con mirar el padre).
        old_other = other.parentWidget()
        if old_other is not None and old_other.layout() is not None:
            old_other.layout().removeWidget(other)
        other.hide()
        if page is not None:
            old = header.parentWidget()
            if old is not None and old.layout() is not None:
                old.layout().removeWidget(header)
            # ``insertWidget`` reparenta: la tarjeta pasa a ser hija de la
            # página nueva y se dibuja arriba del todo, encima del contenido.
            page.layout().insertWidget(0, header)
        header.show()
        if is_factory:
            self._refresh_factory()
            self._check_running(self._factory_entry(), self.factory_warning)

    def _new_page(self) -> tuple:
        """Página de una pestaña con los márgenes de Ajustes (``(page, lay)``).

        El hueco de arriba lo ocupa la tarjeta de versiones, que se inserta en
        la posición 0 al abrir la pestaña.
        """
        page = QWidget()
        page.setObjectName("MigratePage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)
        return page, lay

    def _build_version_bar(self) -> QFrame:
        """Tarjeta superior: de qué versión a qué versión (común a las pestañas).

        Va en una tarjeta como el resto: sobre el fondo oscuro de la ventana, un
        desplegable —que también es oscuro— no se distingue. Cada columna lleva
        su etiqueta y, debajo, la ruta real de esa config: es lo que deja claro
        *dónde* se va a escribir, sobre todo con las LTS en otro disco o una
        config movida con ``BLENDER_USER_CONFIG``.
        """
        card, lay = _settings_card()
        card.setToolTip(tr(
            "Pick a source and a destination version here, then use the tabs "
            "to copy add-ons, individual settings or the whole preferences "
            "file."))
        bar = QHBoxLayout()
        bar.setSpacing(10)

        def column(title: str, tip: str, path_tip: str):
            # Etiqueta y ruta en el color de texto normal (como los rótulos de
            # las opciones en Ajustes): en Muted sobre la tarjeta clara se
            # quedaban en 3,7:1 y costaba leerlas.
            column = QVBoxLayout()
            column.setSpacing(4)
            label = QLabel(title)
            label.setToolTip(tip)
            column.addWidget(label)
            combo = self._version_combo(tip)
            column.addWidget(combo)
            path = QLabel("")
            path.setWordWrap(True)
            path.setToolTip(path_tip)
            column.addWidget(path)
            return column, combo, path

        left, self.source_combo, self.source_path_label = column(
            tr("From"), tr("Version you are copying the add-ons and settings "
                           "from."),
            tr("Folder with the settings and add-ons of the source version. It "
               "is only read, never written."))
        bar.addLayout(left, 1)
        arrow = QLabel(icons.ARROW_RIGHT)
        arrow.setFont(icon_font(16))
        arrow.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        arrow.setToolTip(tr("The add-ons and settings selected on the left are "
                            "copied to the version on the right."))
        bar.addWidget(arrow)
        right, self.target_combo, self.target_path_label = column(
            tr("To"), tr("Version you are copying the add-ons and settings to."),
            tr("Folder with the settings and add-ons of the destination "
               "version. This is where the copy writes; what exists there is "
               "kept as a backup."))
        bar.addLayout(right, 1)
        lay.addLayout(bar)
        return card

    def _build_addons_tab(self) -> QWidget:
        """Pestaña de addons: tablero, resumen y explicación, en ese orden.

        El resumen y la explicación van **debajo** del tablero y **dentro** de
        la pestaña: así no comparten altura con las otras pestañas y no hacen
        saltar la interfaz al cambiar de una a otra (que es lo que pasaba
        teniéndolos en la tarjeta de versiones).
        """
        page, lay = self._new_page()

        # El tablero es un layout DIRECTAMENTE en la página (sin un QWidget que
        # lo envuelva): un contenedor ajustado al tamaño de las tarjetas
        # **recorta su sombra** (QGraphicsDropShadowEffect no puede pintar fuera
        # del padre). Con la página grande de padre, la sombra cae en el hueco y
        # se ve. Además así las tarjetas no se estiran a lo alto: miden lo que
        # miden sus filas.
        board_lay = QHBoxLayout()
        board_lay.setContentsMargins(0, 0, 0, 0)
        board_lay.setSpacing(14)
        self.left_card, self.left_title, self.left_rows = self._board_column(
            tr("Source"), None,
            tr("Add-ons installed in the version you are copying from. Tick "
               "the ones you want in the destination version."))
        self.right_card, self.right_title, self.right_rows = self._board_column(
            tr("Destination"), None,
            tr("Where each add-on lands in the destination version. Add-ons "
               "that were enabled in the source are enabled here too."))
        board_lay.addWidget(self.left_card, 1)
        board_lay.addLayout(self._arrow_column(), 0)
        board_lay.addWidget(self.right_card, 1)
        lay.addLayout(board_lay)

        # Los botones van pegados a las tarjetas (debajo), y el resumen y la
        # explicación quedan debajo de ellos: primero actuar, luego el detalle.
        actions = QHBoxLayout()
        self.select_all_btn = CardButton(
            tr("Select all"),
            tooltip=tr("Tick every add-on that can be copied. The ones marked "
                       "\"Not compatible\" cannot be ticked."))
        self.select_all_btn.clicked.connect(lambda: self._select_all(True))
        self.select_none_btn = CardButton(
            tr("Select none"),
            tooltip=tr("Untick them all, to copy nothing."))
        self.select_none_btn.clicked.connect(lambda: self._select_all(False))
        actions.addWidget(self.select_all_btn)
        actions.addWidget(self.select_none_btn)
        actions.addStretch()
        self.copy_btn = _accent_button(
            tr("Copy selected"),
            tr("Copy the ticked add-ons to the destination version and enable "
               "the ones that were enabled in the source."),
            self.apply)
        actions.addWidget(self.copy_btn)
        lay.addLayout(actions)

        # El resumen y la explicación, en color de texto normal: son datos y
        # ayuda que hay que leer, y en Muted sobre el gris quedaban apagados.
        self.summary = QLabel("")
        self.summary.setToolTip(tr(
            "How many add-ons were found, how many are compatible, how many "
            "you should review and how many cannot be copied."))
        lay.addWidget(self.summary)

        for text in (
            "Copy the add-ons (and extensions) of one installed version to "
            "another, checking first whether they are compatible.",
            # No hay interruptor de "activar tras copiar": el estado se imita
            # del origen (lo activado se activa, lo apagado se queda apagado).
            "Add-ons keep the state they had in the source: the ones that were "
            "enabled there are enabled here too.",
        ):
            label = QLabel(tr(text))
            label.setWordWrap(True)
            lay.addWidget(label)

        # El estirón al final deja la página más alta que las tarjetas: es el
        # hueco donde cae su sombra (y evita que se estiren a lo alto).
        lay.addStretch()
        return page

    def _build_preferences_tab(self) -> QWidget:
        """Pestaña de preferencias: primero el detalle fino, luego los ficheros.

        El detalle va arriba porque es lo recomendado (ajustes sueltos, sin
        pisar todo); el fichero completo es el atajo que reemplaza el
        ``userpref.blend`` entero, y por eso queda debajo.
        """
        page, lay = self._new_page()
        lay.addWidget(self._build_detail_prefs())
        lay.addWidget(self._build_preferences())
        lay.addStretch()
        return page

    def _build_factory_tab(self) -> QWidget:
        """Pestaña de valores de fábrica: reset, recuperar y borrar.

        Va en su propia pestaña porque es una operación distinta (no migra
        nada; deja la versión destino limpia) y así no se mezcla con la
        migración de ajustes. El reset es reversible desde aquí mismo.
        """
        page, lay = self._new_page()
        lay.addWidget(self._build_factory())
        lay.addStretch()
        return page

    def _version_combo(self, tooltip: str) -> QComboBox:
        """Desplegable de versión instalada (en la barra superior)."""
        combo = QComboBox()
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setMinimumWidth(150)
        combo.setToolTip(tooltip)
        combo.currentIndexChanged.connect(lambda _: self._reload())
        return combo

    def _board_column(self, title: str, combo: QComboBox | None,
                      tooltip: str = ""):
        """Una columna del tablero: título (y combo opcional) y hueco de filas.

        Comparte el ``SettingsCard`` con las demás tarjetas, pero con menos
        margen que ``_settings_card``: el tablero va a dos columnas y con los
        16 px de las tarjetas de texto las filas se quedaban estrechas.

        ``combo`` es opcional porque el selector de versiones vive en la barra
        superior (es común a las dos pestañas); se admite aquí por si alguna
        vista futura quiere el suyo en cada columna.
        """
        card = QFrame()
        card.setObjectName("SettingsCard")
        card_shadow(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        header = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("Muted")
        if tooltip:
            label.setToolTip(tooltip)
        header.addWidget(label)
        if combo is not None:
            header.addWidget(combo, 1)
        lay.addLayout(header)
        rows = QVBoxLayout()
        rows.setSpacing(4)
        lay.addLayout(rows)
        lay.addStretch()
        return card, label, rows

    def _arrow_column(self):
        """Columna central: la flecha (un solo sentido) del tablero."""
        column = QVBoxLayout()
        column.addStretch()
        arrow = QLabel(icons.ARROW_RIGHT)
        arrow.setFont(icon_font(28))
        arrow.setAlignment(Qt.AlignHCenter)
        arrow.setToolTip(tr("The ticked add-ons are copied from left to right. "
                            "Nothing is moved: the source version stays as it "
                            "is."))
        column.addWidget(arrow)
        column.addStretch()
        return column

    def _build_preferences(self) -> QFrame:
        """Tarjeta para migrar las preferencias (ficheros de ``config``).

        Va aparte del tablero porque es otra cosa: aquí no hay addons ni
        manifiestos, son ficheros de Blender y el usuario decide si los pisa.
        """
        card, lay = _settings_card("Preferences file")
        hint = QLabel(tr(
            "Copy the preferences file of the source version. It replaces the "
            "current one (a backup is kept)."))
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.pref_checks = {}
        self.pref_rows = QVBoxLayout()
        self.pref_rows.setSpacing(4)
        lay.addLayout(self.pref_rows)

        warning = QLabel(tr(
            "The startup file replaces your default scene and interface. "
            "Leave it off unless you know what it does."))
        warning.setObjectName("Warning")
        warning.setWordWrap(True)
        lay.addWidget(warning)

        self.pref_warning = QLabel("")
        self.pref_warning.setObjectName("Danger")
        self.pref_warning.setWordWrap(True)
        self.pref_warning.setVisible(False)
        lay.addWidget(self.pref_warning)

        self.copy_prefs_btn = _accent_button(
            tr("Copy preferences"), tr("Copy the selected preference files."),
            self.apply_preferences)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self._undo_button())
        row.addWidget(self.copy_prefs_btn)
        lay.addLayout(row)
        return card

    def _build_detail_prefs(self) -> QFrame:
        """Tarjeta de preferencias selectivas (una a una, comparadas con fábrica).

        Es la parte "fina": en vez de copiar el ``userpref.blend`` entero,
        pregunta al Blender origen qué cambió respecto a los valores de fábrica
        y deja marcar cada cambio. La lectura es **automática** al elegir la
        versión de origen (arranca Blender una vez); el botón solo sirve para
        reintentarla si algo falló.
        """
        card, lay = _settings_card("Preferences in detail")
        hint = QLabel(tr(
            "Pick individual settings changed from Blender's defaults. They are "
            "read automatically from the source version (it starts once, it may "
            "take a moment)."))
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.detail_status = QLabel("")
        self.detail_status.setWordWrap(True)
        lay.addWidget(self.detail_status)

        # Las claves van en su propia área de scroll con alto tope (ver
        # ``DETAIL_SCROLL_HEIGHT``). Los botones quedan **fuera**, como en la
        # biblioteca de carpetas: así no hay que bajar hasta el final de una
        # lista larguísima para pulsarlos.
        self.detail_scroll = _ResizableScroll(
            self._resize_detail,
            tooltip=tr("Drag the bottom-right corner to make the settings list "
                       "taller or shorter."))
        self.detail_scroll.setObjectName("DetailPrefs")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_scroll.setMaximumHeight(DETAIL_SCROLL_HEIGHT)
        # El scroll y su contenido transparentes: el fondo lo pone la tarjeta,
        # y un QScrollArea pinta el suyo por defecto (se vería un rectángulo).
        body = QWidget()
        body.setObjectName("DetailPrefsBody")
        self.detail_rows = QVBoxLayout(body)
        self.detail_rows.setContentsMargins(0, 0, 0, 0)
        self.detail_rows.setSpacing(4)
        self.detail_scroll.setWidget(body)
        self.detail_scroll.setVisible(False)
        lay.addWidget(self.detail_scroll)

        row = QHBoxLayout()
        self.detail_load_btn = CardButton(
            tr("Read again"),
            tooltip=tr("Read the settings from the source version again."))
        self.detail_load_btn.clicked.connect(lambda: self.read_source(force=True))
        row.addWidget(self.detail_load_btn)
        row.addStretch()
        self.detail_select_all = CardButton(
            tr("Select all"),
            tooltip=tr("Tick every setting listed below."))
        self.detail_select_all.clicked.connect(
            lambda: self._select_detail(True))
        self.detail_select_none = CardButton(
            tr("Select none"),
            tooltip=tr("Untick them all, to migrate no setting."))
        self.detail_select_none.clicked.connect(
            lambda: self._select_detail(False))
        row.addWidget(self.detail_select_all)
        row.addWidget(self.detail_select_none)
        self.detail_apply_btn = _accent_button(
            tr("Apply to destination"),
            tr("Write the selected settings in the destination version."),
            self.apply_detail_prefs)
        row.addWidget(self.detail_apply_btn)
        lay.addLayout(row)
        self._show_detail_buttons(False)
        return card

    def _show_detail_buttons(self, loaded: bool) -> None:
        for widget in (self.detail_select_all, self.detail_select_none,
                       self.detail_apply_btn):
            widget.setEnabled(loaded)
        self.detail_load_btn.setEnabled(True)

    def _clear_detail_rows(self) -> None:
        self.detail_checks = []
        _clear_layout(self.detail_rows)
        # Sin filas no se enseña el área: un hueco vacío con su barra (y su
        # esquinita) quedaría raro cuando aún no se ha leído nada.
        if hasattr(self, "detail_scroll"):
            self.detail_scroll.setVisible(False)

    def _clamp_height(self, height: int, minimum: int) -> int:
        """Alto de un panel: ni por debajo del mínimo ni más alto que la ventana."""
        maximum = max(minimum, self.height() - 220)
        return max(minimum, min(int(height), maximum))

    def _resize_detail(self, delta: int) -> None:
        """Arrastró el asa de la lista de claves: fija el alto elegido."""
        self._detail_height = self._clamp_height(
            self.detail_scroll.height() + delta, DETAIL_MIN_HEIGHT)
        self.detail_scroll.setFixedHeight(self._detail_height)

    def _resize_snapshots(self, delta: int) -> None:
        """Arrastró el asa de la lista de guardados: fija el alto elegido."""
        self._snapshot_height = self._clamp_height(
            self.snapshot_scroll.height() + delta, SNAPSHOT_MIN_HEIGHT)
        self.snapshot_scroll.setFixedHeight(self._snapshot_height)

    def _source_usable(self) -> bool:
        """True si el origen tiene un ejecutable real con el que preguntarle."""
        executable, _ = _entry_info(self.source_entry)
        return bool(executable) and Path(executable).is_file()

    def read_source(self, force: bool = False) -> None:
        """Lee el estado del origen (addons activos + preferencias) en un hilo.

        Se llama **sola** al cambiar de versión (el usuario no tiene que pulsar
        nada): solo arranca Blender una vez por origen y, si ya se leyó esa
        misma versión, no repite el trabajo. ``force`` rehace la lectura.

        Se hace todo en un arranque para que cambiar de versión cueste un solo
        Blender, no dos.
        """
        if self._source_reading or self.source_entry is None:
            return
        version = getattr(self.source_entry, "version", "")
        if not force and version == self._source_read_for:
            return
        if not self._source_usable():
            self.detail_status.setText(
                tr("The source version has no executable to read."))
            self._show_detail_buttons(False)
            self._clear_detail_rows()
            return
        executable, _ = _entry_info(self.source_entry)
        self._source_reading = True
        self._prefs_loading = True
        self._prefs_waiting = True
        self.detail_load_btn.setEnabled(False)
        # Se vacía lo que hubiera: mientras se lee, una lista de la lectura
        # anterior haría creer que esos siguen siendo los ajustes de ahora.
        self.detail_prefs = []
        self._clear_detail_rows()
        self.detail_status.setText(tr("Reading settings..."))

        def worker():
            try:
                enabled = blender_runner.enabled_addons(executable)
                user = bprefs.read_preferences(executable)
                factory = bprefs.read_preferences(executable, factory=True)
            except Exception as error:  # noqa: BLE001
                self.source_read.emit({"version": version, "error": str(error)})
                self.prefs_loaded.emit({"error": str(error)})
                return
            self.source_read.emit({"version": version, "enabled": enabled})
            self.prefs_loaded.emit({"user": user, "factory": factory})

        threading.Thread(target=worker, daemon=True).start()

    def _on_source_read(self, payload) -> None:
        """Aplica el estado activado/desactivado del origen al plan."""
        self._source_reading = False
        version = payload.get("version") or ""
        if payload.get("enabled") is not None:
            self._source_read_for = version
            self.source_enabled = {bc.addon_id_of(name)
                                   for name in payload["enabled"]}
        # Recalcula el plan con el estado real (marca ``was_enabled``).
        if self.source_cfg is not None and self.target_cfg is not None:
            self._rebuild_plan()
        self._refresh_plan_status()

    def _rebuild_plan(self) -> None:
        """Recalcula el plan de addons con el estado activado del origen."""
        python = bc.python_for_version(self.target_entry.version)
        self.plans = bc.plan_migration(
            self.source_cfg, self.target_cfg, self.platform, self.arch, python,
            enabled_ids=self.source_enabled)
        self._fill_board()

    def _refresh_plan_status(self) -> None:
        """Resume en una línea cuántos addons quedan por copiar."""
        if not self.plans:
            return
        active = sum(1 for plan in self.plans if plan.was_enabled)
        self.detail_status.setText(tr(
            "{changed} settings changed from Blender's defaults · {active} "
            "add-ons enabled in the source.",
            changed=len(self.detail_prefs), active=active))

    def _on_prefs_loaded(self, payload) -> None:
        if not self._prefs_waiting:
            return
        self._prefs_waiting = False
        self._prefs_loading = False
        self.detail_load_btn.setEnabled(True)
        if payload.get("error") or not payload.get("user"):
            self.detail_prefs = []
            self._clear_detail_rows()
            self.detail_status.setText(tr("Could not read the settings."))
            self._show_detail_buttons(False)
            return
        changed = bprefs.diff(payload["user"], payload["factory"])
        env = bprefs.environment_preferences(payload["user"], payload["factory"])
        self.detail_prefs = changed + env
        if not self.detail_prefs:
            # Decir solo "no has cambiado nada" despista cuando el motivo es
            # que la propia aplicación restableció esa versión: el usuario sabe
            # que SÍ tenía ajustes y cree que el detector falla. Si hay una
            # instantánea, se dice de dónde viene y cómo recuperarlos. Y la
            # lista se **vacía**: sin esto quedaban las casillas de la lectura
            # anterior y parecía que aún detectaba aquellos ajustes.
            self._clear_detail_rows()
            self.detail_status.setText(self._no_changes_message())
            self._show_detail_buttons(False)
            return
        self._fill_detail_rows()
        self._show_detail_buttons(True)
        self._refresh_plan_status()

    def _no_changes_message(self) -> str:
        """Por qué no hay nada que copiar, con la causa cuando la sabemos.

        Si hay instantáneas con ajustes es que la app restableció esa versión
        (o el usuario lo hizo desde aquí) y sus ajustes están aparte. Se dice
        **de qué versión** son y dónde se recuperan: la pestaña "Valores de
        fábrica" tiene su propio selector, así que hay que decir que se elija
        esa versión allí, o el usuario la abre con otra y no encuentra nada
        (fue su confusión).
        """
        base = tr("You have no settings changed from Blender's defaults.")
        config = self.source_cfg
        snapshots = bc.snapshots_for(config) if config is not None else []
        if not snapshots:
            return base
        _, version = _entry_info(self.source_entry)
        return base + " " + tr(
            "This app has the settings of Blender {version} saved aside from a "
            "previous reset. To put them back, open the \"Factory settings\" "
            "tab and pick Blender {version} there.", version=version)

    def _fill_detail_rows(self) -> None:
        self._clear_detail_rows()
        self.detail_checks = []
        self.detail_scroll.setVisible(True)
        for section, items in bprefs.group_by_section(self.detail_prefs):
            label = tr(dict(bprefs.SECTIONS).get(section, section))
            header = QLabel(label)
            header.setObjectName("Muted")
            self.detail_rows.addWidget(header)
            for pref in items:
                check = CheckPill(f"{pref.label}  =  {pref.value}")
                check.setChecked(pref.selected)
                # El nombre a secas no dice de dónde sale: la ruta RNA completa
                # en el tooltip es lo que permite comprobarlo en Blender.
                tip = pref.path
                if not pref.selected and bprefs.is_environment(pref.path):
                    tip += "\n\n" + tr(
                        "This depends on your computer, not on your settings. "
                        "Leave it off unless it is the same machine.")
                check.setToolTip(tip)
                check.toggled.connect(
                    lambda checked, p=pref: setattr(p, "selected", checked))
                self.detail_rows.addWidget(check)
                self.detail_checks.append(check)
        # Alto al contenido, con tope: pocas claves no dejan un hueco vacío y
        # muchas no empujan los botones fuera. Se suma el ``sizeHint`` de cada
        # fila a mano porque el del layout (``sizeHint`` con activación) da 0
        # mientras el scroll aún mide 0: la restricción de alto se contagia.
        content = 0
        for index in range(self.detail_rows.count()):
            widget = self.detail_rows.itemAt(index).widget()
            if widget is not None:
                content += widget.sizeHint().height()
        content += self.detail_rows.spacing() * max(
            0, self.detail_rows.count() - 1)
        # Alto: el que el usuario haya elegido con el asa o, si no, el del
        # contenido con tope. ``setFixedHeight`` porque el layout de la página
        # tiene un ``addStretch`` que, si no, se queda el hueco y deja el scroll
        # en su mínimo.
        height = self._detail_height or min(content, DETAIL_SCROLL_HEIGHT)
        self.detail_scroll.setFixedHeight(max(DETAIL_MIN_HEIGHT, height))
        # Con una lista nueva, al principio (si no, hereda la posición anterior).
        self.detail_scroll.verticalScrollBar().setValue(0)

    def _select_detail(self, checked: bool) -> None:
        for pref in self.detail_prefs:
            pref.selected = checked
        for check in getattr(self, "detail_checks", []):
            check.setChecked(checked)

    def apply_detail_prefs(self) -> None:
        """Aplica las claves marcadas en el Blender destino."""
        executable, version = _entry_info(self.target_entry)
        if not executable or not Path(executable).is_file():
            self.detail_status.setText(
                tr("The destination version has no executable to write."))
            return
        selected = [p for p in self.detail_prefs if p.selected]
        if not selected:
            self.status_message.emit(tr("Nothing selected"))
            return
        if self._blocked_by_running():
            return
        self.detail_status.setText(tr("Applying settings..."))
        self._prefs_waiting = True

        def worker():
            result = bprefs.apply_preferences(executable, selected)
            self.prefs_applied.emit({"result": result, "version": version})

        threading.Thread(target=worker, daemon=True).start()

    def _on_prefs_applied(self, payload) -> None:
        if not self._prefs_waiting:
            return
        self._prefs_waiting = False
        result = payload.get("result") or {}
        version = payload.get("version") or ""
        applied = result.get("applied") or []
        errors = result.get("errors") or []
        lines = [tr("Applied {count} settings to Blender {version}.",
                    count=len(applied), version=version)]
        if not applied:
            lines = [tr("No settings were applied.")]
        if errors:
            lines.append("")
            lines.append(tr("These settings no longer exist in this version:"))
            for item in errors[:12]:
                path = item.get("path") or "Blender"
                lines.append(f"· {path}")
        show_info(self, tr("Settings applied"), "\n".join(lines))
        self.status_message.emit(tr("Settings applied"))
        self.detail_status.setText(tr("Applied {count} settings to Blender "
                                      "{version}.", count=len(applied),
                                      version=version))

    def _build_factory(self) -> QFrame:
        """Tarjeta-gestor de los ajustes guardados de esa versión.

        Cada guardado es una fila con su fecha, de qué es, qué trae y qué
        ajustes cambia (eso último se lee en segundo plano), con botones para
        verlos, restaurarlo o borrarlo. El reset sigue siendo una acción aparte.
        """
        # Sin título dentro: la pestaña ya se llama "Factory settings". El
        # texto se rellena en ``_refresh_factory`` porque nombra la versión
        # destino, que el usuario puede cambiar en la barra de arriba.
        card, lay = _settings_card()
        self.factory_hint = QLabel("")
        self.factory_hint.setWordWrap(True)
        lay.addWidget(self.factory_hint)

        # Para qué sirve esto. Sin decirlo, "restablecer" suena a botón
        # destructivo que nadie toca; y es justo lo contrario: la forma más
        # rápida de saber si un problema es de Blender o de tu configuración.
        why = QLabel(tr(
            "Useful when something misbehaves and you want to find out why: "
            "if the problem disappears on a clean Blender, it comes from your "
            "settings or add-ons, not from Blender itself. From there you put "
            "your settings back and enable things one at a time until it "
            "breaks again. It is also the fair way to report a bug, and a way "
            "to record a tutorial with the interface everyone else sees. "
            "Nothing is lost: your settings are saved aside and go back with "
            "one click."))
        why.setWordWrap(True)
        why.setObjectName("Muted")
        lay.addWidget(why)

        # Resumen: cuántos guardados hay y en qué estado está la config viva.
        self.factory_status = QLabel("")
        self.factory_status.setWordWrap(True)
        lay.addWidget(self.factory_status)

        # La lista, en scroll: puede haber muchos guardados.
        self.snapshot_scroll = _ResizableScroll(
            self._resize_snapshots,
            tooltip=tr("Drag the bottom-right corner to make the saved copies "
                       "list taller or shorter."))
        self.snapshot_scroll.setObjectName("SnapshotList")
        self.snapshot_scroll.setWidgetResizable(True)
        self.snapshot_scroll.setFrameShape(QFrame.NoFrame)
        self.snapshot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.snapshot_scroll.setMaximumHeight(SNAPSHOT_SCROLL_HEIGHT)
        body = QWidget()
        body.setObjectName("SnapshotListBody")
        self.snapshot_rows = QVBoxLayout(body)
        self.snapshot_rows.setContentsMargins(0, 0, 0, 0)
        self.snapshot_rows.setSpacing(6)
        self.snapshot_rows.addStretch()
        self.snapshot_scroll.setWidget(body)
        self.snapshot_scroll.setVisible(False)
        lay.addWidget(self.snapshot_scroll)

        self.factory_empty = QLabel(tr(
            "No saved settings. Resetting will keep nothing to go back to."))
        self.factory_empty.setObjectName("Muted")
        self.factory_empty.setWordWrap(True)
        lay.addWidget(self.factory_empty)

        row = QHBoxLayout()
        reset = CardButton(tr("Reset to factory settings"),
                           tooltip=tr("Save the current settings aside and "
                                      "start clean."))
        reset.clicked.connect(self.reset_to_factory)
        row.addWidget(reset)
        row.addStretch()
        self.delete_all_btn = CardButton(
            tr("Delete all saved settings"), variant="danger",
            tooltip=tr("Delete every saved copy of this version for good."))
        self.delete_all_btn.clicked.connect(self.delete_all_snapshots)
        row.addWidget(self.delete_all_btn)
        lay.addLayout(row)

        # Retención: cuántas copias se conservan por versión. Va aquí (y no en
        # Ajustes) porque es justo donde se ven y se borran.
        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel(tr("Keep at most")))
        keep_row.addStretch()
        self.snapshot_keep_combo = QComboBox()
        for value, label in ((3, "3"), (5, "5"), (10, "10"), (0, tr("All"))):
            self.snapshot_keep_combo.addItem(label, value)
        index = self.snapshot_keep_combo.findData(self.snapshot_keep)
        self.snapshot_keep_combo.setCurrentIndex(index if index >= 0 else 1)
        self.snapshot_keep_combo.setToolTip(tr(
            "How many saved copies to keep per version. The oldest are deleted "
            "when a new one is saved."))
        self.snapshot_keep_combo.currentIndexChanged.connect(
            self._on_snapshot_keep_changed)
        keep_row.addWidget(self.snapshot_keep_combo)
        lay.addLayout(keep_row)

        self._refresh_factory()
        return card

    def set_snapshot_keep(self, value: int) -> None:
        """Fija cuántas copias se conservan (lo llama MainWindow con el ajuste)."""
        self.snapshot_keep = int(value)
        if hasattr(self, "snapshot_keep_combo"):
            index = self.snapshot_keep_combo.findData(self.snapshot_keep)
            if index >= 0:
                self.snapshot_keep_combo.blockSignals(True)
                self.snapshot_keep_combo.setCurrentIndex(index)
                self.snapshot_keep_combo.blockSignals(False)

    def _on_snapshot_keep_changed(self, index: int) -> None:
        """El usuario cambió la retención: se guarda y se poda ya."""
        value = self.snapshot_keep_combo.itemData(index)
        if value is None:
            return
        self.snapshot_keep = int(value)
        self.snapshot_keep_changed.emit(self.snapshot_keep)
        config = self._factory_config()
        if config is not None and self.snapshot_keep > 0:
            bc.prune_snapshots(config, self.snapshot_keep)
        self._refresh_factory()

    def _factory_entry(self):
        """Instalada elegida en la pestaña de fábrica (su propio selector)."""
        return self._selected(self.factory_combo)

    def _factory_config(self):
        """Config de la versión que se restablece/recupera en esa pestaña."""
        entry = self._factory_entry()
        if entry is None:
            return None
        return bc.config_for(entry.version, self.platform)

    def _clear_snapshot_rows(self) -> None:
        """Vacía la lista de guardados (deja el hueco del final)."""
        self._snapshot_widgets = {}
        for index in range(self.snapshot_rows.count() - 1, -1, -1):
            widget = self.snapshot_rows.itemAt(index).widget()
            if widget is None:
                continue
            self.snapshot_rows.takeAt(index)
            widget.setParent(None)
            widget.hide()
            widget.deleteLater()

    def _build_snapshot_rows(self, snapshots) -> None:
        """Crea una fila por guardado y le vuelca el análisis ya cacheado."""
        self._snapshot_widgets = {}
        for snapshot in snapshots:
            row = _SnapshotRow(
                snapshot, bc.snapshot_details(snapshot),
                on_restore=self.restore_factory_snapshot,
                on_delete=self.delete_snapshot,
                on_details=self.show_snapshot_details)
            cached = self._analysis.get(str(snapshot))
            if cached is not None:
                row.set_analysis(cached)
            # Antes del hueco final (el ``addStretch`` del layout).
            self.snapshot_rows.insertWidget(self.snapshot_rows.count() - 1,
                                            row)
            self._snapshot_widgets[snapshot] = row
        if snapshots:
            self._snapshot_widgets[snapshots[0]].add_badge(tr("Most recent"))

    def _factory_status_text(self, count: int) -> str:
        """Resumen: cuántos guardados hay y en qué estado está la config viva."""
        text = tr("Saved copies: {count}.", count=count)
        if self._factory_live_count is None:
            return text
        if self._factory_live_count:
            return text + " " + tr(
                "Right now this Blender has {count} settings changed from its "
                "defaults.", count=self._factory_live_count)
        return text + " " + tr(
            "Right now this Blender is at its defaults; restoring a copy "
            "brings your settings back.")

    def _fit_snapshot_scroll(self) -> None:
        """Alto de la lista de guardados: el elegido con el asa o el del contenido."""
        content = 0
        for index in range(self.snapshot_rows.count()):
            widget = self.snapshot_rows.itemAt(index).widget()
            if widget is not None:
                content += widget.sizeHint().height()
        content += self.snapshot_rows.spacing() * max(
            0, self.snapshot_rows.count() - 1)
        height = self._snapshot_height or min(content, SNAPSHOT_SCROLL_HEIGHT)
        self.snapshot_scroll.setFixedHeight(max(SNAPSHOT_MIN_HEIGHT, height))

    def _refresh_factory(self) -> None:
        """Repinta la tarjeta de fábrica: estado, lista de guardados y análisis."""
        if not hasattr(self, "factory_status"):
            return
        config = self._factory_config()
        self._clear_snapshot_rows()
        if config is None:
            self.factory_hint.setText("")
            self.factory_status.setText("")
            self.factory_path_label.setText("")
            self.factory_empty.setVisible(False)
            self.snapshot_scroll.setVisible(False)
            self.delete_all_btn.setEnabled(False)
            return
        _, version = _entry_info(self._factory_entry())
        self.factory_path_label.setText(str(config.root))
        self.factory_hint.setText(tr(
            "Start Blender {version} as if it were freshly installed. Its "
            "current settings are saved aside and can be put back.",
            version=version))
        snapshots = bc.snapshots_for(config)
        self.delete_all_btn.setEnabled(bool(bc.snapshot_dirs(config)))
        if not snapshots:
            self.factory_status.setText("")
            self.factory_empty.setVisible(True)
            self.snapshot_scroll.setVisible(False)
            self._analysis = {}
            self._analyzed_for = ""
            self._factory_live_count = None
            return
        self.factory_empty.setVisible(False)
        self._build_snapshot_rows(snapshots)
        self.snapshot_scroll.setVisible(True)
        self._fit_snapshot_scroll()
        self.factory_status.setText(self._factory_status_text(len(snapshots)))
        self._maybe_analyze_snapshots()

    def _maybe_analyze_snapshots(self) -> None:
        """Lee en segundo plano qué ajustes cambia cada guardado.

        Solo cuando la pestaña está abierta (no en cada ``_reload``) y una vez
        por versión: cada guardado cuesta un arranque de Blender, así que no se
        repite mientras no cambie la versión ni los guardados.
        """
        if not hasattr(self, "_snapshot_widgets"):
            return
        if self.tabs.currentWidget() is not self.factory_page:
            return
        if self._snapshots_waiting or self._analyzed_for:
            return
        entry = self._factory_entry()
        executable, version = _entry_info(entry)
        config = self._factory_config()
        if config is None or not executable or not Path(executable).is_file():
            return
        snapshots = list(bc.snapshots_for(config))
        if not snapshots:
            return
        self._analyzed_for = version
        self._snapshots_waiting = True

        def worker():
            payload = {"version": version, "results": {}, "live": None}
            try:
                factory = bprefs.read_preferences(executable, factory=True,
                                                  timeout=120)
                live = bprefs.read_preferences(executable, timeout=120)
                payload["live"] = len(bprefs.changed(live, factory))
                for snapshot in snapshots:
                    user = bprefs.snapshot_preferences(executable, snapshot,
                                                       timeout=120)
                    payload["results"][str(snapshot)] = bprefs.changed(
                        user, factory)
            except Exception:  # noqa: BLE001 - un fallo no puede tumbar la vista
                payload["failed"] = True
            self.snapshots_analyzed.emit(payload)

        threading.Thread(target=worker, daemon=True).start()

    def _on_snapshots_analyzed(self, payload) -> None:
        self._snapshots_waiting = False
        if payload.get("version") != getattr(self._factory_entry(),
                                             "version", ""):
            return
        results = payload.get("results") or {}
        best = None
        best_count = 0
        for snapshot, row in self._snapshot_widgets.items():
            preferences = results.get(str(snapshot))
            if preferences is None:
                if payload.get("failed"):
                    row.set_unreadable()
                else:
                    row.set_analysis(None)
                continue
            self._analysis[str(snapshot)] = preferences
            row.set_analysis(preferences)
            if len(preferences) > best_count:
                best, best_count = snapshot, len(preferences)
        if best is not None:
            self._snapshot_widgets[best].add_badge(tr("Most complete"))
        live = payload.get("live")
        if live is not None:
            self._factory_live_count = live
            self.factory_status.setText(
                self._factory_status_text(len(self._snapshot_widgets)))

    def show_snapshot_details(self, snapshot) -> None:
        """Abre el diálogo con los ajustes que cambia ese guardado."""
        row = self._snapshot_widgets.get(Path(snapshot))
        preferences = row.analysis if row is not None else None
        if preferences is None:
            show_info(self, tr("Saved settings"),
                      tr("Still reading this copy. Try again in a moment."))
            return
        _show_snapshot_details(self, snapshot, preferences)

    def delete_snapshot(self, snapshot) -> None:
        """Borra un guardado concreto (irreversible)."""
        snapshot = Path(snapshot)
        date = bc.snapshot_date(snapshot) or snapshot.name
        if not confirm(
                self, tr("Delete saved settings"),
                tr("Delete the settings saved on {date} for good? You will not "
                   "be able to restore them.", date=date),
                accept_text=tr("Delete"), danger=True):
            return
        bc.delete_snapshot(snapshot)
        self._analysis.pop(str(snapshot), None)
        self.status_message.emit(tr("Saved settings deleted."))
        self._refresh_factory()

    def delete_all_snapshots(self) -> None:
        """Borra todos los guardados de esa versión (irreversible)."""
        config = self._factory_config()
        if config is None:
            return
        # ``snapshot_dirs`` (no ``snapshots_for``): se borra también lo vacío,
        # que si no quedaría ahí sin forma de limpiarlo desde la interfaz.
        snapshots = bc.snapshot_dirs(config)
        if not snapshots:
            return
        if not confirm(
                self, tr("Delete saved settings"),
                tr("Delete all saved settings of this version for good? You "
                   "will not be able to restore them."),
                accept_text=tr("Delete"), danger=True):
            return
        for snapshot in snapshots:
            bc.delete_snapshot(snapshot)
        self._analysis = {}
        self._analyzed_for = ""
        self.status_message.emit(tr("Saved settings deleted."))
        self._refresh_factory()

    def reset_to_factory(self) -> None:
        """Aparta la config de esa versión (instantánea) para dejarla limpia."""
        entry = self._factory_entry()
        config = self._factory_config()
        if config is None:
            return
        if self._blocked_by_running(entry):
            return
        _, version = _entry_info(entry)
        if not confirm(
                self, tr("Reset to factory settings"),
                tr("Blender {version} will start clean on next launch.\n\nYour "
                   "settings are saved aside, so you can put them back from "
                   "this same screen.", version=version),
                accept_text=tr("Reset"), danger=True):
            return
        snapshot = bc.snapshot_config(config, label=f"v{version}",
                                      keep=self.snapshot_keep)
        if snapshot is None:
            self.factory_status.setText(tr(
                "This version has no settings yet."))
            return
        self._analysis = {}
        self._analyzed_for = ""
        self.status_message.emit(tr("Settings saved aside and reset."))
        show_info(self, tr("Reset to factory settings"),
                  tr("Your settings were saved. Blender {version} will start "
                     "clean the next time you open it.", version=version))
        self._refresh_factory()

    def restore_factory_snapshot(self, snapshot=None) -> None:
        """Copia un guardado a su sitio (el más reciente si no se dice cuál)."""
        entry = self._factory_entry()
        config = self._factory_config()
        if config is None:
            return
        snapshots = bc.snapshots_for(config)
        if not snapshots:
            return
        target = Path(snapshot) if snapshot is not None else snapshots[0]
        if target not in snapshots:
            return
        if self._blocked_by_running(entry):
            return
        _, version = _entry_info(entry)
        date = bc.snapshot_date(target) or target.name
        if not confirm(
                self, tr("Restore settings"),
                tr("Put back in Blender {version} the settings saved on "
                   "{date}?\n\nWhat it has now is saved aside, so this can be "
                   "undone.", version=version, date=date),
                accept_text=tr("Restore")):
            return
        bc.restore_snapshot(config, target, keep=self.snapshot_keep)
        self._analysis = {}
        self._analyzed_for = ""
        self.status_message.emit(tr("Settings restored."))
        self._refresh_factory()

    def _undo_button(self) -> CardButton:
        """Botón para revertir la última migración (si la hay)."""
        self.undo_btn = CardButton(
            tr("Undo last migration"),
            tooltip=tr("Put back what the last migration replaced and remove "
                       "what it copied."))
        self.undo_btn.clicked.connect(self.undo)
        self.undo_btn.setVisible(False)
        return self.undo_btn

    def _refresh_undo(self) -> None:
        """Enseña el botón de deshacer solo si el destino tiene marcador."""
        if self.target_cfg is None or not hasattr(self, "undo_btn"):
            return
        self.undo_btn.setVisible(
            bool(bc.read_migration_marker(self.target_cfg)))

    def _rebuild_preferences(self) -> None:
        """Rellena las casillas de preferencias según el origen/destino."""
        _clear_layout(self.pref_rows)
        self.pref_checks = {}
        self.pref_items = []
        if self.source_cfg is None or self.target_cfg is None:
            self.copy_prefs_btn.setEnabled(False)
            return
        self.pref_items = bc.preference_plan(self.source_cfg, self.target_cfg)
        none = True
        for item in self.pref_items:
            if not item.exists:
                continue
            none = False
            check = CheckPill(item.filename)
            check.setChecked(item.selected)
            check.setEnabled(True)
            check.setToolTip(tr("{name} of the source version:\n{path}",
                                name=item.filename, path=item.source))
            # Lo que ya hay en destino se pisaría: se avisa en el propio texto.
            label = item.filename
            if item.overwrites:
                label += "  ·  " + tr("(replaces the current one)")
            check.setText(label)
            check.toggled.connect(
                lambda checked, it=item: setattr(it, "selected", checked))
            self.pref_rows.addWidget(check)
            self.pref_checks[item.key] = check
        if none:
            empty = QLabel(tr("No preferences found in the source version."))
            empty.setObjectName("Muted")
            self.pref_rows.addWidget(empty)
        self.copy_prefs_btn.setEnabled(not none)

    def set_system(self, platform: str, arch: str) -> None:
        """Fija el SO/arquitectura de este equipo (para la compatibilidad)."""
        self.platform = platform or ""
        self.arch = arch or ""

    # -------------------------------------------------------------- origen
    def set_installed(self, installed) -> None:
        """Recibe las versiones instaladas y rellena los desplegables.

        Se **ordena de más nueva a más vieja** en vez de fiarse del orden de
        entrada: de ahí sale el valor por defecto de los dos combos, y no puede
        depender de cómo venga la lista de fuera. Se deduplica por serie (dos
        diarias de ``main`` comparten carpeta de config).
        """
        self.installed = list(installed or [])
        seen = set()
        choices = []
        for entry in sorted(self.installed,
                            key=lambda item: version_tuple(
                                getattr(item, "version", "") or ""),
                            reverse=True):
            version = (getattr(entry, "version", "") or "")
            series = ".".join(version.split(".")[:2])
            if not series or series in seen:
                continue
            seen.add(series)
            choices.append(entry)
        self._choices = choices

        # Al reordenar, el desplegable mantiene la versión que tuviera elegida.
        self._fill_combo(self.source_combo, choices,
                         self._current_version(self.source_combo))
        self._fill_combo(self.target_combo, choices,
                         self._current_version(self.target_combo))
        # La pestaña de fábrica tiene su propio selector de una versión: se
        # mantiene lo elegido y, la primera vez, arranca en la más nueva (igual
        # que el destino de la migración).
        self._fill_combo(self.factory_combo, choices,
                         self._current_version(self.factory_combo),
                         label=_version_label)
        if choices and self.factory_combo.currentIndex() < 0:
            self.factory_combo.setCurrentIndex(0)
        # Por defecto (solo la primera vez): de la **penúltima** a la **última**,
        # que es el caso normal de "acabo de instalarme la nueva y quiero
        # traerme lo de la anterior".
        if len(choices) >= 2:
            if self.source_combo.currentIndex() < 0:
                self.source_combo.setCurrentIndex(1)
            if self.target_combo.currentIndex() < 0:
                self.target_combo.setCurrentIndex(0)
        self._reload()

    def _current_version(self, combo) -> str:
        index = combo.currentIndex()
        if 0 <= index < len(self._choices):
            return self._choices[index].version
        return ""

    def _fill_combo(self, combo, choices, keep_version: str,
                    label=None) -> None:
        """Rellena un desplegable de versiones.

        ``label`` decide el texto de cada opción (por defecto, versión y carpeta;
        el selector de fábrica usa solo la versión, que allí el nombre de la
        carpeta no aporta nada y repetía el número).
        """
        label = label or (lambda entry: f"Blender {entry.version}  ·  {entry.name}")
        combo.blockSignals(True)
        combo.clear()
        for entry in choices:
            combo.addItem(label(entry))
        index = next((i for i, entry in enumerate(choices)
                      if entry.version == keep_version), -1)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _selected(self, combo):
        index = combo.currentIndex()
        if 0 <= index < len(self._choices):
            return self._choices[index]
        return None

    # ------------------------------------------------------------- informe
    def _reload(self) -> None:
        self._clear_rows()
        self.plans = []
        self.source_cfg = None
        self.target_cfg = None
        self.source_entry = None
        self.target_entry = None
        self._set_warning("")
        self.source_path_label.setText("")
        self.target_path_label.setText("")

        source = self._selected(self.source_combo)
        target = self._selected(self.target_combo)
        if len(self._choices) < 2 or source is None or target is None:
            self.summary.setText(tr("You need at least two installed Blender "
                                    "versions."))
            self._set_controls_enabled(False)
            self._rebuild_preferences()
            return
        if source.version == target.version:
            self.summary.setText(tr("Source and destination must be different."))
            self._set_controls_enabled(False)
            self._rebuild_preferences()
            return

        self.source_entry = source
        self.target_entry = target
        self.source_cfg = bc.config_for(source.version, self.platform)
        self.target_cfg = bc.config_for(target.version, self.platform)
        self._rebuild_preferences()
        self._refresh_undo()
        self._refresh_factory()
        self.source_path_label.setText(str(self.source_cfg.root))
        self.target_path_label.setText(str(self.target_cfg.root))
        self._rebuild_plan()
        self._check_running(target)
        self._refresh_undo()
        # Lectura automática del origen (addons activos + preferencias). Si esa
        # versión ya se leyó, no vuelve a arrancar Blender.
        self.read_source()

    def _fill_board(self) -> None:
        """Pinta el tablero con el plan actual (o el mensaje de vacío)."""
        self._clear_rows()
        if not self.plans:
            self.summary.setText(tr("No add-ons to migrate"))
            self._add_placeholder(self.left_rows,
                                  tr("No add-ons found in this version"))
            self._add_placeholder(self.right_rows, tr(
                "Install some add-ons in the source version first."))
            self._set_controls_enabled(False)
            return
        for index, plan in enumerate(self.plans):
            zebra = bool(index % 2)
            row = _SourceRow(plan, zebra)
            row.changed.connect(self._update_summary)
            self.left_rows.addWidget(row)
            self._rows.append(row)
            self.right_rows.addWidget(_DestRow(plan, zebra))
        self._set_controls_enabled(True)
        self._update_summary()

    def _check_running(self, entry, warning=None) -> None:
        """Avisa (en la tarjeta) si ese Blender está abierto.

        Escribir sus preferencias con Blender abierto es perder el cambio al
        salir. Es un aviso suave en la propia vista; para las acciones que van a
        escribir de verdad se llama a ``_blocked_by_running``, que impide
        continuar. ``warning`` elige la etiqueta (la de migración o la de
        fábrica), porque cada pestaña tiene la suya.
        """
        warning = warning if warning is not None else self.warning
        executable, version = _entry_info(entry)
        try:
            running = blender_runner.is_running(executable)
        except Exception:  # noqa: BLE001 - el aviso no puede tumbar la vista
            running = False
        self._put_warning(warning,
                          self._running_message(version) if running else "")

    @staticmethod
    def _running_message(version: str) -> str:
        return tr("Close Blender {version} before migrating: it would "
                  "overwrite the changes when it quits.", version=version)

    def _blocked_by_running(self, entry=None) -> bool:
        """True si hay **cualquier** Blender abierto (y avisa); bloquea la acción.

        No se comprueba solo el destino: dos builds de la misma serie (5.2.0 y
        5.2.2) comparten carpeta de configuración, así que un Blender abierto
        que no es el elegido también pisaría el cambio al cerrarse. Como no hay
        forma fiable de saber qué serie tiene abierta cada proceso (en Windows
        ni se detectan), se cierra todo.
        """
        try:
            running = blender_runner.is_running(None)
        except Exception:  # noqa: BLE001 - el chequeo no puede tumbar la acción
            running = False
        if not running:
            return False
        show_info(self, tr("Blender is running"), tr(
            "Close every Blender window before continuing: Blender saves its "
            "preferences when it quits and would overwrite the changes."))
        return True

    def _update_summary(self) -> None:
        counts = bc.summary_counts(self.plans)
        self.summary.setText(tr(
            "{total} add-ons · {ok} compatible · {warn} to review · "
            "{blocked} not compatible",
            total=len(self.plans), ok=counts[bc.OK], warn=counts[bc.WARN],
            blocked=counts[bc.BLOCKED]))

    def _add_placeholder(self, layout, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(label)

    def _clear_rows(self) -> None:
        """Vacía las dos columnas del tablero."""
        self._rows = []
        for layout in (self.left_rows, self.right_rows):
            _clear_layout(layout)

    def _select_all(self, checked: bool) -> None:
        for row in self._rows:
            row.set_checked(checked)
        self._update_summary()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (self.copy_btn, self.select_all_btn,
                       self.select_none_btn):
            widget.setEnabled(enabled)

    def _set_warning(self, text: str) -> None:
        self._put_warning(self.warning, text)

    @staticmethod
    def _put_warning(label, text: str) -> None:
        """Pinta el aviso en la etiqueta que le pasen (cada pestaña tiene una)."""
        label.setText(text)
        label.setVisible(bool(text))

    # --------------------------------------------------------------- copiar
    def apply(self) -> None:
        """Copia los addons marcados y los activa como estaban en origen.

        El estado se **imita**, no se fuerza: los addons que en origen estaban
        activados se activan en destino, y los que allí estaban apagados se
        quedan apagados. Así una copia se comporta igual que el original sin
        que el usuario tenga que repasar la lista de addons.
        """
        selected = [plan for plan in self.plans
                    if plan.selected and not plan.blocked]
        if not selected:
            self.status_message.emit(tr("Nothing selected"))
            return
        result = bc.apply_migration(self.plans, self.target_cfg)

        summary = (tr("Copied {count} add-ons.", count=len(result.copied))
                   if result.copied else "")
        lines = _report_lines(
            summary, bool(result.backed_up), result.failed,
            tr("Some add-ons could not be copied:"),
            lambda plan: plan.addon.name)
        show_info(self, tr("Migration complete"), "\n".join(lines))
        self.status_message.emit(
            tr("Copied {count} add-ons.", count=len(result.copied)))
        # Se acaba de escribir el marcador de migración en destino.
        self._refresh_undo()

        # Solo se activan los que estaban activos en origen.
        executable, version = _entry_info(self.target_entry)
        modules = [plan.enable_module for plan in result.copied
                   if plan.was_enabled]
        if not (executable and modules and Path(executable).is_file()):
            return
        if self._blocked_by_running():
            return
        self._start_activation(executable, modules, version)

    def apply_preferences(self) -> None:
        """Copia los ficheros de preferencias marcados.

        Antes de tocar ``userpref.blend`` hay que asegurarse de que el Blender
        destino no está abierto: al salir, reescribiría el fichero y se perdería
        lo que acabamos de poner (y peor: podría guardar un estado mezclado).
        """
        if self._blocked_by_running():
            return
        if not any(item.selected and item.safe for item in self.pref_items):
            self.status_message.emit(tr("Nothing selected"))
            return
        result = bc.apply_preferences(self.pref_items, self.target_cfg)
        summary = (tr("Copied {count} preference files.",
                      count=len(result.copied)) if result.copied else "")
        lines = _report_lines(
            summary, bool(result.backed_up), result.failed,
            tr("Some files could not be copied:"),
            lambda item: item.filename)
        show_info(self, tr("Migration complete"), "\n".join(lines))
        self.status_message.emit(
            tr("Copied {count} preference files.", count=len(result.copied)))
        # Acabamos de escribir en destino: ya hay algo que deshacer.
        self._refresh_undo()

    def undo(self) -> None:
        """Revierte la última migración sobre el destino."""
        if self.target_cfg is None or self.target_entry is None:
            return
        _, version = _entry_info(self.target_entry)
        if not confirm(
                self, tr("Undo last migration"),
                tr("This puts back what the last migration replaced and removes "
                   "what it copied from Blender {version}.\n\nAdd-ons you have "
                   "changed since then will be lost.",
                   version=version),
                accept_text=tr("Undo"), danger=True):
            return
        result = bc.undo_migration(self.target_cfg)
        lines = []
        if result.restored:
            lines.append(tr("Restored {count} items to their previous state.",
                            count=len(result.restored)))
        if result.removed:
            lines.append(tr("Removed {count} items that were copied.",
                            count=len(result.removed)))
        if not lines:
            lines = [tr("There was nothing to undo.")]
        if result.failed:
            lines.append("")
            lines.append(tr("Some items could not be restored:"))
            for path, message in result.failed[:10]:
                lines.append(f"· {Path(path).name}: {message}")
        show_info(self, tr("Migration undone"), "\n".join(lines))
        self.status_message.emit(tr("Migration undone"))
        self._reload()

    def _start_activation(self, executable, modules, version) -> None:
        """Habilita los addons copiados en un hilo (Blender tarda en arrancar)."""
        self.status_message.emit(tr("Enabling the add-ons in Blender..."))
        self._activating = True

        def worker():
            result = blender_runner.enable_addons(executable, modules)
            self.activation_done.emit({"result": result, "version": version})

        threading.Thread(target=worker, daemon=True).start()

    def _on_activation_done(self, payload) -> None:
        if not self._activating:
            return
        self._activating = False
        result = payload.get("result") or {}
        version = payload.get("version") or ""
        lines = []
        enabled = result.get("enabled") or []
        if enabled:
            lines.append(tr("Enabled {count} add-ons in Blender {version}.",
                            count=len(enabled), version=version))
        else:
            lines.append(tr("The add-ons were copied but not enabled. You can "
                            "enable them in Blender's preferences."))
        errors = result.get("errors") or []
        if errors:
            lines.append("")
            lines.append(tr("Could not enable some add-ons:"))
            for item in errors[:10]:
                module = item.get("module") or "Blender"
                lines.append(f"· {module}: {item.get('error', '')}")
        show_info(self, tr("Migration complete"), "\n".join(lines))
        self.status_message.emit(tr("Migration complete"))
