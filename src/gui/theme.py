"""Sistema de diseño visual — Lámina Cartográfica de Archivo Hidráulico."""

from __future__ import annotations

import ctypes
import os
import tkinter as tk
from tkinter import font as tkfont, ttk
from typing import Dict, List, Tuple

# Paleta base
PALETTE_GRAPHITE, PALETTE_SILVER, PALETTE_IVORY, PALETTE_SLATE = "#4A4A4A", "#CBCBCB", "#FFFFE3", "#6D8196"

# Superficies
SHELL_BG, SHELL_SURFACE, SHELL_ELEVATED, SHELL_HOVER, SHELL_BORDER = "#4A4A4A", "#3D3D3D", "#595959", "#666666", "#383838"
SHELL_TEXT, SHELL_TEXT_SECONDARY, SHELL_TEXT_MUTED = "#FFFFE3", "#EFEFD2", "#CBCBCB"
DOCK_BG, DOCK_HOVER, DOCK_BORDER, DOCK_DIVIDER = "#CBCBCB", "#BCBCBC", "#4A4A4A", "#AFAFAF"
PAPER_BG, PAPER_SUBTLE, PAPER_ALT_ROW, PAPER_HOVER = "#FFFFE3", "#F2F2D5", "#F7F7DA", "#E6E8DA"
PAPER_BORDER, PAPER_RULE, INK_PRIMARY, INK_MUTED = "#CBCBCB", "#4A4A4A", "#4A4A4A", "#5A6570"
ACCENT_PRIMARY, ACCENT_HOVER, ACCENT_TEXT, ACCENT_SOFT, ACCENT_INK = "#6D8196", "#5A6C80", "#495B6E", "#E4E8DF", "#FFFFE3"
CANVAS_BG, CANVAS_GRID_MINOR, CANVAS_GRID_MAJOR = "#FFFFE3", "#F1F1D3", "#DADABD"

# Nodos y tuberías
NODE_SOURCE_FILL, NODE_SOURCE_OUTLINE, NODE_SOURCE_TEXT = "#4A4A4A", "#6D8196", "#FFFFE3"
NODE_SINK_FILL, NODE_SINK_OUTLINE, NODE_SINK_TEXT = "#6D8196", "#4A4A4A", "#FFFFE3"
NODE_MANHOLE_FILL, NODE_MANHOLE_OUTLINE, NODE_MANHOLE_TEXT = "#FFFFE3", "#4A4A4A", "#4A4A4A"
PIPE_IDLE_COLOR, HIGHLIGHT_PATH_COLOR, SELECTED_HALO = "#6D8196", "#6D8196", "#4A4A4A"
OVERLOAD_RING_COLOR, OVERLOAD_RING_SEVERE = "#EF4444", "#991B1B"
STATUS_ERR_LIGHT, ACCENT_TEXT_ON_LIGHT = "#B91C1C", ACCENT_TEXT

# Recorridos direccionales y estados UI
TRAV_DOWNSTREAM_EDGE = "#0284C7"
TRAV_DOWNSTREAM_NODE = "#BAE6FD"
TRAV_DOWNSTREAM_OUTLINE = "#0369A1"
TRAV_UPSTREAM_EDGE = "#7C3AED"
TRAV_UPSTREAM_NODE = "#EDE9FE"
TRAV_UPSTREAM_OUTLINE = "#5B21B6"
TRAV_BFS_EDGE = "#0D9488"
TRAV_BFS_NODE = "#CCFBF1"
TRAV_BFS_OUTLINE = "#0F766E"
TRAV_BFS_PATH = "#1D4ED8"
TRAV_DFS_EDGE = "#4F46E5"
TRAV_DFS_NODE = "#E0E7FF"
TRAV_DFS_OUTLINE = "#3730A3"
TRAV_DFS_PATH = "#BE185D"
TRAV_ACTIVE_COLOR = "#D97706"
TRAV_ORIGIN_FILL = "#0F172A"
TRAV_DIM_PIPE = "#D4D4C8"
TRAV_DIM_NODE = "#F5F5E6"
TRAV_DIM_OUTLINE = "#B8B8A8"
TRAV_DIM_TEXT = "#9CA3AF"
ERROR_TEXT = "#DC2626"
ERROR_BG = "#FEF2F2"
OK_TEXT = "#15803D"
DISABLED_BG = "#E5E7EB"
DISABLED_FG = "#9CA3AF"

# Escala oficial 5 colores (PDF Sección 7)
COLOR_SCALE_LEGEND: List[Tuple[str, str, str]] = [
    ("0–25 %", "#22c55e", "Baja"),
    (">25–50 %", "#eab308", "Moderada"),
    (">50–75 %", "#f97316", "Alta"),
    (">75–100 %", "#ef4444", "Cercana máx."),
    (">100 %", "#991b1b", "Excedida"),
]
TIER_TEXT_ON_LIGHT: Dict[str, str] = {
    "#22c55e": "#15803d", "#eab308": "#854d0e", "#f97316": "#c2410c",
    "#ef4444": "#dc2626", "#991b1b": "#991b1b",
}

