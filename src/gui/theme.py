"""Sistema de diseño visual — Lámina Cartográfica de Archivo Hidráulico (#4A4A4A, #CBCBCB, #FFFFE3, #6D8196)."""

import ctypes
import os
import tkinter as tk
from tkinter import font as tkfont
from typing import Dict, Tuple

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
NODE_SURCHARGE_RING = "#D97706"

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

HYETOGRAPH_TO_ES: Dict[str, str] = {
    "uniform": "Uniforme",
    "triangular": "Triangular",
}
ES_TO_HYETOGRAPH: Dict[str, str] = {v: k for k, v in HYETOGRAPH_TO_ES.items()}


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

_FONTS_REGISTERED = False


def _register_local_inter_fonts() -> bool:
    """Registra archivos de fuentes en assets/fonts/ para títulos en Windows y Matplotlib."""
    global _FONTS_REGISTERED
    fonts_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")
    )
    if _FONTS_REGISTERED:
        return os.path.isdir(fonts_dir)
    _FONTS_REGISTERED = True

    if not os.path.isdir(fonts_dir):
        return False

    FR_PRIVATE = 0x10
    try:
        from matplotlib import font_manager
    except Exception:
        font_manager = None

    registered = False
    for fname in os.listdir(fonts_dir):
        if fname.lower().endswith((".ttf", ".otf")):
            fpath = os.path.join(fonts_dir, fname)
            if os.name == "nt":
                try:
                    ctypes.windll.gdi32.AddFontResourceExW(fpath, FR_PRIVATE, 0)
                    registered = True
                except Exception:
                    pass
            if font_manager is not None:
                try:
                    font_manager.fontManager.addfont(fpath)
                    registered = True
                except Exception:
                    pass
    return registered


def resolve_display_font(root: tk.Misc) -> str:
    """Resuelve la fuente para títulos principales (`Inter` 500/SemiBold si está disponible)."""
    _register_local_inter_fonts()
    available = {f.lower(): f for f in tkfont.families(root)}
    for candidate in ("inter medium", "inter semibold", "inter", "segoe ui variable display", "segoe ui"):
        if candidate in available:
            return available[candidate]
    return "Segoe UI"


def resolve_fonts(root: tk.Misc) -> Tuple[str, str, bool]:
    """Resuelve familia sans estándar de UI (`Segoe UI`) y familia monoespaciada.

    Retorna `(ui_font_family, mono_font_family, inter_available)`.
    """
    _register_local_inter_fonts()
    available = {f.lower(): f for f in tkfont.families(root)}
    inter_available = any("inter" in k for k in available)

    ui_family = "Segoe UI"
    for candidate in ("segoe ui variable text", "segoe ui", "arial"):
        if candidate in available:
            ui_family = available[candidate]
            break

    mono_family = "Consolas"
    for candidate in (
        "jetbrainsmono nerd font",
        "jetbrains mono",
        "cascadia mono",
        "firacode nerd font",
        "consolas",
        "courier new",
    ):
        if candidate in available:
            mono_family = available[candidate]
            break

    return ui_family, mono_family, inter_available
