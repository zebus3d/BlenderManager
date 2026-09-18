"""Vista de migración de addons entre versiones de Blender.

El núcleo (``services/blender_config``) hace el trabajo: localiza las carpetas,
lee la versión mínima de cada addon y decide si es compatible. Aquí solo se
enseña el informe, se dejan marcar los que se quieren copiar y se lanza la
copia. La parte de habilitarlos en la versión destino la ejecuta Blender en
segundo plano (``services/blender_runner``), porque el estado *habilitado*
vive dentro de ``userpref.blend``.

La disposición es la de un tablero de transferencia: el **origen** a la
izquierda (con casilla, versión y veredicto), el **destino** a la derecha (con
la carpeta donde caerá cada addon) y una flecha de un solo sentido en medio.
Las dos columnas viven en la **misma área de scroll**, así que las filas quedan
siempre alineadas sin sincronizar nada.

No es una pestaña de compilaciones, así que la barra de filtros y el buscador
se ocultan (lo decide ``MainWindow._set_view``).
"""

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
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
from ui.fonts import glyph_icon, icon_font
from ui.widgets.buttons import CardButton, CheckPill
from ui.widgets.cards import card_shadow
from ui.widgets.dialogs import confirm, show_info
from ui.widgets.labels import ElidedLabel

# Alto fijo de una fila: las dos columnas tienen que cuadrar una con otra.
ROW_HEIGHT = 48

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
        return tr("Its dependencies are built for another Python version.")
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
            "load, it needs a build of the add-on made for that Blender "
            "(its compiled dependencies do not match).")
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
    evita que las cuatro tarjetas de esta vista se vayan separando con el
    tiempo. Devuelve ``(tarjeta, layout)`` y, si hay ``title``, ya lo añade.
    """
    card = QFrame()
    card.setObjectName("SettingsCard")
    # Sombra abajo a la derecha (la misma que las tarjetas de la tienda): las
    # tarjetas van sobre el canvas gris de las pestañas y así se despegan de él.
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
        self._build_ui()
        self.activation_done.connect(self._on_activation_done)
        self.prefs_loaded.connect(self._on_prefs_loaded)
        self.prefs_applied.connect(self._on_prefs_applied)
        self.source_read.connect(self._on_source_read)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        """Estructura de la pantalla.

        Arriba, una **barra fija** con el selector de versiones (origen →
        destino) y las **dos pestañas**; el origen/destino es común a las dos,
        así que no se repite dentro. Debajo, el aviso de Blender abierto. El
        resto vive en un scroll con una pestaña por asunto:

        * **Add-ons**: el tablero y el botón de copiar lo seleccionado.
        * **Preferences**: primero lo fino (ajustes uno a uno), luego los
          ficheros completos y, al final, el reset a valores de fábrica.
        """
        root = QVBoxLayout(self)
        # Sin margen: las pestañas van **a sangre** (el canvas gris llega hasta
        # la barra lateral, el borde derecho y la barra de estado). El padding
        # va en la cabecera de arriba y en el interior de cada pestaña, no aquí.
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("MigrateHeader")
        header_lay = QVBoxLayout(header)
        header_lay.setContentsMargins(24, 20, 24, 14)
        header_lay.setSpacing(12)
        # Título simple (sin tarjeta), como la vista de Ajustes: la barra
        # lateral solo trae iconos, así que aquí hace falta saber dónde estás.
        title = QLabel(tr("Migrate add-ons, extensions and preferences"))
        title.setToolTip(tr(
            "Pick a source and a destination version above, then use the tabs "
            "to copy add-ons, individual settings or the whole preferences "
            "file."))
        header_lay.addWidget(title)
        header_lay.addWidget(self._build_version_bar())

        self.warning = QLabel("")
        self.warning.setObjectName("Danger")
        self.warning.setWordWrap(True)
        self.warning.setVisible(False)
        header_lay.addWidget(self.warning)
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("MigrateTabs")
        self.tabs.addTab(self._build_addons_tab(), tr("Add-ons"))
        self.tabs.addTab(self._build_preferences_tab(), tr("Preferences"))
        self.tabs.addTab(self._build_factory_tab(), tr("Factory settings"))
        root.addWidget(self.tabs, 1)

        self._set_controls_enabled(False)

    def _build_version_bar(self) -> QFrame:
        """Tarjeta superior: de qué versión a qué versión (común a las pestañas).

        Va en una tarjeta gris como el resto: sobre el fondo oscuro de la
        ventana, un desplegable —que también es oscuro— no se distingue. Cada
        columna lleva su etiqueta y, debajo, la ruta real de esa config: es lo
        que deja claro *dónde* se va a escribir, sobre todo con las LTS en otro
        disco o una config movida con ``BLENDER_USER_CONFIG``.
        """
        card, lay = _settings_card()
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
        page = QWidget()
        page.setObjectName("MigratePage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(12)

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
        page = QWidget()
        page.setObjectName("MigratePage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(12)
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
        page = QWidget()
        page.setObjectName("MigratePage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(12)
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

        self.detail_rows = QVBoxLayout()
        self.detail_rows.setSpacing(4)
        lay.addLayout(self.detail_rows)

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
            return
        executable, _ = _entry_info(self.source_entry)
        self._source_reading = True
        self._prefs_loading = True
        self._prefs_waiting = True
        self.detail_load_btn.setEnabled(False)
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
            self.detail_status.setText(tr("Could not read the settings."))
            self._show_detail_buttons(False)
            return
        changed = bprefs.diff(payload["user"], payload["factory"])
        env = bprefs.environment_preferences(payload["user"], payload["factory"])
        self.detail_prefs = changed + env
        if not self.detail_prefs:
            self.detail_status.setText(tr(
                "You have no settings changed from Blender's defaults."))
            self._show_detail_buttons(False)
            return
        self._fill_detail_rows()
        self._show_detail_buttons(True)
        self._refresh_plan_status()

    def _fill_detail_rows(self) -> None:
        self._clear_detail_rows()
        self.detail_checks = []
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
        """Tarjeta para resetear la versión DESTINO a valores de fábrica.

        Se apoya en ``snapshot_config``: aparta la carpeta ``config`` a una
        instantánea y deja que Blender recree todo de fábrica. Se puede volver
        a poner la instantánea, o borrarla para dejarlo limpio para siempre.
        """
        # Sin título dentro: la pestaña ya se llama "Factory settings". El
        # texto se rellena en ``_refresh_factory`` porque nombra la versión
        # destino, que el usuario puede cambiar en la barra de arriba.
        card, lay = _settings_card()
        self.factory_hint = QLabel("")
        self.factory_hint.setWordWrap(True)
        lay.addWidget(self.factory_hint)

        self.factory_status = QLabel("")
        self.factory_status.setWordWrap(True)
        self.factory_status.setToolTip(tr(
            "Settings saved aside by a previous reset, ready to be put back."))
        lay.addWidget(self.factory_status)

        row = QHBoxLayout()
        reset = CardButton(tr("Reset to factory settings"),
                           tooltip=tr("Save the current settings aside and "
                                      "start clean."))
        reset.clicked.connect(self.reset_to_factory)
        row.addWidget(reset)
        row.addStretch()
        self.restore_btn = CardButton(
            tr("Restore last settings"),
            tooltip=tr("Put the saved settings back."))
        self.restore_btn.clicked.connect(self.restore_factory_snapshot)
        row.addWidget(self.restore_btn)
        self.delete_snapshot_btn = CardButton(
            tr("Delete saved settings"), variant="danger",
            tooltip=tr("Delete the saved settings for good."))
        self.delete_snapshot_btn.clicked.connect(self.delete_factory_snapshot)
        row.addWidget(self.delete_snapshot_btn)
        lay.addLayout(row)
        self._refresh_factory()
        return card

    def _target_config(self):
        """Config de la versión destino (la que se resetea/restaura)."""
        if self.target_entry is None:
            return None
        return bc.config_for(self.target_entry.version, self.platform)

    def _refresh_factory(self) -> None:
        """Actualiza el estado de la tarjeta de fábrica."""
        if not hasattr(self, "factory_status"):
            return
        config = self._target_config()
        if config is None:
            self.factory_hint.setText("")
            self.factory_status.setText("")
            self.restore_btn.setEnabled(False)
            self.delete_snapshot_btn.setEnabled(False)
            return
        _, version = _entry_info(self.target_entry)
        self.factory_hint.setText(tr(
            "Put Blender {version} back to a clean state. Its current settings "
            "are saved aside and can be restored, unless you delete them.",
            version=version))
        snapshots = bc.snapshots_for(config)
        if snapshots:
            self.factory_status.setText(tr(
                "Saved settings: {count}. The newest is from {date}.",
                count=len(snapshots), date=snapshots[0].name))
        else:
            self.factory_status.setText(tr(
                "No saved settings. Resetting will keep nothing to go back to."))
        self.restore_btn.setEnabled(bool(snapshots))
        self.delete_snapshot_btn.setEnabled(bool(snapshots))

    def reset_to_factory(self) -> None:
        """Aparta la config del destino (instantánea) para dejarlo limpio."""
        config = self._target_config()
        if config is None:
            return
        if self._blocked_by_running():
            return
        _, version = _entry_info(self.target_entry)
        if not confirm(
                self, tr("Reset to factory settings"),
                tr("Blender {version} will start clean on next launch.\n\nYour "
                   "settings are saved aside, so you can put them back from "
                   "this same screen.", version=version),
                accept_text=tr("Reset"), danger=True):
            return
        snapshot = bc.snapshot_config(config, label=f"v{version}")
        if snapshot is None:
            self.factory_status.setText(tr(
                "This version has no settings yet."))
            return
        self.status_message.emit(tr("Settings saved aside and reset."))
        show_info(self, tr("Reset to factory settings"),
                  tr("Your settings were saved. Blender {version} will start "
                     "clean the next time you open it.", version=version))
        self._refresh_factory()

    def restore_factory_snapshot(self) -> None:
        """Devuelve la instantánea más reciente a su sitio."""
        config = self._target_config()
        if config is None:
            return
        snapshots = bc.snapshots_for(config)
        if not snapshots:
            return
        _, version = _entry_info(self.target_entry)
        if not confirm(
                self, tr("Restore last settings"),
                tr("Put back the saved settings of Blender {version}?\n\nThe "
                   "clean settings you have now are saved aside, so this can "
                   "be undone too.", version=version),
                accept_text=tr("Restore")):
            return
        bc.restore_snapshot(config, snapshots[0])
        self.status_message.emit(tr("Settings restored."))
        self._refresh_factory()

    def delete_factory_snapshot(self) -> None:
        """Borra la instantánea más reciente (irreversible)."""
        config = self._target_config()
        if config is None:
            return
        snapshots = bc.snapshots_for(config)
        if not snapshots:
            return
        if not confirm(
                self, tr("Delete saved settings"),
                tr("Delete the saved settings for good? You will not be able to "
                   "restore them."),
                accept_text=tr("Delete"), danger=True):
            return
        for snapshot in snapshots:
            bc.delete_snapshot(snapshot)
        self.status_message.emit(tr("Saved settings deleted."))
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

    def _fill_combo(self, combo, choices, keep_version: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        for entry in choices:
            combo.addItem(f"Blender {entry.version}  ·  {entry.name}")
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

    def _check_running(self, target) -> None:
        """Avisa (en la tarjeta) si el Blender destino está abierto.

        Escribir sus preferencias con Blender abierto es perder el cambio al
        salir. Es un aviso suave en la propia vista; para las acciones que van a
        escribir de verdad se llama a ``_blocked_by_running``, que impide
        continuar.
        """
        executable, version = _entry_info(target)
        try:
            if blender_runner.is_running(executable):
                self._set_warning(self._running_message(version))
        except Exception:  # noqa: BLE001 - el aviso no puede tumbar la vista
            pass

    @staticmethod
    def _running_message(version: str) -> str:
        return tr("Close Blender {version} before migrating: it would "
                  "overwrite the changes when it quits.", version=version)

    def _blocked_by_running(self) -> bool:
        """True si el Blender destino está abierto (y avisa); bloquea la acción.

        El chequeo no depende de que encontremos el ejecutable: pisar las
        preferencias con Blender abierto es malo aunque la build esté en una
        ruta rara, y ``running_blenders`` se apaña con la ruta que le den.
        """
        executable, version = _entry_info(self.target_entry)
        try:
            running = blender_runner.is_running(executable)
        except Exception:  # noqa: BLE001 - el chequeo no puede tumbar la acción
            running = False
        if not running:
            return False
        show_info(self, tr("Blender {version} is running", version=version),
                  self._running_message(version))
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
        self.warning.setText(text)
        self.warning.setVisible(bool(text))

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
