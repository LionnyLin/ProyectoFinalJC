"""Sistema de diseño visual — Atlas Urbano de Infraestructura (Obsidiana + Papel Técnico + Cobalto)."""

import ctypes
import os
import tkinter as tk
from tkinter import font as tkfont
from typing import Tuple

# Superficies del Shell (Barra superior y riel de comandos en Obsidiana)
SHELL_BG = "#131820"
SHELL_SURFACE = "#1B222D"
SHELL_ELEVATED = "#242D3B"
SHELL_HOVER = "#2D3849"
SHELL_BORDER = "#2F3B4E"
SHELL_TEXT = "#F4F6F9"
SHELL_TEXT_SECONDARY = "#CBD5E1"
SHELL_TEXT_MUTED = "#94A3B8"

# Superficie de dibujo técnico (Lienzo del grafo en porcelana clara)
CANVAS_BG = "#F7F8FA"
CANVAS_GRID_MINOR = "#EBEEF3"
CANVAS_GRID_MAJOR = "#DCE2EC"
CANVAS_BORDER = "#D4DCE6"
CANVAS_FLOAT_BG = "#FFFFFF"
CANVAS_FLOAT_BORDER = "#CBD5E1"

# Superficies editoriales (Panel de análisis, tablas, reproductor, gráficas)
PAPER_BG = "#FFFFFF"
PAPER_SUBTLE = "#F2F4F7"
PAPER_ALT_ROW = "#F8FAFC"
PAPER_HOVER = "#E6ECF4"
PAPER_BORDER = "#D6DEE8"
INK_PRIMARY = "#111827"
INK_SECONDARY = "#334155"
INK_MUTED = "#64748B"

# Cobalto hidráulico (Foco interactivo, CTA primario, selección y rutas BFS/DFS)
ACCENT_PRIMARY = "#0369A1"       # >= 5.9:1 con texto blanco
ACCENT_HOVER = "#075985"
ACCENT_SOFT = "#E0F2FE"
ACCENT_INK = "#FFFFFF"
ACCENT_ON_DARK = "#38BDF8"       # >= 8.5:1 sobre SHELL_BG
ACCENT_ON_DARK_HOVER = "#7DD3FC"
ACCENT_ON_DARK_INK = "#0B1220"

# Nodos y aristas del grafo
NODE_SOURCE_FILL = "#131820"
NODE_SOURCE_BORDER = "#0369A1"
NODE_SOURCE_TEXT = "#FFFFFF"
NODE_SINK_FILL = "#0F766E"
NODE_SINK_BORDER = "#115E59"
NODE_SINK_TEXT = "#FFFFFF"
NODE_MANHOLE_FILL = "#FFFFFF"
NODE_MANHOLE_BORDER = "#475569"
NODE_MANHOLE_TEXT = "#111827"
NODE_SURCHARGE_RING = "#D97706"

PIPE_IDLE_COLOR = "#94A3B8"
PIPE_HIGHLIGHT_PATH = "#0284C7"
PIPE_HIGHLIGHT_HALO = "#BAE6FD"
PIPE_SELECTED_HALO = "#0369A1"
PIPE_OVERLOAD_HALO = "#FECACA"

STATUS_OK_LIGHT = "#047857"
STATUS_OK_DARK = "#34D399"
STATUS_WARN_LIGHT = "#B45309"
STATUS_ERR_LIGHT = "#B91C1C"

# Escala oficial de utilización (Sección 7 — preservada intacta)
COLOR_SCALE_LEGEND = [
    ("0–25 %", "#22c55e", "Baja utilización"),
    (">25–50 %", "#eab308", "Utilización moderada"),
    (">50–75 %", "#f97316", "Utilización alta"),
    (">75–100 %", "#ef4444", "Cercana a capacidad máxima"),
    (">100 %", "#991b1b", "Capacidad excedida"),
]

# Colores de texto legibles sobre fondo blanco por nivel de utilización
TIER_TEXT_ON_LIGHT = [
    "#15803d",
    "#a16207",
    "#c2410c",
    "#dc2626",
    "#991b1b",
]

# Umbrales responsivos de ventana
BREAKPOINT_COMPACT = 940
BREAKPOINT_MEDIUM = 1220
BREAKPOINT_SHORT = 650

# Aliases de compatibilidad
BG_DARK = SHELL_BG
BG_PANEL = PAPER_BG
BG_CARD = PAPER_SUBTLE
BG_CANVAS = CANVAS_BG
BORDER_COLOR = PAPER_BORDER
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