# Modos de lectura cartográfica: id, etiqueta por ancho (full / mid / short)
MAP_MODES: List[Tuple[str, Tuple[str, str, str]]] = [
    ("instant", ("Instantáneo O(t)", "Instantáneo O(t)", "O(t)")),
    ("peak", ("Pico Máximo", "Pico Máximo", "Pico")),
    ("overload_minutes", ("Minutos en Sobrecarga", "Min. Sobrecarga", "Min >100%")),
]
MAP_MODE_KPI_CAPTIONS: Dict[str, Tuple[str, str, str, str]] = {
    "instant": ("UTILIZACIÓN MÁX.", "CRÍTICAS (>75–100%)", "SOBRECARGA (>100%)", "DESCARGA PTAR 31"),
    "peak": ("PICO MÁX. UTIL.", "CRÍTICAS PICO (>75–100%)", "SOBRECARGA PICO (>100%)", "PICO DESCARGA PTAR 31"),
    "overload_minutes": ("MÁX. SOBREC. ACUM.", "TUBERÍAS >0 min >100%", "COLAPSO CRÓNICO (>75%)", "VOLUMEN PTAR 31"),
}

# Traducciones al español
SCENARIO_ES_MAP: Dict[str, str] = {
    "Dry weather": "Tiempo seco", "Light rain": "Lluvia ligera",
    "Moderate rain": "Lluvia moderada", "Heavy rain": "Lluvia fuerte", "Extreme rain": "Lluvia extrema",
}
SCENARIO_SHORT_ES: Dict[str, str] = {
    "Dry weather": "Seco", "Light rain": "Ligera",
    "Moderate rain": "Mod.", "Heavy rain": "Fuerte", "Extreme rain": "Extrema",
}
SPLIT_RULE_TO_ES: Dict[str, str] = {"proportional": "Proporcional", "equal": "Equitativa"}
SPLIT_RULE_FROM_ES: Dict[str, str] = {"Proporcional": "proportional", "Equitativa": "equal"}
SOURCE_DIST_TO_ES: Dict[str, str] = {"capacity": "Por capacidad", "equal": "Uniforme (1/8)"}
SOURCE_DIST_FROM_ES: Dict[str, str] = {"Por capacidad": "capacity", "Uniforme (1/8)": "equal"}

ES_TO_SPLIT_RULE, ES_TO_SOURCE_DIST = SPLIT_RULE_FROM_ES, SOURCE_DIST_FROM_ES

# Umbrales responsivos de ventana (px) y velocidades del reproductor (ms por paso)
BREAKPOINT_COMPACT, BREAKPOINT_MEDIUM, BREAKPOINT_SHORT = 940, 1220, 650
BREAKPOINT_FULL_ACTIONS, BREAKPOINT_HINT = 1660, 980
PLAY_SPEED_MS: Dict[str, int] = {"0.5x": 840, "1x": 420, "2x": 210, "5x": 85, "10x": 40}
MASS_BALANCE_OK_M3 = 1e-6
ACCENT_ON_DARK, ACCENT_ON_DARK_HOVER, ACCENT_ON_DARK_INK = PALETTE_SLATE, "#7D91A6", PALETTE_IVORY

_DPI_AWARENESS_SET = False
_FONTS_REGISTERED = False


def translate_scenario_name(condition: str, short: bool = False) -> str:
    """Traduce la condición climática del dataset al español."""
    return (SCENARIO_SHORT_ES if short else SCENARIO_ES_MAP).get(condition, condition)


def format_scenario_label(scenario_id: int, condition: str, intensity_mm_h: float) -> str:
    """Formatea la etiqueta visible del escenario en español."""
    return f"Esc. {scenario_id}: {translate_scenario_name(condition)} ({intensity_mm_h:g} mm/h)"


def resolve_dpi_scale(root: tk.Misc) -> float:
    """Factor de escala DPI respecto a 96 DPI (entre 1.0 y 3.0)."""
    try:
        if (dpi := float(root.winfo_fpixels("1i"))) > 0.0:
            return max(1.0, min(3.0, dpi / 96.0))
    except Exception:
        pass
    return 1.0


def enable_dpi_awareness() -> None:
    """Activa DPI awareness nativo en Windows sin afectar Linux/macOS."""
    global _DPI_AWARENESS_SET
    if _DPI_AWARENESS_SET or os.name != "nt":
        return
    _DPI_AWARENESS_SET = True
    for fn in (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(1),
               lambda: ctypes.windll.user32.SetProcessDPIAware()):
        try:
            fn()
            return
        except Exception:
            continue


