"""Proyección orbital 3D -> 2D y primitivas QPainter para renderizado hidráulico nativo."""

from dataclasses import dataclass
import math
from typing import Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
)


@dataclass(frozen=True)
class ProjectedPoint:
    """Resultado de proyectar un punto 3D (x, y, z) al plano de pantalla."""

    x: float
    y: float
    depth: float
    scale: float


class OrbitCamera:
    """Cámara orbital con rotación (yaw, pitch), zoom y desplazamiento en pantalla."""

    DEFAULT_YAW = -0.58
    DEFAULT_PITCH = 0.56
    DEFAULT_ZOOM = 1.0
    DEFAULT_DISTANCE = 4.2
    MIN_PITCH = 0.12
    MAX_PITCH = 1.48
    MIN_ZOOM = 0.45
    MAX_ZOOM = 3.80

    def __init__(
        self,
        yaw: float = DEFAULT_YAW,
        pitch: float = DEFAULT_PITCH,
        zoom: float = DEFAULT_ZOOM,
        pan_x: float = 0.0,
        pan_y: float = 0.0,
        distance: float = DEFAULT_DISTANCE,
    ) -> None:
        self.yaw = float(yaw)
        self.pitch = max(self.MIN_PITCH, min(self.MAX_PITCH, float(pitch)))
        self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(zoom)))
        self.pan_x = float(pan_x)
        self.pan_y = float(pan_y)
        self.distance = max(1.5, float(distance))

    def reset(self) -> None:
        self.yaw = self.DEFAULT_YAW
        self.pitch = self.DEFAULT_PITCH
        self.zoom = self.DEFAULT_ZOOM
        self.pan_x = 0.0
        self.pan_y = 0.0

    def orbit(self, dx_px: float, dy_px: float) -> None:
        # Al arrastrar a la derecha (dx > 0), el frente (y1 > 0) debe moverse a la derecha.
        self.yaw -= dx_px * 0.0085
        self.pitch = max(
            self.MIN_PITCH,
            min(self.MAX_PITCH, self.pitch + dy_px * 0.0070),
        )

    def pan(self, dx_px: float, dy_px: float) -> None:
        self.pan_x += dx_px
        self.pan_y += dy_px

    def zoom_by(self, factor: float) -> None:
        self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom * float(factor)))

    def project_point(
        self, x: float, y: float, z: float, width: float, height: float
    ) -> ProjectedPoint:
        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)
        x1 = x * cy - y * sy
        y1 = x * sy + y * cy
        z1 = z

        cp = math.cos(self.pitch)
        sp = math.sin(self.pitch)
        u_x = x1
        u_y = y1 * sp - z1 * cp
        u_z = self.distance - y1 * cp - z1 * sp

        denom = max(0.35, u_z)
        persp = self.distance / denom
        base_px = min(max(120.0, width), max(120.0, height)) * 0.42 * self.zoom
        scale = base_px * persp
        sx = width * 0.5 + self.pan_x + u_x * scale
        sy_px = height * 0.5 + self.pan_y + u_y * scale
        return ProjectedPoint(x=sx, y=sy_px, depth=u_z, scale=scale)

    def screen_scale(self, depth: float, width: float, height: float) -> float:
        denom = max(0.35, depth)
        persp = self.distance / denom
        base_px = min(max(120.0, width), max(120.0, height)) * 0.42 * self.zoom
        return base_px * persp


def shade_color(color: QColor | str, factor: float, alpha: int = 255) -> QColor:
    """Ajusta luminosidad de un color preservando el tono y aplicando alfa."""
    c = QColor(color) if isinstance(color, str) else QColor(color)
    r = max(0, min(255, int(round(c.red() * factor))))
    g = max(0, min(255, int(round(c.green() * factor))))
    b = max(0, min(255, int(round(c.blue() * factor))))
    return QColor(r, g, b, max(0, min(255, int(alpha))))


