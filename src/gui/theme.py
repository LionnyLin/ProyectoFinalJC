"""Sistema de diseño visual — Lámina Cartográfica de Archivo Hidráulico (#4A4A4A, #CBCBCB, #FFFFE3, #6D8196)."""

import os
from typing import Dict, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QWidget

# Paleta principal solicitada
PALETTE_GRAPHITE = "#4A4A4A"
PALETTE_SILVER = "#CBCBCB"
PALETTE_IVORY = "#FFFFE3"
PALETTE_SLATE = "#6D8196"

# Superficies del Shell superior y consola de bitácora (Grafito #4A4A4A)
SHELL_BG = PALETTE_GRAPHITE
SHELL_SURFACE = "#3D3D3D"
SHELL_ELEVATED = "#595959"
SHELL_HOVER = "#666666"
SHELL_BORDER = "#383838"
SHELL_TEXT = PALETTE_IVORY
SHELL_TEXT_SECONDARY = "#EFEFD2"
SHELL_TEXT_MUTED = PALETTE_SILVER

# Superficie estructural de muelles y marcos (Plata Mineral #CBCBCB)
DOCK_BG = PALETTE_SILVER
DOCK_HOVER = "#BCBCBC"
DOCK_BORDER = PALETTE_GRAPHITE
DOCK_DIVIDER = "#AFAFAF"

# Superficie de dibujo técnico (Lienzo del grafo en Vitela #FFFFE3)
CANVAS_BG = PALETTE_IVORY
CANVAS_GRID_MINOR = "#F1F1D3"
CANVAS_GRID_MAJOR = "#DADABD"
CANVAS_BORDER = PALETTE_GRAPHITE
CANVAS_FLOAT_BG = PALETTE_GRAPHITE
CANVAS_FLOAT_FG = PALETTE_IVORY
CANVAS_FLOAT_HOVER = "#5E5E5E"
CANVAS_FLOAT_BORDER = PALETTE_SLATE

# Superficies de lámina editorial (Tarjetas, inspector, tablas, reproductor, gráficas)
PAPER_BG = PALETTE_IVORY
PAPER_SUBTLE = "#F2F2D5"
PAPER_ALT_ROW = "#F7F7DA"
PAPER_HOVER = "#E6E8DA"
PAPER_BORDER = PALETTE_SILVER
PAPER_RULE = PALETTE_GRAPHITE
INK_PRIMARY = PALETTE_GRAPHITE
INK_SECONDARY = "#4A4A4A"
INK_MUTED = "#5A6570"

# Azul Pizarra (#6D8196) — Foco interactivo, CTA primario, pestaña activa y rutas BFS/DFS
ACCENT_PRIMARY = PALETTE_SLATE
ACCENT_HOVER = "#5A6C80"           # >= 4.9:1 con texto #FFFFE3
ACCENT_TEXT_ON_LIGHT = "#495B6E"     # >= 6.2:1 sobre #FFFFE3
ACCENT_SOFT = "#E4E8DF"              # Tinte suave pizarra sobre vitela
ACCENT_INK = PALETTE_IVORY
ACCENT_ON_DARK = PALETTE_SLATE
ACCENT_ON_DARK_HOVER = "#7D91A6"
ACCENT_ON_DARK_INK = PALETTE_IVORY

# Nodos y aristas del grafo
NODE_SOURCE_FILL = PALETTE_GRAPHITE
NODE_SOURCE_BORDER = PALETTE_SLATE
NODE_SOURCE_TEXT = PALETTE_IVORY
NODE_SINK_FILL = PALETTE_SLATE
NODE_SINK_BORDER = PALETTE_GRAPHITE
NODE_SINK_TEXT = PALETTE_IVORY
NODE_MANHOLE_FILL = PALETTE_IVORY
NODE_MANHOLE_BORDER = PALETTE_GRAPHITE
NODE_MANHOLE_TEXT = PALETTE_GRAPHITE
NODE_SURCHARGE_RING = "#EF4444"
NODE_SURCHARGE_RING_DEEP = "#991B1B"

PIPE_IDLE_COLOR = PALETTE_SLATE
PIPE_HIGHLIGHT_PATH = PALETTE_SLATE
PIPE_HIGHLIGHT_HALO = PALETTE_SILVER
PIPE_SELECTED_HALO = PALETTE_GRAPHITE
PIPE_OVERLOAD_HALO = "#FCA5A5"

