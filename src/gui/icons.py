"""Generación de iconografía vectorial anti-aliased vía Pillow con trazo uniforme."""

from typing import Dict
from PIL import Image, ImageDraw, ImageTk


def _render_icon(size: int, draw_fn) -> ImageTk.PhotoImage:
    """Dibuja un icono con supermuestreo 3x para bordes nítidos."""
    scale = 3
    dim = size * scale
    img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_fn(draw, dim, scale)
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(img)


def build_icon_set(fg_dark: str, fg_light: str, fg_on_accent: str) -> Dict[str, ImageTk.PhotoImage]:
    """Construye el conjunto coherente de iconos de la interfaz."""
    icons: Dict[str, ImageTk.PhotoImage] = {}

    def _play(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.18
            d.polygon([(m + dim * 0.08, m), (dim - m, dim * 0.5), (m + dim * 0.08, dim - m)], fill=col)
        return _render_icon(sz, fn)

    def _pause(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.20
            w = dim * 0.20
            d.rectangle([m, m, m + w, dim - m], fill=col)
            d.rectangle([dim - m - w, m, dim - m, dim - m], fill=col)
        return _render_icon(sz, fn)

    def _reset(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.20
            bar_w = dim * 0.12
            d.rectangle([m, m, m + bar_w, dim - m], fill=col)
            d.polygon([(dim - m, m), (m + bar_w + dim * 0.06, dim * 0.5), (dim - m, dim - m)], fill=col)
        return _render_icon(sz, fn)

    def _step_back(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.22
            d.polygon([(dim - m, m), (m, dim * 0.5), (dim - m, dim - m)], fill=col)
        return _render_icon(sz, fn)

    def _step_fwd(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.22
            d.polygon([(m, m), (dim - m, dim * 0.5), (m, dim - m)], fill=col)
        return _render_icon(sz, fn)

    def _sliders(col: str, sz: int = 13) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.6 * s))
            y1, y2, y3 = dim * 0.25, dim * 0.50, dim * 0.75
            m = dim * 0.14
            for y, kx in ((y1, 0.36), (y2, 0.68), (y3, 0.44)):
                d.line([(m, y), (dim - m, y)], fill=col, width=sw)
                r = dim * 0.09
                cx = dim * kx
                d.ellipse([cx - r, y - r, cx + r, y + r], fill=col)
        return _render_icon(sz, fn)

    def _chart(col: str, sz: int = 13) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.6 * s))
            m = dim * 0.16
            d.line([(m, dim - m), (dim - m, dim - m)], fill=col, width=sw)
            bw = dim * 0.14
            d.rectangle([dim * 0.22, dim * 0.50, dim * 0.22 + bw, dim - m], fill=col)
            d.rectangle([dim * 0.44, dim * 0.24, dim * 0.44 + bw, dim - m], fill=col)
            d.rectangle([dim * 0.66, dim * 0.38, dim * 0.66 + bw, dim - m], fill=col)
        return _render_icon(sz, fn)

    def _chevron_down(col: str, sz: int = 11) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.7 * s))
            d.line(
                [(dim * 0.22, dim * 0.36), (dim * 0.50, dim * 0.66), (dim * 0.78, dim * 0.36)],
                fill=col,
                width=sw,
            )
        return _render_icon(sz, fn)

    def _search(col: str, sz: int = 13) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.7 * s))
            d.ellipse([dim * 0.16, dim * 0.16, dim * 0.66, dim * 0.66], outline=col, width=sw)
            d.line([(dim * 0.60, dim * 0.60), (dim * 0.84, dim * 0.84)], fill=col, width=sw)
        return _render_icon(sz, fn)

    def _crosshair(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.5 * s))
            d.ellipse([dim * 0.22, dim * 0.22, dim * 0.78, dim * 0.78], outline=col, width=sw)
            d.line([(dim * 0.50, dim * 0.08), (dim * 0.50, dim * 0.32)], fill=col, width=sw)
            d.line([(dim * 0.50, dim * 0.68), (dim * 0.50, dim * 0.92)], fill=col, width=sw)
            d.line([(dim * 0.08, dim * 0.50), (dim * 0.32, dim * 0.50)], fill=col, width=sw)
            d.line([(dim * 0.68, dim * 0.50), (dim * 0.92, dim * 0.50)], fill=col, width=sw)
        return _render_icon(sz, fn)

    icons["play_on_accent"] = _play(fg_on_accent, 11)
    icons["pause_on_accent"] = _pause(fg_on_accent, 11)
    icons["play_ink"] = _play(fg_light, 11)
    icons["reset_light"] = _reset(fg_light, 11)
    icons["step_back_light"] = _step_back(fg_light, 11)
    icons["step_fwd_light"] = _step_fwd(fg_light, 11)
    icons["sliders_light"] = _sliders(fg_dark, 13)
    icons["sliders_ink"] = _sliders(fg_light, 13)
    icons["chart_light"] = _chart(fg_dark, 13)
    icons["chart_ink"] = _chart(fg_light, 13)
    icons["chevron_light"] = _chevron_down(fg_dark, 10)
    icons["search_ink"] = _search(fg_light, 12)
    icons["crosshair_light"] = _crosshair(fg_light, 12)
    return icons
