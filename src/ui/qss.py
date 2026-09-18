"""Stylesheet global de la aplicación (sustituye a los ``views/*.kv``).

En Kivy el aspecto vivía repartido en cuatro archivos ``.kv`` con instrucciones
de canvas. En Qt todo eso se expresa con QSS: ``border-radius`` para las
esquinas redondeadas, ``qlineargradient`` para el degradado superior de los
botones y los pseudo-estados ``:hover``/``:pressed``/``:checked``/``:disabled``.

Los widgets se distinguen por ``objectName`` (o por una propiedad dinámica para
las variantes de color), igual que en el PoC.
"""

from ui import theme as t


def _lighten(color: str, amount: float) -> str:
    """Mezcla ``color`` (#RRGGBB) hacia blanco, para el degradado."""
    value = color.lstrip("#")
    channels = [int(value[index:index + 2], 16) for index in (0, 2, 4)]
    mixed = [round(channel + (255 - channel) * amount) for channel in channels]
    return "#%02X%02X%02X" % tuple(mixed)


def _volume(color: str, amount: float = 0.09) -> str:
    """Degradado vertical que da volumen a un botón, sobre su color base.

    Es el ``GRADIENT_TOP`` de la versión Kivy: una capa blanca del 9 % arriba
    que se desvanece hacia abajo. En QSS no se pueden apilar dos fondos, así que
    el 9 % de blanco se mezcla en el color del extremo superior.
    """
    return ("qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 {_lighten(color, amount)}, stop:1 {color})")


# Tinte del botón "Lanzar" al pasar el ratón: un azul pizarra lo bastante claro
# para que se note que es pulsable, sin el salto del ACCENT a plena saturación.
LAUNCH_HOVER = "#2B4A66"