STATUS_OK_LIGHT = "#15803D"
STATUS_OK_DARK = "#86EFAC"
STATUS_WARN_LIGHT = "#9A3412"
STATUS_ERR_LIGHT = "#B91C1C"

# Escala oficial de utilización (Sección 7 — preservada intacta)
COLOR_SCALE_LEGEND = [
    ("0–25 %", "#22c55e", "Baja utilización"),
    (">25–50 %", "#eab308", "Utilización moderada"),
    (">50–75 %", "#f97316", "Utilización alta"),
    (">75–100 %", "#ef4444", "Cercana a capacidad máxima"),
    (">100 %", "#991b1b", "Capacidad excedida"),
]

# Colores de texto legibles sobre fondo vitela #FFFFE3 por nivel de utilización
TIER_TEXT_ON_LIGHT = [
    "#15803d",
    "#854d0e",
    "#c2410c",
    "#dc2626",
    "#991b1b",
]

# Umbrales responsivos de ventana
BREAKPOINT_COMPACT = 940
BREAKPOINT_MEDIUM = 1220
BREAKPOINT_SHORT = 650

# Diccionarios de localización integral al español para la capa GUI
SCENARIO_ES_MAP: Dict[str, str] = {
    "Dry weather": "Tiempo seco",
    "Light rain": "Lluvia ligera",
    "Moderate rain": "Lluvia moderada",
    "Heavy rain": "Lluvia fuerte",
    "Extreme rain": "Lluvia extrema",
}

SCENARIO_ES_SHORT_MAP: Dict[str, str] = {
    "Dry weather": "Seco",
    "Light rain": "Ligera",
    "Moderate rain": "Mod.",
    "Heavy rain": "Fuerte",
    "Extreme rain": "Extrema",
}

SPLIT_RULE_TO_ES: Dict[str, str] = {
    "proportional": "Proporcional",
    "equal": "Equitativa",
}
ES_TO_SPLIT_RULE: Dict[str, str] = {v: k for k, v in SPLIT_RULE_TO_ES.items()}

SOURCE_DIST_TO_ES: Dict[str, str] = {
    "capacity": "Por capacidad",
    "equal": "Uniforme (1/8)",
}
ES_TO_SOURCE_DIST: Dict[str, str] = {v: k for k, v in SOURCE_DIST_TO_ES.items()}


def translate_scenario_name(condition: str, compact: bool = False) -> str:
    """Traduce el nombre del escenario del dataset al español para la interfaz."""
    mapping = SCENARIO_ES_SHORT_MAP if compact else SCENARIO_ES_MAP
    return mapping.get(condition, condition)


def format_scenario_display(scenario_id: int, condition: str, intensity_mm_h: float) -> str:
    """Formatea la etiqueta visible del escenario en español."""
    es_name = translate_scenario_name(condition, compact=False)
    return f"Esc. {scenario_id}: {es_name} ({intensity_mm_h:.0f} mm/h)"


# Aliases de compatibilidad
BG_DARK = SHELL_BG
BG_PANEL = PAPER_BG
BG_CARD = DOCK_BG
BG_CANVAS = CANVAS_BG
BORDER_COLOR = PAPER_RULE
ACCENT_BLUE = ACCENT_PRIMARY
ACCENT_GOLD = ACCENT_ON_DARK
TEXT_PRIMARY = INK_PRIMARY
TEXT_SECONDARY = INK_SECONDARY
TEXT_MUTED = INK_MUTED

_MPL_FONTS_REGISTERED = False
_QT_FONTS_REGISTERED = False
_DPI_AWARENESS_SET = False


def enable_dpi_awareness() -> None:
    """Configura la política HiDPI de Qt antes de instanciar QApplication."""
    global _DPI_AWARENESS_SET
    if _DPI_AWARENESS_SET:
        return
    _DPI_AWARENESS_SET = True
    if QApplication.instance() is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )


def register_local_inter_fonts() -> bool:
    """Registra las fuentes en `assets/fonts/` para Qt y Matplotlib."""
    global _MPL_FONTS_REGISTERED, _QT_FONTS_REGISTERED
    fonts_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")
    )
    if not os.path.isdir(fonts_dir):
        return False

    registered = False
    if not _MPL_FONTS_REGISTERED:
        _MPL_FONTS_REGISTERED = True
        try:
            from matplotlib import font_manager
        except Exception:
            font_manager = None
        if font_manager is not None:
            for fname in os.listdir(fonts_dir):
                if fname.lower().endswith((".ttf", ".otf")):
                    try:
                        font_manager.fontManager.addfont(os.path.join(fonts_dir, fname))
                        registered = True
                    except Exception:
                        pass

    if not _QT_FONTS_REGISTERED and QApplication.instance() is not None:
        _QT_FONTS_REGISTERED = True
        for fname in os.listdir(fonts_dir):
            if fname.lower().endswith((".ttf", ".otf")):
                try:
                    fid = QFontDatabase.addApplicationFont(os.path.join(fonts_dir, fname))
                    if fid != -1:
                        registered = True
                except Exception:
                    pass

    return registered


def resolve_fonts() -> Tuple[str, str, str, bool]:
    """Resuelve familias tipográficas `(ui_font, mono_font, display_font, inter_available)`."""
    register_local_inter_fonts()
    families = QFontDatabase.families()
    available = {f.lower(): f for f in families}
    inter_available = any("inter" in k for k in available)

    ui_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
    for candidate in (
        "segoe ui variable text",
        "segoe ui",
        "inter",
        "arial",
        "noto sans",
        "dejavu sans",
    ):
        if candidate in available:
            ui_family = available[candidate]
            break

    display_family = ui_family
    for candidate in (
        "inter medium",
        "inter semibold",
        "inter",
        "segoe ui variable display",
        "segoe ui",
    ):
        if candidate in available:
            display_family = available[candidate]
            break

    mono_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
    for candidate in (
        "jetbrainsmono nerd font",
        "jetbrains mono",
        "cascadia mono",
        "firacode nerd font",
        "consolas",
        "dejavu sans mono",
        "liberation mono",
        "courier new",
    ):
        if candidate in available:
            mono_family = available[candidate]
            break

    return ui_family, mono_family, display_family, inter_available


