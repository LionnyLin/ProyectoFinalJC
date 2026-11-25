"""Renderizador puro con QPainter a partir de una escena calculada (CanvasScene)."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF

from .. import theme
from .layout import CanvasScene


class CanvasRenderer:
    """Dibuja las 6 capas visuales del lienzo cartográfico sin estado propio."""

    _BASE_PX_PER_MPS = 28.0

    def __init__(self, ui_font: str = "Segoe UI") -> None:
        self.ui_font = ui_font

    def paint(
        self,
        painter: QPainter,
        scene: CanvasScene,
        *,
        pulse_time_s: float = 0.0,
        is_playing: bool = False,
        zoom: float = 1.0,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        self._draw_drafting_grid(painter, scene.width, scene.height)

        if scene.empty_message:
            font = QFont(self.ui_font)
            font.setPointSize(10)
            painter.setFont(font)
            painter.setPen(QColor(theme.INK_MUTED))
            painter.drawText(
                QRectF(0, 0, scene.width, scene.height),
                Qt.AlignmentFlag.AlignCenter,
                scene.empty_message,
            )
            return

        self._draw_pipes(painter, scene)
        if is_playing and scene.pulse_tracks:
            self._draw_pulses(painter, scene, pulse_time_s, zoom)
        self._draw_flood_rings(painter, scene)
        self._draw_nodes(painter, scene)
        self._draw_badges(painter, scene)

    @staticmethod
    def _draw_drafting_grid(painter: QPainter, w: int, h: int) -> None:
        painter.fillRect(0, 0, w, h, QColor(theme.CANVAS_BG))
        minor = 36
        major = 144
        minor_pen = QPen(QColor(theme.CANVAS_GRID_MINOR), 1.0)
        major_pen = QPen(QColor(theme.CANVAS_GRID_MAJOR), 1.0)
        for gx in range(0, w, minor):
            painter.setPen(major_pen if gx % major == 0 else minor_pen)
            painter.drawLine(gx, 0, gx, h)
        for gy in range(0, h, minor):
            painter.setPen(major_pen if gy % major == 0 else minor_pen)
            painter.drawLine(0, gy, w, gy)

    @staticmethod
    def _draw_pipes(painter: QPainter, scene: CanvasScene) -> None:
        for p in scene.pipes:
            if p.glow_color:
                pen = QPen(QColor(p.glow_color), p.glow_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(p.sx2, p.sy2))

            if p.halo_color:
                pen = QPen(QColor(p.halo_color), p.halo_width)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(p.halo_end_x, p.halo_end_y))
                if p.has_cushion:
                    cpen = QPen(QColor(theme.CANVAS_BG), p.draw_width + 3.4)
                    cpen.setCapStyle(Qt.PenCapStyle.FlatCap)
                    painter.setPen(cpen)
                    painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(p.halo_end_x, p.halo_end_y))

            if p.parallel_offset > 0.0:
                nx_p, ny_p = -p.uy, p.ux
                par_pen = QPen(QColor(theme.ACCENT_PRIMARY), 1.4)
                painter.setPen(par_pen)
                for sign in (-1.0, 1.0):
                    ox = nx_p * p.parallel_offset * sign
                    oy = ny_p * p.parallel_offset * sign
                    painter.drawLine(
                        QPointF(p.sx1 + ox, p.sy1 + oy),
                        QPointF(p.sx2 + ox, p.sy2 + oy),
                    )

            shaft_end_x = p.sx2 - p.ux * (p.arrow_len * 0.65) if p.draw_arrow else p.sx2
            shaft_end_y = p.sy2 - p.uy * (p.arrow_len * 0.65) if p.draw_arrow else p.sy2
            pen = QPen(QColor(p.color), p.draw_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            if p.dashed:
                pen.setStyle(Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([3.0, 3.0])
            painter.setPen(pen)
            painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(shaft_end_x, shaft_end_y))

            if p.draw_arrow:
                nx_p, ny_p = -p.uy, p.ux
                bx = p.sx2 - p.ux * p.arrow_len
                by = p.sy2 - p.uy * p.arrow_len
                arrow_poly = QPolygonF(
                    [
                        QPointF(p.sx2, p.sy2),
                        QPointF(bx + nx_p * p.arrow_wing, by + ny_p * p.arrow_wing),
                        QPointF(bx - nx_p * p.arrow_wing, by - ny_p * p.arrow_wing),
                    ]
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(p.color)))
                painter.drawPolygon(arrow_poly)

            for x1, y1, x2, y2, bw in p.obstruction_bars:
                bpen = QPen(QColor(theme.INK_PRIMARY), bw)
                bpen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(bpen)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    @classmethod
    def _draw_pulses(
        cls,
        painter: QPainter,
        scene: CanvasScene,
        pulse_time_s: float,
        zoom: float,
    ) -> None:
        sqrt_z = math.sqrt(max(0.1, zoom))
        for tr in scene.pulse_tracks:
            pen = QPen(QColor(tr.color), tr.line_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            nx_p, ny_p = -tr.uy, tr.ux
            sz = tr.chevron_size
            for idx in range(tr.n_pulses):
                phase = idx / float(tr.n_pulses)
                travel = (
                    pulse_time_s * tr.velocity_ms * cls._BASE_PX_PER_MPS * sqrt_z
                    + phase * tr.usable_len
                ) % tr.usable_len
                dist_along = 5.0 + travel
                tx = tr.sx1 + tr.ux * dist_along
                ty = tr.sy1 + tr.uy * dist_along
                bx = tx - tr.ux * sz
                by = ty - tr.uy * sz
                painter.drawPolyline(
                    QPolygonF(
                        [
                            QPointF(bx + nx_p * (sz * 0.72), by + ny_p * (sz * 0.72)),
                            QPointF(tx, ty),
                            QPointF(bx - nx_p * (sz * 0.72), by - ny_p * (sz * 0.72)),
                        ]
                    )
                )

    @staticmethod
    def _draw_flood_rings(painter: QPainter, scene: CanvasScene) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for fr in scene.flood_rings:
            pen = QPen(QColor(fr.color), fr.width)
            if fr.dashed:
                pen.setStyle(Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([3.0, 3.0])
            painter.setPen(pen)
            painter.drawEllipse(QPointF(fr.x, fr.y), fr.radius, fr.radius)

    def _draw_nodes(self, painter: QPainter, scene: CanvasScene) -> None:
        for n in scene.nodes:
            if n.outer_ring_color:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(n.outer_ring_color), n.outer_ring_width))
                painter.drawEllipse(
                    QPointF(n.x, n.y), n.outer_ring_radius, n.outer_ring_radius
                )

            pen = QPen(QColor(n.outline), n.outline_width)
            if n.dashed:
                pen.setStyle(Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([3.0, 2.0])
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(n.fill)))
            painter.drawEllipse(QPointF(n.x, n.y), n.radius, n.radius)

            if n.show_label:
                font = QFont(self.ui_font)
                font.setPixelSize(n.font_px)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor(n.text_color))
                painter.drawText(
                    QRectF(n.x - n.radius, n.y - n.radius, n.radius * 2.0, n.radius * 2.0),
                    Qt.AlignmentFlag.AlignCenter,
                    n.node_id,
                )

    @staticmethod
    def _draw_badges(painter: QPainter, scene: CanvasScene) -> None:
        for b in scene.badges:
            rect = QRectF(b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0)
            painter.setPen(QPen(QColor(b.border), b.border_width))
            painter.setBrush(QBrush(QColor(b.bg)))
            painter.drawRect(rect)

            font = QFont(b.font_family)
            font.setPixelSize(b.font_px)
            font.setBold(b.bold)
            painter.setFont(font)
            painter.setPen(QColor(b.fg))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, b.text)