def register_local_fonts() -> None:
    """Registra fuentes locales en assets/fonts/ para Matplotlib y Win32 GDI."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    _FONTS_REGISTERED = True
    fonts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts"))
    if not os.path.isdir(fonts_dir):
        return
    try:
        from matplotlib import font_manager
    except Exception:
        font_manager = None
    for fname in sorted(os.listdir(fonts_dir)):
        if not fname.lower().endswith((".ttf", ".otf")):
            continue
        fpath = os.path.join(fonts_dir, fname)
        if os.name == "nt":
            try:
                ctypes.windll.gdi32.AddFontResourceExW(fpath, 0x10, 0)
            except Exception:
                pass
        if font_manager is not None:
            try:
                font_manager.fontManager.addfont(fpath)
            except Exception:
                pass


def resolve_fonts(root: tk.Misc) -> Dict[str, Tuple[str, int, str]]:
    """Elige tipografías disponibles en Tk y devuelve el mapa estándar de roles."""
    register_local_fonts()
    avail = {f.lower(): f for f in tkfont.families(root)}
    ui = next((avail[c] for c in ("inter", "segoe ui", "dejavu sans", "arial") if c in avail), "TkDefaultFont")
    mono = next(
        (avail[c] for c in ("cascadia mono", "consolas", "dejavu sans mono", "courier new") if c in avail),
        "TkFixedFont",
    )
    return {
        "headline": (ui, 13, "bold"), "title": (ui, 10, "bold"), "body": (ui, 9, "normal"),
        "label": (ui, 9, "bold"), "mono": (mono, 9, "normal"), "mono_bold": (mono, 9, "bold"),
        "small": (ui, 8, "normal"),
    }


def apply_ttk_theme(root: tk.Misc, fonts: Dict[str, Tuple[str, int, str]]) -> ttk.Style:
    """Configura el tema 'clam' plano con la paleta cartográfica oficial."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    cfg, mp = style.configure, style.map
    cfg(".", background=PAPER_BG, foreground=INK_PRIMARY, font=fonts["body"], bordercolor=PAPER_BORDER, focuscolor=ACCENT_PRIMARY)
    cfg("TFrame", background=PAPER_BG)
    cfg("TLabel", background=PAPER_BG, foreground=INK_PRIMARY, font=fonts["body"])
    cfg("TNotebook", background=DOCK_BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    cfg("TNotebook.Tab", background=DOCK_BG, foreground=INK_PRIMARY, font=fonts["label"],
        padding=(10, 5), borderwidth=1, lightcolor=DOCK_BORDER, darkcolor=DOCK_BORDER, bordercolor=DOCK_BORDER)
    mp("TNotebook.Tab", background=[("selected", PAPER_BG), ("active", DOCK_HOVER)], foreground=[("selected", ACCENT_TEXT)])
    cfg("Treeview", background=PAPER_BG, fieldbackground=PAPER_BG, foreground=INK_PRIMARY,
        font=fonts["mono"], rowheight=22, borderwidth=1, relief="flat")
    mp("Treeview", background=[("selected", ACCENT_PRIMARY)], foreground=[("selected", ACCENT_INK)])
    cfg("Treeview.Heading", background=DOCK_BG, foreground=INK_PRIMARY, font=fonts["label"], relief="flat", borderwidth=1)
    mp("Treeview.Heading", background=[("active", DOCK_HOVER)])
    cfg("TCombobox", fieldbackground=PAPER_BG, background=DOCK_BG, foreground=INK_PRIMARY,
        selectbackground=ACCENT_PRIMARY, selectforeground=ACCENT_INK, arrowcolor=INK_PRIMARY,
        bordercolor=PAPER_RULE, lightcolor=PAPER_RULE, darkcolor=PAPER_RULE, padding=(5, 3))
    mp("TCombobox", fieldbackground=[("readonly", PAPER_BG)], foreground=[("readonly", INK_PRIMARY)], background=[("active", DOCK_HOVER)])
    for opt, val in (("background", PAPER_BG), ("foreground", INK_PRIMARY), ("selectBackground", ACCENT_PRIMARY), ("selectForeground", ACCENT_INK)):
        root.option_add(f"*TCombobox*Listbox.{opt}", val)
    cfg("TScrollbar", background=DOCK_BG, troughcolor=PAPER_SUBTLE, arrowcolor=INK_PRIMARY,
        bordercolor=PAPER_BORDER, lightcolor=DOCK_BG, darkcolor=DOCK_BG, relief="flat", width=11)
    mp("TScrollbar", background=[("active", ACCENT_PRIMARY), ("pressed", ACCENT_HOVER)])
    cfg("TScale", background=ACCENT_PRIMARY, troughcolor=DOCK_BG, bordercolor=PAPER_RULE,
        lightcolor=ACCENT_PRIMARY, darkcolor=ACCENT_PRIMARY, sliderlength=14, sliderrelief="flat")
    mp("TScale", background=[("active", ACCENT_HOVER)])
    cfg("TCheckbutton", background=PAPER_BG, foreground=INK_PRIMARY, font=fonts["body"],
        indicatorcolor=PAPER_BG, indicatorrelief="flat", focuscolor=ACCENT_PRIMARY)
    mp("TCheckbutton", background=[("active", PAPER_HOVER)], indicatorcolor=[("selected", ACCENT_PRIMARY)])
    return style