def apply_variant(widget: QWidget, variant: str) -> None:
    """Actualiza la propiedad dinámica `variant` y refresca el QSS del widget."""
    widget.setProperty("variant", variant)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def build_stylesheet(ui_font: str, mono_font: str, display_font: str) -> str:
    """Construye la hoja de estilo QSS global manteniendo la paleta oficial exacta."""
    return f"""
QWidget {{
    font-family: "{ui_font}";
    color: {INK_PRIMARY};
}}
QMainWindow, QWidget#MainCentral {{
    background-color: {DOCK_BORDER};
}}
QFrame#TopBar {{
    background-color: {SHELL_BG};
    border: none;
}}
QFrame#TopBar QLabel {{
    background-color: transparent;
    color: {SHELL_TEXT};
}}
QLabel#AppTitle {{
    font-family: "{display_font}";
    font-size: 11pt;
    font-weight: bold;
    color: {SHELL_TEXT};
}}
QLabel#AppSubtitle {{
    font-size: 8pt;
    color: {SHELL_TEXT_MUTED};
}}
QFrame#TopBarAccent {{
    background-color: {ACCENT_PRIMARY};
    border: none;
}}
QFrame#StatusBarFrame {{
    background-color: {SHELL_BG};
    border: none;
}}
QFrame#StatusBarAccent {{
    background-color: {ACCENT_PRIMARY};
    border: none;
}}
QLabel#StatusLabel {{
    background-color: transparent;
    color: {SHELL_TEXT};
    font-size: 8pt;
}}
QLabel#ShortcutsHintLabel {{
    background-color: transparent;
    color: {SHELL_TEXT_MUTED};
    font-size: 8pt;
}}

QSplitter#MainSplitter::handle {{
    background-color: {DOCK_BORDER};
}}
QFrame#LeftPanel, QFrame#CenterPanel, QFrame#RightPanel, QWidget#LeftScrollContent, QWidget#LeftScrollPage {{
    background-color: {DOCK_BG};
}}
QFrame#DockSubBar, QFrame#InspectorActionsDock, QWidget#KpiRow {{
    background-color: {DOCK_BG};
}}
QWidget#ChartsHost, QWidget#CompTableWrap, QWidget#TourBody {{
    background-color: {PAPER_BG};
}}
QScrollArea#LeftScrollArea {{
    background-color: {DOCK_BG};
    border: none;
}}
QFrame#DockDivider {{
    background-color: {DOCK_BORDER};
    border: none;
}}
QFrame#PaperDivider {{
    background-color: {PAPER_BORDER};
    border: none;
}}

QFrame#SectionCard {{
    background-color: {PAPER_BG};
    border: 1px solid {DOCK_BORDER};
}}
QFrame#SectionHeader[dark="true"] {{
    background-color: {SHELL_BG};
}}
QFrame#SectionHeader[dark="false"] {{
    background-color: {ACCENT_PRIMARY};
}}
QLabel#SectionHeaderLabel {{
    background-color: transparent;
    color: {SHELL_TEXT};
    font-family: "{display_font}";
    font-size: 9pt;
    font-weight: bold;
}}
QFrame#SectionRule[dark="true"] {{
    background-color: {ACCENT_PRIMARY};
}}
QFrame#SectionRule[dark="false"] {{
    background-color: {DOCK_BORDER};
}}
QWidget#SectionBody {{
    background-color: {PAPER_BG};
}}

QFrame#RightSheetFrame {{
    background-color: {PAPER_BG};
    border: 1px solid {DOCK_BORDER};
}}
QTabWidget#RightTabs::pane {{
    background-color: {PAPER_BG};
    border: none;
    border-top: 1px solid {DOCK_BORDER};
}}
QTabWidget#RightTabs > QTabBar {{
    background-color: {DOCK_BG};
}}
QTabWidget#RightTabs > QTabBar::tab {{
    background-color: {PAPER_SUBTLE};
    color: {INK_PRIMARY};
    border: 1px solid {DOCK_BORDER};
    border-bottom: none;
    padding: 6px 10px;
    margin-top: 5px;
    margin-right: 2px;
    font-weight: bold;
    font-size: 9pt;
}}
QTabWidget#RightTabs > QTabBar::tab:hover:!selected {{
    background-color: {PAPER_HOVER};
}}
QTabWidget#RightTabs > QTabBar::tab:selected {{
    background-color: {ACCENT_PRIMARY};
    color: {ACCENT_INK};
}}
QTabWidget#RightTabs[compactTabs="true"] > QTabBar::tab {{
    padding: 5px 6px;
    font-size: 8pt;
    font-weight: normal;
}}

QFrame#TelemetryHeader {{
    background-color: {DOCK_BG};
    border: 1px solid {DOCK_BORDER};
}}
QWidget#TelemetryTopRow {{
    background-color: {PAPER_BG};
}}
QFrame#ClockPill {{
    background-color: {SHELL_BG};
    border: none;
}}
QLabel#ClockLabel {{
    background-color: transparent;
    color: {SHELL_TEXT};
    font-family: "{mono_font}";
    font-size: 9pt;
    font-weight: bold;
}}
QFrame#KpiCard {{
    background-color: {PAPER_BG};
}}
QFrame#KpiTopRule {{
    background-color: {ACCENT_PRIMARY};
}}
QLabel#KpiCaption {{
    background-color: transparent;
    color: {INK_MUTED};
    font-size: 7pt;
    font-weight: bold;
}}
QLabel#KpiValue {{
    background-color: transparent;
    color: {INK_PRIMARY};
    font-family: "{mono_font}";
    font-size: 10pt;
    font-weight: bold;
}}

QFrame#MapModeBar {{
    background-color: {DOCK_BG};
    border: 1px solid {DOCK_BORDER};
    border-bottom: none;
}}
QLabel#MapModeCaption {{
    background-color: transparent;
    color: {INK_PRIMARY};
    font-size: 8pt;
    font-weight: bold;
}}
QFrame#SegmentedFrame {{
    background-color: {DOCK_BORDER};
    border: 1px solid {DOCK_BORDER};
}}
QFrame#PlayerBar {{
    background-color: {PAPER_BG};
    border: 1px solid {DOCK_BORDER};
}}
QLabel#MassAuditLabel {{
    background-color: {ACCENT_SOFT};
    color: {STATUS_OK_LIGHT};
    border: 1px solid {DOCK_BORDER};
    font-family: "{mono_font}";
    font-size: 8pt;
    font-weight: bold;
    padding: 2px 8px;
}}

QPushButton[variant="primary"] {{
    background-color: {ACCENT_PRIMARY};
    color: {ACCENT_INK};
    border: 1px solid {INK_PRIMARY};
    font-weight: bold;
    padding: 4px 10px;
}}
QPushButton[variant="primary"]:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton[variant="primary"]:disabled {{
    background-color: {DOCK_BG};
    color: {INK_MUTED};
    border: 1px solid {DOCK_DIVIDER};
}}
QPushButton[variant="dark_primary"] {{
    background-color: {ACCENT_ON_DARK};
    color: {ACCENT_ON_DARK_INK};
    border: 1px solid {ACCENT_ON_DARK};
    font-weight: bold;
    padding: 4px 10px;
}}
QPushButton[variant="dark_primary"]:hover {{
    background-color: {ACCENT_ON_DARK_HOVER};
}}
QPushButton[variant="dark_secondary"] {{
    background-color: {SHELL_ELEVATED};
    color: {SHELL_TEXT};
    border: 1px solid {SHELL_BORDER};
    padding: 4px 9px;
}}
QPushButton[variant="dark_secondary"]:hover {{
    background-color: {SHELL_HOVER};
}}
QPushButton[variant="dark_tour"] {{
    background-color: {SHELL_SURFACE};
    color: {PALETTE_IVORY};
    border: 1px solid {PALETTE_IVORY};
    font-weight: bold;
    padding: 4px 10px;
}}
QPushButton[variant="dark_tour"]:hover {{
    background-color: {SHELL_ELEVATED};
    border: 1px solid {ACCENT_ON_DARK_HOVER};
}}
QPushButton[variant="dark_ghost"] {{
    background-color: {SHELL_BG};
    color: {SHELL_TEXT_SECONDARY};
    border: 1px solid {SHELL_BORDER};
    padding: 4px 9px;
}}
QPushButton[variant="dark_ghost"]:hover {{
    background-color: {SHELL_ELEVATED};
}}
QPushButton[variant="dock_secondary"] {{
    background-color: {DOCK_BG};
    color: {INK_PRIMARY};
    border: 1px solid {DOCK_BORDER};
    padding: 4px 8px;
}}
QPushButton[variant="dock_secondary"]:hover {{
    background-color: {DOCK_HOVER};
}}
QPushButton[variant="dock_secondary"]:disabled {{
    background-color: {DOCK_BG};
    color: {INK_MUTED};
    border: 1px solid {DOCK_DIVIDER};
}}
QPushButton[variant="light_secondary"] {{
    background-color: {PAPER_SUBTLE};
    color: {INK_PRIMARY};
    border: 1px solid {DOCK_BORDER};
    padding: 4px 8px;
}}
QPushButton[variant="light_secondary"]:hover {{
    background-color: {PAPER_HOVER};
}}
QPushButton[variant="light_secondary"]:disabled {{
    background-color: {PAPER_SUBTLE};
    color: {INK_MUTED};
    border: 1px solid {PAPER_BORDER};
}}

QPushButton[compactPad="true"] {{
    padding: 2px 6px;
}}

QToolButton#FileMenuButton {{
    background-color: {SHELL_ELEVATED};
    color: {SHELL_TEXT};
    border: 1px solid {ACCENT_PRIMARY};
    padding: 4px 10px;
    font-size: 8pt;
    font-weight: bold;
}}
QToolButton#FileMenuButton:hover {{
    background-color: {SHELL_HOVER};
}}
QToolButton#FileMenuButton::menu-indicator {{
    image: none;
    width: 0px;
}}
QMenu {{
    background-color: {SHELL_BG};
    color: {SHELL_TEXT};
    border: 1px solid {ACCENT_PRIMARY};
    padding: 3px;
}}
QMenu::item {{
    padding: 5px 14px;
    color: {SHELL_TEXT};
}}
QMenu::item:selected {{
    background-color: {ACCENT_PRIMARY};
    color: {ACCENT_INK};
}}
QMenu::separator {{
    height: 1px;
    background: {SHELL_BORDER};
    margin: 3px 6px;
}}

QComboBox, QDoubleSpinBox, QLineEdit {{
    background-color: {PAPER_BG};
    color: {INK_PRIMARY};
    border: 1px solid {DOCK_BORDER};
    padding: 3px 6px;
    selection-background-color: {ACCENT_PRIMARY};
    selection-color: {ACCENT_INK};
}}
QComboBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border: 1px solid {ACCENT_PRIMARY};
}}
QDoubleSpinBox {{
    font-family: "{mono_font}";
    font-size: 9pt;
}}
QComboBox QAbstractItemView {{
    background-color: {PAPER_BG};
    color: {INK_PRIMARY};
    border: 1px solid {DOCK_BORDER};
    selection-background-color: {ACCENT_PRIMARY};
    selection-color: {ACCENT_INK};
    outline: 0;
}}

QCheckBox, QRadioButton {{
    background-color: transparent;
    color: {INK_PRIMARY};
    spacing: 5px;
    font-size: 8pt;
}}

QSlider::groove:horizontal {{
    background-color: {DOCK_BG};
    height: 8px;
    border: 1px solid {PAPER_BORDER};
}}
QSlider::handle:horizontal {{
    background-color: {ACCENT_PRIMARY};
    border: 1px solid {INK_PRIMARY};
    width: 16px;
    margin: -4px 0px;
}}
QSlider::handle:horizontal:hover {{
    background-color: {ACCENT_HOVER};
}}

QTableWidget {{
    background-color: {PAPER_BG};
    alternate-background-color: {PAPER_ALT_ROW};
    color: {INK_PRIMARY};
    gridline-color: {PAPER_BORDER};
    border: none;
    font-family: "{mono_font}";
    font-size: 8pt;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {INK_PRIMARY};
}}
QTableWidget::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {INK_PRIMARY};
}}
QHeaderView::section {{
    background-color: {SHELL_BG};
    color: {SHELL_TEXT};
    border: none;
    border-right: 1px solid {ACCENT_PRIMARY};
    padding: 4px 5px;
    font-family: "{ui_font}";
    font-size: 8pt;
    font-weight: bold;
}}

QPlainTextEdit#TraversalLog {{
    background-color: {SHELL_BG};
    color: {SHELL_TEXT};
    border: 1px solid {ACCENT_PRIMARY};
    font-family: "{mono_font}";
    font-size: 8pt;
    padding: 5px;
}}
QTextEdit#InspectorText {{
    background-color: {PAPER_BG};
    color: {INK_PRIMARY};
    border: none;
    font-family: "{mono_font}";
    font-size: 9pt;
    padding: 8px;
}}

QFrame#SubBar, QFrame#FilterBar, QFrame#CompTopBar, QFrame#InspectorActions, QFrame#InspectorSubCard {{
    background-color: {PAPER_SUBTLE};
}}
QFrame#TourCard {{
    background-color: {PAPER_BG};
    border: 1px solid {DOCK_BORDER};
}}
QFrame#TourHeader {{
    background-color: {ACCENT_PRIMARY};
}}
QFrame#TourFooter {{
    background-color: {PAPER_SUBTLE};
}}
QFrame#ImpactBanner {{
    background-color: #EEF2F6;
    border: 1px solid #94A3B8;
}}
QFrame#ImpactStripe {{
    background-color: #1D4ED8;
}}

QScrollBar:vertical {{
    background: {PAPER_SUBTLE};
    width: 11px;
    margin: 0px;
    border-left: 1px solid {PAPER_BORDER};
}}
QScrollBar::handle:vertical {{
    background: {DOCK_BG};
    min-height: 24px;
    border: 1px solid {DOCK_BORDER};
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT_PRIMARY};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {PAPER_SUBTLE};
    height: 11px;
    margin: 0px;
    border-top: 1px solid {PAPER_BORDER};
}}
QScrollBar::handle:horizontal {{
    background: {DOCK_BG};
    min-width: 24px;
    border: 1px solid {DOCK_BORDER};
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT_PRIMARY};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QMessageBox {{
    background-color: {PAPER_BG};
    color: {INK_PRIMARY};
}}
QMessageBox QLabel {{
    background-color: transparent;
    color: {INK_PRIMARY};
}}
"""
