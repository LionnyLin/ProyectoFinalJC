"""Generación de iconografía vectorial nítida vía QPainter sobre QPixmap/QIcon."""

from typing import Callable, Dict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


def _render_pixmap(size: int, draw_fn: Callable[[QPainter, float], None]) -> QPixmap:
    """Renderiza un QPixmap HiDPI (2x) con antialiasing para trazos limpios."""
    dpr = 2.0
    dim = int(round(size * dpr))
    pm = QPixmap(dim, dim)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    draw_fn(painter, float(size))
    painter.end()
    return pm


def _render_icon(size: int, draw_fn: Callable[[QPainter, float], None]) -> QIcon:
    return QIcon(_render_pixmap(size, draw_fn))


def build_brand_pixmap(
    col_line: str,
    col_node: str,
    col_sink: str,
    size: int = 22,
) -> QPixmap:
    """Dibuja el emblema vectorial del grafo dirigido para la barra superior."""
    def fn(p: QPainter, d: float) -> None:
        p1 = QPointF(d * 0.22, d * 0.24)
        p2 = QPointF(d * 0.22, d * 0.76)
        pm = QPointF(d * 0.54, d * 0.50)
        ps = QPointF(d * 0.80, d * 0.50)

        pen_line = QPen(QColor(col_line), max(1.5, d * 0.085))
        pen_line.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_line)
        p.drawLine(p1, pm)
        p.drawLine(p2, pm)

        pen_sink = QPen(QColor(col_sink), max(1.5, d * 0.085))
        pen_sink.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen_sink)
        p.drawLine(pm, ps)

        r = d * 0.11
        p.setPen(QPen(QColor(col_line), max(1.0, d * 0.05)))
        p.setBrush(QBrush(QColor(col_node)))
        for pt in (p1, p2, pm):
            p.drawEllipse(pt, r, r)

        rs = d * 0.13
        p.setPen(QPen(QColor(col_node), max(1.0, d * 0.05)))
        p.setBrush(QBrush(QColor(col_sink)))
        p.drawEllipse(ps, rs, rs)

    return _render_pixmap(size, fn)


def build_icon_set(
    fg_dark: str,
    fg_light: str,
    fg_on_accent: str,
    accent_color: str = "#6D8196",
) -> Dict[str, QIcon]:
    """Construye el conjunto coherente de iconos de la interfaz."""
    icons: Dict[str, QIcon] = {}

    def _play(col: str, sz: int = 12) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            m = d * 0.18
            poly = QPolygonF(
                [
                    QPointF(m + d * 0.08, m),
                    QPointF(d - m, d * 0.5),
                    QPointF(m + d * 0.08, d - m),
                ]
            )
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawPolygon(poly)

        return _render_icon(sz, fn)

    def _pause(col: str, sz: int = 12) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            m = d * 0.20
            w = d * 0.20
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawRect(QRectF(m, m, w, d - 2 * m))
            p.drawRect(QRectF(d - m - w, m, w, d - 2 * m))

        return _render_icon(sz, fn)

    def _reset(col: str, sz: int = 12) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            m = d * 0.20
            bar_w = d * 0.12
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawRect(QRectF(m, m, bar_w, d - 2 * m))
            poly = QPolygonF(
                [
                    QPointF(d - m, m),
                    QPointF(m + bar_w + d * 0.06, d * 0.5),
                    QPointF(d - m, d - m),
                ]
            )
            p.drawPolygon(poly)

        return _render_icon(sz, fn)

    def _step_back(col: str, sz: int = 12) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            m = d * 0.22
            poly = QPolygonF(
                [QPointF(d - m, m), QPointF(m, d * 0.5), QPointF(d - m, d - m)]
            )
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawPolygon(poly)

        return _render_icon(sz, fn)

    def _step_fwd(col: str, sz: int = 12) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            m = d * 0.22
            poly = QPolygonF(
                [QPointF(m, m), QPointF(d - m, d * 0.5), QPointF(m, d - m)]
            )
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawPolygon(poly)

        return _render_icon(sz, fn)

    def _sliders(col: str, sz: int = 13) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            m = d * 0.14
            pen = QPen(QColor(col), max(1.3, d * 0.12))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            for y, kx in ((d * 0.25, 0.36), (d * 0.50, 0.68), (d * 0.75, 0.44)):
                p.setPen(pen)
                p.drawLine(QPointF(m, y), QPointF(d - m, y))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(col))
                r = d * 0.095
                p.drawEllipse(QPointF(d * kx, y), r, r)

        return _render_icon(sz, fn)

    def _chart(col: str, sz: int = 13) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            m = d * 0.16
            pen = QPen(QColor(col), max(1.3, d * 0.12))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(m, d - m), QPointF(d - m, d - m))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            bw = d * 0.14
            p.drawRect(QRectF(d * 0.22, d * 0.50, bw, d - m - d * 0.50))
            p.drawRect(QRectF(d * 0.44, d * 0.24, bw, d - m - d * 0.24))
            p.drawRect(QRectF(d * 0.66, d * 0.38, bw, d - m - d * 0.38))

        return _render_icon(sz, fn)

    def _chevron_down(col: str, sz: int = 11) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            pen = QPen(QColor(col), max(1.4, d * 0.15))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline(
                QPolygonF(
                    [
                        QPointF(d * 0.22, d * 0.36),
                        QPointF(d * 0.50, d * 0.66),
                        QPointF(d * 0.78, d * 0.36),
                    ]
                )
            )

        return _render_icon(sz, fn)

    def _search(col: str, sz: int = 13) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            pen = QPen(QColor(col), max(1.4, d * 0.13))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(d * 0.16, d * 0.16, d * 0.50, d * 0.50))
            p.drawLine(QPointF(d * 0.60, d * 0.60), QPointF(d * 0.84, d * 0.84))

        return _render_icon(sz, fn)

    def _crosshair(col: str, sz: int = 12) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            pen = QPen(QColor(col), max(1.2, d * 0.12))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(d * 0.22, d * 0.22, d * 0.56, d * 0.56))
            p.drawLine(QPointF(d * 0.50, d * 0.08), QPointF(d * 0.50, d * 0.32))
            p.drawLine(QPointF(d * 0.50, d * 0.68), QPointF(d * 0.50, d * 0.92))
            p.drawLine(QPointF(d * 0.08, d * 0.50), QPointF(d * 0.32, d * 0.50))
            p.drawLine(QPointF(d * 0.68, d * 0.50), QPointF(d * 0.92, d * 0.50))

        return _render_icon(sz, fn)

    def _tour_compass(col: str, sz: int = 13) -> QIcon:
        def fn(p: QPainter, d: float) -> None:
            pen = QPen(QColor(col), max(1.3, d * 0.11))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(d * 0.14, d * 0.14, d * 0.72, d * 0.72))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(d * 0.72, d * 0.28),
                        QPointF(d * 0.44, d * 0.40),
                        QPointF(d * 0.28, d * 0.72),
                        QPointF(d * 0.56, d * 0.60),
                    ]
                )
            )

        return _render_icon(sz, fn)

    icons["brand_network"] = QIcon(build_brand_pixmap(fg_dark, fg_dark, accent_color, 22))
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
    icons["tour_light"] = _tour_compass(fg_dark, 13)
    icons["tour_ink"] = _tour_compass(fg_light, 13)
    return icons