def build_qss() -> str:
    """Devuelve el stylesheet completo, con los tokens del tema interpolados."""
    return f"""
    QWidget {{
        background-color: {t.BG};
        color: {t.TEXT};
        font-size: {t.FONT_SIZE}px;
    }}
    QLabel {{ background: transparent; }}
    /* El contenedor de refresco+buscador NO debe pintar su fondo: si no,
       aparece un recuadro más oscuro dentro de la cabecera. */
    QWidget#HeaderTools {{ background: transparent; }}
    /* Filas que solo agrupan un campo y su botón: sin fondo, o el QWidget
       pinta el BG oscuro y aparece una banda dentro de la tarjeta clara. */
    QWidget#FormRow {{ background: transparent; }}
    QToolTip {{
        background-color: {t.BG};
        color: {t.TEXT};
        border: 1px solid {t.SURFACE_ALT};
        padding: 5px 9px;
    }}

    /* --- Pastillas (filtros de canal, selector de vista) --- */
    QPushButton#Pill {{
        background-color: {t.FILTER};
        border: 1px solid rgba(0,0,0,0.35);
        border-radius: 6px;
        padding: 4px 9px;
        color: {t.TEXT};
        font-weight: bold;
    }}
    QPushButton#Pill:hover {{ background-color: {t.ACCENT_DARK}; color: {t.TEXT_SEL}; }}
    QPushButton#Pill:checked {{ background-color: {t.ACCENT}; color: {t.TEXT_SEL}; }}
    QPushButton#Pill:disabled {{ color: rgba(230,230,230,0.35); }}

    /* --- Pestañas de canal (filtros excluyentes) ---
       Sin páginas debajo, así que se redondean por los cuatro lados y se leen
       como un selector de pestañas en lugar de solapas que esperan un panel. */
    /* El QTabBar es un QWidget pelado y, si no, pinta el BG del tema (el más
       oscuro) y tapa el gris de la fila entre pestaña y pestaña. */
    QTabBar#ChannelTabs {{ background: transparent; }}
    QTabBar#ChannelTabs::tab {{
        background-color: {t.FILTER};
        border: 1px solid rgba(0,0,0,0.35);
        /* Redondeadas arriba y rectas abajo: así se leen como pestañas y no
           como botones. */
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        padding: 4px 12px;
        margin-right: 4px;
        color: {t.TEXT};
        font-weight: bold;
    }}
    QTabBar#ChannelTabs::tab:hover {{ background-color: {t.ACCENT_DARK}; color: {t.TEXT_SEL}; }}
    QTabBar#ChannelTabs::tab:selected {{ background-color: {t.ACCENT}; color: {t.TEXT_SEL}; }}

    /* --- Barra lateral --- */
    QPushButton#SideButton {{
        background-color: {t.BUTTON};
        border: 1px solid rgba(0,0,0,0.35);
        border-radius: 8px;
        min-width: 50px; max-width: 50px;
        min-height: 50px; max-height: 50px;
        color: {t.TEXT};
    }}
    QPushButton#SideButton:hover {{ background-color: {t.ACCENT_DARK}; color: {t.TEXT_SEL}; }}
    QPushButton#SideButton:checked {{ background-color: {t.ACCENT}; color: {t.TEXT_SEL}; }}

    /* --- Botón de tarjeta / acción (relleno + degradado + borde) ---
       El degradado (blanco 9 % arriba) solo va en los botones de color, como en
       Kivy: en los grises enturbia el texto. "dark" es el gris oscuro de las
       pestañas de Blender, que es el que usa Lanzar. */
    QPushButton#CardButton {{
        background-color: {t.BUTTON};
        border: 1px solid rgba(0,0,0,0.35);
        border-radius: 5px;
        padding: 6px 14px;
        color: {t.TEXT};
        font-weight: bold;
    }}
    QPushButton#CardButton:hover {{ background-color: #6A6A6A; }}
    QPushButton#CardButton:pressed {{ background-color: {t.ACCENT_DARK}; }}
    QPushButton#CardButton:disabled {{ color: rgba(230,230,230,0.35); }}
    QPushButton#CardButton[variant="accent"] {{
        background: {_volume(t.ACCENT_BTN)};
    }}
    QPushButton#CardButton[variant="accent"]:hover {{
        background: {_volume(t.ACCENT_DARK)};
    }}
    QPushButton#CardButton[variant="accent"]:pressed {{
        background: {_volume(t.ACCENT)};
    }}
    QPushButton#CardButton[variant="dark"] {{
        background: {_volume(t.FILTER)};
    }}
    QPushButton#CardButton[variant="dark"]:hover {{
        background: {_volume(LAUNCH_HOVER)};
        border: 1px solid {t.ACCENT};
        color: {t.TEXT_SEL};
    }}
    QPushButton#CardButton[variant="dark"]:pressed {{
        background: {_volume(t.ACCENT)};
        border: 1px solid {t.ACCENT};
        color: {t.TEXT_SEL};
    }}
    QPushButton#CardButton[variant="danger"] {{
        background: {_volume(t.DANGER_BTN)};
    }}
    QPushButton#CardButton[variant="danger"]:hover {{
        background: {_volume(t.DANGER)};
        border: 1px solid {t.DANGER_EDGE};
        color: {t.TEXT_SEL};
    }}
    QPushButton#CardButton[variant="danger"]:pressed {{
        background: {_volume(t.DANGER_DARK)};
        border: 1px solid {t.DANGER_EDGE};
        color: {t.TEXT_SEL};
    }}
    /* La papelera es un glifo, así que en el realce vale teñirlo de rojo (3:1).
       El selector se acota a [iconOnly] para no tocar el texto de los botones
       rojos de los diálogos, que sí necesita 4,5:1 y por eso va en blanco. */
    QPushButton#CardButton[variant="danger"][iconOnly="true"]:hover,
    QPushButton#CardButton[variant="danger"][iconOnly="true"]:pressed {{
        color: {t.DANGER_ICON};
    }}
    /* Botón que solo lleva un icono (papelera): con el padding normal (14 px por
       lado) el glifo no cabe cuando la rejilla va pequeña y queda el recuadro
       rojo vacío. Con 4 px sobra sitio incluso a zoom 0.6. */
    QPushButton#CardButton[iconOnly="true"] {{ padding: 6px 4px; }}

    /* --- Botón de info (círculo azul con la "i"), diana 24x24 (WCAG 2.5.8) --- */
    QPushButton#IconLink {{
        background-color: {t.INFO_DISC};
        /* Reborde blanco fino que separa el disco azul del fondo oscuro de la
           tarjeta. En QSS el borde se suma al ancho, así que el contenido baja
           a 20 px para que la diana siga midiendo 24x24 (como la estrella); la
           "i" (13 px) sigue cabiendo de sobra. */
        border: 2px solid {t.TEXT_SEL};
        border-radius: 12px;
        min-width: 20px; max-width: 20px;
        min-height: 20px; max-height: 20px;
        color: {t.TEXT_SEL};
    }}
    QPushButton#IconLink:hover {{ background-color: {t.ACCENT}; }}

    /* --- Estrella de favorito (misma diana de 24x24 que la "i") ---
       Se usa el mismo glifo en los dos estados: apagado cuando no está marcada
       y en ámbar cuando sí (solo empaquetamos la fuente sólida de iconos). */
    QPushButton#StarButton {{
        background: transparent;
        border: none;
        color: {t.MUTED};
        /* El glifo de la estrella aprovecha menos su caja que la "i", así que a
           13 px (el tamaño global) se veía más pequeña que el disco de info.
           Medido con tightBoundingRect: 16 px le da 18x17 px de tinta, a la par
           del disco azul de 20 px de la "i". */
        font-size: 16px;
        min-width: 24px; max-width: 24px;
        min-height: 24px; max-height: 24px;
    }}
    QPushButton#StarButton:hover {{ color: {t.TEXT}; }}
    QPushButton#StarButton:checked {{ color: {t.WARNING}; }}

    /* --- Botón de icono plano (refrescar, etc.) --- */
    QPushButton#IconFlat {{
        background: transparent;
        border: none;
        color: {t.TEXT};
        border-radius: 6px;
        min-width: 32px; max-width: 32px;
        min-height: 32px; max-height: 32px;
    }}
    QPushButton#IconFlat:hover {{ background-color: {t.SURFACE_ALT}; }}

    /* --- Tarjetas ---
       OJO con el orden: en QSS, `#Card[installed="true"]` y `#Card:hover`
       tienen la MISMA especificidad, así que gana la regla que va más abajo.
       Por eso el hover va al FINAL y repite todas las combinaciones: si no,
       las tarjetas instaladas (que llevan [installed="true"]) nunca se
       resaltaban al pasar el ratón. */
    QFrame#Card {{
        background-color: {t.CARD_DIM};
        border-radius: 12px;
        border: none;
    }}
    QFrame#Card[zebra="true"] {{ background-color: {t.CARD_DIM_ALT}; }}
    QFrame#Card[installed="true"] {{ background-color: {t.SURFACE}; }}
    QFrame#Card[installed="true"][zebra="true"] {{ background-color: {t.ROW_ALT}; }}
    QFrame#Card:hover,
    QFrame#Card[zebra="true"]:hover,
    QFrame#Card[installed="true"]:hover,
    QFrame#Card[installed="true"][zebra="true"]:hover {{
        background-color: {t.SURFACE_ALT};
    }}
    /* La propiedad la pone ``_HoverCard`` (enter/leave): cubre el caso de que el
       ratón esté sobre un hijo y el padre no reciba el estado hover. */
    QFrame#Card[hover="true"] {{ background-color: {t.SURFACE_ALT}; }}

    /* --- Paneles / barras --- */
    QFrame#Chrome {{ background-color: {t.CHROME}; border: none; }}
    QFrame#Sidebar {{ background-color: {t.SURFACE}; border: none; }}
    QFrame#SettingsCard {{
        background-color: {t.SURFACE};
        border-radius: 10px;
        border: 1px solid rgba(0,0,0,0.35);
    }}
    /* Filas de addons de la vista de migración. */
    QFrame#AddonRow {{
        background-color: {t.SURFACE};
        border-radius: 8px;
        border: 1px solid rgba(0,0,0,0.35);
    }}
    QFrame#AddonRow[zebra="true"] {{ background-color: {t.ROW_ALT}; }}

    /* --- Casilla de verificación (migración) ---
       El cuadro y la palomita los pinta ``CheckPill`` con QPainter: por QSS no
       se puede (la regla global de ``QWidget`` hereda sobre el ``::indicator``
       y Qt descarta su ``image``). Aquí solo se deja el color del texto. */
    QCheckBox {{ color: {t.TEXT}; spacing: 8px; }}

    /* --- Migración: fondo gris unificado y pestañas ---
       Toda la vista (cabecera + canvas de las pestañas) va del mismo gris
       (SURFACE), de modo que arriba y abajo forman un solo bloque; encima van
       las tarjetas (SURFACE_HIGH) con sombra. Las solapas de las pestañas sí
       son oscuras, para que se lean como pestañas y no se fundan con el gris. */
    QWidget#MigrateView {{ background-color: {t.SURFACE}; }}
    /* La cabecera (título + tarjeta de versiones) se pinta el gris por su
       cuenta: es un QWidget pelado y, si no, la regla global de QWidget le
       pone el BG oscuro y rompe la unificación. */
    QWidget#MigrateHeader {{ background-color: {t.SURFACE}; }}
    QTabWidget#MigrateTabs, QTabWidget#SettingsTabs {{ background-color: {t.SURFACE}; }}
    QTabWidget#MigrateTabs QTabBar, QTabWidget#SettingsTabs QTabBar {{ background-color: {t.SURFACE}; }}
    QTabWidget#MigrateTabs QTabBar::tab, QTabWidget#SettingsTabs QTabBar::tab {{
        background-color: {t.FILTER};
        color: {t.MUTED};
        border: 1px solid rgba(0,0,0,0.45);
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        padding: 6px 16px;
        margin-right: 3px;
        font-weight: bold;
    }}
    QTabWidget#MigrateTabs QTabBar::tab:hover, QTabWidget#SettingsTabs QTabBar::tab:hover {{ background-color: {t.ACCENT_DARK}; color: {t.TEXT_SEL}; }}
    QTabWidget#MigrateTabs QTabBar::tab:selected, QTabWidget#SettingsTabs QTabBar::tab:selected {{ background-color: {t.ACCENT}; color: {t.TEXT_SEL}; }}
    /* Alinea la primera pestaña con el padding interno del canvas (24 px, el
       mismo que la cabecera): si no, el texto de la pestaña queda pegado al
       borde y descuadra con las tarjetas de debajo. */
    QTabWidget#MigrateTabs QTabBar::tab:first {{ margin-left: 24px; }}

    /* El pane es la única parte del QTabWidget que pinta fondo; las páginas se
       pintan el suyo (un QWidget pelado no siempre deja pasar el del pane). */
    QTabWidget#MigrateTabs::pane, QTabWidget#SettingsTabs::pane {{
        border: none;
        border-top: 1px solid {t.SURFACE_ALT};
        background-color: {t.SURFACE};
        top: -1px;
    }}
    QWidget#MigratePage {{ background-color: {t.SURFACE}; }}
    /* Especificidad: `QWidget#MigrateView QWidget` (id+tipo+tipo) ganaría a
       `QFrame#SettingsCard` (id+tipo); por eso las tarjetas se declaran con el
       mismo prefijo. Aplica a TODA la vista (cabecera incluida), porque el
       fondo ahora es gris también arriba. */
    QWidget#MigrateView QFrame#SettingsCard {{ background-color: {t.SURFACE_HIGH}; }}
    QWidget#MigrateView QFrame#AddonRow {{ background-color: {t.CARD_DIM}; }}
    QWidget#MigrateView QFrame#AddonRow[zebra="true"] {{ background-color: {t.CARD_DIM_ALT}; }}

    /* --- Ajustes: el mismo efecto de capas que Migración ---
       Fondo gris (SURFACE) en cada página de pestaña y las tarjetas un escalón
       por encima (SURFACE_HIGH) con sombra (la pone `_settings_card`). */
    QWidget#SettingsPage {{ background-color: {t.SURFACE}; }}
    QWidget#SettingsPage QFrame#SettingsCard {{ background-color: {t.SURFACE_HIGH}; }}

    /* --- Campos de texto --- */
    QLineEdit {{
        background-color: {t.FIELD};
        border: none;
        border-radius: 8px;
        padding: 6px 12px;
        color: {t.TEXT};
        selection-background-color: {t.ACCENT};
    }}
    QLineEdit::placeholder {{ color: {t.MUTED}; }}
    /* Campo de renombrado en línea (doble clic en una instalada): compacto y
       con borde de acento, para que se note que se está editando. */
    QLineEdit#InlineEdit {{
        background-color: {t.FIELD};
        border: 1px solid {t.ACCENT};
        border-radius: 4px;
        padding: 0 4px;
    }}

    /* --- Desplegables --- */
    QComboBox {{
        background-color: {t.FILTER};
        border: 1px solid rgba(0,0,0,0.35);
        border-radius: 5px;
        padding: 4px 8px;
        color: {t.TEXT};
        min-height: 24px;
    }}
    QComboBox:hover {{ background-color: {t.ACCENT_DARK}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background-color: {t.SURFACE};
        color: {t.TEXT};
        selection-background-color: {t.ACCENT};
        border: 1px solid {t.SURFACE_ALT};
        outline: none;
    }}

    /* --- Interruptor Sí/No --- */
    /* --- Interruptor (toggle) ---
       Se pinta a mano en SwitchPill.paintEvent: aquí solo se quita el fondo, el
       borde y el padding que pondría el estilo. */
    QPushButton#Switch {{
        background: transparent;
        border: none;
        padding: 0;
    }}

    /* --- Barra de progreso --- */
    QProgressBar {{
        background-color: {t.FIELD};
        border-radius: 4px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{ background-color: {t.ACCENT}; border-radius: 4px; }}

    /* --- Slider de zoom (sin recuadro: el fondo va transparente) --- */
    QSlider {{
        background: transparent;
        border: none;
    }}
    QSlider::groove:horizontal {{
        background: {t.FIELD};
        height: 6px;
        border-radius: 3px;
    }}
    QSlider::sub-page:horizontal {{ background: {t.ACCENT}; border-radius: 3px; }}
    QSlider::add-page:horizontal {{ background: {t.FIELD}; border-radius: 3px; }}
    QSlider::handle:horizontal {{
        background: {t.BUTTON};
        border: none;
        width: 16px; height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{ background: {t.ACCENT}; }}
    QSlider::handle:horizontal:pressed {{ background: {t.ACCENT_DARK}; }}

    /* --- Etiquetas con color --- */
    QLabel#Muted {{ color: {t.MUTED}; }}
    QLabel#Warning {{ color: {t.WARNING}; font-weight: bold; }}
    QLabel#Info {{ color: {t.INFO_TEXT}; font-weight: bold; }}
    QLabel#Success {{ color: {t.SUCCESS_TEXT}; font-weight: bold; }}
    QLabel#Danger {{ color: {t.DANGER_EDGE}; font-weight: bold; }}
    QLabel#Title {{ font-size: 16px; font-weight: bold; }}
    QLabel#HeaderTitle {{ font-size: 19px; font-weight: bold; }}
    QLabel#FieldLabel {{ color: {t.MUTED}; font-size: 12px; }}

    /* --- Separadores (filas de ajustes) --- */
    QFrame#RowSeparator {{ background-color: rgba(0,0,0,0.18); max-height: 1px; }}

    /* --- Scroll --- */
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{
        background: {t.ACCENT}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
    QScrollBar::handle:horizontal {{
        background: {t.ACCENT}; border-radius: 4px; min-width: 24px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* --- Diálogos --- */
    QDialog {{ background-color: {t.SURFACE}; }}
    QDialog QLabel#DialogTitle {{ color: {t.TEXT}; font-size: 15px; font-weight: bold; }}

    /* --- Menú de la bandeja del sistema --- */
    /* Sin esto el QMenu sale con el estilo claro del escritorio y desentona
       con el tema oscuro (mismo motivo por el que los diálogos son propios). */
    QMenu#TrayMenu {{
        background-color: {t.SURFACE};
        color: {t.TEXT};
        border: 1px solid {t.BORDER};
        padding: 4px;
    }}
    QMenu#TrayMenu::item {{
        padding: 6px 18px;
        border-radius: 4px;
    }}
    QMenu#TrayMenu::item:selected {{
        background-color: {t.ACCENT};
        color: {t.TEXT_SEL};
    }}
    QMenu#TrayMenu::separator {{
        height: 1px;
        background: {t.BORDER};
        margin: 4px 8px;
    }}
    """