def draw_capsule_3d(
    painter: QPainter,
    p1: QPointF,
    p2: QPointF,
    radius_px: float,
    base_color: QColor,
    *,
    outline_color: Optional[QColor] = None,
    highlight_color: Optional[QColor] = None,
    dashed: bool = False,
) -> None:
    """Dibuja un tramo cilíndrico con sombreado lateral en QPainter."""
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    seg_len = math.hypot(dx, dy)
    if seg_len < 0.5:
        return

    diameter = max(1.6, radius_px * 2.0)
    if highlight_color is not None:
        hpen = QPen(highlight_color, diameter + 5.5)
        hpen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(hpen)
        painter.drawLine(p1, p2)

    if outline_color is not None and not dashed:
        open_pen = QPen(outline_color, diameter + 1.6)
        open_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(open_pen)
        painter.drawLine(p1, p2)

    if dashed:
        pen = QPen(base_color, diameter)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([3.0, 2.5])
        painter.setPen(pen)
        painter.drawLine(p1, p2)
        return

    nx = -dy / seg_len
    ny = dx / seg_len
    mx = 0.5 * (p1.x() + p2.x())
    my = 0.5 * (p1.y() + p2.y())
    grad = QLinearGradient(
        mx - nx * radius_px,
        my - ny * radius_px,
        mx + nx * radius_px,
        my + ny * radius_px,
    )
    grad.setColorAt(0.0, shade_color(base_color, 1.24, base_color.alpha()))
    grad.setColorAt(0.45, base_color)
    grad.setColorAt(1.0, shade_color(base_color, 0.72, base_color.alpha()))

    body_pen = QPen(QBrush(grad), diameter)
    body_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(body_pen)
    painter.drawLine(p1, p2)


def draw_vertical_cylinder_3d(
    painter: QPainter,
    base_pt: QPointF,
    top_pt: QPointF,
    radius_px: float,
    base_color: QColor,
    *,
    alpha: int = 225,
) -> None:
    """Dibuja una columna vertical (piezométrica) con sombreado y tapa elíptica."""
    r = max(2.2, float(radius_px))
    col_left = shade_color(base_color, 1.22, alpha)
    col_mid = shade_color(base_color, 0.98, alpha)
    col_right = shade_color(base_color, 0.68, alpha)

    x_top = top_pt.x()
    y_top = top_pt.y()
    x_bot = base_pt.x()
    y_bot = base_pt.y()

    if math.hypot(x_top - x_bot, y_top - y_bot) >= 1.0:
        min_x = min(x_top, x_bot) - r
        max_x = max(x_top, x_bot) + r
        grad = QLinearGradient(min_x, y_top, max_x, y_top)
        grad.setColorAt(0.0, col_left)
        grad.setColorAt(0.42, col_mid)
        grad.setColorAt(1.0, col_right)

        poly = QPolygonF(
            [
                QPointF(x_bot - r, y_bot),
                QPointF(x_top - r, y_top),
                QPointF(x_top + r, y_top),
                QPointF(x_bot + r, y_bot),
            ]
        )
        painter.setPen(QPen(shade_color(base_color, 0.55, alpha), 0.8))
        painter.setBrush(QBrush(grad))
        painter.drawPolygon(poly)

    ry = max(1.6, r * 0.48)
    painter.setPen(QPen(shade_color(base_color, 0.52, alpha), 0.9))
    painter.setBrush(QBrush(shade_color(base_color, 1.32, min(255, alpha + 20))))
    painter.drawEllipse(top_pt, r, ry)


def draw_projected_ellipse_3d(
    painter: QPainter,
    camera: OrbitCamera,
    center_xyz: Tuple[float, float, float],
    rx_world: float,
    ry_world: float,
    width: float,
    height: float,
    fill_color: QColor,
    border_color: QColor,
    border_width: float = 1.2,
    segments: int = 20,
) -> None:
    """Dibuja una elipse horizontal en el plano Z constante de mundo proyectada a 2D."""
    cx, cy, cz = center_xyz
    pts = []
    step = (2.0 * math.pi) / float(max(8, segments))
    for i in range(max(8, segments)):
        ang = i * step
        px = cx + rx_world * math.cos(ang)
        py = cy + ry_world * math.sin(ang)
        pr = camera.project_point(px, py, cz, width, height)
        pts.append(QPointF(pr.x, pr.y))
    poly = QPolygonF(pts)
    painter.setPen(QPen(border_color, border_width))
    painter.setBrush(QBrush(fill_color))
    painter.drawPolygon(poly)


def draw_terrain_quad(
    painter: QPainter,
    corners_2d: Sequence[QPointF],
    fill_color: QColor,
    grid_pen: QPen,
) -> None:
    """Dibuja una celda de la malla de rasante de referencia."""
    painter.setPen(grid_pen)
    painter.setBrush(QBrush(fill_color))
    painter.drawPolygon(QPolygonF(corners_2d))


def point_to_segment_distance_sq(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """Distancia cuadrática mínima entre un punto (px, py) y el segmento (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq <= 1e-9:
        return (px - x1) ** 2 + (py - y1) ** 2
    t = ((px - x1) * dx + (py - y1) * dy) / len_sq
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return (px - proj_x) ** 2 + (py - proj_y) ** 2
