"""Carga de la fuente de iconos (Font Awesome Free) para Qt.

Sustituye a ``LabelBase.register`` de Kivy. Se carga una sola vez y se
devuelve un ``QFont`` con la familia resultante para pintar los glifos.
"""

from PySide6.QtGui import QFont, QFontDatabase

from paths import ASSETS_DIR

_ICON_TTF = ASSETS_DIR / "fonts" / "fa-solid-900.ttf"
_family: str | None = None


def load() -> None:
    """Registra la fuente de iconos (idempotente). Llamar tras crear QApplication."""
    global _family
    if _family is not None:
        return
    if not _ICON_TTF.is_file():
        return
    font_id = QFontDatabase.addApplicationFont(str(_ICON_TTF))
    if font_id == -1:
        return
    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        _family = families[0]


def icon_font(size: int | None = None) -> QFont:
    """Devuelve un ``QFont`` de la fuente de iconos (o la general si falló)."""
    if _family is None:
        load()
    font = QFont(_family) if _family else QFontDatabase.systemFont(
        QFontDatabase.GeneralFont)
    if size:
        font.setPixelSize(size)
    return font


def glyph_icon(glyph: str, size: int = 16, color: str = "#989898"):
    """Renderiza un glifo de la fuente de iconos como ``QIcon``.

    Útil para meter iconos dentro de un ``QLineEdit`` (``addAction``), donde no
    se puede usar directamente la fuente.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setFont(icon_font(size))
    painter.setPen(QColor(color))
    painter.drawText(pix.rect(), Qt.AlignCenter, glyph)
    painter.end()
    return QIcon(pix)
