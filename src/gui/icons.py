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


def build_icon_set(
    fg_dark: str,
    fg_light: str,
    fg_on_accent: str,
    accent_color: str = "#6D8196",
    scale: float = 1.0,
) -> Dict[str, ImageTk.PhotoImage]:
    """Construye el conjunto coherente de iconos de la interfaz ajustado al DPI nativo."""
    icons: Dict[str, ImageTk.PhotoImage] = {}
    dpi_k = max(1.0, float(scale))

    def _sz(base_px: int) -> int:
        return max(8, int(round(base_px * dpi_k)))

    def _brand_network(col_line: str, col_node: str, col_sink: str, sz: int = 22) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.8 * s * dpi_k))
            p1 = (dim * 0.22, dim * 0.24)
            p2 = (dim * 0.22, dim * 0.76)
            pm = (dim * 0.54, dim * 0.50)
            ps = (dim * 0.80, dim * 0.50)
            d.line([p1, pm], fill=col_line, width=sw)
            d.line([p2, pm], fill=col_line, width=sw)
            d.line([pm, ps], fill=col_sink, width=sw)
            r = dim * 0.11
            for cx, cy in (p1, p2, pm):
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col_node, outline=col_line, width=max(1, int(s * dpi_k)))
            rs = dim * 0.13
            d.ellipse([ps[0] - rs, ps[1] - rs, ps[0] + rs, ps[1] + rs], fill=col_sink, outline=col_node, width=max(1, int(s * dpi_k)))
        return _render_icon(_sz(sz), fn)

    def _play(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.18
            d.polygon([(m + dim * 0.08, m), (dim - m, dim * 0.5), (m + dim * 0.08, dim - m)], fill=col)
        return _render_icon(_sz(sz), fn)

    def _pause(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.20
            w = dim * 0.20
            d.rectangle([m, m, m + w, dim - m], fill=col)
            d.rectangle([dim - m - w, m, dim - m, dim - m], fill=col)
        return _render_icon(_sz(sz), fn)

    def _reset(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.20
            bar_w = dim * 0.12
            d.rectangle([m, m, m + bar_w, dim - m], fill=col)
            d.polygon([(dim - m, m), (m + bar_w + dim * 0.06, dim * 0.5), (dim - m, dim - m)], fill=col)
        return _render_icon(_sz(sz), fn)

    def _step_back(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.22
            d.polygon([(dim - m, m), (m, dim * 0.5), (dim - m, dim - m)], fill=col)
        return _render_icon(_sz(sz), fn)

    def _step_fwd(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, _s: int) -> None:
            m = dim * 0.22
            d.polygon([(m, m), (dim - m, dim * 0.5), (m, dim - m)], fill=col)
        return _render_icon(_sz(sz), fn)

    def _sliders(col: str, sz: int = 13) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.6 * s * dpi_k))
            y1, y2, y3 = dim * 0.25, dim * 0.50, dim * 0.75
            m = dim * 0.14
            for y, kx in ((y1, 0.36), (y2, 0.68), (y3, 0.44)):
                d.line([(m, y), (dim - m, y)], fill=col, width=sw)
                r = dim * 0.09
                cx = dim * kx
                d.ellipse([cx - r, y - r, cx + r, y + r], fill=col)
        return _render_icon(_sz(sz), fn)

    def _chart(col: str, sz: int = 13) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.6 * s * dpi_k))
            m = dim * 0.16
            d.line([(m, dim - m), (dim - m, dim - m)], fill=col, width=sw)
            bw = dim * 0.14
            d.rectangle([dim * 0.22, dim * 0.50, dim * 0.22 + bw, dim - m], fill=col)
            d.rectangle([dim * 0.44, dim * 0.24, dim * 0.44 + bw, dim - m], fill=col)
            d.rectangle([dim * 0.66, dim * 0.38, dim * 0.66 + bw, dim - m], fill=col)
        return _render_icon(_sz(sz), fn)

    def _chevron_down(col: str, sz: int = 11) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.7 * s * dpi_k))
            d.line(
                [(dim * 0.22, dim * 0.36), (dim * 0.50, dim * 0.66), (dim * 0.78, dim * 0.36)],
                fill=col,
                width=sw,
            )
        return _render_icon(_sz(sz), fn)

    def _search(col: str, sz: int = 13) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.7 * s * dpi_k))
            d.ellipse([dim * 0.16, dim * 0.16, dim * 0.66, dim * 0.66], outline=col, width=sw)
            d.line([(dim * 0.60, dim * 0.60), (dim * 0.84, dim * 0.84)], fill=col, width=sw)
        return _render_icon(_sz(sz), fn)

    def _crosshair(col: str, sz: int = 12) -> ImageTk.PhotoImage:
        def fn(d: ImageDraw.ImageDraw, dim: int, s: int) -> None:
            sw = max(2, int(1.5 * s * dpi_k))
            d.ellipse([dim * 0.22, dim * 0.22, dim * 0.78, dim * 0.78], outline=col, width=sw)
            d.line([(dim * 0.50, dim * 0.08), (dim * 0.50, dim * 0.32)], fill=col, width=sw)
            d.line([(dim * 0.50, dim * 0.68), (dim * 0.50, dim * 0.92)], fill=col, width=sw)
            d.line([(dim * 0.08, dim * 0.50), (dim * 0.32, dim * 0.50)], fill=col, width=sw)
            d.line([(dim * 0.68, dim * 0.50), (dim * 0.92, dim * 0.50)], fill=col, width=sw)
        return _render_icon(_sz(sz), fn)

    icons["brand_network"] = _brand_network(fg_dark, fg_dark, accent_color, 22)
    icons["play_on_accent"] = _play(fg_on_accent, 11)
    icons["pause_on_accent"] = _pause(fg_on_accent, 11)
    icons["play_ink"] = _play(fg_light, 11)
    icons["reset_light"] = _reset(fg_light, 11)
    icons["step_back_light"] = _step_back(fg_light, 11)
    icons["step_fwd_light"] = _step_fwd(fg_light, 11)
    icons["sliders_light"] = _sliders(fg_dark, 13)
    icons["sliders_ink"] = _sliders(fg_on_accent, 13)
    icons["chart_light"] = _chart(fg_dark, 13)
    icons["chart_ink"] = _chart(fg_on_accent, 13)
    icons["chevron_light"] = _chevron_down(fg_dark, 10)
    icons["search_ink"] = _search(fg_on_accent, 12)
    icons["crosshair_light"] = _crosshair(fg_light, 12)
    return icons
