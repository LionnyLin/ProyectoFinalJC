"""Sistema de diseño visual (Plum #3B153A + Xanthous #F0C987 + Inter 500)."""

import ctypes
import os
import tkinter as tk
from tkinter import font as tkfont
from typing import Tuple

# Paleta principal solicitada (Plum como superficie profunda, Xanthous como acento cálido)
PLUM_DEEP = "#260C25"       # Lienzo de grafo y campos de entrada
PLUM_BASE = "#3B153A"       # Superficie principal de paneles y barra superior
PLUM_ELEVATED = "#4B1D4A"   # Hover, botones secundarios y encabezados de tabla
PLUM_BORDER = "#5E285C"     # Divisores finos 1px (sin cards anidadas)

XANTHOUS = "#F0C987"        # Acento principal, CTAs, métricas clave y selección
XANTHOUS_HOVER = "#F6D8A4"  # Hover del acento principal
XANTHOUS_INK = "#260C25"    # Texto oscuro de alto contraste sobre Xanthous

TEXT_PRIMARY = "#FAF5FA"    # Marfil cálido de alto contraste sobre Plum
TEXT_SECONDARY = "#DFC9DE"  # Etiquetas secundarias legibles
TEXT_MUTED = "#B895B7"      # Metadatos y ejes secundarios

# Aliases de compatibilidad
BG_DARK = PLUM_DEEP
BG_PANEL = PLUM_BASE
BG_CARD = PLUM_ELEVATED
BG_CANVAS = PLUM_DEEP
BORDER_COLOR = PLUM_BORDER
ACCENT_BLUE = XANTHOUS
ACCENT_GOLD = XANTHOUS

# Nodos del grafo
NODE_SOURCE_FILL = "#3B153A"
NODE_SOURCE_BORDER = XANTHOUS
NODE_SINK_FILL = "#065F46"
NODE_SINK_BORDER = "#34D399"
NODE_MANHOLE_FILL = "#4B1D4A"
NODE_MANHOLE_BORDER = "#C8B3C7"
NODE_SURCHARGE_RING = XANTHOUS

PIPE_IDLE_COLOR = "#6E3A6C"
PIPE_HIGHLIGHT_PATH = XANTHOUS
PIPE_SELECTED_HALO = "#FAF5FA"

# Escala oficial de utilización (Sección 7)
COLOR_SCALE_LEGEND = [
    ("0–25 %", "#22c55e", "Baja utilización"),
    (">25–50 %", "#eab308", "Utilización moderada"),
    (">50–75 %", "#f97316", "Utilización alta"),
    (">75–100 %", "#ef4444", "Cercana a capacidad máxima"),
    (">100 %", "#991b1b", "Capacidad excedida"),
]

_FONTS_REGISTERED = False


def _register_local_inter_fonts() -> None:
    """Registra archivos Inter*.ttf en assets/fonts/ para Windows si están presentes."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED or os.name != "nt":
        return
    _FONTS_REGISTERED = True

    fonts_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")
    )
    if not os.path.isdir(fonts_dir):
        return
    FR_PRIVATE = 0x10
    for fname in os.listdir(fonts_dir):
        if fname.lower().endswith((".ttf", ".otf")):
            fpath = os.path.join(fonts_dir, fname)
            try:
                ctypes.windll.gdi32.AddFontResourceExW(fpath, FR_PRIVATE, 0)
            except Exception:
                pass


def resolve_fonts(root: tk.Misc) -> Tuple[str, str, bool]:
    """Resuelve familia sans (`Inter` 500 si está disponible) y familia monoespaciada.

    Retorna `(ui_font_family, mono_font_family, inter_available)`.
    """
    _register_local_inter_fonts()
    available = {f.lower(): f for f in tkfont.families(root)}

    inter_available = False
    ui_family = "Segoe UI"
    for candidate in ("inter medium", "inter", "segoe ui variable text", "segoe ui"):
        if candidate in available:
            ui_family = available[candidate]
            if "inter" in candidate:
                inter_available = True
            break

    mono_family = "Consolas"
    for candidate in ("jetbrainsmono nerd font", "jetbrains mono", "firacode nerd font", "consolas"):
        if candidate in available:
            mono_family = available[candidate]
            break

    return ui_family, mono_family, inter_available
