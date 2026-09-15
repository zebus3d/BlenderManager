"""Stylesheet global de la aplicación (sustituye a los ``views/*.kv``).

En Kivy el aspecto vivía repartido en cuatro archivos ``.kv`` con instrucciones
de canvas. En Qt todo eso se expresa con QSS: ``border-radius`` para las
esquinas redondeadas, ``qlineargradient`` para el degradado superior de los
botones y los pseudo-estados ``:hover``/``:pressed``/``:checked``/``:disabled``.

Los widgets se distinguen por ``objectName`` (o por una propiedad dinámica para
las variantes de color), igual que en el PoC.
"""

from ui import theme as t


def build_qss() -> str:
    """Devuelve el stylesheet completo, con los tokens del tema interpolados."""
    # Degradado vertical sutil (blanco 9% arriba -> transparente abajo), el
    # mismo que la textura GRADIENT_TOP de la versión Kivy.
    grad = ("qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 rgba(255,255,255,0.09), stop:1 rgba(255,255,255,0.0))")
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

    /* --- Botón de tarjeta / acción (relleno + degradado + borde) --- */
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
    QPushButton#CardButton[variant="accent"] {{ background-color: {t.ACCENT_BTN}; }}
    QPushButton#CardButton[variant="accent"]:hover {{ background-color: {t.ACCENT_DARK}; }}
    QPushButton#CardButton[variant="accent"]:pressed {{ background-color: {t.ACCENT}; }}
    QPushButton#CardButton[variant="danger"] {{ background-color: {t.DANGER_BTN}; }}
    QPushButton#CardButton[variant="danger"]:hover {{ background-color: {t.DANGER}; }}
    /* Botón que solo lleva un icono (papelera): con el padding normal (14 px por
       lado) el glifo no cabe cuando la rejilla va pequeña y queda el recuadro
       rojo vacío. Con 4 px sobra sitio incluso a zoom 0.6. */
    QPushButton#CardButton[iconOnly="true"] {{ padding: 6px 4px; }}

    /* --- Botón de info (círculo azul con la "i"), diana 24x24 (WCAG 2.5.8) --- */
    QPushButton#IconLink {{
        background-color: {t.INFO_DISC};
        border: none;
        border-radius: 12px;
        min-width: 24px; max-width: 24px;
        min-height: 24px; max-height: 24px;
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
    QPushButton#Switch {{
        background-color: {t.BUTTON};
        border: 1px solid rgba(0,0,0,0.35);
        border-radius: 6px;
        padding: 3px 10px;
        color: {t.TEXT};
        font-weight: bold;
        min-width: 64px;
    }}
    QPushButton#Switch:hover {{ background-color: {t.ACCENT_DARK}; color: {t.TEXT_SEL}; }}
    QPushButton#Switch:checked {{ background-color: {t.ACCENT}; color: {t.TEXT_SEL}; }}

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
    """
